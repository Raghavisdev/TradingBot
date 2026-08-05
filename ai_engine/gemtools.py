from knowledge.coin import Coin


def analyze_gemtools(coin: Coin):

    score = 0

    breakdown = {}

    # -----------------------------
    # GT Score
    # -----------------------------

    gt = coin.gt_score * 4
    score += gt
    breakdown["GT Score"] = gt

    # -----------------------------
    # Holder Count
    # -----------------------------

    holders = 0

    if coin.holders >= 500:
        holders = 10
    elif coin.holders >= 300:
        holders = 8
    elif coin.holders >= 200:
        holders = 6
    elif coin.holders >= 100:
        holders = 4
    else:
        holders = 2

    score += holders
    breakdown["Holders"] = holders

    # -----------------------------
    # Top10
    # -----------------------------

    top10 = 0

    if coin.top10 <= 20:
        top10 = 10
    elif coin.top10 <= 30:
        top10 = 8
    elif coin.top10 <= 40:
        top10 = 6
    elif coin.top10 <= 50:
        top10 = 3

    score += top10
    breakdown["Top10"] = top10

    # -----------------------------
    # Bundled
    # -----------------------------

    bundled = 0

    if coin.bundled <= 2:
        bundled = 10
    elif coin.bundled <= 5:
        bundled = 8
    elif coin.bundled <= 10:
        bundled = 5
    else:
        bundled = 2

    score += bundled
    breakdown["Bundled"] = bundled

    # -----------------------------
    # Dev Holdings
    # -----------------------------

    dev = 0

    if coin.dev <= 2:
        dev = 10
    elif coin.dev <= 5:
        dev = 8
    elif coin.dev <= 10:
        dev = 5
    elif coin.dev <= 15:
        dev = 2

    score += dev
    breakdown["Developer"] = dev

    # -----------------------------
    # Snipers
    # -----------------------------

    sniper = 0

    if coin.snipers == 0:
        sniper = 10
    elif coin.snipers <= 2:
        sniper = 8
    elif coin.snipers <= 5:
        sniper = 5

    score += sniper
    breakdown["Snipers"] = sniper

    # -----------------------------
    # Insiders
    # -----------------------------

    insider = 0

    if coin.insiders <= 2:
        insider = 10
    elif coin.insiders <= 5:
        insider = 6
    elif coin.insiders <= 10:
        insider = 2

    score += insider
    breakdown["Insiders"] = insider

    # -----------------------------
    # Jeeters
    # -----------------------------

    jeeter = 0

    if coin.jeeters <= 5:
        jeeter = 10
    elif coin.jeeters <= 10:
        jeeter = 8
    elif coin.jeeters <= 20:
        jeeter = 5
    else:
        jeeter = 2

    score += jeeter
    breakdown["Jeeters"] = jeeter

    coin.gemtools_score = score
    coin.has_gemtools = True
    coin.gemtools_breakdown = breakdown

    return coin