from collectors.live_market import update_market
from ai_engine.market_health import calculate_market_health
from ai_engine.exit_ai import get_exit_decision

import time


class TradeManager:

    def __init__(self, portfolio, trader):

        self.portfolio = portfolio
        self.trader = trader

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

            position.market_health = health
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

            if total > 0:
                ratio = position.buys_5m / total
            else:
                ratio = 0

            position.buy_ratio_history.append(ratio)

            position.health_history = position.health_history[-30:]
            position.market_cap_history = position.market_cap_history[-30:]
            position.price_history = position.price_history[-30:]
            position.liquidity_history = position.liquidity_history[-30:]
            position.volume_history = position.volume_history[-30:]
            position.buy_ratio_history = position.buy_ratio_history[-30:]

            # ------------------------------------------
            # Exit AI
            # ------------------------------------------

            action, confidence, reason = get_exit_decision(position)

            position.exit_action = action
            position.exit_confidence = confidence
            position.exit_reason = reason

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

                self.trader.sell_all(position)

            elif action == "SELL_70":

                self.trader.partial_sell(position, 70)

            elif action == "SELL_40":

                self.trader.partial_sell(position, 40)

            elif action == "SELL_20":

                self.trader.partial_sell(position, 20)

            elif action == "SELL_15":

                self.trader.partial_sell(position, 15)

    # ==================================================
    # RUN FOREVER
    # ==================================================

    def run(self):

        print("\n===================================")
        print("🚀 Trade Manager Started")
        print("===================================\n")

        while True:

            try:

                self.update()

            except Exception as e:

                print("Trade Manager Error:", e)

            time.sleep(1)