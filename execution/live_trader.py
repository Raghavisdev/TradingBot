import logging
import os
import uuid

from execution.live_executor import (
    LiveExecutor,
    LiveExecutionResult,
)

from execution.live_signer import (
    LiveSigner,
    LiveSignerError,
)

from execution.solana_sender import (
    SolanaSender,
    SolanaSenderError,
)

from database.execution_order_logger import (
    ExecutionOrderLogger,
)

logger = logging.getLogger("LiveTrader")


class LiveTrader:

    """
    Complete live execution orchestration.

    BUY:
        S6 allocation
          -> Jupiter SOL/TOKEN
          -> unsigned transaction
          -> signer
          -> sender
          -> confirmation

    SELL:
        Position.tokens
          -> exact sell quantity
          -> Jupiter TOKEN/SOL
          -> unsigned transaction
          -> signer
          -> sender
          -> confirmation

    Position state is NOT modified until confirmation.
    """

    def __init__(self, portfolio):

        self.portfolio = portfolio

        self.executor = LiveExecutor()

        self.order_logger = (
            ExecutionOrderLogger()
        )

        self.sender = SolanaSender()

        self.signer = None

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _live_enabled():

        return os.getenv(
            "LIVE_TRADING",
            "False",
        ).lower() in (
            "true",
            "1",
            "yes",
        )

    @staticmethod
    def _sell_percent_of_remaining(
        position,
        percent,
    ):

        percent = float(percent)

        if percent <= 0 or percent > 100:

            raise ValueError(
                "Sell percentage must be > 0 and <= 100"
            )

        tokens = float(
            getattr(
                position,
                "tokens",
                0.0,
            )
            or 0.0
        )

        if tokens <= 0:

            raise ValueError(
                "Position contains no tokens"
            )

        quantity = (
            tokens *
            percent /
            100.0
        )

        if quantity <= 0:

            raise ValueError(
                "Calculated sell quantity is zero"
            )

        return quantity

    def _token_quantity_to_raw(
        self,
        token_mint,
        ui_quantity,
    ):

        decimals = (
            self.executor.get_token_decimals(
                token_mint
            )
        )

        raw = int(
            float(ui_quantity)
            * (10 ** decimals)
        )

        if raw <= 0:

            raise ValueError(
                "Token quantity becomes zero after decimal conversion"
            )

        return raw, decimals

    # =========================================================
    # BUY
    # =========================================================

    def buy(
        self,
        coin,
        amount,
    ):

        symbol = getattr(
            coin,
            "symbol",
            "UNKNOWN",
        )

        contract = getattr(
            coin,
            "contract",
            None,
        )

        signal_id = getattr(
            coin,
            "signal_id",
            None,
        )

        try:

            amount = float(amount)

        except (
            TypeError,
            ValueError,
        ):

            return None

        if amount <= 0:

            return None

        try:

            if getattr(
                self.portfolio,
                "refresh_before_trade",
                True,
            ):

                self.portfolio.refresh()

        except Exception as exc:

            logger.error(
                "[LIVE BUY] Refresh failed: %s",
                exc,
            )

            return None

        available = float(
            self.portfolio.cash
        )

        if amount > available:

            logger.warning(
                "[LIVE BUY] Insufficient capital"
            )

            return None

        if not self.portfolio.can_open_trade(
            amount
        ):

            logger.warning(
                "[LIVE BUY] Portfolio risk blocked"
            )

            return None

        order_id = (
            self.order_logger.create_order(
                signal_id=signal_id,
                symbol=symbol,
                side="BUY",
                requested_amount=amount,
                idempotency_key=str(
                    uuid.uuid4()
                ),
            )
        )

        if not order_id:

            return None

        self.order_logger.update_order(
            order_id,
            status="PREFLIGHT",
        )

        print()
        print("=" * 70)
        print("LIVE BUY")
        print("=" * 70)
        print("Order ID :", order_id)
        print("Symbol   :", symbol)
        print("Amount   :", f"${amount:.2f}")

        result = self.executor.prepare_buy(
            token_mint=contract,
            amount_usd=amount,
            liquidity_usd=float(
                getattr(
                    coin,
                    "liquidity",
                    0.0,
                )
                or 0.0
            ),
            wallet_public_key=(
                self.portfolio.wallet_public_key
            ),
            open_positions=len(
                self.portfolio.get_open_positions()
            ),
        )

        if not result.success:

            self.order_logger.update_order(
                order_id,
                status="FAILED",
                error=result.error,
            )

            print("BUY BLOCKED:", result.error)

            return None

        self.order_logger.update_order(
            order_id,
            status="TRANSACTION_BUILT",
        )

        return self._sign_send_confirm(
            order_id=order_id,
            transaction=result.transaction,
            requested_amount=amount,
            symbol=symbol,
            side="BUY",
        )

    # =========================================================
    # SELL ALL
    # =========================================================

    def sell_all(
        self,
        position,
        exit_reason="",
    ):

        tokens = float(
            getattr(
                position,
                "tokens",
                0.0,
            )
            or 0.0
        )

        if tokens <= 0:

            print(
                "SELL ALL BLOCKED: position has no tokens"
            )

            return False

        return self._execute_sell(
            position=position,
            token_quantity=tokens,
            sell_percent=100.0,
            exit_reason=exit_reason,
        )

    # =========================================================
    # PARTIAL SELL
    # =========================================================

    def partial_sell(
        self,
        position,
        percent,
        exit_reason="",
    ):

        try:

            token_quantity = (
                self._sell_percent_of_remaining(
                    position,
                    percent,
                )
            )

        except ValueError as exc:

            print(
                "PARTIAL SELL BLOCKED:",
                exc,
            )

            return False

        return self._execute_sell(
            position=position,
            token_quantity=token_quantity,
            sell_percent=float(percent),
            exit_reason=exit_reason,
        )

    # =========================================================
    # SELL EXECUTION
    # =========================================================

    def _execute_sell(
        self,
        position,
        token_quantity,
        sell_percent,
        exit_reason,
    ):

        symbol = getattr(
            position,
            "symbol",
            "UNKNOWN",
        )

        contract = getattr(
            position,
            "contract",
            None,
        )

        if not contract:

            print(
                "SELL BLOCKED: missing token contract"
            )

            return False

        try:

            raw_amount, decimals = (
                self._token_quantity_to_raw(
                    contract,
                    token_quantity,
                )
            )

        except Exception as exc:

            print(
                "SELL BLOCKED:",
                exc,
            )

            return False

        print()
        print("=" * 70)
        print("LIVE SELL")
        print("=" * 70)
        print("Symbol          :", symbol)
        print("Contract        :", contract)
        print("UI tokens       :", token_quantity)
        print("Raw token units :", raw_amount)
        print("Decimals        :", decimals)
        print("Sell % remaining:", sell_percent)
        print("Reason          :", exit_reason)

        order_id = (
            self.order_logger.create_order(
                signal_id=getattr(
                    position,
                    "signal_id",
                    None,
                ),
                symbol=symbol,
                side="SELL",
                requested_amount=0.0,
                idempotency_key=str(
                    uuid.uuid4()
                ),
            )
        )

        if not order_id:

            print(
                "SELL BLOCKED: order creation failed"
            )

            return False

        self.order_logger.update_order(
            order_id,
            status="PREFLIGHT",
        )

        try:

            result = self.executor.prepare_sell(
                token_mint=contract,
                token_amount=raw_amount,
                liquidity_usd=float(
                    getattr(
                        position,
                        "liquidity",
                        0.0,
                    )
                    or 0.0
                ),
                wallet_public_key=(
                    self.portfolio.wallet_public_key
                ),
                open_positions=len(
                    self.portfolio.get_open_positions()
                ),
            )

        except Exception as exc:

            self.order_logger.update_order(
                order_id,
                status="FAILED",
                error=str(exc),
            )

            print(
                "SELL PREFLIGHT ERROR:",
                exc,
            )

            return False

        if not result.success:

            self.order_logger.update_order(
                order_id,
                status="FAILED",
                error=result.error,
            )

            print(
                "SELL BLOCKED:",
                result.error,
            )

            return False

        self.order_logger.update_order(
            order_id,
            status="TRANSACTION_BUILT",
        )

        print()
        print("=" * 70)
        print("SELL TRANSACTION READY")
        print("=" * 70)
        print(
            "Price impact:",
            f"{result.price_impact:.4f}%",
        )
        print(
            "Raw bytes:",
            len(bytes(result.transaction)),
        )

        # -----------------------------------------------------
        # CRITICAL:
        #
        # No position modification occurs here.
        # -----------------------------------------------------

        return self._sign_send_confirm(
            order_id=order_id,
            transaction=result.transaction,
            requested_amount=0.0,
            symbol=symbol,
            side="SELL",
            position=position,
            token_quantity=token_quantity,
            sell_percent=sell_percent,
        )

    # =========================================================
    # SIGN -> SEND -> CONFIRM
    # =========================================================

    def _sign_send_confirm(
        self,
        order_id,
        transaction,
        requested_amount,
        symbol,
        side,
        position=None,
        token_quantity=0.0,
        sell_percent=100.0,
    ):

        print()
        print("=" * 70)
        print("SIGNING")
        print("=" * 70)

        try:

            self.signer = LiveSigner(
                expected_public_key=(
                    self.portfolio.wallet_public_key
                ),
            )

            signed = self.signer.sign(
                transaction
            )

            self.signer.verify_signed_transaction(
                signed
            )

        except LiveSignerError as exc:

            self.order_logger.update_order(
                order_id,
                status="SIGNING_BLOCKED",
                error=str(exc),
            )

            print(
                "SIGNING BLOCKED:",
                exc,
            )

            print(
                "No transaction submitted."
            )

            return None

        self.order_logger.update_order(
            order_id,
            status="SIGNED",
        )

        print(
            "Signed transaction : YES"
        )

        # -----------------------------------------------------
        # SUBMISSION
        # -----------------------------------------------------

        print()
        print("=" * 70)
        print("SOLANA SUBMISSION")
        print("=" * 70)

        try:

            self.order_logger.update_order(
                order_id,
                status="SUBMISSION_ATTEMPTED",
            )

            signature = self.sender.send(
                signed
            )

        except SolanaSenderError as exc:

            self.order_logger.update_order(
                order_id,
                status="SUBMISSION_FAILED",
                error=str(exc),
            )

            print(
                "SUBMISSION FAILED:",
                exc,
            )

            return None

        self.order_logger.update_order(
            order_id,
            status="SUBMITTED",
            transaction_signature=signature,
        )

        print(
            "Transaction signature:",
            signature,
        )

        # -----------------------------------------------------
        # CONFIRMATION
        # -----------------------------------------------------

        print()
        print("=" * 70)
        print("CONFIRMATION")
        print("=" * 70)

        try:

            confirmation = (
                self.sender.confirm(
                    signature
                )
            )

        except SolanaSenderError as exc:

            self.order_logger.update_order(
                order_id,
                status="CONFIRMATION_FAILED",
                error=str(exc),
            )

            print(
                "CONFIRMATION FAILED:",
                exc,
            )

            return None

        confirmation_status = (
            confirmation.get(
                "confirmation_status"
            )
        )

        slot = confirmation.get(
            "slot"
        )

        self.order_logger.update_order(
            order_id,
            status="CONFIRMED",
            executed_amount=(
                requested_amount
                if side == "BUY"
                else 0.0
            ),
            transaction_signature=signature,
            confirmation_status=confirmation_status,
            confirmed_slot=slot,
        )

        # -----------------------------------------------------
        # ONLY NOW update position
        # -----------------------------------------------------

        if side == "SELL" and position is not None:

            self._apply_confirmed_sell(
                position=position,
                token_quantity=token_quantity,
                sell_percent=sell_percent,
            )

        print()
        print("=" * 70)
        print(
            f"LIVE {side} CONFIRMED"
        )
        print("=" * 70)
        print("Order ID :", order_id)
        print("Signature:", signature)
        print("Status   :", confirmation_status)

        return {
            "order_id": order_id,
            "signature": signature,
            "confirmation_status": confirmation_status,
            "slot": slot,
            "side": side,
            "symbol": symbol,
        }

    # =========================================================
    # POSITION UPDATE AFTER CONFIRMED SELL
    # =========================================================

    def _apply_confirmed_sell(
        self,
        position,
        token_quantity,
        sell_percent,
    ):

        current_tokens = float(
            getattr(
                position,
                "tokens",
                0.0,
            )
            or 0.0
        )

        actual_sold = min(
            current_tokens,
            float(token_quantity),
        )

        remaining = max(
            0.0,
            current_tokens - actual_sold,
        )

        position.tokens = remaining

        old_remaining_percent = float(
            getattr(
                position,
                "remaining_percent",
                100.0,
            )
            or 0.0
        )

        sold_percent = min(
            old_remaining_percent,
            old_remaining_percent
            * float(sell_percent)
            / 100.0,
        )

        position.remaining_percent = max(
            0.0,
            old_remaining_percent - sold_percent,
        )

        position.sold_percent = min(
            100.0,
            float(
                getattr(
                    position,
                    "sold_percent",
                    0.0,
                )
                or 0.0
            ) + sold_percent,
        )

        if position.tokens <= 0:

            position.status = "CLOSED"

    # =========================================================
    # CLOSE
    # =========================================================

    def close(self):

        if self.order_logger:

            self.order_logger.close()
