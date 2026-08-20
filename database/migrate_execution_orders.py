import sqlite3

from config import DATABASE


REQUIRED_COLUMNS = {
    "transaction_signature": "TEXT",
    "confirmation_status": "TEXT",
    "confirmed_slot": "INTEGER",
}


def main():

    connection = sqlite3.connect(
        DATABASE,
        timeout=30.0,
    )

    try:

        cursor = connection.cursor()

        cursor.execute(
            "PRAGMA busy_timeout=30000;"
        )

        cursor.execute(
            "PRAGMA table_info(execution_orders)"
        )

        existing = {
            row[1]
            for row in cursor.fetchall()
        }

        print("=" * 70)
        print("EXECUTION ORDERS MIGRATION")
        print("=" * 70)

        for column, column_type in REQUIRED_COLUMNS.items():

            if column in existing:

                print(
                    f"[OK] {column} already exists"
                )

                continue

            cursor.execute(
                f"""
                ALTER TABLE execution_orders
                ADD COLUMN {column} {column_type}
                """
            )

            print(
                f"[ADD] {column}"
            )

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
