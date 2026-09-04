import re

from knowledge.coin import Coin


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [
            str(arg).encode("ascii", "backslashreplace").decode("ascii")
            for arg in args
        ]
        print(*safe_args, **kwargs)


def clean_str(s):
    if not s:
        return ""
    return (
        s.replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", "")
        .replace("`", "")
        .replace("'", "")
        .replace('"', "")
        .strip()
    )


def extract_number(text):
    if not text:
        return 0.0

    cleaned = (
        clean_str(text)
        .upper()
        .replace("$", "")
        .replace(",", "")
        .replace("%", "")
    )

    if not cleaned or cleaned == "—":
        return 0.0

    try:
        if cleaned.endswith("K"):
            return float(cleaned[:-1]) * 1000

        if cleaned.endswith("M"):
            return float(cleaned[:-1]) * 1000000

        if cleaned.endswith("B"):
            return float(cleaned[:-1]) * 1000000000

        return float(cleaned)

    except ValueError:
        return 0.0


def gt_score_count(text):

    return text.count("⭐")


SOLANA_CONTRACT_REGEX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def is_valid_solana_contract(contract):
    if not contract or not isinstance(contract, str):
        return False
    return bool(SOLANA_CONTRACT_REGEX.match(contract.strip()))


def parse_signal(text):

    safe_print("\n========== PARSER ==========")

    text = text.strip()

    # ==========================================
    # Ignore only obvious update messages
    # ==========================================

    lower = text.lower()

    ignore_phrases = [
        "take profit",
        "profit booked",
        "sold",
        "closed position",
        "exit position"
    ]

    for phrase in ignore_phrases:

        if lower.startswith(phrase):

            safe_print("Rejected:", phrase)

            return None

    # ==========================================
    # Must start with signal
    # ==========================================

    if "$" not in text:

        safe_print("Rejected : Not a new signal")

        return None

    lines = [

        clean_str(line)

        for line in text.splitlines()

        if clean_str(line)

    ]

    if len(lines) < 2:

        safe_print("Rejected : Too few lines")

        return None

    # ==========================================
    # Parse first line ($SYMBOL or $SYMBOL (NAME))
    # ==========================================

    first_line = lines[0]
    safe_print("first_line:", repr(first_line))

    # Reject GemTools Performance Updates (e.g., 🚀 $DICK x2 🚀, 🚀 $MUSK x5 🚀)
    if re.search(r"\$[A-Za-z0-9_]+\s+(?:x\d+|\d+x)", first_line, re.IGNORECASE) or re.search(r"\b[xX]\d+\b", first_line):

        safe_print("Rejected: GemTools performance update")

        return None

    match = re.search(r"\$([^\s(]+)(?:\s*\((.*?)\))?", first_line)

    if not match:

        safe_print("Rejected : Couldn't parse symbol/name")

        safe_print("first_line causing failure:", repr(first_line))

        return None

    # ==========================================
    # Validate Contract Before Creating Coin Object
    # GemTools always places the contract on line 2.
    # ==========================================

    raw_contract = clean_str(lines[1])

    if not is_valid_solana_contract(raw_contract):

        safe_print("Rejected : Invalid Contract")

        return None

    # ==========================================
    # Create Coin Object Only After Validation Passes
    # ==========================================

    coin = Coin()

    coin.symbol = match.group(1).strip()

    coin.name = match.group(2).strip() if match.group(2) else coin.symbol

    coin.contract = raw_contract

    safe_print(f"Symbol   : {coin.symbol}")

    safe_print(f"Name     : {coin.name}")

    safe_print(f"Contract : {coin.contract}")

    # ==========================================
    # Parse Remaining Lines
    # ==========================================

    for line in lines:
        if "GTscore:" in line:
            coin.gt_score = gt_score_count(line)
            coin.gt_stars = line.replace("GTscore:", "").strip()

        # Some formats have "MC now:" which we should ignore in favor of the original alert MC
        if line.startswith("MC now:"):
            continue

        if "MC:" in line:
            mc = re.search(r"MC:\s*\$([0-9.,]+[KMBkmb]?)", line)
            age = re.search(r"Age:\s*(.*?)\s*(?:·|$)", line)
            holders = re.search(r"Holders:\s*([0-9,]+)", line)
            if mc:
                coin.signal_market_cap = extract_number(mc.group(1))
                coin.market_cap = coin.signal_market_cap
            if age:
                coin.age = age.group(1).strip()
            if holders:
                coin.holders = int(extract_number(holders.group(1)))

        if "Top10:" in line:
            top10 = re.search(r"Top10:\s*([^·]+)", line)
            bundled = re.search(r"Bundled:\s*([^·]+)", line)
            first50 = re.search(r"First50:\s*(.*)", line)
            if top10:
                coin.top10 = extract_number(top10.group(1))
            if bundled:
                coin.bundled = extract_number(bundled.group(1))
            if first50:
                coin.first50 = extract_number(first50.group(1))

        if "Jeeters:" in line:
            jeeters = re.search(r"Jeeters:\s*([^·]+)", line)
            fresh = re.search(r"Fresh:\s*([^·]+)", line)
            snipers = re.search(r"Snipers:\s*(.*)", line)
            if jeeters:
                coin.jeeters = extract_number(jeeters.group(1))
            if fresh:
                coin.fresh = extract_number(fresh.group(1))
            if snipers:
                coin.snipers = extract_number(snipers.group(1))

        if "Insiders:" in line:
            insiders = re.search(r"Insiders:\s*([^·]+)", line)
            dev = re.search(r"Dev:\s*(.*)", line)
            if insiders:
                coin.insiders = extract_number(insiders.group(1))
            if dev:
                coin.dev = extract_number(dev.group(1))

        if "Safe:" in line:
            safe = re.search(r"Safe:\s*([^·]+)", line)
            poor = re.search(r"Poor:\s*(.*)", line)
            if safe:
                coin.safe = extract_number(safe.group(1))
            if poor:
                coin.poor = extract_number(poor.group(1))

        if "🕸" in line or re.search(r"\b\d+C\s*·\s*\d+W\b", line):
            community = re.search(r"(\d+)C", line)
            whales = re.search(r"(\d+)W", line)
            win_rate = re.search(r"([0-9.]+)\s*%", line)
            if community:
                coin.community = int(extract_number(community.group(1)))
            if whales:
                coin.whales = int(extract_number(whales.group(1)))
            if win_rate:
                coin.win_rate = extract_number(win_rate.group(1))

    safe_print("✅ Signal Parsed Successfully")
    return coin
