import time

from execution.jupiter_client import (
    JupiterClient,
    JupiterError,
    SOL_MINT,
)


EXECUTION_MODEL_VERSION = "JUPITER_OBSERVATION_V1"

# For SKIP/WATCH signals, use this amount purely for
# hypothetical execution-quality measurement.
# It does NOT create a trade.
SHADOW_QUOTE_USD = 3.0


class ExecutionIntelligence:

    @staticmethod
    def calculate_snapshot(coin, s6_allocation):

        price = getattr(coin, "price", 0.0) or 0.0
        liq = getattr(coin, "liquidity", 0.0) or 0.0
        vol_5m = getattr(coin, "volume_5m", 0.0) or 0.0

        alloc = float(s6_allocation or 0.0)

        # ---------------------------------------------------------
        # OBSERVED
        # ---------------------------------------------------------

        observed = {
            "requested_allocation_usd": alloc,
            "price_at_decision": float(price),
            "liquidity_usd": float(liq),
            "volume_5m_usd": float(vol_5m),
            "volume_1h_usd": float(
                getattr(coin, "volume_1h", 0.0) or 0.0
            ),
            "buys_5m": int(
                getattr(coin, "buys_5m", 0) or 0
            ),
            "sells_5m": int(
                getattr(coin, "sells_5m", 0) or 0
            ),
            "chain": getattr(coin, "chain", "unknown"),
            "dex": getattr(coin, "dex", "unknown"),
            "pair": getattr(coin, "contract", "unknown"),
        }

        # ---------------------------------------------------------
        # DERIVED
        # ---------------------------------------------------------

        alloc_to_liq = 0.0
        if alloc > 0 and liq > 0:
            alloc_to_liq = alloc / liq

        alloc_to_vol_5m = 0.0
        if alloc > 0 and vol_5m > 0:
            alloc_to_vol_5m = alloc / vol_5m

        derived = {
            "allocation_to_liquidity": alloc_to_liq,
            "allocation_to_volume_5m": alloc_to_vol_5m,
        }

        # ---------------------------------------------------------
        # ESTIMATED
        #
        # Retain the old heuristic for comparison.
        # It is NOT treated as ground truth.
        # ---------------------------------------------------------

        safe_liq = max(float(liq), 1.0)
        safe_vol = max(float(vol_5m), 1.0)

        base_fee = 0.01

        est_entry_impact = (
            alloc / safe_liq * 2.0
        ) + (
            alloc / safe_vol * 0.5
        ) + base_fee

        est_exit_impact = est_entry_impact * 1.5

        est_round_trip = (
            est_entry_impact +
            est_exit_impact
        )

        status = "SAFE"

        if alloc_to_liq > 0.05 or alloc_to_vol_5m > 0.5:
            status = "DANGEROUS_LIQUIDITY"

        elif est_round_trip > 0.10:
            status = "HIGH_IMPACT"

        estimated = {
            "estimated_entry_impact": est_entry_impact,
            "estimated_exit_impact": est_exit_impact,
            "estimated_round_trip_cost": est_round_trip,
            "execution_quality_status": status,
        }

        # ---------------------------------------------------------
        # REAL JUPITER OBSERVATION
        # ---------------------------------------------------------

        jupiter = {
            "available": False,
            "quote_timestamp": time.time(),
            "quote_size_usd": None,
            "input_mint": SOL_MINT,
            "output_mint": getattr(
                coin,
                "contract",
                None,
            ),
            "input_amount_lamports": None,
            "output_amount": None,
            "price_impact_pct": None,
            "route": [],
            "route_count": 0,
            "quote_valid": False,
            "reason": None,
            "error": None,
        }

        chain = str(
            getattr(coin, "chain", "") or ""
        ).lower()

        token_mint = getattr(
            coin,
            "contract",
            None,
        )

        # ---------------------------------------------------------
        # Only query Jupiter for Solana tokens.
        # ---------------------------------------------------------

        if chain != "solana":
            jupiter["reason"] = "NON_SOLANA"

        elif not token_mint:
            jupiter["reason"] = "MISSING_TOKEN_MINT"

        else:

            # Actual S6 allocation for BUY/STRONG BUY.
            #
            # For SKIP/WATCH, use $3 purely as a
            # standardized hypothetical observation.
            quote_usd = (
                alloc
                if alloc > 0
                else SHADOW_QUOTE_USD
            )

            lamports = int(
                quote_usd * 1_000_000_000
            )

            jupiter["quote_size_usd"] = quote_usd
            jupiter["input_amount_lamports"] = lamports

            try:

                client = JupiterClient()

                quote = client.get_quote(
                    input_mint=SOL_MINT,
                    output_mint=token_mint,
                    amount=lamports,
                )

                valid, reason = client.validate_quote(
                    quote,
                    max_price_impact_pct=2.0,
                )

                jupiter["available"] = True
                jupiter["quote_valid"] = bool(valid)
                jupiter["reason"] = reason

                jupiter["input_amount_lamports"] = int(
                    quote.get("inAmount", lamports)
                )

                jupiter["output_amount"] = int(
                    quote.get("outAmount", 0)
                )

                jupiter["price_impact_pct"] = float(
                    quote.get(
                        "priceImpactPct",
                        0.0,
                    )
                )

                routes = quote.get(
                    "routePlan",
                    [],
                ) or []

                jupiter["route_count"] = len(routes)

                for route in routes:

                    swap_info = route.get(
                        "swapInfo",
                        {},
                    )

                    label = swap_info.get(
                        "label"
                    )

                    if label:
                        jupiter["route"].append(
                            label
                        )

            except JupiterError as exc:

                jupiter["reason"] = "QUOTE_ERROR"
                jupiter["error"] = str(exc)

            except Exception as exc:

                jupiter["reason"] = "UNEXPECTED_ERROR"
                jupiter["error"] = repr(exc)

        # ---------------------------------------------------------
        # FINAL SNAPSHOT
        # ---------------------------------------------------------

        return {
            "execution_model_version":
                EXECUTION_MODEL_VERSION,

            "OBSERVED":
                observed,

            "DERIVED":
                derived,

            "ESTIMATED":
                estimated,

            "JUPITER":
                jupiter,
        }
