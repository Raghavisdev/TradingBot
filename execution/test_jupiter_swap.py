import base64
import requests

from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction


JUPITER_URL = "https://api.jup.ag/swap/v1"

SOL_MINT = "So11111111111111111111111111111111111111112"

TOKEN_MINT = "EP5k7WwMYXPNzkAEc8wtUm2imx3sg3NDRNxyt9Ktpump"

# Temporary public key generated only for transaction construction.
# It has NO funds and NO private key is used.
TEST_PUBLIC_KEY = "A7riBTVS63XszAH6dyMKrQoatMPhjZcs92Tz1PNxSCCs"

AMOUNT = 10_000_000       # 0.01 SOL
SLIPPAGE_BPS = 100        # 1%


def main():

    print("=" * 70)
    print("JUPITER UNSIGNED SWAP TEST")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. GET QUOTE
    # ---------------------------------------------------------

    quote_params = {
        "inputMint": SOL_MINT,
        "outputMint": TOKEN_MINT,
        "amount": str(AMOUNT),
        "slippageBps": str(SLIPPAGE_BPS),
    }

    print("\n[1] Requesting quote...")

    response = requests.get(
        f"{JUPITER_URL}/quote",
        params=quote_params,
        timeout=15,
    )

    response.raise_for_status()

    quote = response.json()

    print("    Quote: OK")
    print("    Input :", quote["inAmount"])
    print("    Output:", quote["outAmount"])
    print(
        "    Price impact:",
        quote.get("priceImpactPct"),
        "%"
    )

    # ---------------------------------------------------------
    # 2. REQUEST UNSIGNED SWAP TRANSACTION
    # ---------------------------------------------------------

    print("\n[2] Requesting unsigned swap transaction...")

    payload = {
        "quoteResponse": quote,
        "userPublicKey": TEST_PUBLIC_KEY,
        "wrapAndUnwrapSol": True,
    }

    response = requests.post(
        f"{JUPITER_URL}/swap",
        json=payload,
        timeout=15,
    )

    print("    HTTP:", response.status_code)

    if response.status_code != 200:
        print(response.text[:2000])
        raise RuntimeError(
            "Jupiter failed to construct swap transaction"
        )

    swap = response.json()

    if not swap.get("swapTransaction"):
        raise RuntimeError(
            "Jupiter returned no swapTransaction"
        )

    encoded = swap["swapTransaction"]

    print("    Swap transaction: RECEIVED")
    print("    Base64 length:", len(encoded))

    # ---------------------------------------------------------
    # 3. DECODE TRANSACTION
    # ---------------------------------------------------------

    print("\n[3] Decoding VersionedTransaction...")

    raw_transaction = base64.b64decode(encoded)

    transaction = VersionedTransaction.from_bytes(
        raw_transaction
    )

    print("    Transaction decode: OK")
    print("    Raw bytes:", len(raw_transaction))

    # ---------------------------------------------------------
    # 4. INSPECT
    # ---------------------------------------------------------

    message = transaction.message

    print("\n[4] TRANSACTION INSPECTION")
    print("-" * 70)

    print(
        "Recent blockhash:",
        message.recent_blockhash
    )

    print(
        "Static account keys:",
        len(message.account_keys)
    )

    print(
        "Instructions:",
        len(message.instructions)
    )

    # ---------------------------------------------------------
    # 5. IMPORTANT SAFETY STOP
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("DRY-RUN SUCCESS")
    print("=" * 70)

    print("""
Jupiter successfully constructed an unsigned swap transaction.

NO PRIVATE KEY USED.
NO SIGNATURE CREATED.
NO TRANSACTION SUBMITTED.
NO FUNDS MOVED.

The transaction is now ready for a future signing layer.
""")

    print("STOPPING HERE.")


if __name__ == "__main__":
    main()
