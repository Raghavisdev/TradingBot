import sqlite3
import warnings

import numpy as np
import pandas as pd

from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier

from analytics.s7_models.s6_gate_calibration import (
    load_ids,
    load_s6_trades,
    load_relevant_snapshots,
    attach_entry_snapshots,
    safe_float,
)

warnings.filterwarnings("ignore")

DB = "database/trading.db"

TRAIN_CSV = "analytics/s7_dataset/s7_train.csv"
VAL_CSV = "analytics/s7_dataset/s7_validation.csv"
TEST_CSV = "analytics/s7_dataset/s7_test.csv"

OUTPUT_CSV = (
    "analytics/s7_models/S6_HARD_STOP_GATE_RESULTS.csv"
)

TARGET = "hard_stop"


# ============================================================
# DATASET LABEL
# ============================================================

def classify_dataset(signal_id, train_ids, val_ids, test_ids):

    sid = str(signal_id)

    if sid in train_ids:
        return "TRAIN"

    if sid in val_ids:
        return "VALIDATION"

    if sid in test_ids:
        return "TEST"

    return "OTHER"


# ============================================================
# BUILD ENTRY FEATURES
#
# IMPORTANT:
# Only information available at/around entry is used.
#
# NEVER use:
# realized_pnl
# realized_pct
# mfe
# mae
# exit_reason
# peak_multiple
# exit_price
# exit_time
#
# as model features.
# ============================================================

def build_features(df):

    df = df.copy()

    # --------------------------------------------------------
    # Buy/sell ratio
    # --------------------------------------------------------

    df["buy_sell_ratio"] = (
        df["buys"].fillna(0)
        /
        df["sells"].replace(0, np.nan)
    )

    df["buy_sell_ratio"] = (
        df["buy_sell_ratio"]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(1.0)
    )

    # --------------------------------------------------------
    # Derived entry features
    # --------------------------------------------------------

    df["mc_snapshot_ratio"] = (
        df["snap_market_cap"]
        /
        df["signal_market_cap"].replace(0, np.nan)
    )

    df["mc_snapshot_ratio"] = (
        df["mc_snapshot_ratio"]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(1.0)
    )

    df["buy_pressure"] = (
        df["buys"]
        /
        (df["buys"] + df["sells"]).replace(0, np.nan)
    )

    df["buy_pressure"] = (
        df["buy_pressure"]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.5)
    )

    df["volume_per_liquidity"] = (
        df["volume"]
        /
        df["liquidity"].replace(0, np.nan)
    )

    df["volume_per_liquidity"] = (
        df["volume_per_liquidity"]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )

    # --------------------------------------------------------
    # Features available before outcome
    # --------------------------------------------------------

    feature_columns = [
        "final_score",
        "gt_score",
        "signal_market_cap",

        "snap_market_cap",
        "snap_price",
        "liquidity",
        "volume",
        "buys",
        "sells",
        "holders",
        "market_health",

        "buy_sell_ratio",
        "mc_snapshot_ratio",
        "buy_pressure",
        "volume_per_liquidity",
    ]

    X = df[feature_columns].copy()

    for col in feature_columns:
        X[col] = pd.to_numeric(
            X[col],
            errors="coerce"
        )

    return X, feature_columns


# ============================================================
# MODEL
# ============================================================

def build_model():

    return Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median"
                ),
            ),

            (
                "model",
                RandomForestClassifier(
                    n_estimators=500,
                    max_depth=5,
                    min_samples_leaf=5,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


# ============================================================
# ECONOMIC EVALUATION
# ============================================================

def evaluate_gate(
    df,
    probabilities,
    threshold,
    title,
):

    result = df.copy()

    result["p_hard_stop"] = probabilities

    result["gate_block"] = (
        result["p_hard_stop"] >= threshold
    ).astype(int)

    result["would_trade"] = (
        result["gate_block"] == 0
    ).astype(int)

    actual_pnl = result["realized_pnl"].sum()

    kept = result[
        result["would_trade"] == 1
    ].copy()

    blocked = result[
        result["would_trade"] == 0
    ].copy()

    kept_pnl = kept["realized_pnl"].sum()
    blocked_pnl = blocked["realized_pnl"].sum()

    actual_winners = (
        result["realized_pnl"] > 0
    ).sum()

    kept_winners = (
        kept["realized_pnl"] > 0
    ).sum()

    blocked_winners = (
        blocked["realized_pnl"] > 0
    ).sum()

    hard_stops = (
        result["hard_stop"] == 1
    ).sum()

    blocked_hard_stops = (
        blocked["hard_stop"] == 1
    ).sum()

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)

    print(
        f"Gate threshold:             {threshold:.2f}"
    )

    print(
        f"Trades evaluated:           {len(result)}"
    )

    print(
        f"Trades kept:                {len(kept)}"
    )

    print(
        f"Trades blocked:             {len(blocked)}"
    )

    print(
        f"Actual P&L:                 ${actual_pnl:+.4f}"
    )

    print(
        f"P&L of kept trades:         ${kept_pnl:+.4f}"
    )

    print(
        f"P&L of blocked trades:      ${blocked_pnl:+.4f}"
    )

    print(
        f"Hard stops:                 {hard_stops}"
    )

    print(
        f"Hard stops blocked:         {blocked_hard_stops}"
    )

    if hard_stops > 0:

        print(
            f"Hard-stop recall:           "
            f"{blocked_hard_stops / hard_stops * 100:.2f}%"
        )

    print(
        f"Actual winners:             {actual_winners}"
    )

    print(
        f"Winners kept:               {kept_winners}"
    )

    print(
        f"Winners accidentally blocked:{blocked_winners}"
    )

    if actual_winners > 0:

        print(
            f"Winner retention:           "
            f"{kept_winners / actual_winners * 100:.2f}%"
        )

    if actual_pnl != 0:

        print(
            f"P&L retained vs actual:     "
            f"{kept_pnl / actual_pnl * 100:.2f}%"
        )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 80)
    print("S6 HARD-STOP RISK GATE")
    print("=" * 80)

    # --------------------------------------------------------
    # Dataset IDs
    # --------------------------------------------------------

    train_ids = load_ids(TRAIN_CSV)
    val_ids = load_ids(VAL_CSV)
    test_ids = load_ids(TEST_CSV)

    print()
    print("DATASET")
    print("-" * 80)

    print(
        f"Train signals:             {len(train_ids)}"
    )

    print(
        f"Validation signals:        {len(val_ids)}"
    )

    print(
        f"Test signals:              {len(test_ids)}"
    )

    # --------------------------------------------------------
    # Load actual closed S6 trades
    # --------------------------------------------------------

    trades = load_s6_trades()

    print()
    print(
        f"Closed S6 trades loaded:    {len(trades)}"
    )

    if trades.empty:

        raise RuntimeError(
            "No closed S6 trades found."
        )

    # --------------------------------------------------------
    # Dataset assignment
    # --------------------------------------------------------

    trades["dataset"] = trades[
        "signal_id"
    ].apply(
        lambda x: classify_dataset(
            x,
            train_ids,
            val_ids,
            test_ids,
        )
    )

    print()
    print("S6 TRADES BY DATASET")
    print("-" * 80)

    print(
        trades["dataset"]
        .value_counts()
        .to_string()
    )

    # --------------------------------------------------------
    # Load entry snapshots
    # --------------------------------------------------------

    signal_ids = set(
        trades["signal_id"]
        .astype(str)
    )

    snapshots = load_relevant_snapshots(
        signal_ids
    )

    print()
    print(
        f"Snapshots loaded:          {len(snapshots)}"
    )

    trades = attach_entry_snapshots(
        trades,
        snapshots
    )

    # --------------------------------------------------------
    # Target
    # --------------------------------------------------------

    trades[TARGET] = (
        trades["exit_reason"]
        .fillna("")
        .str.contains(
            "Hard Stop Loss -20.0%",
            regex=False
        )
        .astype(int)
    )

    print()
    print("HARD-STOP TARGET")
    print("-" * 80)

    print(
        trades[TARGET]
        .value_counts()
        .sort_index()
        .to_string()
    )

    # --------------------------------------------------------
    # Build features
    # --------------------------------------------------------

    X, feature_columns = build_features(
        trades
    )

    print()
    print("FEATURES")
    print("-" * 80)

    for feature in feature_columns:
        print(feature)

    # --------------------------------------------------------
    # Train / validation / test
    # --------------------------------------------------------

    train_df = trades[
        trades["dataset"] == "TRAIN"
    ].copy()

    val_df = trades[
        trades["dataset"] == "VALIDATION"
    ].copy()

    test_df = trades[
        trades["dataset"] == "TEST"
    ].copy()

    X_train = X.loc[
        train_df.index
    ]

    y_train = train_df[TARGET]

    X_val = X.loc[
        val_df.index
    ]

    y_val = val_df[TARGET]

    X_test = X.loc[
        test_df.index
    ]

    y_test = test_df[TARGET]

    print()
    print("TRAINING DATA")
    print("-" * 80)

    print(
        f"Train rows:                {len(train_df)}"
    )

    print(
        f"Train hard stops:          {y_train.sum()}"
    )

    print(
        f"Validation rows:           {len(val_df)}"
    )

    print(
        f"Validation hard stops:     {y_val.sum()}"
    )

    print(
        f"Test rows:                 {len(test_df)}"
    )

    print(
        f"Test hard stops:           {y_test.sum()}"
    )

    # --------------------------------------------------------
    # Train
    # --------------------------------------------------------

    if y_train.nunique() < 2:

        raise RuntimeError(
            "Training data contains only one hard-stop class."
        )

    model = build_model()

    print()
    print("TRAINING HARD-STOP MODEL...")
    print("-" * 80)

    model.fit(
        X_train,
        y_train
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    val_prob = model.predict_proba(
        X_val
    )[:, 1]

    print()
    print("=" * 80)
    print("VALIDATION MODEL PERFORMANCE")
    print("=" * 80)

    if y_val.nunique() >= 2:

        print(
            f"ROC-AUC:                   "
            f"{roc_auc_score(y_val, val_prob):.4f}"
        )

    val_pred = (
        val_prob >= 0.50
    ).astype(int)

    print()
    print(
        classification_report(
            y_val,
            val_pred,
            digits=4,
            zero_division=0,
        )
    )

    print(
        "Confusion matrix:"
    )

    print(
        confusion_matrix(
            y_val,
            val_pred,
        )
    )

    # --------------------------------------------------------
    # Test — NO TUNING
    # --------------------------------------------------------

    test_prob = model.predict_proba(
        X_test
    )[:, 1]

    print()
    print("=" * 80)
    print("FINAL TEST — REPORT ONLY")
    print("=" * 80)

    if y_test.nunique() >= 2:

        print(
            f"ROC-AUC:                   "
            f"{roc_auc_score(y_test, test_prob):.4f}"
        )

    test_pred = (
        test_prob >= 0.50
    ).astype(int)

    print()
    print(
        classification_report(
            y_test,
            test_pred,
            digits=4,
            zero_division=0,
        )
    )

    print(
        "Confusion matrix:"
    )

    print(
        confusion_matrix(
            y_test,
            test_pred,
        )
    )

    # --------------------------------------------------------
    # Economic gate analysis
    #
    # Thresholds are NOT optimized against TEST.
    # We simply report several reasonable thresholds.
    # --------------------------------------------------------

    thresholds = [
        0.50,
        0.60,
        0.70,
        0.80,
        0.90,
    ]

    all_results = []

    for threshold in thresholds:

        evaluated = evaluate_gate(
            test_df,
            test_prob,
            threshold,
            f"FINAL TEST — GATE {threshold:.2f}",
        )

        evaluated["threshold"] = threshold

        all_results.append(
            evaluated
        )

    # --------------------------------------------------------
    # Save results
    # --------------------------------------------------------

    results = pd.concat(
        all_results,
        ignore_index=True
    )

    results.to_csv(
        OUTPUT_CSV,
        index=False
    )

    print()
    print("=" * 80)
    print("SAVED")
    print("=" * 80)

    print(
        f"CSV: {OUTPUT_CSV}"
    )

    # --------------------------------------------------------
    # Feature importance
    # --------------------------------------------------------

    rf = model.named_steps["model"]

    importance = pd.Series(
        rf.feature_importances_,
        index=feature_columns,
    ).sort_values(
        ascending=False
    )

    print()
    print("=" * 80)
    print("FEATURE IMPORTANCE")
    print("=" * 80)

    print(
        importance.to_string(
            float_format=lambda x: f"{x:.5f}"
        )
    )


if __name__ == "__main__":
    main()
