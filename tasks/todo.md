# DealerDesk — Task Board

---

## B0 — Project Scaffold
**Status:** COMPLETED
**Depends on:** nothing

### Goal
Turn the `starter/` folder into a real repo root, wire up PostgreSQL, verify the
health endpoint, lock down gitignore, and confirm the project boots cleanly.

### Files to create / change

| Action | Path | Notes |
|---|---|---|
| Copy (move) | `manage.py` | from `starter/` to repo root |
| Copy (move) | `requirements.txt` | from `starter/`; extend with new deps |
| Copy (move) | `dealerdesk/` | Django project package |
| Copy (move) | `core/` | health view + seed_data command |
| Copy (move) | `.env.example` | already good; keep as-is |
| Copy (move) | `.gitignore` | from `starter/`; verify venv + .env covered |
| Create | `ml/` | empty dir with `.gitkeep` (forecast CSV goes here later) |
| Create | `tasks/todo.md` | this file |
| Create | `tasks/lessons.md` | already exists |
| Edit | `requirements.txt` | pin all deps; add `google-genai`, `numpy`, `scipy` |
| Edit | `.env.example` | ensure all four LLM keys present |
| Verify | `GET /api/health/` | must return `{"status": "ok"}` |

### Exact dependency versions to pin
```
Django==4.2.16
djangorestframework==3.15.2
psycopg[binary]==3.2.1
dj-database-url==2.3.0
python-dotenv==1.0.1
requests==2.32.3
google-genai==0.8.0        # Gemini SDK (assistant, B5)
numpy==1.26.4              # forecast (B6)
scipy==1.13.1              # forecast std-dev (B6)
```
*(exact versions confirmed against PyPI Linux wheels before pinning)*

### Edge cases / non-negotiables
- [ ] `.env` must NOT be tracked — verify `git ls-files | grep .env` prints nothing
- [ ] `venv/` or `.venv/` must NOT be tracked
- [ ] `DATA_DIR` in settings points to `<repo root>/data/` — not inside `starter/`
- [ ] `DATABASE_URL` missing → `ImproperlyConfigured` (already in settings.py)
- [ ] No Windows-only packages in requirements.txt

### Tests for B0
- [x] `python manage.py check` exits 0
- [x] `GET /api/health/` → `200 {"status": "ok"}`
- [x] `python manage.py migrate --noinput` exits 0
- [x] `git ls-files | Select-String "^\.env$|/\.env$|venv|\.venv"` prints nothing

### Verification commands
```bash
python manage.py check
python manage.py migrate --noinput
python manage.py runserver 0.0.0.0:8000 &
curl http://localhost:8000/api/health/
```

### Checklist
- [x] B0.1 Copy starter files to repo root
- [x] B0.2 Edit requirements.txt — pin deps + add google-genai, numpy, scipy
- [x] B0.3 Create ml/ dir with .gitkeep
- [x] B0.4 Verify .gitignore covers venv, .env, __pycache__, *.pyc
- [x] B0.5 pip install -r requirements.txt
- [x] B0.6 python manage.py check
- [x] B0.7 python manage.py migrate --noinput
- [x] B0.8 Smoke: GET /api/health/ → 200
- [x] B0.9 git ls-files check — no .env, no venv

### Review
- **Built**: Project scaffold, PostgreSQL 16 on port 5433 with database `dealerdesk`, custom contract error handler (`core/exceptions.py`), standard pagination (`core/pagination.py`), URL structure, and healthy `GET /api/health/`.
- **Verified**: System check clean, migrations applied cleanly, health endpoint returns `200 {"status": "ok"}`, git audited with no secrets.
- **Pushed**: Pushed initial commit to GitHub remote `feature/dealerdesk-aiml` and initialized `main`.

---

## B1 — Products & Inventory (§4, §5)
**Status:** COMPLETED
**Depends on:** B0

### Goal
Implement `catalogue` app with Product model, inventory service, REST endpoints matching API contract §4 and §5, and an idempotent `seed_data` command for `catalogue.csv`.

### Checklist
- [x] B1.1 Create `catalogue` app (`models.py`, `services.py`, `serializers.py`, `views.py`, `urls.py`)
- [x] B1.2 Register `catalogue` in `settings.py` and `dealerdesk/urls.py`
- [x] B1.3 Implement idempotent `bulk_create(update_conflicts=True)` in `seed_data.py`
- [x] B1.4 Write unit and API tests in `catalogue/tests.py`
- [x] B1.5 Run `makemigrations`, `migrate`, `seed_data` twice (600 rows), and `python manage.py test catalogue`

### Review
- **Built**: `catalogue` app with `Product` model (SKU PK, Decimal price, non-negative stock), `catalogue/services.py` (`list_products`, `get_product`, `create_product`, `update_product`, `set_inventory` using `select_for_update`), `ProductSerializer` formatting `price` as 2-dp string, and idempotent `seed_data` via `bulk_create(update_conflicts=True)`.
- **Verified**: `seed_data` run twice produces exactly 600 products; all 4 test suites in `catalogue.tests` pass.
- **Known limits**: None.

---

## B2 — Dealers (§6)
**Status:** PLANNING
**Depends on:** B0

### Goal
Implement `dealers` app with `Dealer` model, service layer, REST endpoints (`GET /api/dealers/`, `POST /api/dealers/`, `GET /api/dealers/{id}/`), and idempotent seeding from `data/dealers.csv` (25 dealers).

### Models and Fields
- `Dealer`:
  - `id`: AutoField / BigAutoField (PK)
  - `dealer_code`: CharField(max_length=64, unique=True)
  - `name`: CharField(max_length=255)
  - `city`: CharField(max_length=128, blank=True, default="")
  - `phone`: CharField(max_length=64, blank=True, default="")
  - `email`: CharField(max_length=255, blank=True, default="")
  - `gstin`: CharField(max_length=64, blank=True, default="")
  - `credit_limit`: DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

### Endpoints
- `GET /api/dealers/` -> Paginated list of dealers
- `POST /api/dealers/` -> `dealer_code` and `name` required, other fields optional (`credit_limit` defaults to `"0.00"`). Duplicate `dealer_code` -> `409 DUPLICATE`. Missing required -> `400 VALIDATION_ERROR`.
- `GET /api/dealers/{id}/` -> `200` dealer object or `404 NOT_FOUND`.

### Files to create / change
- `dealers/` (`__init__.py`, `apps.py`, `models.py`, `services.py`, `serializers.py`, `views.py`, `urls.py`, `tests.py`)
- `dealerdesk/settings.py`: add `"dealers"` to `INSTALLED_APPS`
- `dealerdesk/urls.py`: uncomment `path("api/", include("dealers.urls"))`
- `core/management/commands/seed_data.py`: add `_seed_dealers` loading `data/dealers.csv` idempotently

### Verification commands
- `python manage.py makemigrations dealers && python manage.py migrate`
- `python manage.py seed_data` (twice -> 25 dealers, 600 products)
- `python manage.py test catalogue dealers`

