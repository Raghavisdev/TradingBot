from knowledge.coin import Coin
import strategy


def make_decision(coin: Coin):

    # ==========================================
    # RESET
    # ==========================================

    coin.strengths = []
    coin.weaknesses = []

    # ==========================================
    # STRENGTHS
    # ==========================================

    if coin.liquidity and coin.liquidity > 20000:
        coin.strengths.append("Healthy liquidity")

    if coin.buys_5m > coin.sells_5m:
        coin.strengths.append("Positive buying pressure")

    if coin.bundled <= 2:
        coin.strengths.append("Very low bundled wallets")

    if coin.snipers == 0:
        coin.strengths.append("No sniper wallets")

    if coin.insiders <= 2:
        coin.strengths.append("Low insider ownership")

    if coin.volume_5m > 10000:
        coin.strengths.append("Strong trading volume")

    if coin.safe >= 30:
        coin.strengths.append("High safety score")

    # ==========================================
    # WEAKNESSES
    # ==========================================

    if coin.dev > 10:
        coin.weaknesses.append(
            f"Developer owns {coin.dev}%"
        )

    if coin.top10 > 30:
        coin.weaknesses.append(
            f"Top10 holders own {coin.top10}%"
        )

    if coin.jeeters > 15:
        coin.weaknesses.append(
            f"High jeeters ({coin.jeeters}%)"
        )

    if (
        coin.signal_market_cap
        and coin.live_market_cap
    ):

        growth = coin.live_market_cap / coin.signal_market_cap

        if growth > strategy.WARNING_GROWTH:
            coin.weaknesses.append(
                f"Already moved {growth:.2f}x since alert"
            )

    # ==========================================
    # WEIGHTED AI SCORE
    # ==========================================

    total_score = 0
    total_weight = 0

    if coin.has_gemtools:
        total_score += (
            coin.gemtools_score *
            strategy.GEMTOOLS_WEIGHT
        )
        total_weight += strategy.GEMTOOLS_WEIGHT

    if coin.has_fundamental:
        total_score += (
            coin.fundamental_score *
            strategy.FUNDAMENTAL_WEIGHT
        )
        total_weight += strategy.FUNDAMENTAL_WEIGHT

    if coin.has_wallet:
        total_score += (
            coin.wallet_score *
            strategy.WALLET_WEIGHT
        )
        total_weight += strategy.WALLET_WEIGHT

    if coin.has_narrative:
        total_score += (
            coin.narrative_score *
            strategy.NARRATIVE_WEIGHT
        )
        total_weight += strategy.NARRATIVE_WEIGHT

    if coin.has_social:
        total_score += (
            coin.social_score *
            strategy.SOCIAL_WEIGHT
        )
        total_weight += strategy.SOCIAL_WEIGHT

    if total_weight == 0:

        coin.final_score = 0
        coin.decision = "UNKNOWN"
        coin.decision_reasons = ["No scoring modules active"]

        return coin

    # Normalize based on active modules
    coin.final_score = round(total_score / total_weight)

    # ==========================================
    # FINAL DECISION
    # ==========================================

    if coin.final_score >= 90:
        coin.decision = "STRONG BUY"

    elif coin.final_score >= 80:
        coin.decision = "BUY"

    elif coin.final_score >= 65:
        coin.decision = "WATCH"

    else:
        coin.decision = "SKIP"

    # ==========================================
    # DECISION REASONS
    # Build a human-readable explanation that is
    # stored as training data alongside each signal.
    # ==========================================

    reasons = []

    # Score summary
    reasons.append(f"Final Score: {coin.final_score}/100 → {coin.decision}")

    if coin.has_gemtools:
        reasons.append(f"GT Score: {coin.gt_score}/5 (GemTools module score: {coin.gemtools_score})")

    if coin.has_fundamental:
        reasons.append(f"Fundamental Score: {coin.fundamental_score}")

    # Strengths
    for strength in coin.strengths:
        reasons.append(f"+ {strength}")

    # Weaknesses
    for weakness in coin.weaknesses:
        reasons.append(f"- {weakness}")

    coin.decision_reasons = reasons

    return coin