import sqlite3
import os

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# Database path consistent with project configuration
DATABASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "database", "trading.db"
)


class StatisticsAnalyzer:

    def __init__(self, db_path=DATABASE):
        self.db_path = os.path.abspath(db_path)

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    # ======================================================
    # LOAD DATA
    # ======================================================

    def fetch_all_as_dicts(self, table_name):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = [dict(r) for r in cursor.fetchall()]
        except Exception:
            rows = []
        finally:
            conn.close()
        return rows

    # ======================================================
    # GENERATE REPORT
    # ======================================================

    def generate_report(self):
        signals = self.fetch_all_as_dicts("signals")
        outcomes = self.fetch_all_as_dicts("outcomes")
        snapshots = self.fetch_all_as_dicts("snapshots")
        trades = self.fetch_all_as_dicts("trades")

        total_signals = len(signals)
        tracked_signal_ids = set(s.get("signal_id") for s in snapshots if s.get("signal_id"))
        tracked_signals = len(tracked_signal_ids)
        completed_outcomes = len(outcomes)
        paper_trades = len(trades)

        # Decision Counts
        decision_counts = {"BUY": 0, "WATCH": 0, "SKIP": 0}
        for s in signals:
            d = str(s.get("decision", "")).upper()
            if d in ["BUY", "STRONG BUY"]:
                decision_counts["BUY"] += 1
            elif d == "WATCH":
                decision_counts["WATCH"] += 1
            elif d == "SKIP":
                decision_counts["SKIP"] += 1

        # Metrics from Outcomes
        if outcomes:
            max_returns = [float(o.get("max_return", 0.0) or 0.0) for o in outcomes]
            min_returns = [float(o.get("min_return", 0.0) or 0.0) for o in outcomes]
            durations = [float(o.get("tracking_duration", 0.0) or 0.0) for o in outcomes]

            avg_return = sum(max_returns) / len(max_returns)
            sorted_returns = sorted(max_returns)
            n = len(sorted_returns)
            med_return = (sorted_returns[n // 2] if n % 2 != 0 else (sorted_returns[n // 2 - 1] + sorted_returns[n // 2]) / 2) if n > 0 else 0.0

            max_ret_val = max(max_returns) if max_returns else 0.0
            min_ret_val = min(min_returns) if min_returns else 0.0

            rugged_count = sum(1 for o in outcomes if o.get("rugged"))
            ret_2x_count = sum(1 for o in outcomes if o.get("returned_2x"))
            ret_5x_count = sum(1 for o in outcomes if o.get("returned_5x"))
            ret_10x_count = sum(1 for o in outcomes if o.get("returned_10x"))

            rug_pct = (rugged_count / completed_outcomes) * 100
            pct_2x = (ret_2x_count / completed_outcomes) * 100
            pct_5x = (ret_5x_count / completed_outcomes) * 100
            pct_10x = (ret_10x_count / completed_outcomes) * 100
            avg_holding = sum(durations) / len(durations) if durations else 0.0
        else:
            avg_return = med_return = max_ret_val = min_ret_val = 0.0
            rug_pct = pct_2x = pct_5x = pct_10x = avg_holding = 0.0

        print("\n==================================================")
        print("PROJECT STATISTICS REPORT")
        print("==================================================")
        print(f"Total Signals       : {total_signals}")
        print(f"Tracked Signals     : {tracked_signals}")
        print(f"Completed Outcomes  : {completed_outcomes}")
        print(f"Paper Trades        : {paper_trades}")
        print(f"  |-- BUY           : {decision_counts['BUY']}")
        print(f"  |-- WATCH         : {decision_counts['WATCH']}")
        print(f"  +-- SKIP          : {decision_counts['SKIP']}")
        print("--------------------------------------------------")
        print(f"Average Return      : {avg_return:.2f}%")
        print(f"Median Return       : {med_return:.2f}%")
        print(f"Maximum Return      : {max_ret_val:.2f}%")
        print(f"Minimum Return      : {min_ret_val:.2f}%")
        print(f"Rug %               : {rug_pct:.2f}%")
        print(f"2x %                : {pct_2x:.2f}%")
        print(f"5x %                : {pct_5x:.2f}%")
        print(f"10x %               : {pct_10x:.2f}%")
        print(f"Avg Holding Time    : {avg_holding:.1f}s")
        print("==================================================")

        # ======================================================
        # SCORE BUCKET ANALYSIS
        # ======================================================
        bucket_results = self.analyze_score_buckets(signals, outcomes)

        return {
            "total_signals": total_signals,
            "tracked_signals": tracked_signals,
            "completed_outcomes": completed_outcomes,
            "paper_trades": paper_trades,
            "decision_counts": decision_counts,
            "avg_return": avg_return,
            "med_return": med_return,
            "max_return": max_ret_val,
            "min_return": min_ret_val,
            "rug_pct": rug_pct,
            "pct_2x": pct_2x,
            "pct_5x": pct_5x,
            "pct_10x": pct_10x,
            "avg_holding_time": avg_holding,
            "score_buckets": bucket_results
        }

    # ======================================================
    # SCORE BUCKETS
    # ======================================================

    def analyze_score_buckets(self, signals=None, outcomes=None):
        if signals is None:
            signals = self.fetch_all_as_dicts("signals")
        if outcomes is None:
            outcomes = self.fetch_all_as_dicts("outcomes")

        outcomes_by_id = {o.get("signal_id"): o for o in outcomes if o.get("signal_id")}

        buckets = [
            ("0-49", 0, 49.99),
            ("50-59", 50, 59.99),
            ("60-69", 60, 69.99),
            ("70-79", 70, 79.99),
            ("80-89", 80, 89.99),
            ("90-100", 90, 100)
        ]

        print("\n==========================================================================================")
        print("SCORE BUCKET ANALYSIS")
        print("==========================================================================================")
        print(f"{'Bucket':<8} | {'Signals':<8} | {'Avg Ret %':<10} | {'Med Ret %':<10} | {'Rug %':<8} | {'2x %':<8} | {'5x %':<8} | {'10x %':<8} | {'Win Rate %':<10}")
        print("-" * 94)

        bucket_summary = []

        for label, min_val, max_val in buckets:
            matching = []
            for s in signals:
                sid = s.get("signal_id")
                score = float(s.get("final_score", 0.0) or 0.0)
                if sid in outcomes_by_id and min_val <= score <= max_val:
                    out = outcomes_by_id[sid]
                    matching.append({**s, **out})

            count = len(matching)
            if count > 0:
                rets = [float(m.get("max_return", 0.0) or 0.0) for m in matching]
                avg_ret = sum(rets) / count
                sorted_r = sorted(rets)
                med_ret = sorted_r[count // 2] if count % 2 != 0 else (sorted_r[count // 2 - 1] + sorted_r[count // 2]) / 2

                rug_cnt = sum(1 for m in matching if m.get("rugged"))
                r2x_cnt = sum(1 for m in matching if m.get("returned_2x"))
                r5x_cnt = sum(1 for m in matching if m.get("returned_5x"))
                r10x_cnt = sum(1 for m in matching if m.get("returned_10x"))

                rug_rate = (rug_cnt / count) * 100
                r2x_rate = (r2x_cnt / count) * 100
                r5x_rate = (r5x_cnt / count) * 100
                r10x_rate = (r10x_cnt / count) * 100
                win_rate = r2x_rate
            else:
                avg_ret = med_ret = rug_rate = r2x_rate = r5x_rate = r10x_rate = win_rate = 0.0

            print(f"{label:<8} | {count:<8} | {avg_ret:<10.2f} | {med_ret:<10.2f} | {rug_rate:<8.1f} | {r2x_rate:<8.1f} | {r5x_rate:<8.1f} | {r10x_rate:<8.1f} | {win_rate:<10.1f}")

            bucket_summary.append({
                "bucket": label,
                "signals": count,
                "avg_return": avg_ret,
                "median_return": med_ret,
                "rug_rate": rug_rate,
                "2x_rate": r2x_rate,
                "5x_rate": r5x_rate,
                "10x_rate": r10x_rate,
                "win_rate": win_rate
            })

        print("==========================================================================================\n")
        if HAS_PANDAS:
            return pd.DataFrame(bucket_summary)
        return bucket_summary


def show_statistics():
    analyzer = StatisticsAnalyzer()
    return analyzer.generate_report()


if __name__ == "__main__":
    show_statistics()