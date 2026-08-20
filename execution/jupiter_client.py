import requests
import random
import time


JUPITER_BASE_URL = "https://api.jup.ag/swap/v1"

SOL_MINT = "So11111111111111111111111111111111111111112"

DEFAULT_SLIPPAGE_BPS = 100
DEFAULT_TIMEOUT = 15

# Jupiter/API gateway protection.
# Keep retries bounded so a broken endpoint or invalid token
# cannot stall the trading loop indefinitely.
DEFAULT_MAX_RETRIES = 4
DEFAULT_RETRY_BASE_DELAY = 2.0
DEFAULT_RETRY_MAX_DELAY = 12.0


class JupiterError(Exception):
    pass


class JupiterClient:

    def __init__(
        self,
        slippage_bps=DEFAULT_SLIPPAGE_BPS,
        timeout=DEFAULT_TIMEOUT,
        max_retries=DEFAULT_MAX_RETRIES,
        retry_base_delay=DEFAULT_RETRY_BASE_DELAY,
        retry_max_delay=DEFAULT_RETRY_MAX_DELAY,
    ):
        self.slippage_bps = int(slippage_bps)
        self.timeout = int(timeout)

        self.max_retries = max(
            0,
            int(max_retries),
        )

        self.retry_base_delay = max(
            0.1,
            float(retry_base_delay),
        )

        self.retry_max_delay = max(
            self.retry_base_delay,
            float(retry_max_delay),
        )

    # =========================================================
    # QUOTE
    # =========================================================

    def get_quote(
        self,
        input_mint,
        output_mint,
        amount,
        slippage_bps=None,
    ):
        amount = int(amount)

        if amount <= 0:
            raise JupiterError("Amount must be greater than zero")

        params = {
            "inputMint": str(input_mint),
            "outputMint": str(output_mint),
            "amount": str(amount),
            "slippageBps": str(
                self.slippage_bps
                if slippage_bps is None
                else int(slippage_bps)
            ),
        }

        url = f"{JUPITER_BASE_URL}/quote"

        # -----------------------------------------------------
        # BOUNDED RETRY / BACKOFF
        #
        # 429 = temporary API throttling.
        # 5xx = temporary upstream failure.
        #
        # Client errors such as 400 are returned immediately
        # because retrying an invalid token/request is pointless.
        # -----------------------------------------------------

        response = None

        for attempt in range(
            self.max_retries + 1
        ):

            try:

                response = requests.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                )

            except requests.RequestException as exc:

                if attempt >= self.max_retries:

                    raise JupiterError(
                        f"Jupiter quote request failed "
                        f"after {attempt + 1} attempts: {exc}"
                    ) from exc

                delay = min(
                    self.retry_max_delay,
                    self.retry_base_delay
                    * (2 ** attempt),
                )

                delay += random.uniform(
                    0.0,
                    min(0.5, delay * 0.25),
                )

                print(
                    f"[JUPITER] Quote request failed; "
                    f"retrying in {delay:.2f}s "
                    f"(attempt {attempt + 1}/"
                    f"{self.max_retries})"
                )

                time.sleep(delay)

                continue

            # -------------------------------------------------
            # SUCCESS
            # -------------------------------------------------

            if response.status_code == 200:
                break

            # -------------------------------------------------
            # TEMPORARY THROTTLING / SERVER FAILURE
            # -------------------------------------------------

            if (
                response.status_code == 429
                or response.status_code >= 500
            ):

                if attempt >= self.max_retries:

                    raise JupiterError(
                        f"Jupiter quote HTTP "
                        f"{response.status_code} "
                        f"after {attempt + 1} attempts: "
                        f"{response.text[:500]}"
                    )

                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:
                    delay = float(
                        retry_after
                    )
                except (
                    TypeError,
                    ValueError,
                ):

                    delay = min(
                        self.retry_max_delay,
                        self.retry_base_delay
                        * (2 ** attempt),
                    )

                    delay += random.uniform(
                        0.0,
                        min(0.5, delay * 0.25),
                    )

                delay = min(
                    self.retry_max_delay,
                    max(0.1, delay),
                )

                print(
                    f"[JUPITER] HTTP "
                    f"{response.status_code}; "
                    f"retrying in {delay:.2f}s "
                    f"(attempt {attempt + 1}/"
                    f"{self.max_retries})"
                )

                time.sleep(delay)

                continue

            # -------------------------------------------------
            # PERMANENT CLIENT ERROR
            # -------------------------------------------------

            raise JupiterError(
                f"Jupiter quote HTTP "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )

        if response is None:
            raise JupiterError(
                "Jupiter quote returned no response"
            )

        if response.status_code != 200:
            raise JupiterError(
                f"Jupiter quote HTTP "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise JupiterError(
                f"Invalid Jupiter JSON response: "
                f"{response.text[:500]}"
            ) from exc

        if not data.get("outAmount"):
            raise JupiterError(
                f"Jupiter returned no output amount: {data}"
            )

        return data

    # =========================================================
    # QUOTE VALIDATION
    # =========================================================

    def validate_quote(
        self,
        quote,
        max_price_impact_pct=2.0,
    ):
        if not isinstance(quote, dict):
            return False, "Quote is not a dictionary"

        if not quote.get("inputMint"):
            return False, "Missing inputMint"

        if not quote.get("outputMint"):
            return False, "Missing outputMint"

        in_amount = int(
            quote.get("inAmount", 0)
        )

        out_amount = int(
            quote.get("outAmount", 0)
        )

        if in_amount <= 0:
            return False, "Invalid input amount"

        if out_amount <= 0:
            return False, "Invalid output amount"

        routes = quote.get("routePlan")

        if not routes:
            return False, "No route returned"

        try:
            price_impact = float(
                quote.get("priceImpactPct", 0.0)
            )
        except (TypeError, ValueError):
            return False, "Invalid price impact"

        if price_impact > float(max_price_impact_pct):
            return (
                False,
                (
                    f"Price impact {price_impact:.4f}% "
                    f"exceeds maximum "
                    f"{float(max_price_impact_pct):.4f}%"
                ),
            )

        return True, "Quote accepted"

    # =========================================================
    # SWAP TRANSACTION
    #
    # IMPORTANT:
    # This requests a transaction from Jupiter.
    # It DOES NOT sign or submit it.
    # =========================================================

    def build_swap_transaction(
        self,
        quote,
        user_public_key,
        wrap_and_unwrap_sol=True,
    ):
        if not quote:
            raise JupiterError("Quote is empty")

        if not user_public_key:
            raise JupiterError(
                "user_public_key is required"
            )

        payload = {
            "quoteResponse": quote,
            "userPublicKey": str(user_public_key),
            "wrapAndUnwrapSol": bool(
                wrap_and_unwrap_sol
            ),
        }

        url = f"{JUPITER_BASE_URL}/swap"

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise JupiterError(
                f"Jupiter swap request failed: {exc}"
            ) from exc

        if response.status_code != 200:
            raise JupiterError(
                f"Jupiter swap HTTP "
                f"{response.status_code}: "
                f"{response.text[:1000]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise JupiterError(
                f"Invalid Jupiter swap JSON: "
                f"{response.text[:1000]}"
            ) from exc

        if not data.get("swapTransaction"):
            raise JupiterError(
                "Jupiter returned no swapTransaction"
            )

        return data


# =============================================================
# SIMPLE COMMAND-LINE TEST
# =============================================================

if __name__ == "__main__":

    import sys

    client = JupiterClient(
        slippage_bps=100
    )

    token = (
        sys.argv[1]
        if len(sys.argv) > 1
        else SOL_MINT
    )

    print("=" * 70)
    print("JUPITER CLIENT TEST")
    print("=" * 70)

    print("Input mint :", SOL_MINT)
    print("Output mint:", token)
    print("Amount     : 10,000,000 lamports")
    print("Slippage   : 100 bps")
    print()

    try:

        quote = client.get_quote(
            input_mint=SOL_MINT,
            output_mint=token,
            amount=10_000_000,
        )

        print("QUOTE OK")
        print("-" * 70)
        print("Input amount :", quote["inAmount"])
        print("Output amount:", quote["outAmount"])
        print(
            "Price impact:",
            quote.get("priceImpactPct"),
            "%"
        )

        valid, reason = client.validate_quote(
            quote,
            max_price_impact_pct=2.0,
        )

        print()
        print("VALIDATION:", valid)
        print("REASON:", reason)

    except JupiterError as exc:

        print()
        print("JUPITER ERROR:", exc)

        sys.exit(1)
