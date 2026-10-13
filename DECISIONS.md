# VIKMO DealerDesk — Architectural & Engineering Decisions (`DECISIONS.md`)

**Track:** `aiml` (with all optional Backend Order Engine, Supplier Sync, and Frontend parts also completed)

---

## Part 1: AI / ML Track Questions (Required)

### 1. What does your schema look like, and why are the relationships and delete rules set this way?

Products use SKU as their primary key. Inventory records belong to products and are deleted with them. Orders protect their dealer and product records, while order items are deleted with their order. Chat turns are deleted with their session. Forecast rows store SKU directly and allow only one forecast per SKU per week. (catalogue/models.py:6, catalogue/models.py:34, orders/models.py:31, orders/models.py:63, assistant/models.py:14, forecast/models.py:4)

---

### 2. How does part retrieval work, and where does it fall short?

It searches SKU, name, and brand for a case-insensitive substring, with optional category and vehicle filters. If there are no matches, it tokenizes the query and applies simple plural handling. That works for common catalogue terms, but can miss synonyms, typos, and unusual word forms. (catalogue/services.py:62, catalogue/services.py:89, catalogue/services.py:121)

---

### 3. Walk through the assistant's tool-calling flow.

The chat view passes the request to `handle_chat`, which validates the dealer, loads session history, and provides handlers for part search, stock checks, and draft orders. `run_llm_turn` uses an available model provider—or a deterministic fallback—to call those handlers and produce a reply. The service then checks cited SKUs and saves the turn. (assistant/views.py:11, assistant/services.py:38, assistant/services.py:82, assistant/services.py:162, assistant/llm_provider.py:109, assistant/services.py:168)

---

### 4. How does the assistant get current prices and stock? Can it guarantee every figure is correct?

The search and stock tools fetch product rows during the request and include their current price and stock in the tool results. The system prompt tells the model to use those tools and not guess. A test changes stock from 136 to 42 and checks that the next reply reports 42. Since the app does not validate every number in the final prose, this is strong grounding, not an absolute guarantee. (assistant/services.py:90, assistant/services.py:103, assistant/services.py:113, assistant/llm_provider.py:20, assistant/tests.py:52, assistant/tests.py:64)

---

### 5. How do you defend against prompt injection in supplier descriptions, and what are the limits?

Before product names or descriptions reach the model, a filter redacts several known instruction override phrases. The system prompt also treats catalogue text as untrusted data. The filter can miss paraphrases, encoded text, and other languages, so it reduces risk but cannot eliminate it. (assistant/services.py:16, assistant/services.py:28, assistant/services.py:98, assistant/llm_provider.py:23)

---

### 6. How did you forecast demand and validate the model? Where is the leakage guard?

The script uses a recent weighted average for new SKUs, Croston SBA for intermittent demand, and weighted Ridge regression for regular demand, with promotion and Diwali features. It holds out the final four weeks and compares the hybrid model with three simple baselines. For the backtest, training rows after 2026-08-24 are excluded. (ml/train_forecast.py:102, ml/train_forecast.py:122, ml/train_forecast.py:132, ml/train_forecast.py:141, ml/train_forecast.py:227, ml/train_forecast.py:236)

---

### 7. Which forecasts are hardest, and how do you account for promotions, Diwali, and sparse histories?

High-volume, volatile SKUs are difficult when one-off bulk orders shift demand; the assignment reports a holdout MAE of 23.91 for `GRP-1024`. Promotions are model features or fixed lifts for new and intermittent SKUs. Diwali is represented by proximity to festival dates. Croston SBA handles intermittent sales, while new SKUs use a recent weighted average. (ml/train_forecast.py:41, ml/train_forecast.py:122, ml/train_forecast.py:132, ml/train_forecast.py:141, ml/train_forecast.py:211)

---

### 8. What is the weakest part of the submission, and how would you improve it with two more days?

The forecast fits each regular SKU separately, so a new product cannot borrow seasonal or promotion patterns from related products. I'd try a pooled model that learns shared category patterns, then compare it with the current approach using rolling backtests. I'd also add typo-tolerant catalogue search while preserving vehicle fitment filters. (ml/train_forecast.py:141, catalogue/services.py:74)
---

## Part 2: Django Track Questions (Bonus Sections Attempted: A2 Order Engine & B Supplier Sync)

### 1. Where exactly is overselling prevented? Cite the code, and explain what would happen without it when two confirms arrive together.
- **Citation**: `orders/services.py:293-336` (`confirm_order`). Inside `with transaction.atomic():` (`orders/services.py:293`), we lock the `Order` row (`Order.objects.select_for_update().get(...)` at `orders/services.py:295`) and lock all referenced `Product` rows sorted deterministically by `sku` (`Product.objects.select_for_update().filter(sku__in=skus).order_by("sku")` at `orders/services.py:306-309`).
- **Without it**: Under `READ COMMITTED`, two simultaneous confirm requests for 3 units when `stock = 5` would both read `stock = 5`, both pass the `item.quantity > prod.stock` check (`orders/services.py:315`), and both deduct 3, leaving `stock = -1` (oversold). Sorting by `sku` before `SELECT ... FOR UPDATE` also prevents lock-ordering deadlocks when two multi-line orders overlap in opposite SKU order.

### 2. How do you calculate and round GST? What would go wrong with floats, or with Decimal's default rounding?
- **Citation**: `orders/services.py:29-44` (`compute_line_amounts`). Each line calculates `line_subtotal = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)` and `line_tax = (line_subtotal * Decimal("0.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`. Order `subtotal` and `tax_total` sum the rounded per-line values (`orders/services.py:224-225`, `362-363`).
- **What goes wrong with floats or default rounding**: Binary `float` cannot represent `0.18` or `1459.50` exactly, causing cumulative 1-paisa drift. Python `Decimal`'s default rounding is `ROUND_HALF_EVEN` (banker's rounding), which rounds `0.005` to `0.00` when the preceding digit is even, violating Indian GST commercial rounding (`ROUND_HALF_UP`).

### 3. How do you guarantee unique order numbers and idempotent order creation when duplicate requests arrive at the same moment?
- **Unique order numbers (`orders/services.py:47-66`)**: `_next_order_number()` executes an atomic PostgreSQL upsert: `INSERT INTO orders_dailysequence (date, last_seq) VALUES (%s, 1) ON CONFLICT (date) DO UPDATE SET last_seq = orders_dailysequence.last_seq + 1 RETURNING last_seq`. PostgreSQL serializes conflicting row updates on `date`, guaranteeing strictly sequential, collision-free `ORD-YYYYMMDD-NNNN` numbers.
- **Concurrent idempotency (`orders/services.py:183-204`)**: When `Idempotency-Key` is present, `create_order` acquires a transaction-level PostgreSQL advisory lock (`SELECT pg_advisory_xact_lock(%s)` at `orders/services.py:187-190`) hashed from the key (`_advisory_lock_id` at `orders/services.py:76-78`). A second simultaneous request with the same key blocks until the first commits, then reads the committed `Order` (`orders/services.py:191-195`), verifies `idempotency_body_hash` (`orders/services.py:197-200`), and returns the original order (or raises `409 IDEMPOTENCY_CONFLICT`).

### 4. Where are status transitions enforced, and how do you guarantee a cancel restores stock exactly once?
- **Status transitions**: Enforced inside `transaction.atomic()` with `Order.objects.select_for_update()` in `confirm_order` (`orders/services.py:295-302`), `dispatch_order` (`orders/services.py:384-392`), `deliver_order` (`orders/services.py:402-410`), `cancel_order` (`orders/services.py:422-452`), and `update_order_items` (`orders/services.py:246-252`, raising `409 ORDER_LOCKED` if `status != "DRAFT"`).
- **Cancel restores stock once (`orders/services.py:422-452`)**: `cancel_order` locks the `Order` row first (`select_for_update()`). Only if `order.status == Order.STATUS_CONFIRMED` (`orders/services.py:432`) does it lock the `Product` rows and add back `item.quantity` (`orders/services.py:442`), immediately setting `order.status = Order.STATUS_CANCELLED` (`orders/services.py:445`) before committing. A concurrent or second cancel request waits on the row lock, sees `status == "CANCELLED"`, and raises `409 INVALID_TRANSITION` (`orders/services.py:449`).

### 5. How does your supplier sync handle rate limits, failures and duplicates? How do you guarantee it changes nothing when the feed can't be fully fetched?
- **Rate limits & failures (`supplier_sync/services.py:78-127`)**: Each cursor page is attempted up to `MAX_ATTEMPTS_PER_PAGE = 5` times (`supplier_sync/services.py:16, 81`). On HTTP `429`, it parses `Retry-After` (`supplier_sync/services.py:101-106`) and sleeps that duration before retrying. On HTTP `>= 500` or `requests.RequestException`, it retries with exponential backoff `0.2 * (2 ** (attempt - 1))` (`supplier_sync/services.py:85-90, 108-113`). On `401`/`403` or after 5 failed attempts, it raises `502 SUPPLIER_UNAVAILABLE`.
- **All-or-nothing (`supplier_sync/services.py:72-135, 160`)**: All pages are fetched into `all_raw_items` in memory before `with transaction.atomic():` (`supplier_sync/services.py:160`) is ever entered. If any page fails, no database transaction is opened.
- **Duplicates (`supplier_sync/services.py:148-154`)**: After filtering invalid items (`supplier_sync/services.py:137-146`), items are deduplicated into `deduped[sku]` by comparing parsed ISO-8601 timestamps `_parse_updated_at(raw.get("updated_at"))` (`supplier_sync/services.py:47-51, 152-154`), keeping only the latest version.

### 6. How does the sync decide between created, updated and unchanged, and why does a second run change nothing?
- **Citation**: `supplier_sync/services.py:160-214`. Inside `transaction.atomic()`, existing products matching the deduplicated SKUs are locked (`supplier_sync/services.py:161-166`).
  - If `sku not in existing_map` (`supplier_sync/services.py:178`): instantiated with `stock=0` and added to `to_create` (`created_count += 1`).
  - If `sku in existing_map` (`supplier_sync/services.py:192-209`): compares `name`, `category`, `brand`, `vehicle_fitment`, `description`, and `price` (`Decimal` quantized to `0.01`). Only if at least one field differs is it added to `to_update` (`updated_count += 1`); otherwise `unchanged_count += 1` (`supplier_sync/services.py:210`).
- **Stock preservation & idempotency**: `supplier_stock` is never read and `stock` is omitted from `bulk_update` (`supplier_sync/services.py:214-224`). On a second run with the same feed, all 69 valid deduplicated SKUs exist in `existing_map` with identical field values, resulting in `created: 0, updated: 0, unchanged: 69`.
