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
    raise RuntimeError("FATAL: LIVE_TRADING IS STRICTLY LOCKED FOR S6 PAPER PHASE.")
    WALLET_PUBKEY = os.getenv("WALLET_PUBLIC_KEY", "MOCK_WALLET_PUBLIC_KEY_FOR_TESTING")
    portfolio = LivePortfolio(WALLET_PUBKEY)
    trader = LiveTrader(portfolio)
else:
    print("[PAPER] PAPER TRADING IS ENABLED")
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
    print("[SIGNAL] PROCESSING NEW SIGNAL")
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

        print("[SKIP] Invalid Signal")

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

    print("[OK] Signal Parsed")
    print("[OK] Signal Saved")
    print("[OK] Tracking Started")

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

    print(f"[STARTUP] LIVE_TRADING: {os.getenv('LIVE_TRADING', 'False')}")
    print(f"[STARTUP] ACTIVE PYTHON: {sys.executable}")

    from ai_engine.s6_production_entry import evaluate_s6_production_entry
    production_entry = evaluate_s6_production_entry(coin, portfolio)

    # FINAL S6 ARCHITECTURE overrides legacy decision
    if production_entry.eligible:
        coin.decision = "BUY"
        coin.decision_reason = f"S6 V2 APPROVED: {production_entry.reason}"
        coin.buy_blocked_by = ""
    else:
        coin.decision = "SKIP"
        coin.decision_reason = f"S6 V2 REJECTED: {production_entry.reason}"
        coin.buy_blocked_by = "S6 Execution Evaluator"

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

    # The legacy LAPC-v2 S6 >= 60 override has been removed.

    if coin.decision not in ["BUY", "STRONG BUY"]:

        if not getattr(coin, "buy_blocked_by", None):
            coin.buy_blocked_by = "AI Decision"
        database.update_signal(coin)

        print("\n[SKIP] AI Rejected Trade")
        print("[INFO] Signal will continue to be tracked.")
        print("=" * 70)

        return coin

    # ======================================================
    # DUPLICATE POSITION CHECK
    # ======================================================

    if portfolio.has_position(coin.contract):

        coin.buy_blocked_by = "Duplicate Position"
        database.update_signal(coin)

        print("\n[SKIP] Already Holding This Coin")
        print("=" * 70)

        return coin

    # ======================================================
    # POSITION SIZE
    # ======================================================

    amount = (
        production_entry.decision.amount
        if production_entry.decision is not None
        else 0.0
    )

    if amount <= 0:
        print(f"\n[SKIP] Position Sizer Rejected Trade")
        reason = (
            production_entry.reason
            if "production_entry" in locals()
            else "Position Sizer"
        )
        coin.buy_blocked_by = f"Position Sizer: {reason}"
        database.update_signal(coin)
        print("=" * 70)

        return coin

    # ======================================================
    # PORTFOLIO RISK CHECK
    # ======================================================

    if not portfolio.can_open_trade(amount):

        coin.buy_blocked_by = "Portfolio Risk"
        database.update_signal(coin)

        print("\n[SKIP] Portfolio Risk Manager Blocked Trade")
        print("Reason : Max Positions / Cash Reserve")
        print("=" * 70)

        return coin

    # ======================================================
    # EXECUTE PAPER BUY
    # ======================================================

    print("\n[BUY] BUY APPROVED")

    position = trader.buy(
        coin,
        amount
    )

    if position is None:

        coin.buy_blocked_by = "Buy Execution Failed"
        database.update_signal(coin)

        print("[FAIL] Buy Failed")
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
    print("[OK] TRADE OPENED")
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
