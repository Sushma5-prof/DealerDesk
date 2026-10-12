"""
Forecasting training, backtesting, and prediction script for VIKMO DealerDesk (§10).
Generates ml/forecast.csv (40 SKUs x 4 weeks = 160 rows).

Includes strict temporal leakage guard and backtest comparison against two baselines:
1. 4-week trailing average
2. Seasonal naive (same week last year, t - 52w)
"""
import csv
from datetime import date, datetime
import math
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_CSV = REPO_ROOT / "ml" / "forecast.csv"

FORECAST_WEEKS = [
    "2026-09-28",
    "2026-10-05",
    "2026-10-12",
    "2026-10-19",
]


def parse_date(d_str: str) -> date:
    return datetime.strptime(d_str.strip(), "%Y-%m-%d").date()


def load_diwali_dates() -> list[date]:
    diwali_dates: list[date] = []
    with open(DATA_DIR / "festival_calendar.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["festival"].strip().lower() == "diwali":
                diwali_dates.append(parse_date(row["date"]))
    return diwali_dates


def diwali_proximity_features(week_date: date, diwali_dates: list[date]) -> tuple[float, float]:
    """
    Festive demand lift follows Diwali (not calendar month).
    Returns (pre_diwali_bump, diwali_week_bump) based on days before nearest Diwali.
    """
    diffs = [(d - week_date).days for d in diwali_dates]
    nearest = min(diffs, key=lambda x: abs(x))
    # Peak festive lift in the 1 to 3 weeks leading into Diwali
    pre_lift = math.exp(-0.5 * ((nearest - 10.0) / 10.0) ** 2)
    wide_lift = math.exp(-0.5 * (nearest / 18.0) ** 2)
    return pre_lift, wide_lift


def build_feature_vector(
    week_date: date,
    promo_flag: int,
    diwali_dates: list[date],
    origin_date: date = date(2024, 9, 30),
) -> np.ndarray:
    t_weeks = (week_date - origin_date).days / 7.0
    angle1 = 2.0 * math.pi * t_weeks / 52.1775
    angle2 = 4.0 * math.pi * t_weeks / 52.1775
    pre_diwali, wide_diwali = diwali_proximity_features(week_date, diwali_dates)
    return np.array(
        [
            1.0,
            t_weeks / 104.0,
            math.sin(angle1),
            math.cos(angle1),
            math.sin(angle2),
            math.cos(angle2),
            float(promo_flag),
            pre_diwali,
            wide_diwali,
        ],
        dtype=float,
    )


def fit_predict_sku(
    train_rows: list[tuple[date, float, int]],
    target_weeks: list[tuple[date, int]],
    diwali_dates: list[date],
) -> list[float]:
    """
    Fits a regularized Ridge regression model with trend, Fourier yearly seasonality,
    promotion spike, and Diwali festive lift, blended with recent local level for stability.
    """
    n = len(train_rows)
    if n == 0:
        return [0.0 for _ in target_weeks]

    y = np.array([r[1] for r in train_rows], dtype=float)

    # Short history fallback (< 16 weeks): exponentially weighted moving average + promo lift
    if n < 16:
        recent = y[-min(n, 6) :]
        weights = np.exp(np.linspace(-1.0, 0.0, len(recent)))
        base_level = float(np.sum(recent * weights) / np.sum(weights))
        preds = []
        for w_date, p_flag in target_weeks:
            mult = 1.35 if p_flag == 1 else 1.0
            preds.append(max(0.0, base_level * mult))
        return preds

    X = np.vstack(
        [build_feature_vector(r[0], r[2], diwali_dates) for r in train_rows]
    )
    # Weight recent observations slightly higher
    sample_weights = np.linspace(0.7, 1.3, n)
    W = np.diag(sample_weights)

    # Ridge penalty (do not penalize intercept at index 0)
    reg = np.eye(X.shape[1]) * 1.5
    reg[0, 0] = 0.0

    beta = np.linalg.solve(X.T @ W @ X + reg, X.T @ W @ y)

    # Compute recent residual anchor over last 4 training weeks
    recent_preds = X[-4:] @ beta
    recent_actuals = y[-4:]
    recent_bias = float(np.mean(recent_actuals - recent_preds))

    preds: list[float] = []
    for w_date, p_flag in target_weeks:
        x_fut = build_feature_vector(w_date, p_flag, diwali_dates)
        raw_pred = float(x_fut @ beta) + 0.35 * recent_bias
        preds.append(max(0.0, raw_pred))
    return preds


def baseline_trailing_4w(
    train_rows: list[tuple[date, float, int]],
    target_weeks: list[tuple[date, int]],
) -> list[float]:
    if not train_rows:
        return [0.0 for _ in target_weeks]
    vals = [r[1] for r in train_rows[-4:]]
    avg = sum(vals) / len(vals)
    return [max(0.0, avg) for _ in target_weeks]


def baseline_seasonal_naive(
    train_rows: list[tuple[date, float, int]],
    target_weeks: list[tuple[date, int]],
) -> list[float]:
    by_date = {r[0]: r[1] for r in train_rows}
    fallback = (
        sum(r[1] for r in train_rows[-4:]) / min(len(train_rows), 4)
        if train_rows
        else 0.0
    )
    preds = []
    for w_date, _ in target_weeks:
        ly_date = date.fromordinal(w_date.toordinal() - 52 * 7)
        preds.append(max(0.0, by_date.get(ly_date, fallback)))
    return preds


def main():
    diwali_dates = load_diwali_dates()

    with open(DATA_DIR / "lead_times.csv", encoding="utf-8") as f:
        forecast_skus = [r["sku"].strip() for r in csv.DictReader(f)]

    history_by_sku: dict[str, list[tuple[date, float, int]]] = {
        sku: [] for sku in forecast_skus
    }
    with open(DATA_DIR / "sales_history.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sku = row["sku"].strip()
            if sku in history_by_sku:
                history_by_sku[sku].append(
                    (
                        parse_date(row["week_start"]),
                        float(row["units_sold"]),
                        int(row["promo_flag"]),
                    )
                )

    for sku in history_by_sku:
        history_by_sku[sku].sort(key=lambda x: x[0])

    # ---- Backtest evaluation with strict temporal leakage guard ----
    backtest_cutoff = date(2026, 8, 24)  # Last 4 weeks (2026-08-31..2026-09-21) held out
    model_errors = []
    b1_errors = []
    b2_errors = []

    for sku in forecast_skus:
        rows = history_by_sku[sku]
        # LEAKAGE GUARD: strictly filter training rows <= backtest_cutoff
        bt_train = [r for r in rows if r[0] <= backtest_cutoff]
        bt_test = [r for r in rows if r[0] > backtest_cutoff]
        if not bt_test or not bt_train:
            continue

        targets = [(r[0], r[2]) for r in bt_test]
        actuals = [r[1] for r in bt_test]

        p_model = fit_predict_sku(bt_train, targets, diwali_dates)
        p_b1 = baseline_trailing_4w(bt_train, targets)
        p_b2 = baseline_seasonal_naive(bt_train, targets)

        for a, pm, pb1, pb2 in zip(actuals, p_model, p_b1, p_b2):
            model_errors.append(abs(a - pm))
            b1_errors.append(abs(a - pb1))
            b2_errors.append(abs(a - pb2))

    mae_model = float(np.mean(model_errors))
    mae_b1 = float(np.mean(b1_errors))
    mae_b2 = float(np.mean(b2_errors))
    rmse_model = float(np.sqrt(np.mean(np.square(model_errors))))
    rmse_b1 = float(np.sqrt(np.mean(np.square(b1_errors))))
    rmse_b2 = float(np.sqrt(np.mean(np.square(b2_errors))))

    print("=== Backtest Results (Holdout: 2026-08-31 to 2026-09-21, 40 SKUs) ===")
    print(f"{'Method':<38} | {'MAE':>8} | {'RMSE':>8}")
    print("-" * 60)
    print(f"{'DealerDesk Ridge+Festival+Promo Model':<38} | {mae_model:>8.2f} | {rmse_model:>8.2f}")
    print(f"{'Baseline 1: 4-Week Trailing Average':<38} | {mae_b1:>8.2f} | {rmse_b1:>8.2f}")
    print(f"{'Baseline 2: Seasonal Naive (Last Year)':<38} | {mae_b2:>8.2f} | {rmse_b2:>8.2f}")

    # ---- Final training up to 2026-09-21 and forecasting 2026-09-28..2026-10-19 ----
    promo_map: dict[tuple[str, str], int] = {}
    with open(DATA_DIR / "promo_calendar.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            promo_map[(row["sku"].strip(), row["week_start"].strip())] = int(
                row["promo_flag"]
            )

    final_cutoff = date(2026, 9, 21)
    output_rows: list[tuple[str, str, str]] = []

    for sku in forecast_skus:
        # LEAKAGE GUARD: training data strictly <= 2026-09-21
        full_train = [r for r in history_by_sku[sku] if r[0] <= final_cutoff]
        fut_targets = [
            (parse_date(w), promo_map.get((sku, w), 0)) for w in FORECAST_WEEKS
        ]
        preds = fit_predict_sku(full_train, fut_targets, diwali_dates)
        for w_str, pred_val in zip(FORECAST_WEEKS, preds):
            output_rows.append((sku, w_str, f"{max(0.0, pred_val):.2f}"))

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sku", "week_start", "forecast_units"])
        writer.writerows(output_rows)

    print(f"\nWrote {len(output_rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
