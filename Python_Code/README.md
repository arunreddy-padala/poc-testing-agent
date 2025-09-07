
---

# Item Catalog API

A lightweight Flask-based **catalog service** for managing and querying items (products).
Supports creation, filtering, searching, sorting, pagination, projections, stats, and related items.
Designed with **deterministic sample data** for benchmarking and load testing (e.g., with JMeter).

---

## 🚀 Features

* In-memory + JSON file persistence (`data.json`).
* Deterministic sample dataset (\~1000 items by default).
* Rich query support:

  * Filtering by category, vendor, price, rating, tags, or text search.
  * Multi-field sorting (`sort_by=price,-rating,name`).
  * Pagination via `offset/limit` or `page/page_size`.
  * Field projection (`fields=id,name,price`).
* Optional aggregate statistics.
* Extra views by category, price range, and “related items”.


---

## 📂 Data Storage

* Items are held in memory (`ITEMS` list).
* On startup:

  * If `data.json` exists → load it.
  * Otherwise → generate sample data, then save.
* Data is persisted to `data.json` atomically (via temp file swap).

---

## 📑 API Reference

### 1. Create Item

**POST `/items`**

**Body JSON:**

```json
{
  "name": "My Product",
  "category": "electronics",
  "price": 199.99,
  "rating": 4.2,
  "tags": ["sale", "popular"],
  "stock": 50,
  "vendor": "Acme Inc.",
  "attributes": {"color": "red", "size": "M"}
}
```

**Notes:**

* `id` and `created_at` auto-assigned.
* If `category == "luxury"` or `price > 1000`:

  * Adds `"luxury"` tag.
  * Ensures rating ≥ 4.

**Response:**
`201 Created` with the created item.
`Location` header points to `/items/<id>`.

---

### 2. Get Single Item

**GET `/items/<item_id>`**

Query params:

* `fields=id,name,price,rating` → return only selected fields.

---

### 3. List/Search Items

**GET `/items`**

#### Filtering

* `category=electronics`
* `vendor=Acme Inc.`
* `min_price=100&max_price=500`
* `min_rating=3.5&max_rating=5`
* `tag=pro&tag=lite` (repeatable)
* `q=omega` (searches name, vendor, category, tags)

#### Sorting

* `sort_by=price,-rating,name`
  (prefix `-` for descending)

#### Pagination

* Offset/limit → `?offset=100&limit=50`
* Page/page\_size → `?page=2&page_size=25`

#### Projection

* `fields=id,name,price`

#### Stats

* `include_stats=true`
  Adds `stats_over_page` and `stats_over_filtered`.

**Response:**

```json
{
  "data": [...],
  "meta": {
    "mode": "page",
    "page": 2,
    "page_size": 25,
    "total": 400,
    "pages": 16,
    "returned": 25,
    "has_next": true,
    "stats_over_page": {"avg_price": 250.3, "avg_rating": 4.1, "count": 25},
    "stats_over_filtered": {"avg_price": 245.6, "avg_rating": 4.0, "count": 400}
  }
}
```

Header: `X-Total-Count: 400`

---

### 4. List by Category

**GET `/categories/<category>/items`**

Same features as `/items`, but implicitly filtered by category from the path.

---

### 5. List by Price Range

**GET `/items/price/<min>/<max>`**

Example:
`/items/price/100/500?sort_by=-rating`

Same features as `/items`.

---

### 6. Related Items

**GET `/items/<item_id>/related`**

Query params:

* `limit=5` (default)
* `sort_by=-rating,price`
* `fields=id,name,price`

**Response:**

```json
{
  "base_item": {"id": "1234-uuid", "category": "electronics"},
  "related": [
    {"id": "5678-uuid", "name": "Swift Gadget 200", "price": 199.99, "rating": 4.7},
    ...
  ]
}
```

---

## ❌ Error Format

Consistent JSON envelope:

```json
{
  "error": {
    "status": 404,
    "message": "Item not found.",
    "timestamp": "2025-09-06T23:59:59Z"
  }
}
```

---

## 🧪 Load Testing

* Ships with deterministic \~1000-item dataset for reproducible JMeter runs.
* Default vendors, categories, and tags for realistic filtering scenarios.

---

## ⚡ Quickstart (curl Examples)

Create an item:

```bash
curl -X POST http://localhost:8000/items \
  -H "Content-Type: application/json" \
  -d '{
        "name": "Super Gadget",
        "category": "electronics",
        "price": 299.99,
        "tags": ["new", "popular"],
        "stock": 10,
        "vendor": "Acme Inc.",
        "attributes": {"color": "blue", "size": "L"}
      }'
```

Get a single item by ID:

```bash
curl http://localhost:8000/items/<item_id>?fields=id,name,price,rating
```

List items (filter, sort, paginate):

```bash
curl "http://localhost:8000/items?category=electronics&min_price=100&max_price=500&sort_by=-rating&limit=5"
```

List items in a category:

```bash
curl "http://localhost:8000/categories/electronics/items?sort_by=price&page=1&page_size=3"
```

List items in a price range:

```bash
curl "http://localhost:8000/items/price/100/300?fields=id,name,price&include_stats=true"
```

Get related items:

```bash
curl "http://localhost:8000/items/<item_id>/related?limit=5&fields=id,name,price,rating"
```

---

## 🔧 Notes

* Thread-safe with a global lock (`STORE_LOCK`).
* File writes are atomic to prevent corruption.
* For production: run behind a real WSGI server (e.g., Gunicorn, uWSGI).
* Extendable with `PUT`/`DELETE` endpoints if needed.

---


