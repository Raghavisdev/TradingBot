import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "analytics", "paper_lab", "s6_exit_config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {
            "hard_stop_pct": -30.0,
            "trail_activation_pct": 50.0,
            "trailing_stop_pct": 30.0,
            "profit_rungs": [{"trigger_pct": 150.0, "sell_pct": 50.0}]
        }
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def evaluate_s6_exit(position, current_price):
    """
    Returns: action (str), percent_to_sell (float), reason (str)
    """
    config = load_config()
    
    if position.entry_price <= 0:
        return "HOLD", 0.0, ""
        
    unrealized_pct = (current_price - position.entry_price) / position.entry_price * 100.0
    
    # 1. Hard Stop
    if unrealized_pct <= config.get("hard_stop_pct", -30.0):
        return "SELL_ALL", 100.0, "Hard Stop"
        
    # 2. Update High Water Mark
    high_water = getattr(position, "high_water_mark", position.entry_price)
    if current_price > high_water:
        position.high_water_mark = current_price
        high_water = current_price
        
    max_ret = (high_water - position.entry_price) / position.entry_price * 100.0
    
    # 3. Trailing Stop
    if max_ret >= config.get("trail_activation_pct", 50.0):
        trail_stop_ret = max_ret - config.get("trailing_stop_pct", 30.0)
        if unrealized_pct <= trail_stop_ret:
            return "SELL_ALL", 100.0, "Trailing Stop"
            
    # 4. Profit Rungs
    fired = getattr(position, "fired_ladder_levels", set())
    for rung in config.get("profit_rungs", []):
        trigger = float(rung["trigger_pct"])
        if unrealized_pct >= trigger and trigger not in fired:
            fired.add(trigger)
            position.fired_ladder_levels = fired
            return "SELL_PCT", float(rung["sell_pct"]), f"Rung {trigger}%"
            
    return "HOLD", 0.0, ""
