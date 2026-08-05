import threading

from parsers.signal_parser import parse_signal

from collectors.manager import collect_all

from ai_engine.gemtools import analyze_gemtools
from ai_engine.fundamentals import analyze_fundamentals
from ai_engine.decision import make_decision
from ai_engine.position_sizer import get_position_size

from execution.paper_trader import PaperTrader

from trading.portfolio import Portfolio
from trading.trade_manager import TradeManager
from trading.tracker_manager import tracker_manager

from database.database import database


# ==========================================================
# GLOBAL OBJECTS
# ==========================================================

portfolio = Portfolio()

paper_trader = PaperTrader(portfolio)

trade_manager = TradeManager(
    portfolio,
    paper_trader
)


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
    print("🚀 PROCESSING NEW SIGNAL")
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

        print("❌ Invalid Signal")

        return None

    coin.raw_message = message

    # ======================================================
    # SAVE RAW SIGNAL
    # ======================================================

    database.create_signal(coin)

    # ======================================================
    # START TRACKING IMMEDIATELY
    # Every valid signal is tracked — regardless of decision or buy.
    # ======================================================

    tracker_manager.start_tracking(coin)

    print("✅ Signal Parsed")
    print("💾 Signal Saved")
    print("📡 Tracking Started")

    # ======================================================
    # COLLECT LIVE MARKET DATA
    # ======================================================

    coin = collect_all(coin)

    # ======================================================
    # AI ANALYSIS
    # ======================================================

    coin = analyze_gemtools(coin)

    coin = analyze_fundamentals(coin)

    coin = make_decision(coin)

    # ======================================================
    # UPDATE SIGNAL WITH AI RESULT
    # ======================================================

    database.update_signal(coin)

    # ======================================================
    # PRINT REPORT
    # ======================================================

    print(coin)

    # ======================================================
    # AI REJECTED
    # ======================================================

    if coin.decision not in ["BUY", "STRONG BUY"]:

        coin.buy_blocked_by = "AI Decision"
        database.update_signal(coin)

        print("\n❌ AI Rejected Trade")
        print("📡 Signal will continue to be tracked.")
        print("=" * 70)

        return coin

    # ======================================================
    # DUPLICATE POSITION CHECK
    # ======================================================

    if portfolio.has_position(coin.contract):

        coin.buy_blocked_by = "Duplicate Position"
        database.update_signal(coin)

        print("\n⚠ Already Holding This Coin")
        print("=" * 70)

        return coin

    # ======================================================
    # POSITION SIZE
    # ======================================================

    amount = get_position_size(
        coin,
        portfolio
    )

    if amount <= 0:

        coin.buy_blocked_by = "Position Sizer"
        database.update_signal(coin)

        print("\n❌ Position Sizer Rejected Trade")
        print("=" * 70)

        return coin

    # ======================================================
    # PORTFOLIO RISK CHECK
    # ======================================================

    if not portfolio.can_open_trade(amount):

        coin.buy_blocked_by = "Portfolio Risk"
        database.update_signal(coin)

        print("\n⚠ Portfolio Risk Manager Blocked Trade")
        print("Reason : Max Positions / Cash Reserve")
        print("=" * 70)

        return coin

    # ======================================================
    # EXECUTE PAPER BUY
    # ======================================================

    print("\n✅ BUY APPROVED")

    position = paper_trader.buy(
        coin,
        amount
    )

    if position is None:

        coin.buy_blocked_by = "Buy Execution Failed"
        database.update_signal(coin)

        print("❌ Buy Failed")
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
    print("📈 TRADE OPENED")
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