import base64
import os
import requests

from solders.transaction import VersionedTransaction

from execution.jupiter_client import (
    JupiterClient,
    JupiterError,
    SOL_MINT,
)

from execution.live_risk import LiveRiskManager

from trading.live_wallet import (
    LiveWallet,
    LiveWalletError,
    LAMPORTS_PER_SOL,
)


SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL",
    "https://api.mainnet-beta.solana.com",
)


class LiveExecutionResult:

    def __init__(
        self,
        success,
        transaction=None,
        quote=None,
        price_impact=None,
        amount_usd=0.0,
        token_mint=None,
        token_amount=0,
        direction=None,
        error=None,
    ):
        self.success = bool(success)
        self.transaction = transaction
        self.quote = quote
        self.price_impact = price_impact
        self.amount_usd = float(amount_usd or 0.0)
        self.token_mint = token_mint
        self.token_amount = int(token_amount or 0)
        self.direction = direction
        self.error = error


class LiveExecutor:

    """
    Live execution preparation layer.

    BUY:
        SOL -> TOKEN

    SELL:
        TOKEN -> SOL

    This class NEVER:
        - loads private keys
        - signs
        - submits
        - modifies portfolio state

    It only prepares and validates transactions.
    """

    def __init__(self):

        self.jupiter = JupiterClient(
            slippage_bps=int(
                os.getenv(
                    "LIVE_MAX_SLIPPAGE_BPS",
                    "100",
                )
            )
        )

        self.risk = LiveRiskManager()

        self.rpc_url = os.getenv(
            "SOLANA_RPC_URL",
            SOLANA_RPC_URL,
        )

    # =========================================================
    # RPC
    # =========================================================

    def _rpc(self, method, params):

        try:

            response = requests.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params,
                },
                timeout=15,
            )

            response.raise_for_status()

            data = response.json()

        except requests.RequestException as exc:

            raise RuntimeError(
                f"Solana RPC request failed: {exc}"
            ) from exc

        except ValueError as exc:

            raise RuntimeError(
                "Solana RPC returned invalid JSON"
            ) from exc

        if "error" in data:

            raise RuntimeError(
                f"Solana RPC error: {data['error']}"
            )

        return data.get("result")

    # =========================================================
    # TOKEN DECIMALS
    # =========================================================

    def get_token_decimals(self, token_mint):

        result = self._rpc(
            "getTokenSupply",
            [
                token_mint,
                {
                    "commitment": "confirmed",
                },
            ],
        )

        if not result:

            raise RuntimeError(
                "Token supply response was empty"
            )

        value = result.get("value")

        if not value:

            raise RuntimeError(
                "Token supply value missing"
            )

        decimals = int(
            value.get("decimals")
        )

        if decimals < 0 or decimals > 18:

            raise RuntimeError(
                f"Invalid token decimals: {decimals}"
            )

        return decimals

    # =========================================================
    # BUILD / DECODE
    # =========================================================

    def _decode_transaction(self, encoded):

        try:

            raw = base64.b64decode(
                encoded
            )

            transaction = (
                VersionedTransaction.from_bytes(
                    raw
                )
            )

        except Exception as exc:

            raise JupiterError(
                f"Transaction decode failed: {exc}"
            ) from exc

        return transaction, raw

    # =========================================================
    # BUY
    # =========================================================

    def prepare_buy(
        self,
        token_mint,
        amount_usd,
        liquidity_usd,
        wallet_public_key,
        open_positions=0,
    ):

        print("=" * 70)
        print("LIVE EXECUTOR — BUY PREFLIGHT")
        print("=" * 70)

        try:

            amount_usd = float(amount_usd)
            liquidity_usd = float(liquidity_usd)
            open_positions = int(open_positions)

        except (
            TypeError,
            ValueError,
        ) as exc:

            return LiveExecutionResult(
                False,
                error=f"Invalid parameters: {exc}",
                direction="BUY",
            )

        if amount_usd <= 0:

            return LiveExecutionResult(
                False,
                error="Amount must be greater than zero",
                direction="BUY",
            )

        if not token_mint:

            return LiveExecutionResult(
                False,
                error="Token mint is required",
                direction="BUY",
            )

        if not wallet_public_key:

            return LiveExecutionResult(
                False,
                error="Wallet public key is required",
                direction="BUY",
            )

        print("Token           :", token_mint)
        print("Amount USD      :", amount_usd)
        print("Liquidity USD   :", liquidity_usd)
        print("Wallet          :", wallet_public_key)
        print("Open positions  :", open_positions)

        # -----------------------------------------------------
        # USD -> SOL
        # -----------------------------------------------------

        try:

            wallet = LiveWallet(
                wallet_public_key
            )

            lamports = wallet.usd_to_lamports(
                amount_usd
            )

            sol_amount = (
                lamports /
                LAMPORTS_PER_SOL
            )

            sol_price = (
                wallet.get_sol_usd_price()
            )

        except LiveWalletError as exc:

            return LiveExecutionResult(
                False,
                error=f"USD -> SOL conversion failed: {exc}",
                direction="BUY",
            )

        print()
        print("[1] USD -> SOL conversion")
        print(
            "    USD amount :",
            f"${amount_usd:.4f}",
        )
        print(
            "    SOL price  :",
            f"${sol_price:.4f}",
        )
        print(
            "    SOL amount :",
            f"{sol_amount:.9f}",
        )
        print(
            "    Lamports   :",
            f"{lamports:,}",
        )

        # -----------------------------------------------------
        # QUOTE
        # -----------------------------------------------------

        print()
        print("[2] Requesting Jupiter BUY quote...")

        try:

            quote = self.jupiter.get_quote(
                input_mint=SOL_MINT,
                output_mint=token_mint,
                amount=lamports,
            )

        except JupiterError as exc:

            return LiveExecutionResult(
                False,
                error=str(exc),
                direction="BUY",
            )

        try:

            price_impact = float(
                quote.get(
                    "priceImpactPct",
                    999,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            price_impact = 999.0

        print("    Quote: OK")
        print("    Input :", quote.get("inAmount"))
        print("    Output:", quote.get("outAmount"))
        print(
            "    Price impact:",
            price_impact,
            "%",
        )

        # -----------------------------------------------------
        # VALIDATION
        # -----------------------------------------------------

        valid, reason = (
            self.jupiter.validate_quote(
                quote,
                max_price_impact_pct=(
                    self.risk.max_price_impact_pct
                ),
            )
        )

        print()
        print("[3] Quote validation")
        print("    Valid :", valid)
        print("    Reason:", reason)

        if not valid:

            return LiveExecutionResult(
                False,
                quote=quote,
                price_impact=price_impact,
                amount_usd=amount_usd,
                token_mint=token_mint,
                error=reason,
                direction="BUY",
            )

        # -----------------------------------------------------
        # RISK
        # -----------------------------------------------------

        decision = self.risk.check_trade(
            amount_usd=amount_usd,
            liquidity_usd=liquidity_usd,
            price_impact_pct=price_impact,
            open_positions=open_positions,
        )

        print()
        print("[4] Live risk check")
        print("    Approved:", decision.approved)
        print("    Reason  :", decision.reason)

        if not decision.approved:

            return LiveExecutionResult(
                False,
                quote=quote,
                price_impact=price_impact,
                amount_usd=amount_usd,
                token_mint=token_mint,
                error=decision.reason,
                direction="BUY",
            )

        # -----------------------------------------------------
        # TRANSACTION
        # -----------------------------------------------------

        print()
        print("[5] Building unsigned BUY transaction...")

        try:

            swap = (
                self.jupiter.build_swap_transaction(
                    quote=quote,
                    user_public_key=wallet_public_key,
                )
            )

            encoded = swap.get(
                "swapTransaction"
            )

            if not encoded:

                raise JupiterError(
                    "Jupiter returned no swap transaction"
                )

            transaction, raw = (
                self._decode_transaction(
                    encoded
                )
            )

        except Exception as exc:

            return LiveExecutionResult(
                False,
                quote=quote,
                price_impact=price_impact,
                amount_usd=amount_usd,
                token_mint=token_mint,
                error=str(exc),
                direction="BUY",
            )

        print("    Transaction : RECEIVED")
        print("    Raw bytes   :", len(raw))
        print(
            "    Instructions:",
            len(transaction.message.instructions),
        )

        print()
        print("BUY PREFLIGHT COMPLETE")
        print("NO SIGNING.")
        print("NO SUBMISSION.")
        print("NO FUNDS MOVED.")

        return LiveExecutionResult(
            True,
            transaction=transaction,
            quote=quote,
            price_impact=price_impact,
            amount_usd=amount_usd,
            token_mint=token_mint,
            token_amount=int(
                quote.get("outAmount", 0)
            ),
            direction="BUY",
        )

    # =========================================================
    # SELL
    # =========================================================

    def prepare_sell(
        self,
        token_mint,
        token_amount,
        liquidity_usd,
        wallet_public_key,
        open_positions=1,
    ):

        print("=" * 70)
        print("LIVE EXECUTOR — SELL PREFLIGHT")
        print("=" * 70)

        try:

            token_amount = int(
                token_amount
            )

            liquidity_usd = float(
                liquidity_usd
            )

            open_positions = int(
                open_positions
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            return LiveExecutionResult(
                False,
                error=f"Invalid SELL parameters: {exc}",
                direction="SELL",
            )

        if token_amount <= 0:

            return LiveExecutionResult(
                False,
                error="Token amount must be greater than zero",
                direction="SELL",
            )

        if not token_mint:

            return LiveExecutionResult(
                False,
                error="Token mint is required",
                direction="SELL",
            )

        if not wallet_public_key:

            return LiveExecutionResult(
                False,
                error="Wallet public key is required",
                direction="SELL",
            )

        print("Token           :", token_mint)
        print("Token amount    :", token_amount)
        print("Liquidity USD   :", liquidity_usd)
        print("Wallet          :", wallet_public_key)
        print("Open positions  :", open_positions)

        # -----------------------------------------------------
        # SELL QUOTE
        # -----------------------------------------------------

        print()
        print("[1] Requesting Jupiter SELL quote...")

        try:

            quote = self.jupiter.get_quote(
                input_mint=token_mint,
                output_mint=SOL_MINT,
                amount=token_amount,
            )

        except JupiterError as exc:

            return LiveExecutionResult(
                False,
                error=str(exc),
                direction="SELL",
            )

        try:

            price_impact = float(
                quote.get(
                    "priceImpactPct",
                    999,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            price_impact = 999.0

        print("    Quote: OK")
        print("    Token input :", quote.get("inAmount"))
        print("    SOL output  :", quote.get("outAmount"))
        print(
            "    Price impact:",
            price_impact,
            "%",
        )

        # -----------------------------------------------------
        # VALIDATE
        # -----------------------------------------------------

        valid, reason = (
            self.jupiter.validate_quote(
                quote,
                max_price_impact_pct=(
                    self.risk.max_price_impact_pct
                ),
            )
        )

        print()
        print("[2] SELL quote validation")
        print("    Valid :", valid)
        print("    Reason:", reason)

        if not valid:

            return LiveExecutionResult(
                False,
                quote=quote,
                price_impact=price_impact,
                token_mint=token_mint,
                token_amount=token_amount,
                error=reason,
                direction="SELL",
            )

        # -----------------------------------------------------
        # SELL RISK
        #
        # We use the quote's estimated SOL output to calculate
        # an approximate USD trade value.
        # -----------------------------------------------------

        try:

            wallet = LiveWallet(
                wallet_public_key
            )

            sol_price = (
                wallet.get_sol_usd_price()
            )

            output_lamports = int(
                quote.get(
                    "outAmount",
                    0,
                )
            )

            estimated_usd = (
                output_lamports /
                LAMPORTS_PER_SOL
                * sol_price
            )

        except Exception as exc:

            return LiveExecutionResult(
                False,
                quote=quote,
                price_impact=price_impact,
                token_mint=token_mint,
                token_amount=token_amount,
                error=(
                    f"Unable to value SELL quote: {exc}"
                ),
                direction="SELL",
            )

        decision = self.risk.check_trade(
            amount_usd=estimated_usd,
            liquidity_usd=liquidity_usd,
            price_impact_pct=price_impact,
            open_positions=open_positions,
        )

        print()
        print("[3] SELL risk check")
        print("    Estimated USD:", f"${estimated_usd:.6f}")
        print("    Approved     :", decision.approved)
        print("    Reason       :", decision.reason)

        if not decision.approved:

            return LiveExecutionResult(
                False,
                quote=quote,
                price_impact=price_impact,
                amount_usd=estimated_usd,
                token_mint=token_mint,
                token_amount=token_amount,
                error=decision.reason,
                direction="SELL",
            )

        # -----------------------------------------------------
        # BUILD TRANSACTION
        # -----------------------------------------------------

        print()
        print("[4] Building unsigned SELL transaction...")

        try:

            swap = (
                self.jupiter.build_swap_transaction(
                    quote=quote,
                    user_public_key=wallet_public_key,
                )
            )

            encoded = swap.get(
                "swapTransaction"
            )

            if not encoded:

                raise JupiterError(
                    "Jupiter returned no SELL transaction"
                )

            transaction, raw = (
                self._decode_transaction(
                    encoded
                )
            )

        except Exception as exc:

            return LiveExecutionResult(
                False,
                quote=quote,
                price_impact=price_impact,
                amount_usd=estimated_usd,
                token_mint=token_mint,
                token_amount=token_amount,
                error=str(exc),
                direction="SELL",
            )

        print("    Transaction : RECEIVED")
        print("    Raw bytes   :", len(raw))
        print(
            "    Instructions:",
            len(transaction.message.instructions),
        )

        print()
        print("SELL PREFLIGHT COMPLETE")
        print("NO SIGNING.")
        print("NO SUBMISSION.")
        print("NO FUNDS MOVED.")

        return LiveExecutionResult(
            True,
            transaction=transaction,
            quote=quote,
            price_impact=price_impact,
            amount_usd=estimated_usd,
            token_mint=token_mint,
            token_amount=token_amount,
            direction="SELL",
        )


if __name__ == "__main__":

    print(
        "LiveExecutor is an execution library."
    )
    print(
        "Use LiveTrader or an explicit test harness."
    )
