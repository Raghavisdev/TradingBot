import pandas as pd
import numpy as np

from scipy.stats import spearmanr


DATA = (
    "analytics/s7_models/"
    "adaptive_training_dataset_v2.csv"
)


def main():

    df = pd.read_csv(DATA)

    print("=" * 90)
    print("S7 ADAPTIVE FEATURE AUDIT V1")
    print("=" * 90)

    print(f"Rows: {len(df)}")
    print(f"Features: {len(df.columns)}")

    # ==========================================================
    # TARGETS
    # ==========================================================

    targets = [
        "realized_pct",
        "mfe",
        "runner_50",
        "runner_100",
        "runner_200",
    ]

    # ==========================================================
    # CANDIDATE FEATURES
    #
    # Exclude:
    # - future outcomes
    # - identifiers
    # - execution outcomes
    # ==========================================================

    excluded = {
        "trade_id",
        "signal_id",
        "symbol",
        "contract",
        "entry_time",

        "realized_pnl",
        "realized_pct",
        "mfe",
        "mae",
        "peak_multiple",
        "runner_50",
        "runner_100",
        "runner_200",
        "exit_reason",

        "fees",
        "slippage",
    }

    features = [
        c for c in df.columns
        if c not in excluded
        and pd.api.types.is_numeric_dtype(df[c])
    ]

    print()
    print(
        f"Candidate numeric features: {len(features)}"
    )

    # ==========================================================
    # SPEARMAN ASSOCIATION
    # ==========================================================

    results = []

    for feature in features:

        x = pd.to_numeric(
            df[feature],
            errors="coerce"
        )

        for target in targets:

            y = pd.to_numeric(
                df[target],
                errors="coerce"
            )

            mask = (
                x.notna()
                & y.notna()
            )

            if mask.sum() < 20:
                continue

            try:
                rho, p = spearmanr(
                    x[mask],
                    y[mask]
                )
            except Exception:
                continue

            results.append({
                "feature": feature,
                "target": target,
                "n": int(mask.sum()),
                "spearman": float(rho),
                "p_value": float(p),
                "abs_spearman": abs(float(rho)),
            })

    result = pd.DataFrame(results)

    # ==========================================================
    # TOP ASSOCIATIONS
    # ==========================================================

    print()
    print("=" * 90)
    print("TOP FEATURES BY RUNNER_100 ASSOCIATION")
    print("=" * 90)

    x = (
        result[
            result["target"] == "runner_100"
        ]
        .sort_values(
            "abs_spearman",
            ascending=False
        )
        .head(20)
    )

    print(
        x[
            [
                "feature",
                "n",
                "spearman",
                "p_value",
            ]
        ].to_string(
            index=False
        )
    )

    # ==========================================================
    # RUNNER_50
    # ==========================================================

    print()
    print("=" * 90)
    print("TOP FEATURES BY RUNNER_50 ASSOCIATION")
    print("=" * 90)

    x = (
        result[
            result["target"] == "runner_50"
        ]
        .sort_values(
            "abs_spearman",
            ascending=False
        )
        .head(20)
    )

    print(
        x[
            [
                "feature",
                "n",
                "spearman",
                "p_value",
            ]
        ].to_string(
            index=False
        )
    )

    # ==========================================================
    # MFE
    # ==========================================================

    print()
    print("=" * 90)
    print("TOP FEATURES BY MFE ASSOCIATION")
    print("=" * 90)

    x = (
        result[
            result["target"] == "mfe"
        ]
        .sort_values(
            "abs_spearman",
            ascending=False
        )
        .head(20)
    )

    print(
        x[
            [
                "feature",
                "n",
                "spearman",
                "p_value",
            ]
        ].to_string(
            index=False
        )
    )

    # ==========================================================
    # REALIZED RETURN
    # ==========================================================

    print()
    print("=" * 90)
    print("TOP FEATURES BY REALIZED RETURN")
    print("=" * 90)

    x = (
        result[
            result["target"] == "realized_pct"
        ]
        .sort_values(
            "abs_spearman",
            ascending=False
        )
        .head(20)
    )

    print(
        x[
            [
                "feature",
                "n",
                "spearman",
                "p_value",
            ]
        ].to_string(
            index=False
        )
    )

    # ==========================================================
    # SAVE
    # ==========================================================

    out = (
        "analytics/s7_models/"
        "adaptive_feature_audit_v1.csv"
    )

    result.to_csv(
        out,
        index=False
    )

    print()
    print("=" * 90)
    print("SAVED")
    print("=" * 90)
    print(out)


if __name__ == "__main__":
    main()
