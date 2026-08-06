"""
Module 5 — Narrative Engine
-----------------------------
Classifies every coin into a narrative category based on its name,
symbol, and Telegram message content.

Narratives tracked:
    AI, Meme, Politics, Dog, Cat, Gaming, Infrastructure,
    RWA, DeFi, Layer2, Space, Animal, Pepe, Sport, Music

Returns:
    primary_narrative    (str)   : Most likely narrative
    secondary_narrative  (str)   : Second narrative (if applicable)
    narrative_confidence (float) : 0.0–1.0

MODE: PASSIVE COLLECTION ONLY.
"""


# ======================================================
# NARRATIVE KEYWORD DEFINITIONS
# ======================================================

NARRATIVE_KEYWORDS = {
    "AI": [
        "ai", "artificial intelligence", "gpt", "llm", "machine learning",
        "neural", "agent", "agi", "robot", "chatbot", "autonomous",
        "compute", "intelligence", "openai", "claude", "gemini",
    ],
    "Meme": [
        "meme", "degen", "wen", "ngmi", "wagmi", "hodl", "based", "gm",
        "pepe", "wojak", "clown", "moon boy", "shill", "lol", "lmao",
        "gigachad", "chad", "sigma", "npc",
    ],
    "Politics": [
        "trump", "biden", "maga", "republican", "democrat", "president",
        "election", "vote", "political", "senator", "congress", "elon",
        "government", "policy", "patriot", "america", "usa",
    ],
    "Dog": [
        "doge", "dog", "shib", "shiba", "puppy", "woof", "canine",
        "hound", "retriever", "poodle", "bone", "fetch", "bark",
        "husky", "lab", "labrador", "corgi", "doggo",
    ],
    "Cat": [
        "cat", "kitten", "meow", "feline", "purrr", "kitty", "tabby",
        "nyan", "catcoin", "cattoken", "meoow",
    ],
    "Gaming": [
        "game", "gaming", "play", "nft", "metaverse", "virtual", "quest",
        "rpg", "fps", "guild", "clan", "esport", "gamer", "pixel",
        "loot", "dungeon", "adventure", "arcade",
    ],
    "Infrastructure": [
        "protocol", "chain", "layer", "bridge", "oracle", "validator",
        "node", "rpc", "sdk", "api", "infrastructure", "network",
        "consensus", "finality", "throughput",
    ],
    "RWA": [
        "rwa", "real world", "tokenized", "asset", "commodity", "gold",
        "property", "real estate", "bond", "equity", "security token",
    ],
    "DeFi": [
        "defi", "liquidity", "yield", "farm", "pool", "swap", "amm",
        "lending", "borrow", "collateral", "vault", "protocol", "dex",
        "perp", "perpetual", "derivative",
    ],
    "Layer2": [
        "layer2", "l2", "rollup", "optimism", "arbitrum", "scaling",
        "zk", "zero knowledge", "proof", "sidechain",
    ],
    "Space": [
        "space", "rocket", "cosmos", "stellar", "astro", "moon",
        "galaxy", "orbit", "nasa", "mars", "alien", "ufo",
    ],
    "Animal": [
        "bear", "bull", "fish", "whale", "shark", "ape", "monkey",
        "frog", "rabbit", "wolf", "fox", "tiger", "lion", "panda",
        "elephant", "bird", "penguin",
    ],
    "Sport": [
        "sport", "soccer", "football", "basketball", "nba", "fifa",
        "tennis", "baseball", "boxing", "mma", "ufc", "champion",
        "league", "team", "player", "athlete",
    ],
    "Music": [
        "music", "song", "beat", "rap", "hip hop", "artist", "album",
        "concert", "nft music", "sound", "audio", "band", "dj",
    ],
}


# ======================================================
# NARRATIVE CLASSIFIER
# ======================================================

def classify_narrative(text: str) -> dict:
    """
    Classifies a text string into one or two narratives.
    Returns primary, secondary, and confidence.
    """
    if not text:
        return {
            "primary_narrative": "Unknown",
            "secondary_narrative": "",
            "narrative_confidence": 0.0,
        }

    lower = text.lower()
    scores = {}

    for narrative, keywords in NARRATIVE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lower)
        if hits > 0:
            scores[narrative] = hits

    if not scores:
        return {
            "primary_narrative": "Unknown",
            "secondary_narrative": "",
            "narrative_confidence": 0.0,
        }

    sorted_narratives = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    primary = sorted_narratives[0][0]
    primary_hits = sorted_narratives[0][1]
    secondary = sorted_narratives[1][0] if len(sorted_narratives) > 1 else ""

    # Confidence: ratio of primary hits to total hits
    total_hits = sum(scores.values())
    confidence = round(primary_hits / total_hits, 4) if total_hits > 0 else 0.0

    return {
        "primary_narrative": primary,
        "secondary_narrative": secondary,
        "narrative_confidence": confidence,
    }


def collect_narrative(coin) -> dict:
    """
    Classifies the coin's narrative from its name, symbol, and Telegram message.
    Returns safe defaults on failure.
    """
    default = {
        "primary_narrative": "Unknown",
        "secondary_narrative": "",
        "narrative_confidence": 0.0,
    }

    try:
        symbol = getattr(coin, "symbol", "") or ""
        name = getattr(coin, "name", "") or ""
        raw_message = getattr(coin, "raw_message", "") or ""

        # Combine all text sources for classification
        combined_text = f"{symbol} {name} {raw_message}"

        return classify_narrative(combined_text)

    except Exception as e:
        symbol = getattr(coin, "symbol", "")
        print(f"[INTELLIGENCE] Narrative classification error for {symbol}: {e}")
        return default
