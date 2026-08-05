import time

from trading.position import Position
from collectors.live_market import update_position

from ai_engine.market_health import calculate_market_health
from ai_engine.exit_ai import get_exit_decision


# ==========================================
# CREATE TEST POSITION
# ==========================================

p = Position()

p.symbol = "BBQCOIN"
p.contract = "33cjJr5CWcJ3mxUvQP6z8JgAofumGDLFgLqUtq9Cpump"

p.entry_price = 0.000060
p.entry_market_cap = 35000

p.invested_amount = 3

p.initialize()

print("\nPosition Initialized")
print("----------------------------")
print("Highest MC :", p.highest_market_cap)
print("Lowest MC  :", p.lowest_market_cap)


# ==========================================
# LIVE LOOP
# ==========================================

while True:

    # -----------------------------
    # Update Live Market
    # -----------------------------

    update_position(p)

    # -----------------------------
    # Market Health AI
    # -----------------------------

    health, breakdown = calculate_market_health(p)

    p.market_health = health
    p.market_health_breakdown = breakdown

    # -----------------------------
    # Exit AI
    # -----------------------------

    action, confidence, reason = get_exit_decision(p)

    p.exit_action = action
    p.exit_confidence = confidence
    p.exit_reason = reason

    # -----------------------------
    # Display Position
    # -----------------------------

    print(p)

    # -----------------------------
    # Market Health
    # -----------------------------

    print("\n==============================")
    print("MARKET HEALTH")
    print("==============================")

    print(f"Overall Score : {p.market_health}/100\n")

    for key, value in p.market_health_breakdown.items():
        print(f"{key:<20}: {value}")

    # -----------------------------
    # Exit AI
    # -----------------------------

    print("\n==============================")
    print("EXIT AI")
    print("==============================")

    print(f"Action       : {p.exit_action}")
    print(f"Confidence   : {p.exit_confidence}%")
    print(f"Reason       : {p.exit_reason}")

    # -----------------------------
    # Wait
    # -----------------------------

    time.sleep(1)