"""
analytics/paper_lab/lab_engine.py
-----------------------------------
Real-Time Multi-Strategy Observer Engine for Paper Lab (Phase 3).

Orchestrates live forward paper trading across S1-S5.
Reuses existing snapshot stream — zero duplicated polling.
Encapsulates all logic so exceptions NEVER crash the main pipeline or trackers.
"""

import time
import traceback
from analytics.paper_lab.strategies import get_initial_strategies
from analytics.paper_lab.lab_portfolio import LabPortfolio, LabPosition
from analytics.paper_lab.persistence import PaperLabPersistence
from analytics.paper_lab.report import generate_paper_lab_reports


def _signal_to_dict(signal):
    """
    Safely converts a signal object (Coin instance, dict, or object with to_dict) into a dict.
    """
    if not signal:
        return {}
    if isinstance(signal, dict):
        return dict(signal)
    if hasattr(signal, "to_dict") and callable(getattr(signal, "to_dict")):
        return signal.to_dict()
    if hasattr(signal, "__dict__"):
        return vars(signal).copy()
    return {}


class PaperLabEngine:
    """
    Real-time observer engine for forward paper trading.
    """

    def __init__(self, db_path=None, initial_cash=100.0, include_moonbag=False):
        self.persistence    = PaperLabPersistence(db_path)
        self.initial_cash   = initial_cash

        self.strategies     = {}  # strategy_id -> strategy_instance
        self.portfolios     = {}  # strategy_id -> LabPortfolio instance
        self.signals_seen   = set()
        self.pending_signals = {} # signal_id -> signal_dict (signals waiting for 1st price snapshot)

        # Initialize strategies & portfolios
        for strat in get_initial_strategies(include_moonbag=include_moonbag):
            sid = strat.strategy_id
            self.strategies[sid] = strat
            self.portfolios[sid] = LabPortfolio(sid, initial_cash=initial_cash)

        # Recover historical traded signal_ids & open trades from DB
        self._recover_state()

    # ============================================================
    # RECOVERY ON STARTUP
    # ============================================================

    def _recover_state(self):
        """
        Restores traded_signal_ids and OPEN trades from DB on startup.
        """
        try:
            # 1. Restore traded_signal_ids for each strategy
            traded_map = self.persistence.load_traded_signal_ids()
            for sid, sig_set in traded_map.items():
                if sid in self.portfolios:
                    self.portfolios[sid].traded_signal_ids = sig_set

            # 2. Restore OPEN trades
            open_trades = self.persistence.load_open_trades()
            for r in open_trades:
                sid = r.get("strategy_id")
                if sid not in self.portfolios:
                    continue
                port = self.portfolios[sid]

                # Reconstruct position
                pos = LabPosition(
                    trade_id=r.get("trade_id"),
                    strategy_id=sid,
                    strategy_version=r.get("strategy_version", "1.0"),
                    signal_id=r.get("signal_id"),
                    symbol=r.get("symbol"),
                    contract=r.get("contract", ""),
                    entry_time=r.get("entry_time"),
                    entry_price=r.get("entry_price"),
                    entry_mc=r.get("entry_market_cap"),
                    invested=r.get("invested")
                )
                pos.remaining_pct = float(r.get("remaining_pct") or 100.0)
                pos.realized_pnl  = float(r.get("realized_pnl") or 0.0)
                pos.mfe           = float(r.get("mfe") or 0.0)
                pos.mae           = float(r.get("mae") or 0.0)

                # Subtract cash for recovered open position if not already accounted for
                port.cash -= pos.invested * (pos.remaining_pct / 100.0)
                port.open_positions.append(pos)
                port.traded_signal_ids.add(pos.signal_id)

            print(f"[PAPER LAB ENGINE] Recovered state: {len(open_trades)} OPEN positions across {len(self.portfolios)} strategies.")
        except Exception as e:
            print(f"[PAPER LAB ENGINE RECOVERY ERROR] {e}")
            traceback.print_exc()

    # ============================================================
    # SIGNAL INGESTION (on_new_signal)
    # ============================================================

    def on_new_signal(self, signal):
        """
        Receives a new signal from the production pipeline (Coin object or dict).
        Evaluates entry for each strategy independently.
        If signal_price is missing/invalid, registers signal as pending for 1st snapshot.
        Fails safely without raising exceptions.
        """
        try:
            if not signal:
                return
            signal_dict = _signal_to_dict(signal)
            sig_id = signal_dict.get("signal_id")
            if not sig_id:
                return

            self.signals_seen.add(sig_id)

            price = float(signal_dict.get("signal_price") or 0.0)

            # If signal has no valid price at ingestion, register as pending for 1st price snapshot
            if price <= 0:
                self.pending_signals[sig_id] = signal_dict
                return

            # Signal has a valid price -> Immediate entry evaluation
            for sid, strat in self.strategies.items():
                port = self.portfolios[sid]

                # STRICT ONE-ENTRY-PER-SIGNAL RULE
                if port.has_traded_signal(sig_id):
                    continue

                amount = strat.evaluate_entry(signal_dict, port)
                if amount > 0 and port.can_open(amount):
                    mc    = float(signal_dict.get("signal_market_cap") or 0.0)
                    ts    = float(signal_dict.get("signal_time") or time.time())
                    symbol = signal_dict.get("symbol", "?")
                    contract = signal_dict.get("contract", "")

                    pos = port.open_position(
                        trade_id=None,
                        strategy_version=strat.strategy_version,
                        signal_id=sig_id,
                        symbol=symbol,
                        contract=contract,
                        entry_time=ts,
                        entry_price=price,
                        entry_mc=mc,
                        invested=amount
                    )
                    if pos:
                        self.persistence.save_trade_open(pos.to_dict())
                        print(f"[PAPER LAB] [{sid}] BUY {symbol} | ${amount:.2f} @ ${price:.8f}")

        except Exception as e:
            print(f"[PAPER LAB ENGINE ERROR] on_new_signal failed: {e}")

    # ============================================================
    # SNAPSHOT UPDATE (on_snapshot)
    # ============================================================

    def on_snapshot(self, snapshot):
        """
        Receives a 5-second snapshot from existing tracking stream.
        1. Evaluates pending signals on their FIRST valid price snapshot.
        2. Updates open positions for all strategies and evaluates exit rules.
        Fails safely without raising exceptions.
        """
        try:
            if not snapshot:
                return
            snap_dict = snapshot if isinstance(snapshot, dict) else (
                snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
            )
            sig_id = snap_dict.get("signal_id")
            if not sig_id:
                return

            price = float(snap_dict.get("price") or 0.0)
            mc    = float(snap_dict.get("market_cap") or 0.0)
            ts    = float(snap_dict.get("timestamp") or time.time())

            # 1. PROCESS PENDING SIGNALS ON FIRST VALID PRICE SNAPSHOT
            if sig_id in self.pending_signals:
                if price > 0:
                    sig_dict = self.pending_signals.pop(sig_id)
                    eval_sig = dict(sig_dict)
                    eval_sig["signal_price"] = price
                    eval_sig["signal_market_cap"] = mc if mc > 0 else float(eval_sig.get("signal_market_cap") or 0.0)
                    eval_sig["signal_time"] = ts

                    for sid, strat in self.strategies.items():
                        port = self.portfolios[sid]
                        if port.has_traded_signal(sig_id):
                            continue
                        amount = strat.evaluate_entry(eval_sig, port)
                        if amount > 0 and port.can_open(amount):
                            symbol   = eval_sig.get("symbol", "?")
                            contract = eval_sig.get("contract", "")
                            pos = port.open_position(
                                trade_id=None,
                                strategy_version=strat.strategy_version,
                                signal_id=sig_id,
                                symbol=symbol,
                                contract=contract,
                                entry_time=ts,
                                entry_price=price,
                                entry_mc=mc,
                                invested=amount
                            )
                            if pos:
                                self.persistence.save_trade_open(pos.to_dict())
                                print(f"[PAPER LAB] [{sid}] BUY (1st Snap) {symbol} | ${amount:.2f} @ ${price:.8f}")

            for sid, strat in self.strategies.items():
                port = self.portfolios[sid]

                # Find open positions for this signal
                open_for_sig = [p for p in port.open_positions if p.signal_id == sig_id]
                for pos in open_for_sig:
                    pos.update_snapshot(snap_dict)
                    port.record_equity(ts)

                    action, pct, reason = strat.evaluate_exit(snap_dict, pos)

                    if action == "SELL_ALL":
                        port.close_position(pos, reason, ts, price, mc)
                        self.persistence.update_trade(pos.to_dict())
                        print(f"[PAPER LAB] [{sid}] CLOSE {pos.symbol} | {reason} | PnL={pos.realized_pnl:+.2f}")

                    elif action == "SELL_PCT" and pct > 0:
                        rec = port.close_position_by_partial_sell(pos, pct, reason, ts, price, mc)
                        if rec:
                            self.persistence.save_partial_sell(rec)
                            self.persistence.update_trade(pos.to_dict())
                            mb_pct = getattr(strat, "moonbag_pct", 0.0)
                            if mb_pct > 0 and abs(pos.remaining_pct - mb_pct) < 0.1:
                                print(f"[PAPER LAB] [{sid}] MANAGED CLOSE | {pos.symbol} | {reason}")
                                print(f"[PAPER LAB] [{sid}] MOONBAG HOLD | {pos.symbol} | remaining={mb_pct:g}%")
                            else:
                                print(f"[PAPER LAB] [{sid}] PARTIAL -{pct:.1f}% {pos.symbol} | {reason}")

                        if pos.remaining_pct <= 0.01:
                            if pos in port.open_positions:
                                port.open_positions.remove(pos)
                            port.closed_trades.append(pos.to_dict())

                    # Periodic update of open position stats (MFE/MAE) in DB
                    elif pos.status == "OPEN":
                        self.persistence.update_trade(pos.to_dict())

                # Record equity snapshot
                self.persistence.save_equity_snapshot(
                    strategy_id=sid,
                    cash=port.cash,
                    position_value=port.total_position_value,
                    equity=port.total_equity,
                    ts=ts
                )

        except Exception as e:
            print(f"[PAPER LAB ENGINE ERROR] on_snapshot failed: {e}")

    # ============================================================
    # REPORT GENERATION
    # ============================================================

    def generate_reports(self):
        """
        Triggers report generation into analytics/paper_lab/results/.
        Fails safely without raising exceptions.
        """
        try:
            return generate_paper_lab_reports(
                self.portfolios,
                signals_considered_count=len(self.signals_seen)
            )
        except Exception as e:
            print(f"[PAPER LAB ENGINE ERROR] generate_reports failed: {e}")
            return []


# Global Singleton Instance for clean integration
_PAPER_LAB_INSTANCE = None


def get_paper_lab_engine(db_path=None):
    """Returns the singleton PaperLabEngine instance."""
    global _PAPER_LAB_INSTANCE
    if _PAPER_LAB_INSTANCE is None:
        _PAPER_LAB_INSTANCE = PaperLabEngine(db_path=db_path)
    return _PAPER_LAB_INSTANCE
