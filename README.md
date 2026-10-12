# VIKMO DealerDesk

A Django REST API for an auto-parts dealer network.
**Track:** AI / ML — Dealer Assistant + Forecasting (plus full Order Engine & Supplier Sync bonus sections).

---

## LLM Provider & Architecture (§9)

- **Primary Provider:** Google Gemini (`gemini-2.0-flash`, read from `GEMINI_API_KEY`)
- **Multi-Provider Support:** Also supports `OPENAI_API_KEY` (`gpt-4o-mini`), `GROQ_API_KEY` (`llama-3.3-70b-versatile`), and `ANTHROPIC_API_KEY` (`claude-3-5-haiku-latest`) automatically via [`assistant/llm_provider.py`](assistant/llm_provider.py).
- **Tools (`search_parts`, `check_stock`, `create_draft_order`):** Call the exact same service layer functions (`catalogue.services` and `orders.services`) as the REST API.
- **Prompt Injection Defense:** Product names and descriptions are sanitized and passed strictly inside structured tool result JSON payloads, never interpolated into system instructions.
- **Session Memory:** Stored in PostgreSQL (`ConversationSession` / `ConversationTurn`), isolated by `session_id`.

---

## Forecasting & Reorder (§10)

- **Committed Forecast File:** [`ml/forecast.csv`](ml/forecast.csv) (40 SKUs × 4 weeks `2026-09-28` to `2026-10-19` = 160 rows).
- **Training & Backtest Script:** [`ml/train_forecast.py`](ml/train_forecast.py) fits a regularized per-SKU Ridge model with trend, Fourier yearly seasonality harmonics, promotion flag (`promo_calendar.csv`), and Diwali festive-season proximity (`festival_calendar.csv`), with strict temporal leakage guards.

| Method | Holdout MAE | Holdout RMSE |
|---|---:|---:|
| **DealerDesk Ridge + Festival + Promo Model** | **6.55** | **10.04** |
| Baseline 1: 4-Week Trailing Average | 8.76 | 15.01 |
| Baseline 2: Seasonal Naive (Same Week Last Year) | 12.27 | 19.72 |

---

## Setup & Run

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Set DATABASE_URL (PostgreSQL) and your LLM provider key (e.g. GEMINI_API_KEY)
```

### 3. Migrate, seed, and run

```bash
python manage.py migrate --noinput
python manage.py seed_data
python manage.py seed_data        # idempotent
python manage.py runserver 0.0.0.0:8000 --noreload
```

### 4. Run tests & smoke test

```bash
python manage.py test
python smoke_test.py --base-url http://localhost:8000 --track aiml
python smoke_test.py --base-url http://localhost:8000 --all
```

---

## Build Blocks Status

| Block | Deliverable | Status |
|---|---|---|
| B0 | Project scaffold, PostgreSQL config, health check | ✅ Done |
| B1 | Products (§4) + Inventory (§5) + idempotent seed | ✅ Done |
| B2 | Dealers (§6) + idempotent seed | ✅ Done |
| B3 | Orders full lifecycle, GST rounding, concurrency locks, idempotency (§7.1–§7.5) | ✅ Done |
| B4 | Supplier sync with pagination, retries, deduplication, atomic all-or-nothing (§8) | ✅ Done |
| B5 | Dealer Assistant — LLM tool-calling, memory, prompt-injection shield (§9) | ✅ Done |
| B6 | Forecasting & reorder API + `ml/forecast.csv` (§10) | ✅ Done |
| B7 & B8 | Verification gates, smoke tests (`12/12 PASS`), security & secrets audit | ✅ Done |
