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