import time
import logging
from datetime import datetime

from collectors.live_market import update_market
from ai_engine.market_health import calculate_market_health
from ai_engine.exit_ai import get_exit_decision
from trading.position import Position
from database.database import database
from database.database import database
import os

try:
    from analytics.paper_lab.persistence import PaperLabPersistence
    _fwd_persistence = PaperLabPersistence()
except Exception:
    _fwd_persistence = None

logger = logging.getLogger("TradeManager")


class TradeManager:

    def __init__(self, portfolio, trader):

        self.portfolio = portfolio
        self.trader    = trader

    # ==================================================
    # RECOVER OPEN POSITIONS FROM DATABASE
    # Called once at startup. Reconstructs Position objects
    # from paper_trades rows so the bot resumes managing them.
    # ==================================================

    def recover_open_positions(self, strategy_id: str = "default"):
        """
        Loads all OPEN paper_trades rows for this strategy and
        injects reconstructed Position objects into the portfolio.

        Logs [PAPER RECOVERY] for each position restored.
        """
        try:
            open_rows = database.get_open_paper_trades(strategy_id=strategy_id)
        except Exception as e:
            logger.error("[PAPER RECOVERY] DB query failed: %s", e)
            return

        if not open_rows:
            logger.info("[PAPER RECOVERY] No open paper positions to recover.")
            return

        recovered = 0

        for row in open_rows:
            try:
                # Skip if already in portfolio (e.g. duplicate startup call)
                contract = row.get("contract")
                if contract and self.portfolio.has_position(contract):
                    logger.info("[PAPER RECOVERY] Already in portfolio, skipping: %s",
                                row.get("symbol", "?"))
                    continue

                position = Position()

                # Identity
                position.trade_id         = row["trade_id"]
                position.strategy_id      = row.get("strategy_id",      "default")
                position.strategy_version = row.get("strategy_version", "1.0")
                position.signal_id        = row.get("signal_id")
                position.symbol           = row.get("symbol",    "?")
                position.contract         = row.get("contract",  "")
                position.status           = "OPEN"

                # Entry data
                position.entry_price      = float(row.get("entry_price",      0.0) or 0.0)
                position.entry_market_cap = float(row.get("entry_market_cap", 0.0) or 0.0)
                position.entry_time       = float(row.get("entry_time",       0.0) or 0.0)
                position.invested_amount  = float(row.get("invested",         0.0) or 0.0)
                position.tokens           = float(row.get("tokens",           0.0) or 0.0)

                # Restore partial-sell state
                val = row.get("remaining_pct")
                position.remaining_percent = float(val) if val is not None else 100.0
                position.remaining_percent = max(0.0, min(100.0, position.remaining_percent))
                position.sold_percent      = 100.0 - position.remaining_percent
                position.realized_profit   = float(row.get("realized_pnl",    0.0) or 0.0)
                
                if position.remaining_percent <= 0:
                    position.status = "CLOSED"
                    logger.info("[PAPER RECOVERY] Skipping fully exited position: %s", position.trade_id)
                    continue

                # Restore excursion metrics
                position.mfe = float(row.get("mfe", 0.0) or 0.0)
                position.mae = float(row.get("mae", 0.0) or 0.0)

                # Current price = entry until first live update
                position.current_price      = position.entry_price
                position.current_market_cap = position.entry_market_cap
                position.highest_price      = position.entry_price
                position.highest_market_cap = position.entry_market_cap
                position.lowest_price       = position.entry_price
                position.lowest_market_cap  = position.entry_market_cap

                # Probe state (LAPC-v2)
                position.probe_entry_time = float(row.get("probe_entry_time", 0.0) or 0.0)
                position.probe_entry_market_cap = float(row.get("probe_entry_market_cap", 0.0) or 0.0)
                position.scale_in_completed = int(row.get("scale_in_completed", 0) or 0)
                position.post_probe_snapshot_count = int(row.get("post_probe_snapshot_count", 0) or 0)

                # Friction
                position.entry_fees = float(row.get("fees", 0.0) or 0.0)
                position.entry_slippage = float(row.get("slippage", 0.0) or 0.0)
                position.network_fee = float(row.get("network_fee", 0.0) or 0.0)

                # buy_time (datetime) â€” approximate from entry_time if available
                try:
                    position.buy_time = datetime.fromtimestamp(position.entry_time) \
                                        if position.entry_time else datetime.now()
                except Exception:
                    position.buy_time = datetime.now()

                self.portfolio.add_position(position)

                # Adjust portfolio cash: subtract invested amount (was already accounted for)
                # Only subtract if cash would not go negative (guard against double-deduction)
                if self.portfolio.cash >= position.invested_amount:
                    self.portfolio.cash -= position.invested_amount

                # Fetch final_score for LAPC-v2
                position.final_score = 0
                if position.signal_id:
                    try:
                        c = database.signal_logger.connection.cursor()
                        c.execute("SELECT final_score FROM signals WHERE signal_id = ?", (position.signal_id,))
                        res = c.fetchone()
                        if res:
                            position.final_score = int(res[0])
                        c.close()
                    except Exception:
                        pass

                recovered += 1

                logger.info(
                    "[PAPER RECOVERY] Restored position: %s | trade_id=%s | "
                    "invested=$%.2f | entry=$%.8f | remaining=%.0f%%",
                    position.symbol, position.trade_id,
                    position.invested_amount, position.entry_price,
                    position.remaining_percent,
                )

            except Exception as e:
                logger.error("[PAPER RECOVERY] Failed to restore row %s: %s",
                             row.get("trade_id", "?"), e)

        logger.info("[PAPER RECOVERY] Recovered %d open position(s) for strategy '%s'.",
                    recovered, strategy_id)

    # ==================================================
    # UPDATE ALL OPEN POSITIONS
    # ==================================================

    def update(self):

        open_positions = self.portfolio.get_open_positions()

        if not open_positions:
            return

        for position in open_positions:

            if position.status == "CLOSED":
                continue

            # ------------------------------------------
            # Update Live Market Data
            # ------------------------------------------

            update_market(position)

            if position.current_market_cap is None:
                continue

            # ------------------------------------------
            # Calculate Market Health
            # ------------------------------------------

            health, breakdown = calculate_market_health(position)

            position.market_health           = health
            position.market_health_breakdown = breakdown

            # ------------------------------------------
            # SAVE HISTORY
            # ------------------------------------------

            position.health_history.append(health)
            position.market_cap_history.append(position.current_market_cap)
            position.price_history.append(position.current_price)
            position.liquidity_history.append(position.liquidity)
            position.volume_history.append(position.volume_5m)

            total = position.buys_5m + position.sells_5m
            ratio = (position.buys_5m / total) if total > 0 else 0
            position.buy_ratio_history.append(ratio)

            # Keep rolling window at 30 snapshots
            position.health_history       = position.health_history[-30:]
            position.market_cap_history   = position.market_cap_history[-30:]
            position.price_history        = position.price_history[-30:]
            position.liquidity_history    = position.liquidity_history[-30:]
            position.volume_history       = position.volume_history[-30:]
            position.buy_ratio_history    = position.buy_ratio_history[-30:]

            # ------------------------------------------
            # LAPC-v2 SMART SCALE-IN (REMOVED FOR S6 BASELINE)
            # ------------------------------------------

            # ------------------------------------------
            # Persist MFE / MAE (non-blocking, best-effort)
            # ------------------------------------------

            trade_id = getattr(position, "trade_id", None)
            if trade_id:
                try:
                    database.update_mfe_mae(trade_id, position.mfe, position.mae)
                except Exception:
                    pass  # Non-critical

            # ------------------------------------------
            # Exit AI
            # ------------------------------------------
            
            action = None
            confidence = 0.0
            reason = ""
            
            if getattr(position, "strategy_id", "") == "S6_Moonshot_Ladder":
                # Initialize state if not present
                if not hasattr(position, 's6_state'):
                    position.s6_state = 'NORMAL'
                if not hasattr(position, 's6_stop_price'):
                    position.s6_stop_price = position.entry_price * 0.80 # Initial -20% stop
                
                hwm = position.highest_price
                current_price = position.current_price
                
                # Check Moonshot transition (trigger at +100% from entry)
                if position.s6_state == 'NORMAL' and (hwm / position.entry_price) >= 2.0:
                    position.s6_state = 'MOONSHOT'
                    # Log moonshot variables
                    if _fwd_persistence:
                        try:
                            _fwd_persistence.save_forward_tick({"event": "MOONSHOT_ACTIVATED", "trade_id": position.trade_id, "hwm": hwm, "liquidity": position.liquidity})
                        except: pass
                
                # Calculate candidate stop based on current state
                if position.s6_state == 'MOONSHOT':
                    # INTENTIONAL PARADOX: Widening the trail to -30% (0.70x peak) creates breathing room.
                    # Because of the max() ratcheting rule below, the stop will NOT drop.
                    # e.g., At 2.0x, normal stop was 1.6x. Moonshot candidate is 1.4x.
                    # max(1.6, 1.4) = 1.6x. 
                    # The stop remains flat at 1.6x until peak > 2.285x, where 0.70 * peak > 1.6x.
                    candidate_stop = hwm * 0.70 # -30% from peak
                else:
                    candidate_stop = hwm * 0.80 # -20% from peak
                
                # Strict ratcheting constraint (Stop can never decrease)
                position.s6_stop_price = max(position.s6_stop_price, candidate_stop)
                
                # Trigger liquidation
                if current_price <= position.s6_stop_price:
                    action = "SELL_ALL"
                    confidence = 100.0
                    reason = f"S6 {position.s6_state} TRAIL BREAK: Price {current_price:.6f} <= Stop {position.s6_stop_price:.6f}"
                else:
                    action = "HOLD"
                    confidence = 0.0
                    reason = ""
            
            if action is None:
                action, confidence, reason = get_exit_decision(position)

            position.exit_action     = action
            position.exit_confidence = confidence
            position.exit_reason     = reason

            # ------------------------------------------
            # FORWARD TICK LEDGER LOGGING
            # ------------------------------------------
            import os
            import time
            if _fwd_persistence and getattr(position, "strategy_id", "default").startswith("S6"):
                try:
                    full_log = os.getenv("FORWARD_TICK_LEDGER_FULL", "False").lower() in ("true", "1", "yes")
                    
                    # Track last logged HWM to only log on changes if not full
                    last_logged_hwm = getattr(position, "_last_logged_hwm", 0.0)
                    hwm_changed = getattr(position, "highest_price", 0.0) > last_logged_hwm
                    
                    if full_log or hwm_changed or action != "HOLD":
                        tick_dict = {
                            "trade_id": position.trade_id,
                            "timestamp": time.time(),
                            "price": position.current_price,
                            "market_cap": position.current_market_cap,
                            "liquidity": position.liquidity,
                            "volume": position.volume_5m,
                            "buys": position.buys_5m,
                            "sells": position.sells_5m,
                            "hwm": getattr(position, "highest_price", 0.0),
                            "current_retracement": getattr(position, "highest_pnl_pct", 0.0) - getattr(position, "pnl_pct", 0.0),
                            "strategy_state": str(getattr(position, "fired_ladder_levels", [])),
                            "experiment_id": "FORWARD_TEST_01",
                            "strategy_id": getattr(position, "strategy_id", "default")
                        }
                        _fwd_persistence.save_forward_tick(tick_dict)
                        position._last_logged_hwm = getattr(position, "highest_price", 0.0)
                except Exception as e:
                    logger.error(f"[FORWARD LEDGER] Failed to save tick: {e}")

            # ------------------------------------------
            # Display
            # ------------------------------------------

            print(position)

            print("=" * 60)
            print("MARKET HEALTH :", health)
            print("EXIT ACTION   :", action)
            print("CONFIDENCE    :", confidence)
            print("REASON        :", reason)
            print("=" * 60)

            # ------------------------------------------
            # Execute Exit
            # ------------------------------------------

            if action == "SELL_ALL":

                if position.remaining_percent > 0:
                    self.trader.sell_all(
                        position,
                        exit_reason=reason,
                    )

            elif action.startswith("SELL_") and action != "SELL_ALL":
                
                # Prevent the same AI exit action from being
                # executed repeatedly on consecutive update cycles.
                executed_actions = getattr(
                    position,
                    "executed_exit_actions",
                    set(),
                )

                if action in executed_actions:

                    print(
                        "EXIT ACTION SKIPPED:",
                        action,
                        "(Already Executed)",
                    )
                else:

                    try:
                        pct_to_sell = float(action.split("_")[1])
                    except:
                        pct_to_sell = 0.0

                    if pct_to_sell > 0:
                        success = self.trader.partial_sell(
                            position,
                            percent=pct_to_sell,
                            exit_reason=reason,
                        )
                        if success:
                            executed_actions.add(action)
                            position.executed_exit_actions = executed_actions



    # ==================================================
    # RUN FOREVER
    # ==================================================

    def run(self):

        print("\n===================================")
        print("ðŸš€ Trade Manager Started")
        print("===================================\n")

        while True:

            try:
                self.update()

            except Exception as e:
                print("Trade Manager Error:", e)

            time.sleep(1)

