"""
Module 3 — Sentiment Engine v2
--------------------------------
Analyzes Telegram message text for sentiment.
Keyword-frequency approach — no external API.

v2 adds:
    sentiment_strength (float): 0.0-1.0 — how strongly the text leans.
    A neutral message near 0.0, a strongly one-sided message near 1.0.

Returns:
    sentiment_positive   (float) : 0.0-1.0
    sentiment_neutral    (float) : 0.0-1.0
    sentiment_negative   (float) : 0.0-1.0
    sentiment_confidence (float) : 0.0-1.0
    sentiment_strength   (float) : 0.0-1.0

MODE: PASSIVE COLLECTION ONLY.
"""

POSITIVE_SIGNALS = [
    "moon", "bullish", "pump", "surge", "rally", "launch", "partnership",
    "breakout", "adoption", "gem", "hold", "accumulate", "list", "buy",
    "growth", "potential", "strong", "solid", "based", "legit", "real deal",
    "exciting", "next 100x", "next 10x", "huge", "fire", "let's go", "letsgo",
    "wagmi", "lfg", "alpha", "undervalued", "early", "massive", "trending",
    "utility", "team", "vision", "roadmap", "milestone", "mainnet", "upgrade",
    "partnership", "airdrop", "staking", "reward", "momentum", "volume spike",
    "new ath", "all time high", "record", "breakout", "accumulate",
]

NEGATIVE_SIGNALS = [
    "rug", "scam", "dump", "crash", "bear", "fake", "fraud", "exit",
    "caution", "warning", "red flag", "redflag", "sus", "suspicious",
    "honeypot", "avoid", "risky", "ponzi", "dead", "gone", "failed",
    "hack", "exploit", "ban", "lawsuit", "concern", "ngmi", "rekt",
    "dumping", "selling", "sell", "oops", "mistake", "rugpull",
    "exit liquidity", "bagholder", "don't buy", "imagine buying",
    "top signal", "cope", "hopium", "red flags", "stay away",
    "already dumped", "too late", "insider dump", "dev wallet",
]

NEUTRAL_SIGNALS = [
    "token", "project", "coin", "crypto", "blockchain", "solana", "sol",
    "market", "price", "volume", "trade", "exchange", "wallet", "address",
    "contract", "mint", "launch", "listing", "pair",
]


def analyze_sentiment(text: str) -> dict:
    """Analyzes text for sentiment. Always returns a valid dict."""
    if not text or not isinstance(text, str):
        return {
            "sentiment_positive": 0.0, "sentiment_neutral": 1.0,
            "sentiment_negative": 0.0, "sentiment_confidence": 0.0,
            "sentiment_strength": 0.0,
        }

    lower = text.lower()

    pos = sum(1 for phrase in POSITIVE_SIGNALS if phrase in lower)
    neg = sum(1 for phrase in NEGATIVE_SIGNALS if phrase in lower)
    neu = sum(1 for phrase in NEUTRAL_SIGNALS  if phrase in lower)

    total = pos + neg + neu

    if total == 0:
        return {
            "sentiment_positive": 0.0, "sentiment_neutral": 1.0,
            "sentiment_negative": 0.0, "sentiment_confidence": 0.1,
            "sentiment_strength": 0.0,
        }

    pos_ratio = round(pos / total, 4)
    neg_ratio = round(neg / total, 4)
    neu_ratio = round(neu / total, 4)

    # Confidence: how strongly skewed away from neutral
    max_ratio = max(pos_ratio, neg_ratio, neu_ratio)
    confidence = round(min(max_ratio * 1.5, 1.0), 4)

    # Strength: absolute lean (ignores direction, measures conviction)
    # 0 = perfectly neutral, 1 = entirely positive or entirely negative
    if (pos + neg) == 0:
        strength = 0.0
    else:
        # Ratio of dominant signal (pos or neg) vs neutral
        dominant = max(pos, neg)
        strength = round(min(dominant / max(total, 1), 1.0), 4)

    return {
        "sentiment_positive":   pos_ratio,
        "sentiment_neutral":    neu_ratio,
        "sentiment_negative":   neg_ratio,
        "sentiment_confidence": confidence,
        "sentiment_strength":   strength,
    }


def collect_sentiment(coin) -> dict:
    """Runs sentiment analysis on coin's raw Telegram message."""
    default = {
        "sentiment_positive": 0.0, "sentiment_neutral": 1.0,
        "sentiment_negative": 0.0, "sentiment_confidence": 0.0,
        "sentiment_strength": 0.0,
    }
    try:
        raw_message = getattr(coin, "raw_message", "") or ""
        return analyze_sentiment(raw_message)
    except Exception as e:
        symbol = getattr(coin, "symbol", "")
        print(f"[INTELLIGENCE] Sentiment error for {symbol}: {e}")
        return default
