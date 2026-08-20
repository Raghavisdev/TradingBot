
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb


# ============================================================
# CONFIGURATION
# ============================================================

DB = "database/trading.db"

TRAIN = "analytics/s7_dataset/s7_train.csv"
VALIDATION = "analytics/s7_dataset/s7_validation.csv"
TEST = "analytics/s7_dataset/s7_test.csv"

MODEL_2X = "analytics/s7_models/model_Y_2x.ubj"
MODEL_RUG = "analytics/s7_models/model_Y_rug.ubj"

REPORT_PATH = (
    "analytics/s7_models/"
    "S7_V2_CONVERGENCE_V3_REPORT.txt"
)

TRADES_PATH = (
    "analytics/s7_models/"
    "S7_V2_CONVERGENCE_V3_TRADES.csv"
)


# ============================================================
# MODEL LOADING
# ============================================================

def load_model(path):
    print(f"Loading model: {path}")

    model = xgb.XGBClassifier()
    model.load_model(path)

    return model


def get_model_features(model):
    """
    Return the exact feature names stored inside the trained
    XGBoost model.

    This prevents feature-name mismatch between the training
    dataset and the split CSV files.
    """

    names = model.get_booster().feature_names

    if not names:
        raise RuntimeError(
            "Trained XGBoost model has no feature names."
        )

    return list(names)


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_s6_traded_ids(con):
    """
    Authoritative definition of whether S6 Moonshot actually
    traded a signal.

    IMPORTANT:
    signals.decision == SKIP does NOT mean S6 Moonshot skipped it.

    The paper_lab_trades table is the source of truth for actual
    S6 Moonshot execution.
    """

    rows = con.execute(
        """
        SELECT DISTINCT signal_id
        FROM paper_lab_trades
        WHERE strategy_id = 'S6_Moonshot_Ladder'
        """
    ).fetchall()

    return {
        str(row[0])
        for row in rows
        if row[0] is not None
    }


def remove_s6_traded(df, traded_ids):
    """
    Remove every signal that S6 Moonshot actually traded.
    """

    result = df.copy()

    result["signal_id"] = (
        result["signal_id"]
        .astype(str)
    )

    return result[
        ~result["signal_id"].isin(traded_ids)
    ].copy()


def restore_s6_decision_feature(con, df):
    """
    Restore X_s6_decision from the authoritative signals table.

    V2 models were trained with X_s6_decision, but the split CSV
    does not necessarily contain that feature.

    Encoding:
        SKIP  -> 0
        WATCH -> 1
        BUY   -> 2
        missing/unknown -> NaN
    """

    result = df.copy()

    result["signal_id"] = (
        result["signal_id"]
        .astype(str)
    )

    ids = result["signal_id"].tolist()

    if not ids:
        result["X_s6_decision"] = np.nan
        return result

    placeholders = ",".join(
        "?" for _ in ids
    )

    rows = con.execute(
        f"""
        SELECT signal_id, decision
        FROM signals
        WHERE signal_id IN ({placeholders})
        """,
        ids,
    ).fetchall()

    decision_by_id = {
        str(signal_id): decision
        for signal_id, decision in rows
    }

    decision_map = {
        "SKIP": 0.0,
        "WATCH": 1.0,
        "BUY": 2.0,
    }

    result["X_s6_decision"] = (
        result["signal_id"]
        .map(decision_by_id)
        .map(decision_map)
    )

    return result


def attach_outcomes(con, df):
    """
    Attach historical outcomes for validation/test diagnostics.

    This function is used for threshold selection on validation
    and for final diagnostic reporting.

    Outcomes are NEVER used to trigger an actual replay trade.
    """

    result = df.copy()

    result["signal_id"] = (
        result["signal_id"]
        .astype(str)
    )

    outcomes = pd.read_sql_query(
        """
        SELECT
            signal_id,
            max_return,
            min_return,
            rugged,
            returned_2x,
            returned_5x,
            returned_10x
        FROM outcomes
        """,
        con,
    )

    outcomes["signal_id"] = (
        outcomes["signal_id"]
        .astype(str)
    )

    # Avoid duplicate columns if the CSV already contains them.
    for col in [
        "max_return",
        "min_return",
        "rugged",
        "returned_2x",
        "returned_5x",
        "returned_10x",
    ]:
        if col in result.columns:
            result = result.drop(
                columns=[col]
            )

    result = result.merge(
        outcomes,
        on="signal_id",
        how="left",
    )

    return result


# ============================================================
# FEATURE PREPARATION
# ============================================================

def prepare_model_input(df, feature_names):
    """
    Construct exactly the feature matrix expected by XGBoost.

    Missing columns are created as NaN.

    Existing extra columns are ignored.

    Column order exactly matches the trained model.
    """

    x = df.copy()

    for feature in feature_names:

        if feature not in x.columns:
            x[feature] = np.nan

    x = x[feature_names].copy()

    x = x.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    for col in x.columns:
        x[col] = pd.to_numeric(
            x[col],
            errors="coerce",
        )

    return x


def score_population(
    df,
    model_2x,
    model_rug,
    feature_names,
):
    """
    Generate p_2x and p_rug without modifying the underlying
    dataset.
    """

    result = df.copy()

    x = prepare_model_input(
        result,
        feature_names,
    )

    result["p_2x"] = (
        model_2x.predict_proba(x)[:, 1]
    )

    result["p_rug"] = (
        model_rug.predict_proba(x)[:, 1]
    )

    return result


# ============================================================
# VALIDATION THRESHOLD SELECTION
# ============================================================

def economic_proxy(row):
    """
    Conservative validation-only economic proxy.

    This is NOT the final P&L.

    It is used only to select thresholds from validation.

        5x winner -> +4 units
        2x winner -> +1 unit
        rug       -> -1 unit
        otherwise -> 0
    """

    if int(row.get("returned_5x", 0) or 0):
        return 4.0

    if int(row.get("returned_2x", 0) or 0):
        return 1.0

    if int(row.get("rugged", 0) or 0):
        return -1.0

    return 0.0


def choose_thresholds(validation):
    """
    Select rescue thresholds exclusively from validation.

    Final test is completely untouched during this process.
    """

    if validation.empty:
        raise RuntimeError(
            "Validation has zero genuinely S6-untraded signals."
        )

    best = None

    opportunity_thresholds = np.arange(
        0.20,
        0.91,
        0.025,
    )

    rug_thresholds = np.arange(
        0.20,
        0.96,
        0.025,
    )

    for opp_threshold in opportunity_thresholds:

        for rug_threshold in rug_thresholds:

            selected = validation[
                (validation["p_2x"] >= opp_threshold)
                &
                (validation["p_rug"] <= rug_threshold)
            ]

            if len(selected) < 2:
                continue

            proxy_returns = [
                economic_proxy(row)
                for _, row in selected.iterrows()
            ]

            proxy_score = float(
                np.sum(proxy_returns)
            )

            rugs = int(
                selected["rugged"]
                .fillna(0)
                .astype(int)
                .sum()
            )

            count = len(selected)

            # Prefer higher proxy score.
            #
            # On ties:
            #   1. fewer rugs
            #   2. fewer trades
            #
            # This avoids unnecessarily broad rescue populations.
            candidate = (
                proxy_score,
                -rugs,
                -count,
            )

            if (
                best is None
                or candidate > best["ranking"]
            ):
                best = {
                    "opp_threshold": float(
                        opp_threshold
                    ),
                    "rug_threshold": float(
                        rug_threshold
                    ),
                    "proxy_score": proxy_score,
                    "rugs": rugs,
                    "count": count,
                    "ranking": candidate,
                }

    if best is None:
        raise RuntimeError(
            "No valid threshold combination found."
        )

    return best


# ============================================================
# REAL S6 EXECUTION REPLAY
# ============================================================

def get_signal(con, signal_id):

    row = con.execute(
        """
        SELECT
            signal_id,
            timestamp,
            symbol,
            contract,
            signal_price,
            signal_market_cap,
            gt_score,
            final_score,
            decision
        FROM signals
        WHERE signal_id = ?
        """,
        (str(signal_id),),
    ).fetchone()

    if not row:
        return None

    columns = [
        "signal_id",
        "timestamp",
        "symbol",
        "contract",
        "signal_price",
        "signal_market_cap",
        "gt_score",
        "final_score",
        "decision",
    ]

    return dict(
        zip(columns, row)
    )


def parse_timestamp(value):

    if value is None:
        return None

    try:
        return pd.to_datetime(
            value
        ).timestamp()
    except Exception:
        try:
            return float(value)
        except Exception:
            return None


def get_entry_snapshot(
    con,
    signal_id,
    t0,
):
    """
    Use the first valid executable snapshot at or after T0.

    No outcome information is used here.
    """

    row = con.execute(
        """
        SELECT
            CAST(timestamp AS REAL),
            price,
            market_cap,
            liquidity,
            volume,
            buys,
            sells,
            holders,
            market_health
        FROM snapshots
        WHERE signal_id = ?
          AND CAST(timestamp AS REAL) >= ?
          AND CAST(price AS REAL) > 0
        ORDER BY CAST(timestamp AS REAL) ASC
        LIMIT 1
        """,
        (
            str(signal_id),
            float(t0),
        ),
    ).fetchone()

    if not row:
        return None

    columns = [
        "timestamp",
        "price",
        "market_cap",
        "liquidity",
        "volume",
        "buys",
        "sells",
        "holders",
        "market_health",
    ]

    return dict(
        zip(columns, row)
    )


def get_future_snapshots(
    con,
    signal_id,
    entry_time,
):
    """
    Only snapshots strictly AFTER the hypothetical entry.
    """

    rows = con.execute(
        """
        SELECT
            CAST(timestamp AS REAL),
            price,
            market_cap,
            liquidity,
            volume,
            buys,
            sells,
            holders,
            market_health,
            exit_action,
            exit_confidence
        FROM snapshots
        WHERE signal_id = ?
          AND CAST(timestamp AS REAL) > ?
        ORDER BY CAST(timestamp AS REAL) ASC
        """,
        (
            str(signal_id),
            float(entry_time),
        ),
    ).fetchall()

    columns = [
        "timestamp",
        "price",
        "market_cap",
        "liquidity",
        "volume",
        "buys",
        "sells",
        "holders",
        "market_health",
        "exit_action",
        "exit_confidence",
    ]

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def build_entry_signal(
    signal,
    snapshot,
):
    """
    Build the signal structure expected by the real S6 strategy.
    """

    result = dict(signal)

    result["signal_time"] = float(
        snapshot["timestamp"]
    )

    result["signal_price"] = float(
        snapshot["price"]
    )

    signal_mc = float(
        signal.get("signal_market_cap")
        or 0.0
    )

    if signal_mc <= 0:
        signal_mc = float(
            snapshot.get("market_cap")
            or 0.0
        )

    result["signal_market_cap"] = signal_mc

    result["liquidity"] = snapshot.get(
        "liquidity"
    )

    result["volume"] = snapshot.get(
        "volume"
    )

    result["buys"] = snapshot.get(
        "buys"
    )

    result["sells"] = snapshot.get(
        "sells"
    )

    result["holders"] = snapshot.get(
        "holders"
    )

    result["market_health"] = snapshot.get(
        "market_health"
    )

    buys = float(
        snapshot.get("buys")
        or 0.0
    )

    sells = float(
        snapshot.get("sells")
        or 0.0
    )

    if sells > 0:
        result["buy_sell_ratio"] = (
            buys / sells
        )
    elif buys > 0:
        result["buy_sell_ratio"] = min(
            buys,
            3.0,
        )
    else:
        result["buy_sell_ratio"] = 1.0

    return result


def replay_candidate(
    con,
    strategy,
    signal_id,
):
    """
    Replay ONE genuinely S6-untraded signal through the real
    S6 Moonshot entry/exit implementation.

    Outcomes are never consulted to make trading decisions.
    """

    signal = get_signal(
        con,
        signal_id,
    )

    if signal is None:
        return {
            "signal_id": signal_id,
            "status": "NO_SIGNAL",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
        }

    t0 = parse_timestamp(
        signal.get("timestamp")
    )

    if t0 is None:
        return {
            "signal_id": signal_id,
            "status": "INVALID_T0",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
        }

    entry_snapshot = get_entry_snapshot(
        con,
        signal_id,
        t0,
    )

    if entry_snapshot is None:
        return {
            "signal_id": signal_id,
            "status": "NO_ENTRY_SNAPSHOT",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
        }

    entry_signal = build_entry_signal(
        signal,
        entry_snapshot,
    )

    # --------------------------------------------------------
    # Isolated rescue sleeve
    # --------------------------------------------------------

    from analytics.paper_lab.lab_portfolio import (
        LabPortfolio,
    )

    portfolio = LabPortfolio(
        strategy_id="S7_V3_RESCUE",
        initial_cash=500.0,
        max_open=8,
        min_cash=2.0,
    )

    amount = strategy.evaluate_entry(
        entry_signal,
        portfolio,
    )

    if amount <= 0:
        return {
            "signal_id": signal_id,
            "status": "S6_ENTRY_REJECTED",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
        }

    entry_time = float(
        entry_snapshot["timestamp"]
    )

    entry_price = float(
        entry_snapshot["price"]
    )

    entry_mc = float(
        entry_snapshot["market_cap"]
        or 0.0
    )

    pos = portfolio.open_position(
        trade_id=(
            f"S7_V3_{signal_id[:8]}"
        ),
        strategy_version=(
            strategy.strategy_version
        ),
        signal_id=signal_id,
        symbol=(
            signal.get("symbol")
            or "?"
        ),
        contract=(
            signal.get("contract")
            or ""
        ),
        entry_time=entry_time,
        entry_price=entry_price,
        entry_mc=entry_mc,
        invested=float(amount),
    )

    if not pos:
        return {
            "signal_id": signal_id,
            "status": "PORTFOLIO_REJECTED",
            "invested": 0.0,
            "pnl": 0.0,
            "realized_pct": 0.0,
        }

    # --------------------------------------------------------
    # Future snapshots
    # --------------------------------------------------------

    future = get_future_snapshots(
        con,
        signal_id,
        entry_time,
    )

    closed = False

    for snapshot in future:

        action, pct, reason = (
            strategy.evaluate_exit(
                snapshot,
                pos,
            )
        )

        ts = float(
            snapshot["timestamp"]
        )

        price = float(
            snapshot["price"]
            or 0.0
        )

        mc = float(
            snapshot["market_cap"]
            or 0.0
        )

        if action == "SELL_ALL":

            portfolio.close_position(
                pos,
                reason,
                ts,
                price,
                mc,
            )

            closed = True
            break

        if (
            action == "SELL_PCT"
            and pct > 0
        ):

            portfolio.close_position_by_partial_sell(
                pos,
                pct,
                reason,
                ts,
                price,
                mc,
            )

            if pos.remaining_pct <= 0.01:
                closed = True
                break

    # --------------------------------------------------------
    # Horizon close
    # --------------------------------------------------------

    if (
        not closed
        and pos.status == "OPEN"
        and future
    ):

        last = future[-1]

        portfolio.close_position(
            pos,
            "S7_V3_HORIZON_CLOSE",
            float(last["timestamp"]),
            float(last["price"] or 0.0),
            float(
                last["market_cap"]
                or 0.0
            ),
        )

    invested = float(
        pos.invested
    )

    pnl = float(
        pos.realized_pnl
    )

    realized_pct = (
        pnl / invested * 100.0
        if invested > 0
        else 0.0
    )

    return {
        "signal_id": signal_id,
        "status": "CLOSED",
        "invested": invested,
        "pnl": pnl,
        "realized_pct": realized_pct,
    }


# ============================================================
# ACTUAL S6 BASELINE
# ============================================================

def get_actual_s6_baseline(
    con,
    test_ids,
):
    """
    Actual recorded S6 Moonshot performance on final test.
    """

    trades = pd.read_sql_query(
        """
        SELECT
            signal_id,
            invested,
            realized_pnl,
            realized_pct,
            exit_reason
        FROM paper_lab_trades
        WHERE strategy_id = 'S6_Moonshot_Ladder'
        """,
        con,
    )

    if trades.empty:
        return trades

    trades["signal_id"] = (
        trades["signal_id"]
        .astype(str)
    )

    return trades[
        trades["signal_id"].isin(test_ids)
    ].copy()


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("S7 V3 — CORRECTED ECONOMIC CONVERGENCE")
    print("=" * 70)

    con = sqlite3.connect(DB)

    # --------------------------------------------------------
    # Load datasets
    # --------------------------------------------------------

    train = pd.read_csv(TRAIN)
    validation = pd.read_csv(VALIDATION)
    test = pd.read_csv(TEST)

    for df in [
        train,
        validation,
        test,
    ]:
        df["signal_id"] = (
            df["signal_id"]
            .astype(str)
        )

    print()
    print("DATASET")
    print("-" * 70)
    print("Train:", len(train))
    print("Validation:", len(validation))
    print("Final test:", len(test))

    # --------------------------------------------------------
    # Actual S6 coverage
    # --------------------------------------------------------

    s6_traded_ids = get_s6_traded_ids(
        con
    )

    validation_untraded = (
        remove_s6_traded(
            validation,
            s6_traded_ids,
        )
    )

    test_untraded = (
        remove_s6_traded(
            test,
            s6_traded_ids,
        )
    )

    print()
    print("ACTUAL S6 COVERAGE")
    print("-" * 70)

    print(
        "Validation S6-traded:",
        len(validation)
        - len(validation_untraded),
    )

    print(
        "Validation genuinely untraded:",
        len(validation_untraded),
    )

    print(
        "Test S6-traded:",
        len(test)
        - len(test_untraded),
    )

    print(
        "Test genuinely untraded:",
        len(test_untraded),
    )

    # --------------------------------------------------------
    # Restore authoritative S6 decision feature
    # --------------------------------------------------------

    validation_untraded = (
        restore_s6_decision_feature(
            con,
            validation_untraded,
        )
    )

    test_untraded = (
        restore_s6_decision_feature(
            con,
            test_untraded,
        )
    )

    # --------------------------------------------------------
    # Attach outcomes
    #
    # Validation outcomes are allowed for threshold selection.
    # Final-test outcomes are diagnostics only.
    # --------------------------------------------------------

    validation_untraded = attach_outcomes(
        con,
        validation_untraded,
    )

    test_untraded = attach_outcomes(
        con,
        test_untraded,
    )

    # --------------------------------------------------------
    # Load trained models
    # --------------------------------------------------------

    model_2x = load_model(
        MODEL_2X
    )

    model_rug = load_model(
        MODEL_RUG
    )

    feature_names_2x = (
        get_model_features(
            model_2x
        )
    )

    feature_names_rug = (
        get_model_features(
            model_rug
        )
    )

    if feature_names_2x != feature_names_rug:
        raise RuntimeError(
            "Y_2x and Y_rug models do not have "
            "identical feature schemas."
        )

    feature_names = feature_names_2x

    print()
    print("MODEL FEATURE SCHEMA")
    print("-" * 70)
    print(
        "Expected features:",
        len(feature_names),
    )

    print(
        "X_s6_decision present:",
        "X_s6_decision" in feature_names,
    )

    print()
    print(
        "Features:"
    )

    for feature in feature_names:
        print(
            " ",
            feature,
        )

    # --------------------------------------------------------
    # Score validation
    # --------------------------------------------------------

    validation_untraded = score_population(
        validation_untraded,
        model_2x,
        model_rug,
        feature_names,
    )

    # --------------------------------------------------------
    # Select thresholds ONLY from validation
    # --------------------------------------------------------

    threshold = choose_thresholds(
        validation_untraded
    )

    opp_threshold = (
        threshold["opp_threshold"]
    )

    rug_threshold = (
        threshold["rug_threshold"]
    )

    print()
    print("THRESHOLD SELECTION")
    print("-" * 70)

    print(
        f"Opportunity threshold: "
        f"{opp_threshold:.6f}"
    )

    print(
        f"Rug threshold:         "
        f"{rug_threshold:.6f}"
    )

    print(
        "Validation accepted:",
        threshold["count"],
    )

    print(
        "Validation rugs:",
        threshold["rugs"],
    )

    print(
        "Validation proxy score:",
        threshold["proxy_score"],
    )

    # --------------------------------------------------------
    # Score FINAL TEST
    #
    # This happens AFTER thresholds are locked.
    # --------------------------------------------------------

    test_untraded = score_population(
        test_untraded,
        model_2x,
        model_rug,
        feature_names,
    )

    # --------------------------------------------------------
    # Select final-test rescues
    # --------------------------------------------------------

    selected = test_untraded[
        (
            test_untraded["p_2x"]
            >= opp_threshold
        )
        &
        (
            test_untraded["p_rug"]
            <= rug_threshold
        )
    ].copy()

    print()
    print("FINAL TEST")
    print("-" * 70)

    print(
        "Genuinely S6-untraded:",
        len(test_untraded),
    )

    print(
        "Accepted S7 rescues:",
        len(selected),
    )

    if not selected.empty:

        print()
        print(
            "Accepted signals:"
        )

        print(
            selected[
                [
                    "signal_id",
                    "p_2x",
                    "p_rug",
                ]
            ].to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # Real S6 strategy
    # --------------------------------------------------------

    from analytics.paper_lab.strategies import (
        Strategy_S6_Moonshot_Ladder,
    )

    strategy = (
        Strategy_S6_Moonshot_Ladder()
    )

    # --------------------------------------------------------
    # Replay
    # --------------------------------------------------------

    replay_rows = []

    for signal_id in selected[
        "signal_id"
    ].astype(str):

        print()
        print(
            f"Replaying {signal_id[:8]}..."
        )

        result = replay_candidate(
            con,
            strategy,
            signal_id,
        )

        print(
            "  status:",
            result["status"],
        )

        print(
            "  invested: "
            f"${result['invested']:.4f}"
        )

        print(
            "  realized P&L: "
            f"${result['pnl']:+.4f}"
        )

        replay_rows.append(
            result
        )

    replay = pd.DataFrame(
        replay_rows
    )

    if replay.empty:

        replay = pd.DataFrame(
            columns=[
                "signal_id",
                "status",
                "invested",
                "pnl",
                "realized_pct",
            ]
        )

    # --------------------------------------------------------
    # Save trade-level replay
    # --------------------------------------------------------

    replay.to_csv(
        TRADES_PATH,
        index=False,
    )

    # --------------------------------------------------------
    # Rescue statistics
    # --------------------------------------------------------

    rescue_invested = float(
        replay["invested"]
        .fillna(0)
        .sum()
    )

    rescue_pnl = float(
        replay["pnl"]
        .fillna(0)
        .sum()
    )

    rescue_roi = (
        rescue_pnl
        / rescue_invested
        * 100.0
        if rescue_invested > 0
        else 0.0
    )

    winning_rescues = int(
        (
            replay["pnl"]
            > 0
        ).sum()
    )

    losing_rescues = int(
        (
            replay["pnl"]
            < 0
        ).sum()
    )

    zero_rescues = int(
        (
            replay["pnl"]
            == 0
        ).sum()
    )

    # --------------------------------------------------------
    # Actual S6 baseline
    # --------------------------------------------------------

    test_ids = set(
        test["signal_id"]
    )

    s6_test = (
        get_actual_s6_baseline(
            con,
            test_ids,
        )
    )

    s6_pnl = float(
        s6_test["realized_pnl"]
        .fillna(0)
        .sum()
    )

    s6_invested = float(
        s6_test["invested"]
        .fillna(0)
        .sum()
    )

    s6_roi = (
        s6_pnl
        / s6_invested
        * 100.0
        if s6_invested > 0
        else 0.0
    )

    combined_pnl = (
        s6_pnl
        + rescue_pnl
    )

    # --------------------------------------------------------
    # Diagnostic outcomes for selected rescues
    # --------------------------------------------------------

    # Outcomes are already attached to test_untraded.
    # selected is a subset, so do not merge them again.
    selected_with_outcomes = selected.copy()

    if not selected_with_outcomes.empty:

        selected_rugs = int(
            selected_with_outcomes[
                "rugged"
            ]
            .fillna(0)
            .astype(int)
            .sum()
        )

        selected_2x = int(
            selected_with_outcomes[
                "returned_2x"
            ]
            .fillna(0)
            .astype(int)
            .sum()
        )

        selected_5x = int(
            selected_with_outcomes[
                "returned_5x"
            ]
            .fillna(0)
            .astype(int)
            .sum()
        )

        selected_10x = int(
            selected_with_outcomes[
                "returned_10x"
            ]
            .fillna(0)
            .astype(int)
            .sum()
        )

    else:

        selected_rugs = 0
        selected_2x = 0
        selected_5x = 0
        selected_10x = 0

    # --------------------------------------------------------
    # Verdict
    # --------------------------------------------------------

    if len(selected) == 0:

        verdict = "NO_RESCUES"

    elif rescue_pnl > 0:

        verdict = "POSITIVE_LIFT"

    else:

        verdict = "FAIL"

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    report = f"""
S7 V2 CORRECTED ECONOMIC CONVERGENCE V3
======================================================================

CORE QUESTION
S7 may only rescue signals that the complete
S6_Moonshot_Ladder system genuinely did NOT trade.

DATASET
----------------------------------------------------------------------
Train rows:                     {len(train)}
Validation rows:                {len(validation)}
Final test rows:                {len(test)}

ACTUAL S6 COVERAGE
----------------------------------------------------------------------
Validation S6-traded:           {len(validation) - len(validation_untraded)}
Validation genuinely untraded:  {len(validation_untraded)}

Final test S6-traded:           {len(test) - len(test_untraded)}
Final test genuinely untraded:  {len(test_untraded)}

MODEL
----------------------------------------------------------------------
Model Y_2x:                     {MODEL_2X}
Model Y_rug:                    {MODEL_RUG}
Model features:                 {len(feature_names)}
X_s6_decision restored:         YES

THRESHOLD SELECTION
----------------------------------------------------------------------
Opportunity threshold:          {opp_threshold:.6f}
Rug threshold:                  {rug_threshold:.6f}

Validation accepted:            {threshold["count"]}
Validation rugs:                {threshold["rugs"]}
Validation proxy score:         {threshold["proxy_score"]:.4f}

FINAL TEST RESCUE POPULATION
----------------------------------------------------------------------
Genuinely S6-untraded:          {len(test_untraded)}
Accepted S7 rescues:            {len(selected)}
Successfully replayed:          {len(replay)}

DIAGNOSTIC OUTCOMES OF SELECTED RESCUES
----------------------------------------------------------------------
Historical 2x:                  {selected_2x}
Historical 5x:                  {selected_5x}
Historical 10x:                 {selected_10x}
Historical rugs:                {selected_rugs}

REAL S7 RESCUE EXECUTION
----------------------------------------------------------------------
Invested capital:               ${rescue_invested:.4f}
Realized P&L:                   ${rescue_pnl:+.4f}
Return on invested capital:     {rescue_roi:+.4f}%

Winning rescues:                {winning_rescues}
Losing rescues:                 {losing_rescues}
Zero-P&L rescues:               {zero_rescues}

REAL S6 BASELINE
----------------------------------------------------------------------
S6 final-test trades:           {len(s6_test)}
S6 invested capital:            ${s6_invested:.4f}
S6 realized P&L:                ${s6_pnl:+.4f}
S6 return on capital:           {s6_roi:+.4f}%

ECONOMIC CONVERGENCE
----------------------------------------------------------------------
S6 baseline P&L:                ${s6_pnl:+.4f}
S7 incremental P&L:             ${rescue_pnl:+.4f}
Combined P&L:                   ${combined_pnl:+.4f}
Incremental lift:               ${rescue_pnl:+.4f}

VERDICT
----------------------------------------------------------------------
{verdict}

SAFEGUARDS
----------------------------------------------------------------------
- Actual S6 Moonshot trades are excluded from S7 rescue population.
- Validation is used for threshold selection only.
- Final-test outcomes are not used to select thresholds.
- S7 does not veto existing S6 trades.
- S7 replay uses the actual S6 Moonshot entry mechanism.
- S7 replay uses the actual S6 Moonshot exit mechanism.
- S6 source code is not modified.
- Actual S6 ledger is not modified.
- Rescue replay uses an isolated portfolio.
- Outcomes are diagnostic and do not trigger trading decisions.

FILES
----------------------------------------------------------------------
Trade-level replay:
{TRADES_PATH}

Report:
{REPORT_PATH}
"""

    Path(
        REPORT_PATH
    ).write_text(
        report.strip() + "\n",
        encoding="utf-8",
    )

    con.close()

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("S7 V3 RESULT")
    print("=" * 70)

    print(
        f"S6 baseline P&L:   ${s6_pnl:+.4f}"
    )

    print(
        f"S7 incremental:    ${rescue_pnl:+.4f}"
    )

    print(
        f"Combined P&L:      ${combined_pnl:+.4f}"
    )

    print(
        f"S7 rescue ROI:     {rescue_roi:+.4f}%"
    )

    print(
        f"Accepted rescues:  {len(selected)}"
    )

    print(
        f"Replayed rescues:  {len(replay)}"
    )

    print(
        f"Verdict:           {verdict}"
    )

    print()
    print(
        "Report:",
        REPORT_PATH,
    )

    print(
        "Trades:",
        TRADES_PATH,
    )


if __name__ == "__main__":
    main()
