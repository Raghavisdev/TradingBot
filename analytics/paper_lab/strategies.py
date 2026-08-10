"""
analytics/paper_lab/strategies.py
-----------------------------------
Initial Paper Lab Strategy Definitions (S1 - S5).

Each strategy object provides:
  - strategy_id
  - strategy_version
  - evaluate_entry(signal_dict, portfolio) -> float (invested amount, 0 if no entry)
  - evaluate_exit(snapshot_dict, position) -> tuple (action, pct, reason)
"""


class BaseLabStrategy:
    """Base class for Paper Lab strategies."""

    strategy_id      = "BASE"
    strategy_version = "1.0"

    def evaluate_entry(self, signal, portfolio) -> float:
        """
        Returns investment amount in USD if entry conditions met, else 0.0.
        Checks portfolio.has_traded_signal(signal_id) before evaluating.
        """
        raise NotImplementedError

    def evaluate_exit(self, snapshot, position) -> tuple:
        """
        Returns (action, pct_to_sell, reason):
            'HOLD'     - do nothing
            'SELL_PCT' - sell pct_to_sell % of remaining position
            'SELL_ALL' - close full position
        """
        raise NotImplementedError


# ============================================================
# PROFIT TAKING & EXIT LOGIC HELPERS
# ============================================================

def _evaluate_composite_exit(position, stop_loss_pct=-20.0, levels=None,
                             trailing_dist=20.0, trailing_act=25.0):
    """
    Standard composite exit evaluator:
      1. Hard stop loss
      2. Multi-level partial profit taking
      3. Trailing stop protection
    """
    # 1. Hard Stop Loss
    if position.pnl_pct <= stop_loss_pct:
        return ("SELL_ALL", 100, f"Hard Stop Loss {stop_loss_pct}%")

    # 2. Multi-level Partial Profit Taking
    if levels:
        fired_count = len(position.partial_sells)
        for i, (target_pct, sell_pct) in enumerate(levels):
            if i < fired_count:
                continue  # level already fired
            if position.pnl_pct >= target_pct:
                return ("SELL_PCT", sell_pct, f"Profit Target +{target_pct}%")
            break

    # 3. Trailing Stop Protection
    if position.highest_pnl_pct >= trailing_act:
        drawdown = position.highest_pnl_pct - position.pnl_pct
        if drawdown >= trailing_dist:
            return ("SELL_ALL", 100,
                    f"Trailing Stop (peak={position.highest_pnl_pct:.1f}%, now={position.pnl_pct:.1f}%)")

    return ("HOLD", 0, "")


# ============================================================
# STRATEGY DEFINITIONS S1 - S5
# ============================================================

class Strategy_S1(BaseLabStrategy):
    """
    S1: A_Imm_$25_P1_SL-20 (version 1.0)
    Entry: Immediate, fixed $25
    Exit: P1 (+25%->25%, +50%->25%, +100%->25%), trailing after +25%, hard stop -20%
    """
    strategy_id      = "A_Imm_$25_P1_SL-20"
    strategy_version = "1.0"

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0
        amount = 25.0
        return amount if portfolio.can_open(amount) else 0.0

    def evaluate_exit(self, snapshot, position) -> tuple:
        levels = [(25, 25), (50, 25), (100, 25)]
        return _evaluate_composite_exit(
            position, stop_loss_pct=-20.0, levels=levels,
            trailing_dist=20.0, trailing_act=25.0
        )


class Strategy_S2(BaseLabStrategy):
    """
    S2: B_Score60_$10_P1_SL-20 (version 1.0)
    Entry: final_score >= 60, fixed $10
    Exit: P1, trailing after +25%, hard stop -20%
    """
    strategy_id      = "B_Score60_$10_P1_SL-20"
    strategy_version = "1.0"

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0
        score = float(signal.get("final_score") or 0.0)
        if score < 60.0:
            return 0.0
        amount = 10.0
        return amount if portfolio.can_open(amount) else 0.0

    def evaluate_exit(self, snapshot, position) -> tuple:
        levels = [(25, 25), (50, 25), (100, 25)]
        return _evaluate_composite_exit(
            position, stop_loss_pct=-20.0, levels=levels,
            trailing_dist=20.0, trailing_act=25.0
        )


class Strategy_S3(BaseLabStrategy):
    """
    S3: B_Score65_$10_P1_SL-20 (version 1.0)
    Entry: final_score >= 65, fixed $10
    Exit: P1, trailing after +25%, hard stop -20%
    """
    strategy_id      = "B_Score65_$10_P1_SL-20"
    strategy_version = "1.0"

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0
        score = float(signal.get("final_score") or 0.0)
        if score < 65.0:
            return 0.0
        amount = 10.0
        return amount if portfolio.can_open(amount) else 0.0

    def evaluate_exit(self, snapshot, position) -> tuple:
        levels = [(25, 25), (50, 25), (100, 25)]
        return _evaluate_composite_exit(
            position, stop_loss_pct=-20.0, levels=levels,
            trailing_dist=20.0, trailing_act=25.0
        )


class Strategy_S4(BaseLabStrategy):
    """
    S4: A_Imm_$10_P2_SL-20 (version 1.0)
    Entry: Immediate, fixed $10
    Exit: P2 (+50%->30%, +100%->30%, +200%->20%), trailing after +25%, hard stop -20%
    """
    strategy_id      = "A_Imm_$10_P2_SL-20"
    strategy_version = "1.0"

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0
        amount = 10.0
        return amount if portfolio.can_open(amount) else 0.0

    def evaluate_exit(self, snapshot, position) -> tuple:
        levels = [(50, 30), (100, 30), (200, 20)]
        return _evaluate_composite_exit(
            position, stop_loss_pct=-20.0, levels=levels,
            trailing_dist=20.0, trailing_act=25.0
        )


class Strategy_S5(BaseLabStrategy):
    """
    S5: A_Imm_Pct20_P1_SL-20 (version 1.0)
    Entry: Immediate, 20% of strategy available cash
    Exit: P1, trailing after +25%, hard stop -20%
    """
    strategy_id      = "A_Imm_Pct20_P1_SL-20"
    strategy_version = "1.0"

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0
        amount = portfolio.cash * 0.20
        return amount if portfolio.can_open(amount) else 0.0

    def evaluate_exit(self, snapshot, position) -> tuple:
        levels = [(25, 25), (50, 25), (100, 25)]
        return _evaluate_composite_exit(
            position, stop_loss_pct=-20.0, levels=levels,
            trailing_dist=20.0, trailing_act=25.0
        )


def _evaluate_composite_exit_moonbag(position, stop_loss_pct=-20.0, levels=None,
                                     trailing_dist=20.0, trailing_act=25.0,
                                     moonbag_pct=5.0):
    """
    Moonbag composite exit evaluator:
      - If remaining_pct <= moonbag_pct + 0.01:
          Managed portion is closed, return ('HOLD', 0, '') to keep moonbag open.
      - Standard rules (StopLoss, ProfitTaking, TrailingStop):
          If action == 'SELL_ALL': convert to SELL_PCT so remaining_pct after sell equals moonbag_pct.
          If action == 'SELL_PCT': cap so remaining_pct after sell does not drop below moonbag_pct.
    """
    remaining = getattr(position, "remaining_pct", 100.0)
    if remaining <= moonbag_pct + 0.01:
        return ("HOLD", 0, "")

    action, pct, reason = _evaluate_composite_exit(
        position, stop_loss_pct=stop_loss_pct, levels=levels,
        trailing_dist=trailing_dist, trailing_act=trailing_act
    )

    if action == "HOLD":
        return ("HOLD", 0, "")

    if action == "SELL_ALL":
        sell_frac = (remaining - moonbag_pct) / remaining
        sell_pct  = sell_frac * 100.0
        return ("SELL_PCT", sell_pct, f"{reason} (Moonbag {moonbag_pct}% retained)")

    if action == "SELL_PCT" and pct > 0:
        pct_remaining_after = remaining * (1.0 - pct / 100.0)
        if pct_remaining_after < moonbag_pct:
            max_sell_pct = (remaining - moonbag_pct) / remaining * 100.0
            return ("SELL_PCT", max_sell_pct, f"{reason} (Capped at Moonbag {moonbag_pct}%)")
        return (action, pct, reason)

    return ("HOLD", 0, "")


class Strategy_S6(BaseLabStrategy):
    """
    S6: A_Imm_$25_P1_SL-20_MB5 (version 1.0)
    Entry: Immediate, fixed $25
    Exit: P1 (+25%->25%, +50%->25%, +100%->25%), trailing after +25%, hard stop -20%
    Moonbag: 5% of original investment retained as permanent runner
    """
    strategy_id      = "A_Imm_$25_P1_SL-20_MB5"
    strategy_version = "1.0"
    moonbag_pct      = 5.0

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0
        amount = 25.0
        return amount if portfolio.can_open(amount) else 0.0

    def evaluate_exit(self, snapshot, position) -> tuple:
        levels = [(25, 25), (50, 25), (100, 25)]
        return _evaluate_composite_exit_moonbag(
            position, stop_loss_pct=-20.0, levels=levels,
            trailing_dist=20.0, trailing_act=25.0, moonbag_pct=5.0
        )


class Strategy_S7(BaseLabStrategy):
    """
    S7: A_Imm_$25_P1_SL-20_MB10 (version 1.0)
    Entry: Immediate, fixed $25
    Exit: P1, trailing after +25%, hard stop -20%
    Moonbag: 10% of original investment retained as permanent runner
    """
    strategy_id      = "A_Imm_$25_P1_SL-20_MB10"
    strategy_version = "1.0"
    moonbag_pct      = 10.0

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0
        amount = 25.0
        return amount if portfolio.can_open(amount) else 0.0

    def evaluate_exit(self, snapshot, position) -> tuple:
        levels = [(25, 25), (50, 25), (100, 25)]
        return _evaluate_composite_exit_moonbag(
            position, stop_loss_pct=-20.0, levels=levels,
            trailing_dist=20.0, trailing_act=25.0, moonbag_pct=10.0
        )


class Strategy_S8(BaseLabStrategy):
    """
    S8: A_Imm_$25_P1_SL-20_MB20 (version 1.0)
    Entry: Immediate, fixed $25
    Exit: P1, trailing after +25%, hard stop -20%
    Moonbag: 20% of original investment retained as permanent runner
    """
    strategy_id      = "A_Imm_$25_P1_SL-20_MB20"
    strategy_version = "1.0"
    moonbag_pct      = 20.0

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0
        amount = 25.0
        return amount if portfolio.can_open(amount) else 0.0

    def evaluate_exit(self, snapshot, position) -> tuple:
        levels = [(25, 25), (50, 25), (100, 25)]
        return _evaluate_composite_exit_moonbag(
            position, stop_loss_pct=-20.0, levels=levels,
            trailing_dist=20.0, trailing_act=25.0, moonbag_pct=20.0
        )


def get_initial_strategies(include_moonbag: bool = False):
    """
    Returns list of Paper Lab strategy instances.
    Default (include_moonbag=False) returns S1 - S5 for live forward testing.
    If include_moonbag=True, returns S1 - S8 including experimental Moonbag strategies.
    """
    strats = [
        Strategy_S1(),
        Strategy_S2(),
        Strategy_S3(),
        Strategy_S4(),
        Strategy_S5(),
    ]
    if include_moonbag:
        strats.extend([
            Strategy_S6(),
            Strategy_S7(),
            Strategy_S8(),
        ])
    return strats
