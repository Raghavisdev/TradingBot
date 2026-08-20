import os
from dataclasses import dataclass


@dataclass
class LiveRiskDecision:
    approved: bool
    reason: str


class LiveRiskManager:

    def __init__(self):

        # LIVE_TRADING authorizes real execution.
        # LIVE_PREFLIGHT allows the complete risk pipeline
        # to be evaluated without authorizing fund movement.
        self.enabled = os.getenv(
            "LIVE_TRADING",
            "False"
        ).lower() in (
            "true",
            "1",
            "yes"
        )

        self.preflight = os.getenv(
            "LIVE_PREFLIGHT",
            "False"
        ).lower() in (
            "true",
            "1",
            "yes"
        )

        self.max_trade_usd = float(
            os.getenv(
                "LIVE_MAX_TRADE_USD",
                "5.0"
            )
        )

        self.max_price_impact_pct = float(
            os.getenv(
                "LIVE_MAX_PRICE_IMPACT_PCT",
                "2.0"
            )
        )

        self.max_slippage_bps = int(
            os.getenv(
                "LIVE_MAX_SLIPPAGE_BPS",
                "100"
            )
        )

        self.max_open_positions = int(
            os.getenv(
                "LIVE_MAX_OPEN_POSITIONS",
                "3"
            )
        )

        self.min_liquidity_usd = float(
            os.getenv(
                "LIVE_MIN_LIQUIDITY_USD",
                "10000"
            )
        )

    def check_trade(
        self,
        amount_usd: float,
        liquidity_usd: float,
        price_impact_pct: float,
        open_positions: int,
    ) -> LiveRiskDecision:

        if not self.enabled and not self.preflight:
            return LiveRiskDecision(
                False,
                "LIVE_TRADING is disabled and LIVE_PREFLIGHT is disabled"
            )

        if amount_usd <= 0:
            return LiveRiskDecision(
                False,
                "Invalid trade amount"
            )

        if amount_usd > self.max_trade_usd:
            return LiveRiskDecision(
                False,
                f"Trade ${amount_usd:.2f} exceeds "
                f"max ${self.max_trade_usd:.2f}"
            )

        if liquidity_usd < self.min_liquidity_usd:
            return LiveRiskDecision(
                False,
                f"Liquidity ${liquidity_usd:.2f} below "
                f"minimum ${self.min_liquidity_usd:.2f}"
            )

        if price_impact_pct > self.max_price_impact_pct:
            return LiveRiskDecision(
                False,
                f"Price impact {price_impact_pct:.4f}% exceeds "
                f"maximum {self.max_price_impact_pct:.4f}%"
            )

        if open_positions >= self.max_open_positions:
            return LiveRiskDecision(
                False,
                f"Maximum open positions reached: "
                f"{open_positions}/{self.max_open_positions}"
            )

        return LiveRiskDecision(
            True,
            "Trade passed live risk checks"
        )


if __name__ == "__main__":

    risk = LiveRiskManager()

    print("=" * 70)
    print("LIVE RISK MANAGER TEST")
    print("=" * 70)

    print(
        "Live trading enabled :",
        risk.enabled
    )

    print(
        "Max trade            :",
        risk.max_trade_usd
    )

    print(
        "Max price impact     :",
        risk.max_price_impact_pct,
        "%"
    )

    print(
        "Max open positions   :",
        risk.max_open_positions
    )

    print(
        "Min liquidity        :",
        risk.min_liquidity_usd
    )

    result = risk.check_trade(
        amount_usd=3.0,
        liquidity_usd=50000,
        price_impact_pct=0.1,
        open_positions=0,
    )

    print()
    print(
        "APPROVED:",
        result.approved
    )

    print(
        "REASON  :",
        result.reason
    )
