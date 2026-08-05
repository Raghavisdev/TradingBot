import time

from collectors.live_market import update_market
from config import TRACKING_DURATION, MAX_API_FAILURES
from ai_engine.market_health import calculate_market_health
from ai_engine.exit_ai import get_exit_decision


class SignalTracker:

    def __init__(self, coin):

        self.coin = coin

        self.signal_id = coin.signal_id

        # Preserve existing tracking_started timestamp if present, otherwise set to now
        if getattr(self.coin, "tracking_started", None) and float(self.coin.tracking_started) > 0:
            self.created_at = float(self.coin.tracking_started)
        else:
            self.created_at = time.time()
            self.coin.tracking_started = self.created_at

        self.last_update = time.time()

        self.snapshots = 0

        self.finished = False

        self.outcome = None

        self.coin.tracking = True

        # Reset min_return to None so the sentinel works correctly
        # (0 is a valid return value, so we cannot use it as "unset")
        self.coin.min_return = None

        # Track consecutive API failures to stop infinite polling on invalid/dead contracts
        self.consecutive_api_failures = 0

    # =====================================================
    # UPDATE TRACKER
    # =====================================================

    def update(self):

        self.last_update = time.time()

        self.snapshots += 1

        # ---------------------------------------------
        # Update Live Market Data
        # ---------------------------------------------

        update_market(self.coin)

        # Track consecutive API failures (no trading pairs / network error / invalid contract)
        if not getattr(self.coin, "last_api_success", True):
            self.consecutive_api_failures += 1
        else:
            self.consecutive_api_failures = 0

        # Stop infinite polling after MAX_API_FAILURES consecutive API failures
        if self.consecutive_api_failures >= MAX_API_FAILURES:
            self.finished = True
            self.coin.tracking_finished = time.time()
            self.coin.tracking = False
            self.coin.tracking_end_reason = "MAX_API_FAILURES"
            print(f"[TRACKER STOPPED] Max consecutive failures reached ({self.consecutive_api_failures}) for {self.coin.symbol}. Stopping tracker.")

        # ---------------------------------------------
        # Peak Market Cap
        # ---------------------------------------------

        if self.coin.live_market_cap is not None:

            if (
                self.coin.peak_market_cap is None
                or self.coin.live_market_cap > self.coin.peak_market_cap
            ):

                self.coin.peak_market_cap = self.coin.live_market_cap

        # ---------------------------------------------
        # Lowest Market Cap
        # ---------------------------------------------

        if self.coin.live_market_cap is not None:

            if (
                self.coin.lowest_market_cap is None
                or self.coin.live_market_cap < self.coin.lowest_market_cap
            ):

                self.coin.lowest_market_cap = self.coin.live_market_cap

        # ---------------------------------------------
        # Peak Price
        # ---------------------------------------------

        if self.coin.price is not None:

            if (
                self.coin.peak_price is None
                or self.coin.price > self.coin.peak_price
            ):

                self.coin.peak_price = self.coin.price

        # ---------------------------------------------
        # Lowest Price
        # ---------------------------------------------

        if self.coin.price is not None:

            if (
                self.coin.lowest_price is None
                or self.coin.price < self.coin.lowest_price
            ):

                self.coin.lowest_price = self.coin.price

        # ---------------------------------------------
        # Return
        # ---------------------------------------------

        if (
            self.coin.signal_market_cap
            and self.coin.live_market_cap
        ):

            current_return = (
                (
                    self.coin.live_market_cap
                    - self.coin.signal_market_cap
                )
                /
                self.coin.signal_market_cap
            ) * 100

            # Max Return
            self.coin.max_return = max(
                self.coin.max_return,
                current_return
            )

            # Min Return (most negative drawdown)
            if self.coin.min_return is None:
                self.coin.min_return = current_return
            else:
                self.coin.min_return = min(
                    self.coin.min_return,
                    current_return
                )

            # Multiplier milestones (based on peak return)
            if self.coin.max_return >= 100:
                self.coin.returned_2x = True

            if self.coin.max_return >= 400:
                self.coin.returned_5x = True

            if self.coin.max_return >= 900:
                self.coin.returned_10x = True

            # Time To Peak: seconds since tracking started when peak was last updated
            if (
                self.coin.peak_market_cap is not None
                and self.coin.live_market_cap >= self.coin.peak_market_cap
            ):
                self.coin.time_to_peak = time.time() - self.created_at

        # ---------------------------------------------
        # Rug Detection
        # ---------------------------------------------

        if (
            self.coin.signal_market_cap
            and self.coin.live_market_cap
        ):

            if self.coin.live_market_cap < self.coin.signal_market_cap * 0.20:

                self.coin.rugged = True

        # ---------------------------------------------
        # Snapshot Count
        # ---------------------------------------------

        self.coin.snapshot_count = self.snapshots

        # ---------------------------------------------
        # Finish After Tracking Duration
        # ---------------------------------------------

        if time.time() - self.created_at > TRACKING_DURATION:

            self.finished = True
            self.coin.tracking_finished = time.time()
            self.coin.tracking = False
            self.coin.tracking_end_reason = "NORMAL_24H"

    # =====================================================
    # BUILD SNAPSHOT
    # =====================================================

    def build_snapshot(self):

        return {

            "signal_id": self.coin.signal_id,

            "timestamp": time.time(),

            "market_cap": self.coin.live_market_cap,

            "price": self.coin.price,

            "liquidity": self.coin.liquidity,

            "volume": self.coin.volume_5m,

            "holders": self.coin.holders,

            "buys": self.coin.buys_5m,

            "sells": self.coin.sells_5m,

            "market_health": getattr(
                self.coin,
                "market_health",
                0
            ),

            "exit_action": getattr(
                self.coin,
                "exit_action",
                "HOLD"
            ),

            "exit_confidence": getattr(
                self.coin,
                "exit_confidence",
                0
            )
        }

    # =====================================================
    # RESTORE STATE FROM DB SNAPSHOTS
    # =====================================================

    def restore_state(self, snapshots):
        """
        Restores cumulative outcome metrics from historical snapshot records in SQLite.
        """
        if not snapshots:
            return

        self.snapshots = len(snapshots)
        self.coin.snapshot_count = self.snapshots

        signal_mc = self.coin.signal_market_cap or 0

        for snap in snapshots:
            mc = snap.get("market_cap")
            price = snap.get("price")
            ts = float(snap.get("timestamp") or 0)

            # Peak & Lowest Market Cap
            if mc is not None:
                if self.coin.peak_market_cap is None or mc > self.coin.peak_market_cap:
                    self.coin.peak_market_cap = mc
                    if self.created_at and ts > self.created_at:
                        self.coin.time_to_peak = ts - self.created_at

                if self.coin.lowest_market_cap is None or mc < self.coin.lowest_market_cap:
                    self.coin.lowest_market_cap = mc

            # Peak & Lowest Price
            if price is not None:
                if self.coin.peak_price is None or price > self.coin.peak_price:
                    self.coin.peak_price = price

                if self.coin.lowest_price is None or price < self.coin.lowest_price:
                    self.coin.lowest_price = price

            # Return & Drawdown
            if signal_mc > 0 and mc is not None:
                curr_ret = ((mc - signal_mc) / signal_mc) * 100

                self.coin.max_return = max(self.coin.max_return, curr_ret)

                if self.coin.min_return is None:
                    self.coin.min_return = curr_ret
                else:
                    self.coin.min_return = min(self.coin.min_return, curr_ret)

                if curr_ret <= -80 or mc < signal_mc * 0.20:
                    self.coin.rugged = True

        # Restore latest market state on the coin object
        last_snap = snapshots[-1]
        if last_snap.get("market_cap") is not None:
            self.coin.live_market_cap = float(last_snap.get("market_cap"))
            self.coin.market_cap = float(last_snap.get("market_cap"))
        if last_snap.get("price") is not None:
            self.coin.price = float(last_snap.get("price"))
        if last_snap.get("liquidity") is not None:
            self.coin.liquidity = float(last_snap.get("liquidity"))
        if last_snap.get("volume") is not None:
            self.coin.volume_5m = float(last_snap.get("volume"))
        if last_snap.get("holders") is not None:
            self.coin.holders = int(last_snap.get("holders"))
        if last_snap.get("buys") is not None:
            self.coin.buys_5m = int(last_snap.get("buys"))
        if last_snap.get("sells") is not None:
            self.coin.sells_5m = int(last_snap.get("sells"))
        if last_snap.get("market_health") is not None:
            self.coin.market_health = float(last_snap.get("market_health"))

        # Milestones based on peak max_return
        if self.coin.max_return >= 100:
            self.coin.returned_2x = True
        if self.coin.max_return >= 400:
            self.coin.returned_5x = True
        if self.coin.max_return >= 900:
            self.coin.returned_10x = True

    # =====================================================
    # FINISH
    # =====================================================

    def finish(self):

        self.finished = True

        self.coin.tracking = False

        self.coin.tracking_finished = time.time()

        if not getattr(self.coin, "tracking_end_reason", None) or self.coin.tracking_end_reason == "NORMAL_24H":
            self.coin.tracking_end_reason = "MANUAL_STOP"