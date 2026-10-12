"""
Service layer for Forecasting and Reorder Suggestions (§10).
Pure functions for the contract §10 reorder formula + live stock integration.
"""
import csv
from functools import lru_cache
import math
from django.conf import settings

from catalogue.models import Product
from core.exceptions import NotFoundError
from .models import ForecastRow

FORECAST_WEEKS = [
    "2026-09-28",
    "2026-10-05",
    "2026-10-12",
    "2026-10-19",
]


def compute_sample_sigma(units_series: list[float]) -> float:
    """
    Contract §10: sample standard deviation (n - 1) of units_sold over the
    most recent 12 weeks of sales_history.csv for that SKU (all available weeks if < 12).
    """
    recent = units_series[-12:]
    n = len(recent)
    if n < 2:
        return 0.0
    mean = sum(recent) / n
    variance = sum((x - mean) ** 2 for x in recent) / (n - 1)
    return math.sqrt(variance)


def compute_reorder_metrics(
    sku: str,
    current_stock: int,
    lead_time_weeks: int,
    forecast_units: list[float],
    sigma: float,
) -> dict:
    """
    Pure function implementing Contract §10 reorder formula:
    - L = lead_time_weeks
    - lead_time_demand = sum of forecast_units for the first L forecast weeks
    - safety_stock = ceil(1.65 * sigma * sqrt(L))
    - reorder_point = lead_time_demand + safety_stock
    - reorder_qty = max(0, ceil(reorder_point - current_stock))
    """
    L = int(lead_time_weeks)
    lead_time_demand = round(sum(forecast_units[:L]), 4)
    safety_stock = int(math.ceil(1.65 * sigma * math.sqrt(L)))
    reorder_point = round(lead_time_demand + safety_stock, 4)
    reorder_qty = max(0, int(math.ceil(reorder_point - current_stock)))

    return {
        "sku": sku,
        "current_stock": int(current_stock),
        "lead_time_weeks": L,
        "lead_time_demand": lead_time_demand,
        "safety_stock": safety_stock,
        "reorder_point": reorder_point,
        "reorder_qty": reorder_qty,
    }


@lru_cache(maxsize=1)
def _load_static_forecast_and_history() -> tuple[
    list[tuple[str, int]],
    dict[str, list[dict]],
    dict[str, float],
]:
    """
    Loads lead_times.csv, ml/forecast.csv, and sales_history.csv (for 12-week sample sigma).
    """
    data_dir = settings.DATA_DIR
    ml_csv = settings.ML_DIR / "forecast.csv"

    lead_times: list[tuple[str, int]] = []
    with open(data_dir / "lead_times.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lead_times.append((row["sku"].strip(), int(row["lead_time_weeks"])))

    forecast_map: dict[str, dict[str, float]] = {}
    if ml_csv.exists():
        with open(ml_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sku = row["sku"].strip()
                wk = row["week_start"].strip()
                val = float(row["forecast_units"])
                forecast_map.setdefault(sku, {})[wk] = val

    ordered_forecasts: dict[str, list[dict]] = {}
    for sku, _ in lead_times:
        wk_map = forecast_map.get(sku, {})
        ordered_forecasts[sku] = [
            {"week_start": wk, "forecast_units": wk_map.get(wk, 0.0)}
            for wk in FORECAST_WEEKS
        ]

    history_rows: dict[str, list[tuple[str, float]]] = {
        sku: [] for sku, _ in lead_times
    }
    with open(data_dir / "sales_history.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sku = row["sku"].strip()
            if sku in history_rows:
                history_rows[sku].append(
                    (row["week_start"].strip(), float(row["units_sold"]))
                )

    sigma_by_sku: dict[str, float] = {}
    for sku, rows in history_rows.items():
        rows.sort(key=lambda x: x[0])
        sigma_by_sku[sku] = compute_sample_sigma([r[1] for r in rows])

    return lead_times, ordered_forecasts, sigma_by_sku


def get_sku_forecast(sku: str) -> dict:
    _, ordered_forecasts, _ = _load_static_forecast_and_history()
    if sku not in ordered_forecasts:
        raise NotFoundError(f"SKU '{sku}' is not a forecast SKU.")

    # Check if DB has ForecastRow entries (seeded by seed_data), else use CSV map
    db_rows = list(
        ForecastRow.objects.filter(sku=sku).order_by("week_start")
    )
    if len(db_rows) == 4:
        forecast_list = [
            {"week_start": r.week_start, "forecast_units": r.forecast_units}
            for r in db_rows
        ]
    else:
        forecast_list = ordered_forecasts[sku]

    return {
        "sku": sku,
        "forecast": forecast_list,
    }


def get_reorder_suggestions() -> list[dict]:
    lead_times, ordered_forecasts, sigma_by_sku = _load_static_forecast_and_history()
    skus = [sku for sku, _ in lead_times]

    # Fetch live current_stock from Product table
    stock_by_sku = dict(
        Product.objects.filter(sku__in=skus).values_list("sku", "stock")
    )

    # Check DB forecast rows
    db_forecasts: dict[str, dict[str, float]] = {}
    for r in ForecastRow.objects.filter(sku__in=skus):
        db_forecasts.setdefault(r.sku, {})[r.week_start] = r.forecast_units

    results = []
    for sku, L in lead_times:
        if sku in db_forecasts and len(db_forecasts[sku]) == 4:
            f_units = [db_forecasts[sku][wk] for wk in FORECAST_WEEKS]
        else:
            f_units = [x["forecast_units"] for x in ordered_forecasts[sku]]

        current_stock = stock_by_sku.get(sku, 0)
        sigma = sigma_by_sku.get(sku, 0.0)
        results.append(
            compute_reorder_metrics(
                sku=sku,
                current_stock=current_stock,
                lead_time_weeks=L,
                forecast_units=f_units,
                sigma=sigma,
            )
        )
    return results
