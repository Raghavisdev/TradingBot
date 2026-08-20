import os
import time
import requests


SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL",
    "https://api.mainnet-beta.solana.com",
)

LAMPORTS_PER_SOL = 1_000_000_000

SOL_PRICE_CACHE_TTL = float(
    os.getenv(
        "LIVE_SOL_PRICE_CACHE_TTL",
        "10.0",
    )
)

SOL_RESERVE = float(
    os.getenv(
        "LIVE_SOL_RESERVE",
        "0.01",
    )
)


class LiveWalletError(Exception):
    pass


class LiveWallet:

    def __init__(self, public_key):

        if not public_key:
            raise LiveWalletError(
                "Wallet public key is required"
            )

        self.public_key = str(public_key)

        # Short-lived price cache.
        # Prevents repeated Jupiter price requests during
        # one execution cycle while keeping the conversion fresh.
        self._sol_price_usd = None
        self._sol_price_timestamp = 0.0

    # =========================================================
    # SOLANA RPC
    # =========================================================

    def _rpc(self, method, params):

        try:

            response = requests.post(
                SOLANA_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params,
                },
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

        except requests.RequestException as exc:

            raise LiveWalletError(
                f"Solana RPC request failed: {exc}"
            ) from exc

        except ValueError as exc:

            raise LiveWalletError(
                "Solana RPC returned invalid JSON"
            ) from exc

        if "error" in data:

            raise LiveWalletError(
                f"Solana RPC error: {data['error']}"
            )

        if "result" not in data:

            raise LiveWalletError(
                "Solana RPC returned no result"
            )

        return data["result"]

    # =========================================================
    # SOL BALANCE
    # =========================================================

    def get_sol_balance(self):

        result = self._rpc(
            "getBalance",
            [
                self.public_key,
                {
                    "commitment": "confirmed"
                },
            ],
        )

        lamports = int(
            result["value"]
        )

        return (
            lamports /
            LAMPORTS_PER_SOL
        )

    # =========================================================
    # SOL/USD PRICE
    # =========================================================

    def get_sol_usd_price(self):

        now = time.time()

        # -----------------------------------------------------
        # CACHE
        # -----------------------------------------------------

        if (
            self._sol_price_usd is not None
            and (
                now - self._sol_price_timestamp
            ) < SOL_PRICE_CACHE_TTL
        ):
            return self._sol_price_usd

        # -----------------------------------------------------
        # FRESH PRICE
        # -----------------------------------------------------

        try:

            response = requests.get(
                "https://api.jup.ag/price/v3",
                params={
                    "ids": (
                        "So11111111111111111111111111111111111111112"
                    )
                },
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

        except requests.RequestException as exc:

            raise LiveWalletError(
                f"Jupiter SOL price request failed: {exc}"
            ) from exc

        except ValueError as exc:

            raise LiveWalletError(
                "Jupiter SOL price returned invalid JSON"
            ) from exc

        sol_data = data.get(
            "So11111111111111111111111111111111111111112"
        )

        if not sol_data:

            raise LiveWalletError(
                "Jupiter returned no SOL price"
            )

        try:
            price = float(
                sol_data["usdPrice"]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:

            raise LiveWalletError(
                "Jupiter returned an invalid SOL price"
            ) from exc

        if price <= 0:

            raise LiveWalletError(
                "Invalid SOL/USD price"
            )

        # -----------------------------------------------------
        # UPDATE CACHE
        # -----------------------------------------------------

        self._sol_price_usd = price
        self._sol_price_timestamp = now

        return price

    # =========================================================
    # USD -> SOL LAMPORTS
    # =========================================================

    def usd_to_lamports(self, amount_usd):

        amount_usd = float(amount_usd)

        if amount_usd <= 0:
            raise LiveWalletError(
                "USD amount must be greater than zero"
            )

        sol_price = self.get_sol_usd_price()

        sol_amount = (
            amount_usd /
            sol_price
        )

        lamports = int(
            sol_amount *
            LAMPORTS_PER_SOL
        )

        if lamports <= 0:
            raise LiveWalletError(
                "USD amount converts to zero lamports"
            )

        return lamports

    # =========================================================
    # TOTAL WALLET VALUE
    # =========================================================

    def get_wallet_value_usd(self):

        sol_balance = (
            self.get_sol_balance()
        )

        sol_price = (
            self.get_sol_usd_price()
        )

        return (
            sol_balance *
            sol_price
        )

    # =========================================================
    # AVAILABLE TRADING CAPITAL
    # =========================================================

    def get_available_capital_usd(self):

        sol_balance = (
            self.get_sol_balance()
        )

        tradable_sol = max(
            0.0,
            sol_balance - SOL_RESERVE,
        )

        sol_price = (
            self.get_sol_usd_price()
        )

        return (
            tradable_sol *
            sol_price
        )


# =============================================================
# READ-ONLY TEST
# =============================================================

if __name__ == "__main__":

    import sys

    if len(sys.argv) != 2:

        print(
            "Usage:"
        )

        print(
            "python3 -m trading.live_wallet "
            "<WALLET_PUBLIC_KEY>"
        )

        sys.exit(1)

    wallet = LiveWallet(
        sys.argv[1]
    )

    try:

        sol = wallet.get_sol_balance()

        price = wallet.get_sol_usd_price()

        value = wallet.get_wallet_value_usd()

        available = wallet.get_available_capital_usd()

        print("=" * 70)
        print("LIVE WALLET READ-ONLY TEST")
        print("=" * 70)

        print(
            "Wallet       :",
            wallet.public_key
        )

        print(
            "SOL balance  :",
            f"{sol:.9f} SOL"
        )

        print(
            "SOL price    :",
            f"${price:.2f}"
        )

        print(
            "Wallet value :",
            f"${value:.2f}"
        )

        print(
            "SOL reserve  :",
            f"{SOL_RESERVE:.4f} SOL"
        )

        print(
            "Available    :",
            f"${available:.2f}"
        )

        print()
        print(
            "READ-ONLY:"
        )
        print(
            "No signing."
        )
        print(
            "No swap."
        )
        print(
            "No funds moved."
        )

    except Exception as exc:

        print(
            "WALLET ERROR:",
            exc
        )

        sys.exit(1)
