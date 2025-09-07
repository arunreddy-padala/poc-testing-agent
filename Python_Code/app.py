# app.py
import json
import os
import threading
import uuid
import random
import string
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

from flask import Flask, request, jsonify, make_response, url_for

app = Flask(__name__)

# ----------------------------
# Storage (in-memory + JSON file)
# ----------------------------
DATA_FILE = "data.json"
STORE_LOCK = threading.Lock()
ITEMS: List[Dict[str, Any]] = []  # each item is a dict

# Allowed fields in the item (helps validation and "fields" projection)
ITEM_FIELDS = {
    "id", "name", "category", "price", "rating", "tags",
    "created_at", "stock", "vendor", "attributes"
}

RANDOM = random.Random(42)  # deterministic seed for reproducibility


# ----------------------------
# Utilities
# ----------------------------
def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def load_data() -> None:
    global ITEMS
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            ITEMS[:] = json.load(f)
    else:
        # If no file, generate a sizable deterministic sample dataset for JMeter.
        generate_sample_data(n=1000)
        save_data()


def save_data() -> None:
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ITEMS, f, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)


def generate_name() -> str:
    adj = ["Swift", "Solid", "Bright", "Prime", "Aero", "Hyper", "Quantum", "Omega", "Nimbus", "Vector"]
    noun = ["Widget", "Gadget", "Module", "Device", "Kit", "Bundle", "Unit", "Pack", "Core", "Engine"]
    return f"{RANDOM.choice(adj)} {RANDOM.choice(noun)} {RANDOM.randint(100, 999)}"


def generate_tags() -> List[str]:
    pool = ["new", "sale", "clearance", "eco", "luxury", "budget", "refurb", "popular", "pro", "lite"]
    n = RANDOM.randint(1, 4)
    return RANDOM.sample(pool, n)


def generate_vendor() -> str:
    vendors = ["Acme Inc.", "Globex", "Initech", "Umbrella", "WayneTech", "Stark Industries", "Tyrell", "Aperture"]
    return RANDOM.choice(vendors)


def random_attributes() -> Dict[str, Any]:
    colors = ["red", "blue", "green", "black", "white", "silver", "gold"]
    sizes = ["XS", "S", "M", "L", "XL"]
    return {
        "color": RANDOM.choice(colors),
        "size": RANDOM.choice(sizes),
        "sku": "".join(RANDOM.choice(string.ascii_uppercase + string.digits) for _ in range(8)),
    }


def generate_sample_data(n: int = 500) -> None:
    """Populate ITEMS with deterministic but varied data."""
    global ITEMS
    categories = ["electronics", "home", "outdoors", "toys", "apparel", "office", "beauty"]
    base_time = datetime(2023, 1, 1)
    ITEMS.clear()
    for i in range(n):
        created = base_time + timedelta(minutes=i * 17)  # spaced-out timestamps
        item = {
            "id": str(uuid.uuid4()),
            "name": generate_name(),
            "category": RANDOM.choice(categories),
            "price": round(RANDOM.uniform(5.0, 1500.0), 2),
            "rating": round(RANDOM.uniform(1.0, 5.0), 2),
            "tags": generate_tags(),
            "created_at": created.isoformat(timespec="seconds") + "Z",
            "stock": RANDOM.randint(0, 1000),
            "vendor": generate_vendor(),
            "attributes": random_attributes(),
        }
        ITEMS.append(item)


def parse_bool(v: Optional[str]) -> Optional[bool]:
    if v is None:
        return None
    return v.lower() in ("1", "true", "yes", "y", "on")


def coerce_number(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def project_fields(item: Dict[str, Any], fields: Optional[List[str]]) -> Dict[str, Any]:
    if not fields:
        return item
    return {k: v for k, v in item.items() if k in fields}


def multi_field_sort_key(fields: List[Tuple[str, bool]]):
    """
    Build a key function for multi-field sorting.
    fields: list of (field_name, ascending)
    """
    def key_fn(it: Dict[str, Any]):
        key_parts = []
        for fname, asc in fields:
            val = it.get(fname)
            # Normalize strings for case-insensitive ordering
            if isinstance(val, str):
                val = val.lower()
            # None-safe sorting: None goes last in ascending, first in descending
            none_sentinel = (float("inf") if asc else float("-inf"))
            if val is None:
                val = none_sentinel
            key_parts.append(val if asc else _negate_if_number(val))
        # As a final stable tiebreaker, use created_at then id
        key_parts.append(it.get("created_at", ""))
        key_parts.append(it.get("id", ""))
        return tuple(key_parts)
    return key_fn


def _negate_if_number(x: Any) -> Any:
    return -x if isinstance(x, (int, float)) else x


def apply_filters(data: List[Dict[str, Any]], args) -> List[Dict[str, Any]]:
    """
    Supported filters:
      - category
      - min_price, max_price
      - tag (can repeat, e.g. ?tag=pro&tag=lite)
      - q  (substring search across name/vendor/tags/category)
      - min_rating, max_rating
      - vendor
    """
    out = data
    category = args.get("category")
    vendor = args.get("vendor")
    min_price = coerce_number(args.get("min_price"))
    max_price = coerce_number(args.get("max_price"))
    min_rating = coerce_number(args.get("min_rating"))
    max_rating = coerce_number(args.get("max_rating"))
    tags = args.getlist("tag") if hasattr(args, "getlist") else args.get("tag", [])
    if isinstance(tags, str):
        tags = [tags]
    q = args.get("q")

    if category:
        out = [x for x in out if x.get("category") == category]
    if vendor:
        out = [x for x in out if x.get("vendor") == vendor]
    if min_price is not None:
        out = [x for x in out if isinstance(x.get("price"), (int, float)) and x["price"] >= min_price]
    if max_price is not None:
        out = [x for x in out if isinstance(x.get("price"), (int, float)) and x["price"] <= max_price]
    if min_rating is not None:
        out = [x for x in out if isinstance(x.get("rating"), (int, float)) and x["rating"] >= min_rating]
    if max_rating is not None:
        out = [x for x in out if isinstance(x.get("rating"), (int, float)) and x["rating"] <= max_rating]
    if tags:
        tset = set(tags)
        out = [x for x in out if tset.issubset(set(x.get("tags", [])))]
    if q:
        ql = q.lower()
        out = [
            x for x in out
            if ql in x.get("name", "").lower()
            or ql in x.get("vendor", "").lower()
            or ql in x.get("category", "").lower()
            or any(ql in str(tag).lower() for tag in x.get("tags", []))
        ]
    return out


def apply_sort(data: List[Dict[str, Any]], sort_by: Optional[str]) -> List[Dict[str, Any]]:
    """
    sort_by: comma-separated fields, prefix with '-' for descending
             e.g., 'price,-rating,name'
    """
    if not sort_by:
        # default sort: -created_at (newest first), then name
        fields = [("created_at", False), ("name", True)]
    else:
        fields = []
        for raw in sort_by.split(","):
            raw = raw.strip()
            if not raw:
                continue
            asc = True
            if raw.startswith("-"):
                asc = False
                raw = raw[1:]
            fields.append((raw, asc))
    key_fn = multi_field_sort_key(fields)
    return sorted(data, key=key_fn)


def apply_pagination(data: List[Dict[str, Any]], args) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Supports page/page_size (1-based) and offset/limit (0-based).
    If offset/limit present, they take precedence.
    """
    total = len(data)
    # Offset/limit style
    limit = args.get("limit")
    offset = args.get("offset")
    if limit is not None or offset is not None:
        try:
            lim = int(limit) if limit is not None else 50
            off = int(offset) if offset is not None else 0
        except ValueError:
            lim, off = 50, 0
        lim = max(0, min(lim, 500))
        off = max(0, off)
        page_data = data[off: off + lim]
        meta = {
            "mode": "offset",
            "offset": off,
            "limit": lim,
            "total": total,
            "returned": len(page_data),
            "has_more": off + lim < total,
        }
        return page_data, meta

    # Page/page_size style
    try:
        page = int(args.get("page", 1))
        page_size = int(args.get("page_size", 50))
    except ValueError:
        page, page_size = 1, 50
    page = max(1, page)
    page_size = max(1, min(page_size, 500))
    start = (page - 1) * page_size
    end = start + page_size
    page_data = data[start:end]
    pages = (total + page_size - 1) // page_size if page_size else 0
    meta = {
        "mode": "page",
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "returned": len(page_data),
        "has_next": page < pages,
        "has_prev": page > 1,
    }
    return page_data, meta


def compute_stats(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not data:
        return {"avg_price": None, "avg_rating": None, "count": 0}
    prices = [d["price"] for d in data if isinstance(d.get("price"), (int, float))]
    ratings = [d["rating"] for d in data if isinstance(d.get("rating"), (int, float))]
    return {
        "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "count": len(data),
    }


def parse_fields_param(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    fields = [f.strip() for f in raw.split(",") if f.strip()]
    # Keep only allowed fields to avoid surprises
    return [f for f in fields if f in ITEM_FIELDS]


# ----------------------------
# Error helpers
# ----------------------------
def json_error(status: int, message: str):
    resp = jsonify({"error": {"status": status, "message": message, "timestamp": now_iso()}})
    return make_response(resp, status)


# ----------------------------
# Routes
# ----------------------------
@app.route("/items", methods=["POST"])
def create_item():
    """
    Create a new item.
    Body JSON: {name, category, price, rating?, tags?, stock?, vendor?, attributes?}
    - id assigned if not provided
    - created_at auto-set
    """
    payload = request.get_json(silent=True)
    if not payload:
        return json_error(400, "Invalid or missing JSON body.")

    # Basic validation
    name = payload.get("name")
    category = payload.get("category")
    price = coerce_number(payload.get("price"))
    if not name or not category or price is None:
        return json_error(400, "Fields 'name', 'category', and numeric 'price' are required.")

    # Build the item
    new_item = {
        "id": payload.get("id") or str(uuid.uuid4()),
        "name": name,
        "category": category,
        "price": round(float(price), 2),
        "rating": round(float(coerce_number(payload.get("rating")) or 0), 2),
        "tags": payload.get("tags") or [],
        "created_at": now_iso(),
        "stock": int(payload.get("stock") or 0),
        "vendor": payload.get("vendor") or generate_vendor(),
        "attributes": payload.get("attributes") or {},
    }

    # Simple business logic example:
    # If category is "luxury" or price > 1000, auto-add "luxury" tag and ensure rating >= 4
    if new_item["category"].lower() == "luxury" or new_item["price"] > 1000:
        if "luxury" not in new_item["tags"]:
            new_item["tags"].append("luxury")
        new_item["rating"] = max(new_item["rating"], 4.0)

    with STORE_LOCK:
        # Reject duplicate id
        if any(it["id"] == new_item["id"] for it in ITEMS):
            return json_error(409, "Item with this 'id' already exists.")
        ITEMS.append(new_item)
        save_data()

    resp = make_response(jsonify(new_item), 201)
    resp.headers["Location"] = url_for("get_item", item_id=new_item["id"], _external=False)
    return resp


@app.route("/items/<item_id>", methods=["GET"])
def get_item(item_id: str):
    """
    Fetch a single item by id.
    Optional: ?fields=name,price,rating  (projection)
    """
    fields = parse_fields_param(request.args.get("fields"))
    with STORE_LOCK:
        item = next((x for x in ITEMS if x["id"] == item_id), None)
    if not item:
        return json_error(404, "Item not found.")
    return jsonify(project_fields(item, fields))


@app.route("/items", methods=["GET"])
def list_items():
    """
    GET ALL #1
    Query params:
      - Filtering: category, vendor, min_price, max_price, min_rating, max_rating, tag (repeat), q
      - Sorting: sort_by=price,-rating,name
      - Pagination: page, page_size  OR  offset, limit
      - Projection: fields=name,price
      - Stats: include_stats=true
    Returns: { data: [...], meta: {...} } and X-Total-Count header
    """
    args = request.args
    include_stats = parse_bool(args.get("include_stats"))
    fields = parse_fields_param(args.get("fields"))
    sort_by = args.get("sort_by")

    with STORE_LOCK:
        data = ITEMS.copy()

    # Filters
    data = apply_filters(data, args)
    total_after_filter = len(data)

    # Sorting
    data = apply_sort(data, sort_by)

    # Pagination
    page_data, meta = apply_pagination(data, args)
    if include_stats:
        meta["stats_over_page"] = compute_stats(page_data)
        meta["stats_over_filtered"] = compute_stats(data)

    # Projection
    if fields:
        page_data = [project_fields(x, fields) for x in page_data]

    resp = make_response(jsonify({"data": page_data, "meta": meta}), 200)
    resp.headers["X-Total-Count"] = str(total_after_filter)
    return resp


@app.route("/categories/<category>/items", methods=["GET"])
def list_items_by_category(category: str):
    """
    GET ALL #2 (different endpoint + path var)
    Same query features as /items (sorting, pagination, projection, stats), implicitly filtered by category.
    """
    # Reuse the main list endpoint logic but force category filter
    # Build a mutable dict of args
    class ArgsProxy(dict):
        def get(self, k, default=None):
            if k == "category":
                return category
            return super().get(k, default)
        def getlist(self, k):
            val = self.get(k)
            if isinstance(val, list):
                return val
            if val is None:
                return []
            return [val]

    raw = dict(request.args)
    args = ArgsProxy(**raw)
    args["category"] = category  # enforce

    include_stats = parse_bool(args.get("include_stats"))
    fields = parse_fields_param(args.get("fields"))
    sort_by = args.get("sort_by")

    with STORE_LOCK:
        data = ITEMS.copy()

    data = apply_filters(data, args)
    total_after_filter = len(data)
    data = apply_sort(data, sort_by)
    page_data, meta = apply_pagination(data, args)
    if include_stats:
        meta["stats_over_page"] = compute_stats(page_data)
        meta["stats_over_filtered"] = compute_stats(data)
    if fields:
        page_data = [project_fields(x, fields) for x in page_data]

    resp = make_response(jsonify({"data": page_data, "meta": meta}), 200)
    resp.headers["X-Total-Count"] = str(total_after_filter)
    return resp


@app.route("/items/price/<min_price>/<max_price>", methods=["GET"])
def list_items_by_price_range(min_price: str, max_price: str):
    """
    GET ALL #3 (extra variant): price range via path variables plus usual query features.
    """
    # Convert and place into args override
    mn = coerce_number(min_price)
    mx = coerce_number(max_price)
    if mn is None or mx is None:
        return json_error(400, "min_price and max_price must be numeric.")

    class ArgsProxy(dict):
        def get(self, k, default=None):
            if k == "min_price":
                return mn
            if k == "max_price":
                return mx
            return super().get(k, default)
        def getlist(self, k):
            val = self.get(k)
            if isinstance(val, list):
                return val
            if val is None:
                return []
            return [val]

    raw = dict(request.args)
    args = ArgsProxy(**raw)
    args["min_price"] = mn
    args["max_price"] = mx

    include_stats = parse_bool(args.get("include_stats"))
    fields = parse_fields_param(args.get("fields"))
    sort_by = args.get("sort_by")

    with STORE_LOCK:
        data = ITEMS.copy()

    data = apply_filters(data, args)
    total_after_filter = len(data)
    data = apply_sort(data, sort_by)
    page_data, meta = apply_pagination(data, args)
    if include_stats:
        meta["stats_over_page"] = compute_stats(page_data)
        meta["stats_over_filtered"] = compute_stats(data)
    if fields:
        page_data = [project_fields(x, fields) for x in page_data]

    resp = make_response(jsonify({"data": page_data, "meta": meta}), 200)
    resp.headers["X-Total-Count"] = str(total_after_filter)
    return resp


@app.route("/items/<item_id>/related", methods=["GET"])
def related_items(item_id: str):
    """
    Bonus: get "related items" in the same category (useful for varied path + query params).
    Query: limit (default 5), sort_by, fields
    """
    try:
        limit = int(request.args.get("limit", 5))
    except ValueError:
        limit = 5
    limit = max(0, min(limit, 50))
    sort_by = request.args.get("sort_by")
    fields = parse_fields_param(request.args.get("fields"))

    with STORE_LOCK:
        current = next((x for x in ITEMS if x["id"] == item_id), None)
        if not current:
            return json_error(404, "Item not found.")
        same_cat = [x for x in ITEMS if x["category"] == current["category"] and x["id"] != item_id]

    same_cat = apply_sort(same_cat, sort_by or "-rating,price")
    out = same_cat[:limit]
    if fields:
        out = [project_fields(x, fields) for x in out]
    return jsonify({"base_item": {"id": current["id"], "category": current["category"]}, "related": out})


# ----------------------------
# App startup
# ----------------------------
with STORE_LOCK:
    load_data()


# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    # threaded=True to handle concurrent JMeter requests; use a real WSGI server for serious loads.
    app.run(host="0.0.0.0", port=8000, threaded=True)
