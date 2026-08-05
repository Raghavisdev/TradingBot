import sqlite3

DB_NAME = "database/tradingbot.db"


def log_signal(coin):

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""

    INSERT INTO signals(

        symbol,
        name,
        contract,

        signal_market_cap,
        live_market_cap,

        gt_score,

        gemtools_score,
        fundamental_score,
        wallet_score,
        narrative_score,
        social_score,

        final_score,

        decision

    )

    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)

    """, (

        coin.symbol,
        coin.name,
        coin.contract,

        coin.signal_market_cap,
        coin.live_market_cap,

        coin.gt_score,

        coin.gemtools_score,
        coin.fundamental_score,
        coin.wallet_score,
        coin.narrative_score,
        coin.social_score,

        coin.final_score,

        coin.decision

    ))

    conn.commit()

    conn.close()

    print("✅ Signal Logged")