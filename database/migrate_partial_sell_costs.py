import sqlite3

from config import DATABASE


REQUIRED_COLUMNS = {
    "fees": "REAL DEFAULT 0.0",
    "slippage": "REAL DEFAULT 0.0",
}


def main():
    connection = sqlite3.connect(
        DATABASE,
        timeout=30.0,
    )

    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")

        cursor.execute(
            "PRAGMA table_info(paper_partial_sells)"
        )

        existing = {
            row[1]
            for row in cursor.fetchall()
        }

        print("=" * 70)
        print("PARTIAL SELL COST MIGRATION")
        print("=" * 70)

        for column, definition in REQUIRED_COLUMNS.items():

            if column in existing:
                print(f"[OK] {column} already exists")
                continue

            cursor.execute(
                f"""
                ALTER TABLE paper_partial_sells
                ADD COLUMN {column} {definition}
                """
            )

            print(f"[ADD] {column}")

        connection.commit()

        print()
        print("Migration committed successfully.")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()
