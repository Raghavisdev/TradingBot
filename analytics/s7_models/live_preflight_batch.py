import base64
import sqlite3
import time

from solders.transaction import VersionedTransaction

from config import DATABASE
from execution.jupiter_client import JupiterClient, JupiterError, SOL_MINT
from trading.live_wallet import LiveWallet, LAMPORTS_PER_SOL


WALLET = "E9ecD6sGtj5DXHJ7ETxbPBMS7rYdgCJjzRcbai4q1ScH"

TEST_AMOUNT_USD = 1.0
MAX_PRICE_IMPACT_PCT = 2.0

TOKEN_LIMIT = 20

# Diagnostic batch pacing.
# This is intentionally conservative because each token can
# generate multiple Jupiter API requests (quote + swap build).
# Normal live execution is not governed by this batch delay.
BATCH_DELAY_SECONDS = 3.0


def get_tokens():

    con = sqlite3.connect(DATABASE)

    try:
        return con.execute(
            """
            SELECT symbol, contract
            FROM paper_lab_trades
            WHERE strategy_id = 'S6_Moonshot_Ladder'
              AND contract IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (TOKEN_LIMIT,),
        ).fetchall()

    finally:
        con.close()


def main():

    tokens = get_tokens()

    wallet = LiveWallet(WALLET)

    jupiter = JupiterClient(
        slippage_bps=100
    )

    print("=" * 90)
    print("S6 LIVE EXECUTION PREFLIGHT — 20 RECENT CONTRACTS")
    print("=" * 90)

    print(f"Test amount       : ${TEST_AMOUNT_USD:.2f}")
    print(f"Max price impact  : {MAX_PRICE_IMPACT_PCT:.2f}%")
    print(f"Max slippage      : 100 bps")
    print(f"Wallet            : {WALLET}")
    print()
    print("NO SIGNING")
    print("NO SUBMISSION")
    print("NO FUNDS MOVED")
    print("=" * 90)

    results = []

    for index, (symbol, token) in enumerate(tokens, 1):

        # Keep diagnostic traffic below Jupiter/API gateway
        # rate limits. Do not sleep before the first token.
        if index > 1:
            print(
                f"Waiting {BATCH_DELAY_SECONDS:.1f}s "
                f"before next token..."
            )
            time.sleep(
                BATCH_DELAY_SECONDS
            )

        print()
        print("-" * 90)
        print(f"[{index:02d}/{len(tokens)}] {symbol}")
        print(f"Token: {token}")

        started = time.time()

        try:

            lamports = wallet.usd_to_lamports(
                TEST_AMOUNT_USD
            )

            sol_amount = (
                lamports /
                LAMPORTS_PER_SOL
            )

            quote = jupiter.get_quote(
                input_mint=SOL_MINT,
                output_mint=token,
                amount=lamports,
            )

            price_impact = float(
                quote.get(
                    "priceImpactPct",
                    999,
                )
            )

            if price_impact > MAX_PRICE_IMPACT_PCT:

                results.append(
                    (
                        symbol,
                        token,
                        "RISK_REJECTED",
                        price_impact,
                        time.time() - started,
                    )
                )

                print(
                    f"RISK REJECTED | "
                    f"impact={price_impact:.4f}%"
                )

                continue

            valid, reason = jupiter.validate_quote(
                quote,
                max_price_impact_pct=MAX_PRICE_IMPACT_PCT,
            )

            if not valid:

                results.append(
                    (
                        symbol,
                        token,
                        "QUOTE_REJECTED",
                        price_impact,
                        time.time() - started,
                    )
                )

                print(
                    f"QUOTE REJECTED | {reason}"
                )

                continue

            swap = jupiter.build_swap_transaction(
                quote=quote,
                user_public_key=WALLET,
            )

            encoded = swap.get(
                "swapTransaction"
            )

            if not encoded:
                raise RuntimeError(
                    "Jupiter returned no swapTransaction"
                )

            raw = base64.b64decode(
                encoded
            )

            transaction = (
                VersionedTransaction.from_bytes(
                    raw
                )
            )

            elapsed = time.time() - started

            results.append(
                (
                    symbol,
                    token,
                    "PASS",
                    price_impact,
                    elapsed,
                )
            )

            print(
                f"PASS | "
                f"impact={price_impact:.4f}% | "
                f"SOL={sol_amount:.9f} | "
                f"bytes={len(raw)} | "
                f"instructions={len(transaction.message.instructions)} | "
                f"{elapsed:.2f}s"
            )

        except JupiterError as exc:

            elapsed = time.time() - started

            results.append(
                (
                    symbol,
                    token,
                    "JUPITER_ERROR",
                    None,
                    elapsed,
                )
            )

            print(
                f"JUPITER ERROR | {exc}"
            )

        except Exception as exc:

            elapsed = time.time() - started

            results.append(
                (
                    symbol,
                    token,
                    "ERROR",
                    None,
                    elapsed,
                )
            )

            print(
                f"ERROR | {type(exc).__name__}: {exc}"
            )

    print()
    print("=" * 90)
    print("PREFLIGHT SUMMARY")
    print("=" * 90)

    counts = {}

    for row in results:
        status = row[2]
        counts[status] = counts.get(status, 0) + 1

    for status, count in sorted(
        counts.items()
    ):
        print(
            f"{status:<20}: {count}"
        )

    impacts = [
        row[3]
        for row in results
        if row[3] is not None
    ]

    if impacts:

        print()
        print(
            f"Price impact min : {min(impacts):.4f}%"
        )

        print(
            f"Price impact max : {max(impacts):.4f}%"
        )

        print(
            f"Price impact avg : "
            f"{sum(impacts) / len(impacts):.4f}%"
        )

    print()
    print("Funds moved : $0.00")
    print("Signing     : NO")
    print("Submission  : NO")
    print("=" * 90)


if __name__ == "__main__":
    main()
