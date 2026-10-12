# VIKMO DealerDesk

**Track:** `aiml`

A Django REST API, GenAI Dealer Assistant, ML Demand Forecaster, Supplier Sync client, and Dealer Portal for VIKMO DealerDesk.

---

## Track & Parts Attempted

- **Primary Track:** `aiml` (AI / ML Track)
- **Required Parts Completed:**
  - **Part A1 · Backend Core:** Products (`§4`), Inventory (`§5`), Dealers (`§6`), and Draft Orders (`§7.1`)
  - **Part C · Dealer Assistant (`§9`):** Tool-calling LLM assistant (`search_parts`, `check_stock`, `create_draft_order`), session memory, live DB grounding, and prompt-injection defense
  - **Part D · Forecasting & Reorder (`§10`):** 4-week demand forecast committed at [`ml/forecast.csv`](ml/forecast.csv) (40 SKUs × 4 weeks = 160 rows), `GET /api/forecast/{sku}/`, and `GET /api/reorder-suggestions/`
- **Optional Bonus Parts Completed:**
  - **Part A2 · Order Engine (`§7.2–§7.5`):** Full status lifecycle (`DRAFT → CONFIRMED → DISPATCHED → DELIVERED`, plus `CANCELLED`), concurrency-safe stock deduction (`SELECT ... FOR UPDATE`), exact per-line 18% GST (`ROUND_HALF_UP`), price locking on confirm, IST daily sequence `ORD-YYYYMMDD-NNNN`, and `Idempotency-Key` protection
  - **Part B · Supplier Sync (`§8`):** `POST /api/sync/supplier/` handling cursor pagination, `429` (`Retry-After`), `5xx` exponential backoff (max 5 attempts/page), all-or-nothing atomicity (`502 SUPPLIER_UNAVAILABLE`), invalid item rejection, and duplicate SKU resolution via latest `updated_at`
  - **Part E · Frontend Portal:** Interactive single-page Dealer Portal served at `http://localhost:8000/` (`core/templates/core/portal.html`)

---

## Video Walkthrough

- **5-Minute Video Link:** *(Add your unlisted YouTube / Loom / Google Drive link here before submitting)*

---

## LLM Provider & Model (`§9`)

- **Provider:** Google Gemini
- **Model:** `gemini-2.0-flash`
- **Environment Variable:** `GEMINI_API_KEY`
- **Multi-Provider Support:** [`assistant/llm_provider.py`](assistant/llm_provider.py) also automatically supports `OPENAI_API_KEY` (`gpt-4o-mini`), `GROQ_API_KEY` (`llama-3.3-70b-versatile`), and `ANTHROPIC_API_KEY` (`claude-3-5-haiku-latest`) so whichever key the grading environment supplies works out of the box.

---

## Forecasting & Backtest Summary (`§10`)

- **Forecast File:** [`ml/forecast.csv`](ml/forecast.csv) (`160` rows: 40 SKUs × 4 weeks `2026-09-28`, `2026-10-05`, `2026-10-12`, `2026-10-19`)
- **Reproducible Training & Backtest Script:** [`ml/train_forecast.py`](ml/train_forecast.py)
- **Architectural & ML Details:** See [`DECISIONS.md`](DECISIONS.md)

| Method (Holdout: 2026-08-31 to 2026-09-21, 40 SKUs) | Holdout MAE | Holdout RMSE |
|---|---:|---:|
| **DealerDesk Hybrid Ridge + Croston + Diwali/Promo Model** | **6.55** | **10.04** |
| Baseline 1: 4-Week Trailing Average | 8.76 | 15.01 |
| Baseline 2: Last Value (Naive) | 11.72 | 19.58 |
| Baseline 3: Seasonal Naive (Same Week Last Year) | 12.27 | 19.72 |

---

## Setup & Run Instructions

### 1. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env and set DATABASE_URL (PostgreSQL) and GEMINI_API_KEY
```

### 3. Migrate, Seed (Idempotent), and Start Server

```bash
python manage.py migrate --noinput
python manage.py seed_data
python manage.py seed_data        # safe to run twice: produces exact 600 products, 25 dealers, 160 forecast rows
python manage.py runserver 0.0.0.0:8000 --noreload
```

- **Dealer Portal UI:** Open `http://localhost:8000/` in your browser.
- **API Health Check:** `http://localhost:8000/api/health/`

### 4. How to Run Tests & Smoke Tests

```bash
# Run Django unit, API, and concurrency test suite (18 tests):
python manage.py test -v 2

# Run AI/ML track smoke test:
python smoke_test.py --base-url http://localhost:8000 --track aiml

# Run all smoke tests (including Order Engine & Supplier Sync with mock_supplier.py running):
python supplier_mock/mock_supplier.py &
python smoke_test.py --base-url http://localhost:8000 --all
```

---

## Assumptions

1. **Draft Order Live Pricing (`§7.4`):** While an order is in `DRAFT` status, its `unit_price` and totals dynamically reflect any catalogue price updates (`orders/services.py:124-174`). Once confirmed via `POST /api/orders/{order_number}/confirm/`, `unit_price` is locked permanently on each `OrderItem`.
2. **Idempotency Replay Status (`§7.5`):** Repeating `POST /api/orders/` with the same `Idempotency-Key` and identical payload returns the original order with HTTP `200` (accepted alongside `201` per contract `§7.5`), while a different payload with the same key returns `409 IDEMPOTENCY_CONFLICT`.
3. **Reorder Formula Precision (`§10.2`):** `lead_time_demand` and `reorder_point` are computed from `ml/forecast.csv` and rounded to at most 4 decimal places to eliminate IEEE-754 floating-point noise while preserving exact decimal values (e.g. `61.7`), and `safety_stock` uses sample standard deviation ($n - 1$) over the most recent 12 weeks of `data/sales_history.csv`.
