import time

from knowledge.coin import Coin


def market_cap_score(mc):

    if mc is None:
        return 0

    if mc < 5000:
        return 5

    elif mc < 10000:
        return 10

    elif mc < 25000:
        return 18

    elif mc < 50000:
        return 25

    elif mc < 150000:
        return 20

    return 12


def liquidity_score(liq):

    if liq is None:
        return 0

    if liq < 5000:
        return 5

    elif liq < 10000:
        return 12

    elif liq < 25000:
        return 20

    return 25


def buy_pressure_score(buys, sells):

    buys = buys or 0
    sells = sells or 0

    total = buys + sells

    if total == 0:
        return 0

    ratio = buys / total

    return int(ratio * 20)


def volume_score(volume):

    volume = volume or 0

    if volume < 500:
        return 2

    elif volume < 2000:
        return 8

    elif volume < 10000:
        return 12

    return 15


def age_score(pair_created):

    if pair_created is None:
        return 0

    minutes = (time.time() * 1000 - pair_created) / 60000

    if minutes < 1:
        return 15

    elif minutes < 5:
        return 13

    elif minutes < 15:
        return 10

    elif minutes < 60:
        return 7

    return 3


def analyze_fundamentals(coin: Coin):

    mc = market_cap_score(coin.market_cap)
    liq = liquidity_score(coin.liquidity)
    bp = buy_pressure_score(coin.buys_5m, coin.sells_5m)
    vol = volume_score(coin.volume_5m)
    age = age_score(coin.pair_created)

    coin.fundamental_score = mc + liq + bp + vol + age

    coin.fundamental_breakdown = {
        "Market Cap": mc,
        "Liquidity": liq,
        "Buy Pressure": bp,
        "Volume": vol,
        "Age": age
    }

    return coin