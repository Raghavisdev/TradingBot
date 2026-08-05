import requests


def analyze_narrative(signal):
    """
    Checks if the token has a strong narrative.

    Returns:
        score (0-20)
        reasons (list)
    """

    score = 0
    reasons = []

    token_name = signal["name"]
    token_symbol = signal["symbol"]

    print(f"\nSearching narrative for {token_name}...")

    query = f"{token_name} {token_symbol}"

    try:
        url = "https://api.duckduckgo.com/"

        params = {
            "q": query,
            "format": "json"
        }

        response = requests.get(url, params=params, timeout=5)

        data = response.json()

        related = data.get("RelatedTopics", [])

        if len(related) > 0:
            score += 15
            reasons.append("Narrative found")
        else:
            reasons.append("No obvious narrative")

    except Exception:
        reasons.append("Narrative search failed")

    return {
        "score": score,
        "reasons": reasons
    }