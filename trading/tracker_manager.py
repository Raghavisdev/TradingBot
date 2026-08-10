import threading
import time
from datetime import datetime

from trading.signal_tracker import SignalTracker
from database.database import database
from knowledge.coin import Coin
from config import SNAPSHOT_INTERVAL


def parse_timestamp(ts_str):
    if not ts_str:
        return time.time()
    try:
        dt = datetime.fromisoformat(str(ts_str))
        return dt.timestamp()
    except Exception:
        return time.time()


class TrackerManager:

    def __init__(self):

        self.trackers = {}

        self.running = False

        self.thread = None

        self.lock = threading.Lock()

    # =====================================================
    # START MANAGER
    # =====================================================

    def start(self):

        if self.running:
            return

        self.running = True

        # Re-hydrate active trackers or finalize > 24h outcomes on startup
        self.recover_trackers()

        self.thread = threading.Thread(
            target=self.run,
            daemon=True
        )

        self.thread.start()

        print("\n===================================")
        print("Tracker Manager Started")
        print("===================================\n")

    # =====================================================
    # RECOVER TRACKERS FROM DATABASE
    # =====================================================

    def recover_trackers(self):
        """
        Queries all uncompleted signals from SQLite on startup.
        If tracking window (> 24h) has elapsed: finalizes and saves outcome.
        If tracking window (< 24h) is still active: restores tracker state and resumes live tracking.
        """
        print("\n===================================")
        print("Recovering Signal Trackers...")
        print("===================================")

        try:
            uncompleted = database.get_uncompleted_signals()
            all_signals = database.get_signals()
            all_outcomes = database.get_outcomes()

            already_completed_count = len(all_outcomes)
            unfinished_count = len(uncompleted)

            print(f"[DB STATS] Total Signals: {len(all_signals)} | Completed Outcomes: {already_completed_count} | Unfinished Signals: {unfinished_count}")

            if not uncompleted:
                print("[OK] No uncompleted signals found in database.\n")
                return

            recovered_count = 0
            completed_count = 0

            for sig_row in uncompleted:
                coin = Coin()
                coin.signal_id = sig_row["signal_id"]
                coin.signal_time = sig_row.get("timestamp")
                coin.source = sig_row.get("source", "GemTools")
                coin.symbol = sig_row.get("symbol")
                coin.name = sig_row.get("name")
                coin.contract = sig_row.get("contract")
                coin.raw_message = sig_row.get("telegram_message", "")
                coin.signal_market_cap = sig_row.get("signal_market_cap")
                coin.signal_price = sig_row.get("signal_price")
                coin.gt_score = sig_row.get("gt_score", 0)
                coin.decision = sig_row.get("decision", "")
                coin.final_score = sig_row.get("final_score", 0)
                coin.bought = bool(sig_row.get("bought", 0))
                coin.buy_blocked_by = sig_row.get("buy_blocked_by", "")

                # Determine start timestamp
                raw_started = sig_row.get("tracking_started")
                if raw_started and float(raw_started) > 0:
                    start_ts = float(raw_started)
                else:
                    start_ts = parse_timestamp(coin.signal_time)

                coin.tracking_started = start_ts

                # Fetch snapshots from DB
                snapshots = database.get_snapshots_for_signal(coin.signal_id)

                # Initialize tracker instance and restore cumulative state
                tracker = SignalTracker(coin)
                tracker.created_at = start_ts
                tracker.restore_state(snapshots)

                elapsed = time.time() - start_ts

                if elapsed >= 86400:
                    tracker.finished = True
                    coin.tracking_finished = start_ts + 86400
                    coin.tracking = False
                    database.save_outcome(coin)
                    completed_count += 1
                    print(f"[OUTCOME] Recovered & Saved Outcome : {coin.symbol} (Elapsed: {elapsed/3600:.1f}h)")
                else:
                    with self.lock:
                        self.trackers[coin.signal_id] = tracker
                    recovered_count += 1
                    print(f"[TRACKING] Resumed Live Tracking     : {coin.symbol} (Elapsed: {elapsed/3600:.1f}h, {len(snapshots)} snapshots)")

            print(f"[SUCCESS] Recovery Summary:")
            print(f"  |-- Unfinished signals found : {unfinished_count}")
            print(f"  |-- Trackers restored        : {recovered_count}")
            print(f"  |-- Outcomes finalized       : {completed_count}")
            print(f"  +-- Already completed        : {already_completed_count}\n")

        except Exception as e:
            print("[ERROR] Tracker Recovery Error :", e)

    # =====================================================
    # STOP MANAGER
    # =====================================================

    def stop(self):

        self.running = False

    # =====================================================
    # ADD NEW SIGNAL
    # =====================================================

    def start_tracking(self, coin):

        with self.lock:

            if coin.signal_id in self.trackers:

                return

            tracker = SignalTracker(coin)

            self.trackers[coin.signal_id] = tracker

        print(f"[TRACKING] Started : {coin.symbol}")

    # =====================================================
    # REMOVE TRACKER
    # =====================================================

    def stop_tracking(self, signal_id):

        with self.lock:

            if signal_id in self.trackers:

                del self.trackers[signal_id]

    # =====================================================
    # UPDATE ALL TRACKERS
    # =====================================================

    def update_all(self):

        with self.lock:

            remove_list = []

            for signal_id, tracker in list(self.trackers.items()):

                try:

                    tracker.update()

                    # Save snapshot ONLY if API update succeeded
                    if not getattr(tracker.coin, "last_api_success", True):
                        print(f"[SNAPSHOT SKIPPED] Stale snapshot skipped due to API failure: {tracker.coin.symbol}")
                    else:
                        snapshot = tracker.build_snapshot()
                        database.save_snapshot(snapshot)

                        # Paper Lab forward snapshot feed (Phase 3 Observer)
                        try:
                            from analytics.paper_lab.lab_engine import get_paper_lab_engine
                            get_paper_lab_engine().on_snapshot(snapshot)
                        except Exception as lab_e:
                            print(f"[PAPER LAB ERROR] Snapshot dispatch failed: {lab_e}")

                    if tracker.finished:

                        database.save_outcome(tracker.coin)

                        remove_list.append(signal_id)

                except Exception as e:

                    print("Tracker Error :", e)

            for signal_id in remove_list:

                del self.trackers[signal_id]

    # =====================================================
    # LOOP
    # =====================================================

    def run(self):

        while self.running:

            self.update_all()

            time.sleep(SNAPSHOT_INTERVAL)

    # =====================================================
    # STATUS
    # =====================================================

    def print_status(self):

        print("\n==============================")
        print("TRACKER STATUS")
        print("==============================")
        print("Active :", len(self.trackers))
        print("==============================\n")


tracker_manager = TrackerManager()

tracker_manager.start()