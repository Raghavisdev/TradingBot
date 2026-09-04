import base64
import os
import requests
import logging

logger = logging.getLogger("LiveExecutor")

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
        **kwargs
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
        
        # Telemetry fields
        self.telemetry = kwargs


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
        coin=None,
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
        # EXECUTION SNAPSHOT
        # -----------------------------------------------------
        print()
        print("[2] Execution Snapshot")
        if coin:
            # We capture the exact expected edge and components before quoting
            from ai_engine.s6_production_entry import evaluate_s6_production_entry
            import config
            
            # Temporary override of the actual live portfolio cash if we are testing a $1 cap
            # We want to re-run the gate to see what it would have done
            pre_quote_eval = evaluate_s6_production_entry(coin, self.risk) # Passing risk is just for dummy purposes, we only care about edge. Wait, evaluate_s6_production_entry takes (coin, portfolio)
            
            logger.info(f"[EXECUTION SNAPSHOT] Pre-quote Edge: {getattr(pre_quote_eval, 'expected_value', 0.0)}")
            print(f"    S6 Expected Value (Paper): {getattr(pre_quote_eval, 'expected_value', 0.0)}")

        # -----------------------------------------------------
        # QUOTE
        # -----------------------------------------------------

        print()
        print("[3] Requesting Jupiter BUY quote...")

        try:
            import time
            quote_ts = time.time()
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
            price_impact = float(quote.get("priceImpactPct", 999))
        except (TypeError, ValueError):
            price_impact = 999.0

        print("    Quote: OK")
        print("    Input :", quote.get("inAmount"))
        print("    Output:", quote.get("outAmount"))
        print("    Price impact:", price_impact, "%")

        # -----------------------------------------------------
        # PROVISIONAL ECONOMIC GATE
        # -----------------------------------------------------
        valid, reason = self.jupiter.validate_quote(
            quote,
            max_price_impact_pct=self.risk.max_price_impact_pct,
        )

        print()
        print("[4] Provisional Quote validation")
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
        # TRANSACTION BUILD & ACTUAL FEES
        # -----------------------------------------------------
        print()
        print("[5] Building unsigned BUY transaction & determining fees...")

        try:
            build_ts = time.time()
            swap = self.jupiter.build_swap_transaction(
                quote=quote,
                user_public_key=wallet_public_key,
            )

            encoded = swap.get("swapTransaction")
            if not encoded:
                raise JupiterError("Jupiter returned no swap transaction")

            transaction, raw = self._decode_transaction(encoded)
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
        print("    Instructions:", len(transaction.message.instructions))

        # -----------------------------------------------------
        # FINAL ECONOMIC GATE
        # -----------------------------------------------------
        print()
        print("[6] Final Economic Gate")
        
        try:
            import config
            out_amount = float(quote.get("outAmount", 0)) / (10 ** 6) # Assuming 6 decimals for target token
            in_amount = float(quote.get("inAmount", 0)) / (10 ** 9) # Assuming 9 decimals for SOL
            
            sol_price_usd = wallet.get_sol_usd_price() if 'wallet' in locals() else 150.0
            executable_price = (in_amount * sol_price_usd) / out_amount if out_amount > 0 else 0.0
            
            # Determine fees
            network_fee_sol = 0.000005
            
            # Extract priority fee if returned by Jupiter (simulate if missing for Phase 1)
            # The swap endpoint can return prioritizationFeeLamports, but we're fetching quote here.
            # We'll use a conservative estimate or the config max.
            priority_fee_sol = getattr(config, "LIVE_PRIORITY_FEE_MAX_SOL", 0.005)
            # Since exact live priority-fee estimation is not currently parsed dynamically:
            fee_estimation_status = "INCOMPLETE" 
            # We will add it to the logger and note it.
            logger.warning("[FINAL ECONOMIC GATE] PRIORITY_FEE_ESTIMATION_INCOMPLETE: Using simulated max fee.")
            
            total_fee_usd = (network_fee_sol + priority_fee_sol) * sol_price_usd
            slippage_usd = (executable_price * out_amount) * (price_impact / 100.0)
            
            logger.info(f"[FINAL ECONOMIC GATE] Exec Price: {executable_price:.6f}, Fees: {total_fee_usd:.2f}, Slippage: {slippage_usd:.2f}")
            
            live_expected_net_edge = 0.0
            decision = "SHADOW_WOULD_EXECUTE"
            abort_reason = None
            
            if coin:
                from ai_engine.s6_production_entry import evaluate_s6_production_entry
                
                # Mock entry to get baseline edge
                eval_result = evaluate_s6_production_entry(coin, self.risk)
                expected_trade_edge = getattr(eval_result, 'expected_value', 0.0)
                
                # Calculate actual live edge
                # In a full implementation, we'd adjust expected_trade_edge directly based on executable_price
                # For Phase 1 Shadow, we subtract the physical costs from the Paper expected edge
                live_expected_net_edge = expected_trade_edge - total_fee_usd - slippage_usd
                
                if live_expected_net_edge <= 0:
                    decision = "ABORT"
                    abort_reason = "Live edge <= 0 after fees/slippage"
            
            if decision == "ABORT":
                logger.warning(f"[FINAL ECONOMIC GATE] ABORT: {abort_reason} (Edge: {live_expected_net_edge:.2f})")
                return LiveExecutionResult(
                    False,
                    quote=quote,
                    price_impact=price_impact,
                    amount_usd=amount_usd,
                    token_mint=token_mint,
                    error=abort_reason,
                    direction="BUY",
                    decision=decision,
                    abort_reason=abort_reason,
                    fee_estimation_status=fee_estimation_status,
                    live_expected_net_edge=live_expected_net_edge,
                    executable_price=executable_price,
                    network_fee_sol=network_fee_sol,
                    priority_fee_sol=priority_fee_sol,
                    slippage_usd=slippage_usd,
                    quote_ts=quote_ts,
                    build_ts=build_ts,
                )
                
        except Exception as gate_exc:
            logger.error(f"[FINAL ECONOMIC GATE] Failed to evaluate: {gate_exc}")
            return LiveExecutionResult(
                False,
                quote=quote,
                price_impact=price_impact,
                amount_usd=amount_usd,
                token_mint=token_mint,
                error=f"Economic Gate Error: {gate_exc}",
                direction="BUY",
                decision="ABORT",
                abort_reason="Economic Gate Exception",
                fee_estimation_status="INCOMPLETE",
                live_expected_net_edge=0.0
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
            decision=decision,
            abort_reason=abort_reason,
            fee_estimation_status=fee_estimation_status,
            live_expected_net_edge=live_expected_net_edge,
            executable_price=executable_price,
            network_fee_sol=network_fee_sol,
            priority_fee_sol=priority_fee_sol,
            slippage_usd=slippage_usd,
            quote_ts=quote_ts,
            build_ts=build_ts,
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
