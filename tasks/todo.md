# DealerDesk — Task Board

---

## B0 — Project Scaffold
**Status:** PLANNING
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
- [ ] `python manage.py check` exits 0
- [ ] `GET /api/health/` → `200 {"status": "ok"}`
- [ ] `python manage.py migrate --noinput` exits 0
- [ ] `git ls-files | grep -E '(^|/)\.env$|^venv/'` prints nothing

### Verification commands
```bash
python manage.py check
python manage.py migrate --noinput
python manage.py runserver 0.0.0.0:8000 &
curl http://localhost:8000/api/health/
```

### Checklist
- [ ] B0.1 Copy starter files to repo root
- [ ] B0.2 Edit requirements.txt — pin deps + add google-genai, numpy, scipy
- [ ] B0.3 Create ml/ dir with .gitkeep
- [ ] B0.4 Verify .gitignore covers venv, .env, __pycache__, *.pyc, ml/forecast.csv excluded? (no — forecast.csv IS committed)
- [ ] B0.5 pip install -r requirements.txt (sandboxed)
- [ ] B0.6 python manage.py check
- [ ] B0.7 python manage.py migrate --noinput
- [ ] B0.8 Smoke: GET /api/health/ → 200
- [ ] B0.9 git ls-files check — no .env, no venv

---
