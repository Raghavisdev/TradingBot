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


class Strategy_S6_Moonshot_Ladder(BaseLabStrategy):
    """
    S6: S6_Moonshot_Ladder (version 1.0)
    Phase 4 Paper Lab Strategy.

    Objective:
        Capture large crypto runners (2x, 5x, 10x, 100x+) while progressively realizing profit and retaining a 30% moonbag.

    Entry:
        - final_score >= 65.0
        - Multi-factor momentum & market health confirmation on available signal/snapshot fields
        - Capital-Aware Position Sizing:
            Base size = 1.0% of S6 current total equity ($500 starting equity -> $5.00).
            Drawdown tier scaling (relative to peak equity):
                >= 95% of peak equity  -> 1.00%
                90% - 95% of peak      -> 0.75%
                80% - 90% of peak      -> 0.50%
                < 80% of peak          -> 0.25%
        - Portfolio limits:
            Max 8 simultaneous S6 positions.
            Max 15% total deployed capital limit.

    Profit Ladder (relative to original position):
        - At +20%:   sell 20% original
        - At +50%:   sell 10% original
        - At +100%:  sell 10% original
        - At +200%:  sell 10% original
        - At +500%:  sell 10% original
        - At +1000%: sell 10% original
        - Remaining 30% original retained as permanent moonbag runner.

    Risk Management:
        - Initial hard stop: -20.0%
        - Breakeven protection after +20% return.
        - Dynamic trailing stop distances based on peak return:
            +20% to +50%:   15%
            +50% to +100%:  20%
            +100% to +300%: 25%
            +300% to +1000%: 30%
            > +1000%:        35%
        - Stop level is unloosened (monotonically non-decreasing stop threshold).
    """

    strategy_id      = "S6_Moonshot_Ladder"
    strategy_version = "1.0"
    moonbag_pct      = 30.0
    initial_cash     = 500.0
    max_open         = 8

    ladder_levels = [
        (20.0, 20.0),
        (50.0, 10.0),
        (100.0, 10.0),
        (200.0, 10.0),
        (500.0, 10.0),
        (1000.0, 10.0),
    ]

    def compute_entry_quality(self, signal) -> float:
        """
        Computes weighted Entry Quality Score Q in [0.0, 1.0].
        Treats features as weighted evidence rather than rigid gates.
        """
        # 1. GT stars (1-3 scale)
        gt = float(signal.get("gt_score") or 2.0)
        q_gt = 1.0 if gt >= 3 else (0.5 if gt >= 2 else 0.0)

        # 2. Liquidity ($)
        liq = float(signal.get("liquidity") or 0.0)
        q_liq = 1.0 if liq >= 10000 else (0.5 if liq >= 1000 else (0.2 if liq > 0 else 0.5))

        # 3. Buy/Sell Ratio
        buys = int(signal.get("buys") or signal.get("buys_5m") or 0)
        sells = int(signal.get("sells") or signal.get("sells_5m") or 0)
        bs_ratio = (buys / sells) if sells > 0 else (float(buys) if buys > 0 else 1.0)
        q_bs = 1.0 if bs_ratio >= 1.5 else (0.8 if bs_ratio >= 1.2 else (0.5 if bs_ratio >= 0.8 else 0.2))

        # 4. Effective Entry Market Cap ($)
        mc = float(signal.get("signal_market_cap") or signal.get("snap_mc") or 35000.0)
        q_mc = 1.0 if 30000 <= mc <= 50000 else (0.6 if (20000 <= mc < 30000 or 50000 < mc <= 100000) else 0.3)

        # 5. Final Score (0-100)
        fs = float(signal.get("final_score") or 60.0)
        q_fs = 1.0 if fs >= 70 else (0.8 if fs >= 65 else (0.6 if fs >= 60 else 0.4))

        # Weighted Quality Score Q
        Q = 0.20 * q_gt + 0.25 * q_liq + 0.25 * q_bs + 0.15 * q_mc + 0.15 * q_fs
        return min(max(Q, 0.0), 1.0)

    def evaluate_entry(self, signal, portfolio) -> float:
        sig_id = signal.get("signal_id")
        if portfolio.has_traded_signal(sig_id):
            return 0.0

        if signal.get("valid") is False:
            return 0.0

        # Calculate Quality Score Q
        Q = self.compute_entry_quality(signal)

        # Base sizing tiers relative to $500 equity:
        # Q < 0.35 -> $2.00 (0.4%)
        # 0.35 <= Q < 0.60 -> $5.00 (1.0%)
        # 0.60 <= Q < 0.80 -> $9.00 (1.8%)
        # Q >= 0.80 -> $14.00 (2.8%)
        if Q < 0.35:
            size_pct = 0.0040
        elif Q < 0.60:
            size_pct = 0.0100
        elif Q < 0.80:
            size_pct = 0.0180
        else:
            size_pct = 0.0280

        total_eq = portfolio.total_equity
        if total_eq <= 0:
            return 0.0

        peak_eq = max(getattr(portfolio, "initial_cash", 500.0), getattr(portfolio, "_peak_equity", total_eq))
        equity_ratio = total_eq / peak_eq if peak_eq > 0 else 1.0

        if equity_ratio >= 0.95:
            dd_factor = 1.00
        elif equity_ratio >= 0.90:
            dd_factor = 0.75
        elif equity_ratio >= 0.80:
            dd_factor = 0.50
        else:
            dd_factor = 0.25

        amount = total_eq * size_pct * dd_factor

        # Minimum exploratory allocation is $2.00 at baseline $500 equity
        if amount < 2.0 and Q >= 0.1 and total_eq >= 100.0:
            amount = 2.0

        # Enforce portfolio limits: max 8 positions, max 15% total deployed capital limit
        can_open = portfolio.can_open_capital_aware(amount, max_deployed_pct=0.15) if hasattr(portfolio, "can_open_capital_aware") else portfolio.can_open(amount)
        if not can_open:
            return 0.0

        return amount

    def evaluate_exit(self, snapshot, position) -> tuple:
        """
        Returns exit action:
            ('HOLD', 0, '')
            ('SELL_ALL', 100, reason)
            ('SELL_PCT_LADDER', crossed_levels, reason)
        """
        current_pnl = round(position.pnl_pct, 6)
        peak_pnl    = round(position.highest_pnl_pct, 6)

        # 1. HARD STOP LOSS (-20.0%) if peak never reached breakeven (+20%)
        if current_pnl <= -20.0 and peak_pnl < 20.0:
            return ("SELL_ALL", 100, "Hard Stop Loss -20.0%")

        # 2. PROFIT LADDER LEVEL EVALUATION
        crossed = []
        for target_pct, orig_sell_pct in self.ladder_levels:
            if target_pct in position.fired_ladder_levels:
                continue
            if current_pnl >= target_pct - 1e-5:
                crossed.append((target_pct, orig_sell_pct))

        if crossed:
            return ("SELL_PCT_LADDER", crossed, f"Profit Target +{crossed[0][0]:g}%")

        # 3. DYNAMIC TRAILING STOP & BREAKEVEN PROTECTION (after +20% peak)
        if peak_pnl >= 20.0:
            if peak_pnl < 50.0:
                dist = 15.0
            elif peak_pnl < 100.0:
                dist = 20.0
            elif peak_pnl < 300.0:
                dist = 25.0
            elif peak_pnl < 1000.0:
                dist = 30.0
            else:
                dist = 35.0

            breakeven_stop = 0.0
            candidate_stop = max(breakeven_stop, peak_pnl - dist)

            effective_stop = max(getattr(position, "highest_stop_pnl_pct", -20.0), candidate_stop)
            position.highest_stop_pnl_pct = effective_stop

            if current_pnl <= effective_stop:
                return ("SELL_ALL", 100,
                        f"Trailing Stop (peak={peak_pnl:.1f}%, now={current_pnl:.1f}%, stop={effective_stop:.1f}%)")

        return ("HOLD", 0, "")


# Legacy / Experimental Moonbag Strategy definitions
class Strategy_S7(BaseLabStrategy):
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
    Default returns S1 - S6 (S6_Moonshot_Ladder added alongside S1-S5).
    If include_moonbag=True, returns S1 - S8 including experimental Moonbag strategies S7, S8.
    """
    strats = [
        Strategy_S1(),
        Strategy_S2(),
        Strategy_S3(),
        Strategy_S4(),
        Strategy_S5(),
        Strategy_S6_Moonshot_Ladder(),
    ]
    if include_moonbag:
        strats.extend([
            Strategy_S7(),
            Strategy_S8(),
        ])
    return strats
