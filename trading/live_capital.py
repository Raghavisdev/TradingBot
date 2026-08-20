from dataclasses import dataclass

from trading.live_wallet import LiveWallet


@dataclass
class LiveCapital:
    wallet_value_usd: float
    available_capital_usd: float


class LiveCapitalManager:

    def __init__(self, wallet_public_key):
        self.wallet = LiveWallet(wallet_public_key)

    def get_capital(self):
        wallet_value = self.wallet.get_wallet_value_usd()
        available = self.wallet.get_available_capital_usd()

        return LiveCapital(
            wallet_value_usd=wallet_value,
            available_capital_usd=available,
        )

    def get_position_size_cap(self, percentage=0.10):
        capital = self.get_capital()

        return (
            capital.available_capital_usd
            * float(percentage)
        )


if __name__ == "__main__":

    import sys

    if len(sys.argv) != 2:
        print(
            "Usage: python3 -m trading.live_capital "
            "<WALLET_PUBLIC_KEY>"
        )
        raise SystemExit(1)

    manager = LiveCapitalManager(sys.argv[1])
    capital = manager.get_capital()

    print("=" * 70)
    print("LIVE CAPITAL READ-ONLY TEST")
    print("=" * 70)

    print(
        f"Wallet value       : "
        f"${capital.wallet_value_usd:.2f}"
    )

    print(
        f"Available capital  : "
        f"${capital.available_capital_usd:.2f}"
    )

    print(
        f"10% capital cap    : "
        f"${manager.get_position_size_cap(0.10):.2f}"
    )

    print()
    print("READ-ONLY: no signing, no swap, no funds moved.")
