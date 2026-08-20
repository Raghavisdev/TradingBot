import time
import uuid
import logging
import sqlite3

from config import DATABASE


logger = logging.getLogger("ExecutionOrderLogger")


class ExecutionOrderLogger:

    def __init__(self):

        self.connection = sqlite3.connect(
            DATABASE,
            timeout=30.0,
            check_same_thread=False,
        )

        self.connection.row_factory = sqlite3.Row

        cursor = self.connection.cursor()

        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
        finally:
            cursor.close()

    # =========================================================
    # CREATE ORDER
    # =========================================================

    def create_order(
        self,
        signal_id=None,
        symbol=None,
        side="BUY",
        requested_amount=0.0,
        idempotency_key=None,
    ):

        order_id = str(uuid.uuid4())

        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())

        now = time.time()

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                INSERT INTO execution_orders(
                    order_id,
                    idempotency_key,
                    signal_id,
                    symbol,
                    side,
                    requested_amount,
                    executed_amount,
                    status,
                    created_at,
                    updated_at,
                    error,
                    transaction_signature,
                    confirmation_status,
                    confirmed_slot
                )
                VALUES(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    order_id,
                    idempotency_key,
                    signal_id,
                    symbol,
                    side,
                    float(requested_amount),
                    0.0,
                    "CREATED",
                    now,
                    now,
                    None,
                    None,
                    None,
                    None,
                ),
            )

            self.connection.commit()

            logger.info(
                "[EXECUTION ORDER] CREATED | "
                "order_id=%s | symbol=%s | side=%s | amount=%.4f",
                order_id,
                symbol,
                side,
                float(requested_amount),
            )

            return order_id

        except sqlite3.IntegrityError:

            self.connection.rollback()

            logger.warning(
                "[EXECUTION ORDER] Duplicate idempotency key: %s",
                idempotency_key,
            )

            return None

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[EXECUTION ORDER] create failed: %s",
                exc,
            )

            return None

        finally:

            cursor.close()

    # =========================================================
    # FIND BY IDEMPOTENCY KEY
    # =========================================================

    def get_by_idempotency_key(
        self,
        idempotency_key,
    ):

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                SELECT *
                FROM execution_orders
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            )

            row = cursor.fetchone()

            return dict(row) if row else None

        finally:

            cursor.close()

    # =========================================================
    # UPDATE BASIC STATUS
    # =========================================================

    def update_order(
        self,
        order_id,
        status,
        executed_amount=None,
        error=None,
    ):

        now = time.time()

        cursor = self.connection.cursor()

        try:

            if executed_amount is None:

                cursor.execute(
                    """
                    UPDATE execution_orders
                       SET status = ?,
                           error = ?,
                           updated_at = ?
                     WHERE order_id = ?
                    """,
                    (
                        status,
                        error,
                        now,
                        order_id,
                    ),
                )

            else:

                cursor.execute(
                    """
                    UPDATE execution_orders
                       SET status = ?,
                           executed_amount = ?,
                           error = ?,
                           updated_at = ?
                     WHERE order_id = ?
                    """,
                    (
                        status,
                        float(executed_amount),
                        error,
                        now,
                        order_id,
                    ),
                )

            self.connection.commit()

            return cursor.rowcount > 0

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[EXECUTION ORDER] update failed: %s",
                exc,
            )

            return False

        finally:

            cursor.close()

    # =========================================================
    # RECORD SIGNATURE
    # =========================================================

    def record_submission(
        self,
        order_id,
        transaction_signature,
    ):

        if not transaction_signature:

            raise ValueError(
                "transaction_signature is required"
            )

        now = time.time()

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                UPDATE execution_orders
                   SET status = ?,
                       transaction_signature = ?,
                       updated_at = ?
                 WHERE order_id = ?
                """,
                (
                    "SUBMITTED",
                    str(transaction_signature),
                    now,
                    order_id,
                ),
            )

            self.connection.commit()

            success = cursor.rowcount > 0

            if success:

                logger.info(
                    "[EXECUTION ORDER] SUBMITTED | "
                    "order_id=%s | signature=%s",
                    order_id,
                    transaction_signature,
                )

            return success

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[EXECUTION ORDER] submission update failed: %s",
                exc,
            )

            return False

        finally:

            cursor.close()

    # =========================================================
    # RECORD CONFIRMATION
    # =========================================================

    def record_confirmation(
        self,
        order_id,
        transaction_signature,
        confirmation_status,
        confirmed_slot=None,
        executed_amount=None,
    ):

        if not transaction_signature:

            raise ValueError(
                "transaction_signature is required"
            )

        now = time.time()

        cursor = self.connection.cursor()

        try:

            if executed_amount is None:

                cursor.execute(
                    """
                    UPDATE execution_orders
                       SET status = ?,
                           transaction_signature = ?,
                           confirmation_status = ?,
                           confirmed_slot = ?,
                           updated_at = ?,
                           error = NULL
                     WHERE order_id = ?
                    """,
                    (
                        "CONFIRMED",
                        str(transaction_signature),
                        str(confirmation_status),
                        confirmed_slot,
                        now,
                        order_id,
                    ),
                )

            else:

                cursor.execute(
                    """
                    UPDATE execution_orders
                       SET status = ?,
                           transaction_signature = ?,
                           confirmation_status = ?,
                           confirmed_slot = ?,
                           executed_amount = ?,
                           updated_at = ?,
                           error = NULL
                     WHERE order_id = ?
                    """,
                    (
                        "CONFIRMED",
                        str(transaction_signature),
                        str(confirmation_status),
                        confirmed_slot,
                        float(executed_amount),
                        now,
                        order_id,
                    ),
                )

            self.connection.commit()

            success = cursor.rowcount > 0

            if success:

                logger.info(
                    "[EXECUTION ORDER] CONFIRMED | "
                    "order_id=%s | signature=%s | "
                    "confirmation=%s | slot=%s",
                    order_id,
                    transaction_signature,
                    confirmation_status,
                    confirmed_slot,
                )

            return success

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[EXECUTION ORDER] confirmation update failed: %s",
                exc,
            )

            return False

        finally:

            cursor.close()

    # =========================================================
    # RECORD FAILURE
    # =========================================================

    def record_failure(
        self,
        order_id,
        status,
        error,
    ):

        now = time.time()

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                UPDATE execution_orders
                   SET status = ?,
                       error = ?,
                       updated_at = ?
                 WHERE order_id = ?
                """,
                (
                    str(status),
                    str(error),
                    now,
                    order_id,
                ),
            )

            self.connection.commit()

            return cursor.rowcount > 0

        except Exception as exc:

            self.connection.rollback()

            logger.error(
                "[EXECUTION ORDER] failure update failed: %s",
                exc,
            )

            return False

        finally:

            cursor.close()

    # =========================================================
    # GET ORDER
    # =========================================================

    def get_order(
        self,
        order_id,
    ):

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                SELECT *
                FROM execution_orders
                WHERE order_id = ?
                """,
                (order_id,),
            )

            row = cursor.fetchone()

            return dict(row) if row else None

        finally:

            cursor.close()

    # =========================================================
    # CLOSE
    # =========================================================

    def close(self):

        self.connection.close()
