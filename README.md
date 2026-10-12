# VIKMO DealerDesk

A Django REST API for an auto-parts dealer network.
**Track:** AI / ML — Dealer Assistant + Forecasting.

---

## LLM Provider

- **Provider:** Google Gemini
- **Model:** `gemini-2.0-flash`
- **Key variable:** `GEMINI_API_KEY`

The code also recognises `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `GROQ_API_KEY`
(first non-empty key wins at start-up). The grader supplies its own key.

---

## Setup & Run

### 1. Prerequisites

- Python 3.11 or newer
- PostgreSQL (local `createdb dealerdesk`, or a free hosted instance on [Neon](https://neon.tech) / [Supabase](https://supabase.com))

### 2. Clone and create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env: set DATABASE_URL and your GEMINI_API_KEY
```

### 4. Migrate, seed, and run

```bash
python manage.py migrate --noinput
python manage.py seed_data        # loads data/ CSVs + ml/forecast.csv
python manage.py seed_data        # run twice — must be idempotent
python manage.py runserver 0.0.0.0:8000
```

### 5. Smoke test

```bash
# In a fresh terminal with the server running:
python smoke_test.py --base-url http://localhost:8000 --track aiml
```

---

## Supplier mock (for §8 Supplier Sync)

```bash
python supplier_mock/mock_supplier.py --calm   # no rate limits (first steps)
python supplier_mock/mock_supplier.py          # realistic: rate limits + transient failures
```

Set `SUPPLIER_API_URL=http://127.0.0.1:8099` and `SUPPLIER_API_KEY=dev-supplier-key`
in your `.env`.

---

## Build blocks

| Block | What was built | Status |
|---|---|---|
| B0 | Project scaffold, health check, git, requirements | ✅ Done |
| B1 | Products (§4) + Inventory (§5) | ⬜ |
| B2 | Dealers (§6) | ⬜ |
| B3 | Orders full lifecycle (§7) | ⬜ |
| B4 | Supplier sync (§8) | ⬜ |
| B5 | Dealer Assistant — Gemini tool-calling (§9) | ⬜ |
| B6 | Forecasting + reorder API (§10) | ⬜ |
| B7 | Hardening + security | ⬜ |
| B8 | Final polish + submission | ⬜ |

---

## Known limits

- Session memory is in-process (dict keyed by `session_id`). Under multi-worker
  deployments sessions would not share memory. The grader uses a single worker
  (`--noreload`), so this is fine for submission.

---

## Data

All CSV files live in `data/` (unchanged from the assignment bundle).
`ml/forecast.csv` (40 SKUs × 4 weeks = 160 rows) is committed in `ml/`.
