import asyncio
import signal
import sys
import logging

from config import validate_config
from utils.logger import setup_logging
from database.models import create_tables
from database.database import database
from trading.tracker_manager import tracker_manager
from trading.health_monitor import HealthMonitor
from telegram_client import connect_to_telegram
from message_handler import register_handlers

logger = logging.getLogger("Main")

# Global health monitor instance
health_monitor = None
client_instance = None


async def run_bot():
    global health_monitor, client_instance

    # 1. Setup Production Logging
    setup_logging()

    logger.info("===================================")
    logger.info("🚀 Starting Trading Bot (Production Mode)")
    logger.info("===================================")

    # 2. Validate Environment & Credentials Configuration
    try:
        validate_config()
        logger.info("[CONFIG] Environment configuration validated successfully.")
    except Exception as e:
        logger.critical("[FATAL CONFIG ERROR] %s", e)
        sys.exit(1)

    # 3. Create & Verify Database Schema
    try:
        create_tables()
        logger.info("[DB] Database tables initialized and WAL mode confirmed.")
    except Exception as e:
        logger.critical("[FATAL DB ERROR] Database initialization failed: %s", e)
        sys.exit(1)

    # 4. Start Tracker Manager & Re-hydrate Active Trackers
    try:
        tracker_manager.start()
        logger.info("[TRACKER] TrackerManager started.")
    except Exception as e:
        logger.critical("[FATAL TRACKER ERROR] Tracker recovery failed: %s", e)
        sys.exit(1)

    # 5. Start Health Monitor Daemon (Logs Runtime Status every 10 min)
    health_monitor = HealthMonitor(tracker_manager)
    health_monitor.start()

    # 6. Connect Telegram Client & Register Message Listeners
    while True:
        try:
            logger.info("🚀 Connecting Telegram Client...")
            client = await connect_to_telegram()
            client_instance = client

            register_handlers(client)

            logger.info("===================================")
            logger.info("🤖 Trading Bot Running")
            logger.info("👂 Waiting for GemTools Signals...")
            logger.info("===================================")

            await client.run_until_disconnected()

        except asyncio.CancelledError:
            logger.info("[SHUTDOWN] Main task cancelled.")
            break

        except Exception as e:
            logger.warning("[CONNECTION LOST] Telegram disconnected: %s", e)
            logger.info("🔄 Reconnecting Telegram in 5 seconds...")
            await asyncio.sleep(5)


def shutdown_handler(signum, frame):
    """
    Handles OS signals (SIGINT / SIGTERM) for clean, safe process termination.
    """
    signame = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    logger.info("\n===================================")
    logger.info("[SHUTDOWN] Received signal %s. Initiating graceful shutdown...", signame)
    logger.info("===================================")

    # 1. Stop Health Monitor
    if health_monitor:
        health_monitor.stop()
        logger.info("[SHUTDOWN] Health Monitor stopped.")

    # 2. Stop Tracker Manager
    if tracker_manager:
        tracker_manager.stop()
        logger.info("[SHUTDOWN] Tracker Manager stopped.")

    # 3. Close Database Connections
    try:
        database.close()
        logger.info("[SHUTDOWN] Database connections closed.")
    except Exception as e:
        logger.warning("[SHUTDOWN ERROR] Database close error: %s", e)

    logger.info("✅ Graceful Shutdown Complete. Exiting.")
    logging.shutdown()
    sys.exit(0)


if __name__ == "__main__":
    # Register SIGINT (Ctrl+C) and SIGTERM (VPS service stop)
    signal.signal(signal.SIGINT, shutdown_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        shutdown_handler(signal.SIGINT, None)