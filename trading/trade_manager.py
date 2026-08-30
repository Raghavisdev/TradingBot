import time
import logging
from datetime import datetime

from collectors.live_market import update_market
from ai_engine.market_health import calculate_market_health
from ai_engine.exit_ai import get_exit_decision
from trading.position import Position
from database.database import database

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
                position.remaining_percent = float(row.get("remaining_pct", 100.0) or 100.0)
                position.sold_percent      = 100.0 - position.remaining_percent
                position.realized_profit   = float(row.get("realized_pnl",    0.0) or 0.0)

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
            # LAPC-v2 SMART SCALE-IN (S6_Moonshot_Ladder)
            # ------------------------------------------

            if getattr(position, "strategy_id", "") == "S6_Moonshot_Ladder":
                scale_in_completed = getattr(position, "scale_in_completed", 1)
                probe_entry_time = getattr(position, "probe_entry_time", 0.0)

                # We only count snapshots where time.time() > probe_entry_time, ensuring it's strictly post-probe
                if scale_in_completed == 0 and probe_entry_time > 0 and time.time() > probe_entry_time:
                    position.post_probe_snapshot_count = getattr(position, "post_probe_snapshot_count", 0) + 1

                    if position.post_probe_snapshot_count >= 3:
                        final_score = getattr(position, "final_score", 0)
                        mc_change = (position.current_market_cap - position.probe_entry_market_cap) / position.probe_entry_market_cap if getattr(position, "probe_entry_market_cap", 0.0) > 0 else -1

                        if final_score >= 65 and mc_change >= -0.10:
                            scale_amount = 5.0
                            print(f"LAPC-v2 SCALE-IN TRIGGERED for {position.symbol}. MC change: {mc_change*100:.2f}%")

                            # The paper_trader.scale_in() method inherently enforces the $35 deployment cap limit.
                            # It sets scale_in_completed = 1 via DB if successful.
                            # But if the trader rejects it (e.g. not enough cash, or cap reached), we should still mark it as completed to prevent endless re-attempts.
                            success = self.trader.scale_in(position, scale_amount)
                            position.scale_in_completed = 1
                            if not success:
                                print(f"LAPC-v2 SCALE-IN FAILED for {position.symbol} (rejected by executor)")
                            database.update_probe_state(position.trade_id, position.scale_in_completed, position.post_probe_snapshot_count)
                        else:
                            position.scale_in_completed = 1
                            print(f"LAPC-v2 SCALE-IN REJECTED for {position.symbol}. Score {final_score}, MC change {mc_change*100:.2f}%")
                            database.update_probe_state(position.trade_id, position.scale_in_completed, position.post_probe_snapshot_count)
                    else:
                        database.update_probe_state(position.trade_id, position.scale_in_completed, position.post_probe_snapshot_count)

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

            action, confidence, reason = get_exit_decision(position)

            position.exit_action     = action
            position.exit_confidence = confidence
            position.exit_reason     = reason

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

            elif action in {
                "SELL_70",
                "SELL_40",
                "SELL_20",
                "SELL_15",
            }:

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
                        "already executed for this position.",
                    )

                elif position.remaining_percent <= 0:

                    print(
                        "EXIT ACTION SKIPPED:",
                        action,
                        "position already fully sold.",
                    )

                else:

                    percent = {
                        "SELL_70": 70,
                        "SELL_40": 40,
                        "SELL_20": 20,
                        "SELL_15": 15,
                    }[action]

                    previous_remaining = (
                        position.remaining_percent
                    )

                    try:

                        result = self.trader.partial_sell(
                            position,
                            percent,
                            exit_reason=reason,
                        )

                        # Only mark the action as executed if
                        # the sell operation reports success.
                        if result is not False:

                            executed_actions.add(action)

                            position.executed_exit_actions = (
                                executed_actions
                            )

                            print(
                                "EXIT ACTION EXECUTED:",
                                action,
                                "|",
                                f"Remaining: "
                                f"{position.remaining_percent}%",
                            )

                        else:

                            print(
                                "EXIT ACTION FAILED:",
                                action,
                                "| Action remains retryable.",
                            )

                    except Exception as exc:

                        print(
                            "EXIT ACTION ERROR:",
                            action,
                            "|",
                            exc,
                        )

                        # Do not mark failed actions as executed.
                        position.remaining_percent = max(
                            0,
                            position.remaining_percent,
                        )

                        print(
                            "Previous remaining:",
                            previous_remaining,
                        )

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

