from knowledge.coin import Coin
import strategy


def validate_coin(coin: Coin):

    coin.valid = True
    coin.reject_reason = ""
    coin.warnings = []

    # ----------------------------------
    # HARD REJECTION RULES
    # ----------------------------------

    if coin.dev > strategy.MAX_DEV:
        coin.valid = False
        coin.reject_reason = f"Developer owns {coin.dev}%"
        return coin

    if coin.bundled > strategy.MAX_BUNDLED:
        coin.valid = False
        coin.reject_reason = f"Bundled wallets {coin.bundled}%"
        return coin

    if coin.top10 > strategy.MAX_TOP10:
        coin.valid = False
        coin.reject_reason = f"Top10 owns {coin.top10}%"
        return coin

    if coin.snipers > strategy.MAX_SNIPERS:
        coin.valid = False
        coin.reject_reason = f"Snipers {coin.snipers}%"
        return coin

    if (
        coin.signal_market_cap and
        coin.signal_market_cap > strategy.MAX_MARKET_CAP
    ):
        coin.valid = False
        coin.reject_reason = "Market cap too large"
        return coin

    if coin.holders < strategy.MIN_HOLDERS:
        coin.valid = False
        coin.reject_reason = "Very few holders"
        return coin

    # ----------------------------------
    # WARNINGS
    # ----------------------------------

    if coin.dev >= strategy.WARNING_DEV:
        coin.warnings.append(
            f"Developer owns {coin.dev}%"
        )

    if coin.top10 >= strategy.WARNING_TOP10:
        coin.warnings.append(
            f"Top10 owns {coin.top10}%"
        )

    if coin.bundled >= strategy.WARNING_BUNDLED:
        coin.warnings.append(
            f"Bundled wallets {coin.bundled}%"
        )

    return coin


def validate_s6_execution(coin, strategy_id="S6_Moonshot_Ladder"):
    """
    Validates execution constraints for S6_Moonshot_Ladder.
    Fails closed if data is missing or MCx > 2.0.

    Returns: (is_valid: bool, reason: str)
    """
    if strategy_id != "S6_Moonshot_Ladder":
        return True, "Not S6"

    sig_mc = getattr(coin, "signal_market_cap", 0)
    live_mc = getattr(coin, "live_market_cap", 0)

    if not sig_mc or float(sig_mc) <= 0:
        return False, "Missing or invalid signal market cap"

    if not live_mc or float(live_mc) <= 0:
        return False, "Missing or invalid live market cap"

    mcx = float(live_mc) / float(sig_mc)

    if mcx > 2.0:
        return False, f"MCx ({mcx:.2f}) > 2.0"

    return True, f"MCx ({mcx:.2f}) <= 2.0"
