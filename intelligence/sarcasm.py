"""
Module 4 — Sarcasm Detector v2
--------------------------------
Detects sarcasm in Telegram messages.

v2 adds:
    - Expanded phrase list with crypto-specific sarcasm patterns
    - Explicit "bear signal" phrases: exit liquidity, bagholder, etc.
    - Negation + positive claim detection
    - Returns probability only (0.0-1.0)

MODE: PASSIVE COLLECTION ONLY.
"""

# ======================================================
# DIRECT SARCASM MARKERS
# ======================================================

SARCASM_MARKERS = [
    # Classic sarcasm patterns
    "sure...", "yeah right", "totally", "oh wow", "amazing 😂",
    "🙄", "definitely not", "not a rug", "obviously", "for sure 😂",
    "lol", "nice try", "another one", "great project", "totally legit",
    "another 1000x", "another gem", "top signal", "top signal 😂",
    "trust me bro", "genius", "groundbreaking", "revolutionary",
    "life changing", "unbelievable", "wow so", "...", "🤡", "💀", "🫠",
    "definitely gonna moon", "totally safe", "no way this rugs",

    # Crypto-specific sarcasm
    "exit liquidity",       # "you are the exit liquidity"
    "bagholder",            # holding a losing position
    "imagine buying",       # mocking buyers
    "don't buy",            # explicit negative
    "stay away",
    "top signal",           # called at the top
    "sell signal",
    "already dumped",
    "dev sold",
    "team sold",
    "insiders dumped",
    "early investors dumped",
    "last chance to buy",   # fear-based selling signal
    "don't be left behind", # FOMO manipulation marker
    "not financial advice 😂",
    "nfa 😂",
    "100x easy",            # unrealistic claim marker
    "guaranteed profit",
    "can't lose",
    "riskless",
    "safe investment",
    "definitely not a scam",
    "totally not a rug",
    "rugproof",
]

# ======================================================
# STRONG CLAIMS (unrealistic)
# ======================================================

STRONG_CLAIMS = [
    "1000x", "100x", "moon", "gem", "next big", "100%", "guaranteed",
    "can't lose", "sure thing", "next btc", "game changer", "revolutionary",
    "life changing", "never seen before", "the next solana", "next eth",
    "next shib", "next doge", "10000x", "billionaire",
]

# ======================================================
# DOUBT / MOCKERY MARKERS
# ======================================================

DOUBT_MARKERS = [
    "😂", "lol", "lmao", "🙄", "💀", "🤡", "haha", "sure", "right",
    "obviously", "totally", "definitely", "omg", "wow", "amazing",
    "pfffft", "riight", "kek", "🤣", "ok bro",
]

# ======================================================
# EXPLICIT BEAR SIGNALS (not sarcasm, but negative intent)
# ======================================================

EXPLICIT_NEGATIVES = [
    "exit liquidity", "bagholder", "don't buy", "imagine buying",
    "already rugged", "dev dumped", "team dumped", "avoid this",
    "stay away from", "red flag", "honeypot", "bundled tokens",
    "insider dump",
]


def detect_sarcasm(text: str) -> dict:
    """Computes sarcasm probability for a text string. Always valid."""
    if not text or not isinstance(text, str):
        return {"sarcasm_probability": 0.0}

    lower = text.lower()
    score = 0.0

    # Score 1: Direct sarcasm markers
    marker_hits = sum(1 for m in SARCASM_MARKERS if m.lower() in lower)
    score += marker_hits * 0.20

    # Score 2: Contradiction — strong claim + doubt marker
    has_strong_claim = any(c in lower for c in STRONG_CLAIMS)
    has_doubt        = any(d.lower() in lower for d in DOUBT_MARKERS)
    if has_strong_claim and has_doubt:
        score += 0.40

    # Score 3: Explicit bear signals (certain negative intent)
    explicit_hits = sum(1 for p in EXPLICIT_NEGATIVES if p in lower)
    score += explicit_hits * 0.25

    return {"sarcasm_probability": round(min(score, 1.0), 4)}


def collect_sarcasm(coin) -> dict:
    """Runs sarcasm detection on coin's raw Telegram message."""
    try:
        raw_message = getattr(coin, "raw_message", "") or ""
        return detect_sarcasm(raw_message)
    except Exception as e:
        symbol = getattr(coin, "symbol", "")
        print(f"[INTELLIGENCE] Sarcasm error for {symbol}: {e}")
        return {"sarcasm_probability": 0.0}
