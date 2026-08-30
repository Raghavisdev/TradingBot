import threading
import os
import sys
from parsers.signal_parser import parse_signal

from collectors.manager import collect_all

from ai_engine.gemtools import analyze_gemtools
from ai_engine.fundamentals import analyze_fundamentals
from ai_engine.decision import make_decision
from ai_engine.position_sizer import get_position_size

from execution.paper_trader import PaperTrader
from execution.live_trader import LiveTrader

from trading.portfolio import Portfolio
from trading.live_portfolio import LivePortfolio
from trading.trade_manager import TradeManager
from trading.tracker_manager import tracker_manager

from database.database import database

from intelligence.runner import intelligence_runner


# ==========================================================
# GLOBAL OBJECTS
# ==========================================================

LIVE_TRADING = os.getenv("LIVE_TRADING", "False").lower() in ("true", "1", "yes")

if LIVE_TRADING:
    print("ðŸš€ LIVE TRADING IS ENABLED")
    WALLET_PUBKEY = os.getenv("WALLET_PUBLIC_KEY", "MOCK_WALLET_PUBLIC_KEY_FOR_TESTING")
    portfolio = LivePortfolio(WALLET_PUBKEY)
    trader = LiveTrader(portfolio)
else:
    print("ðŸ§ª PAPER TRADING IS ENABLED")
    portfolio = Portfolio()
    trader = PaperTrader(portfolio)

trade_manager = TradeManager(
    portfolio,
    trader
)


# ==========================================================
# RECOVER OPEN PAPER POSITIONS FROM DATABASE
# Must run before the trade manager thread starts so that
# any positions open when the bot last stopped are rehydrated
# into the portfolio and immediately managed by Exit AI.
# ==========================================================

trade_manager.recover_open_positions(strategy_id="S6_Moonshot_Ladder")

# ==========================================================
# START TRADE MANAGER
# ==========================================================

manager_thread = threading.Thread(
    target=trade_manager.run,
    daemon=True
)

manager_thread.start()


# ==========================================================
# PROCESS TELEGRAM SIGNAL
# ==========================================================

def process_message(message):

    print("\n" + "=" * 70)
    print("ðŸš€ PROCESSING NEW SIGNAL")
    print("=" * 70)

    # ======================================================
    # PARSE SIGNAL
    # ======================================================
    print("\n================ PIPELINE DEBUG ================")
    print("TYPE:", type(message))
    print("MESSAGE:")
    print(repr(message))
    print("================================================")

    coin = parse_signal(message)

    if coin is None:

        print("âŒ Invalid Signal")

        return None

    coin.raw_message = message

    # ======================================================
    # SAVE RAW SIGNAL
    # ======================================================

    database.create_signal(coin)

    # ======================================================
    # START TRACKING IMMEDIATELY
    # Every valid signal is tracked â€” regardless of decision or buy.
    # ======================================================

    tracker_manager.start_tracking(coin)

    # ======================================================
    # PASSIVE INTELLIGENCE COLLECTION (AI V2)
    # Runs in a background daemon thread â€” does NOT affect
    # the existing BUY/WATCH/SKIP decision in any way.
    # ======================================================

    intelligence_runner.collect(coin)

    print("âœ… Signal Parsed")
    print("ðŸ’¾ Signal Saved")
    print("ðŸ“¡ Tracking Started")

    # ======================================================
    # COLLECT LIVE MARKET DATA
    # ======================================================

    coin = collect_all(coin)

    # ======================================================
    # AI ANALYSIS (LEGACY)
    # Always run make_decision to populate final_score (as it was used in research)
    # and to preserve legacy causal availability.
    coin = analyze_gemtools(coin)
    coin = analyze_fundamentals(coin)
    coin = make_decision(coin)

    vnext_mode = os.getenv("S6_Moonshot_VNext_MODE", "DISABLED").upper()

    print(f"[STARTUP] VNEXT MODE: {vnext_mode}")
    print(f"[STARTUP] LIVE_TRADING: {os.getenv('LIVE_TRADING', 'False')}")
    print(f"[STARTUP] ACTIVE PYTHON: {sys.executable}")

    if vnext_mode != "DISABLED":
        # vNext EVALUATION
        from ai_engine.s6_vnext.entry import vnext_evaluate_entry
        vnext_decision, vnext_reason = vnext_evaluate_entry(coin)

        if vnext_mode == "SHADOW":
            # In shadow, we preserve legacy for production but log vNext
            coin_legacy_decision = coin.decision

            # Write to shadow comparison CSV
            import csv
            from pathlib import Path
            project_root = Path(__file__).resolve().parent.parent
            research_dir = project_root / "research"
            research_dir.mkdir(parents=True, exist_ok=True)
            shadow_file = str(research_dir / "phase6_shadow_comparison.csv")

            file_exists = os.path.exists(shadow_file)
            with open(shadow_file, "a", newline='') as sf:
                writer = csv.writer(sf)
                if not file_exists:
                    writer.writerow(["signal_id", "timestamp", "production_decision", "vnext_decision", "reason_for_difference"])
                writer.writerow([getattr(coin, "signal_id", "unknown"), getattr(coin, "timestamp", ""), coin_legacy_decision, vnext_decision, vnext_reason])

        elif vnext_mode in ["PAPER", "LIVE"]:
            # vNext entirely overrides legacy AI
            coin.decision = vnext_decision

    # ======================================================
    # UPDATE SIGNAL WITH AI RESULT
    # ======================================================

    database.update_signal(coin)

    # ======================================================
    # PAPER LAB MULTI-STRATEGY EVALUATION (Phase 3 Observer)
    # Failsafe non-blocking wrapper for S1-S5
    # ======================================================
    # try:
    #     from analytics.paper_lab.lab_engine import get_paper_lab_engine
    #     get_paper_lab_engine().on_new_signal(coin)
    # except Exception as lab_e:
    #     print(f"[PAPER LAB ERROR] Signal dispatch failed: {lab_e}")

    # ======================================================
    # S7 LIVE SHADOW EVALUATION
    # ======================================================
    try:
        from s7_shadow.live_evaluator import evaluate_and_record_shadow_decision

        # Calculate what S6 allocation would be if it wasn't rejected
        s6_amount = 0.0
        if coin.decision in ["BUY", "STRONG BUY"]:
            s6_amount = get_position_size(coin, portfolio)

        evaluate_and_record_shadow_decision(coin, s6_amount, coin.decision)
    except Exception as s7_e:
        print(f"[S7 SHADOW ERROR] {s7_e}")

    # ======================================================
    # PRINT REPORT
    # ======================================================

    print(coin)

    # ======================================================
    # AI REJECTED
    # ======================================================

    # LAPC-v2 S6 Override:
    # For S6 specifically, probe eligibility is lowered to final_score >= 62.
    if coin.decision not in ["BUY", "STRONG BUY"] and getattr(coin, "final_score", 0) >= 62:
        coin.decision = "BUY"

    if coin.decision not in ["BUY", "STRONG BUY"]:

        coin.buy_blocked_by = "AI Decision"
        database.update_signal(coin)

        print("\nâŒ AI Rejected Trade")
        print("ðŸ“¡ Signal will continue to be tracked.")
        print("=" * 70)

        return coin

    # ======================================================
    # DUPLICATE POSITION CHECK
    # ======================================================

    if portfolio.has_position(coin.contract):

        coin.buy_blocked_by = "Duplicate Position"
        database.update_signal(coin)

        print("\nâš  Already Holding This Coin")
        print("=" * 70)

        return coin

    # ======================================================
    # POSITION SIZE
    # ======================================================

    vnext_mode = os.getenv("S6_Moonshot_VNext_MODE", "DISABLED").upper()
    if vnext_mode in ["PAPER", "LIVE"]:
        from ai_engine.s6_vnext.entry import vnext_get_position_size
        amount = vnext_get_position_size(coin, portfolio)
    else:
        amount = get_position_size(
            coin,
            portfolio
        )

    if amount <= 0:

        coin.buy_blocked_by = "Position Sizer"
        database.update_signal(coin)

        print("\nâŒ Position Sizer Rejected Trade")
        print("=" * 70)

        return coin

    # ======================================================
    # PORTFOLIO RISK CHECK
    # ======================================================

    if not portfolio.can_open_trade(amount):

        coin.buy_blocked_by = "Portfolio Risk"
        database.update_signal(coin)

        print("\nâš  Portfolio Risk Manager Blocked Trade")
        print("Reason : Max Positions / Cash Reserve")
        print("=" * 70)

        return coin

    # ======================================================
    # EXECUTE PAPER BUY
    # ======================================================

    print("\nâœ… BUY APPROVED")

    position = trader.buy(
        coin,
        amount
    )

    if position is None:

        coin.buy_blocked_by = "Buy Execution Failed"
        database.update_signal(coin)

        print("âŒ Buy Failed")
        print("=" * 70)

        return coin

    # Link Position to Coin
    coin.position = position
    coin.bought = True
    database.update_signal(coin)

    # ======================================================
    # PORTFOLIO SUMMARY
    # ======================================================

    print("\n==============================")
    print("ðŸ“ˆ TRADE OPENED")
    print("==============================")

    print(f"Coin           : {position.symbol}")
    print(f"Investment     : ${amount:.2f}")
    print(f"Entry Price    : ${position.entry_price:.8f}")
    print(f"Entry MC       : ${position.entry_market_cap:,.0f}")
    print(f"Cash Remaining : ${portfolio.cash:.2f}")
    print(f"Open Trades    : {len(portfolio.get_open_positions())}")

    print("==============================")

    print("=" * 70)

    return coin
