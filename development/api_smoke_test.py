"""End-to-end REST API check against the running test instance.

Run with ``./dev smoke``. Exercises the whole app through HTTP only -- no Django
imports, no shortcuts -- so it proves the API a script or another service would
actually use. Every check prints PASS or FAIL and the script exits non-zero if
anything failed.

Reads NAUTOBOT_URL and NAUTOBOT_SUPERUSER_API_TOKEN from the environment
(./dev smoke sets both from development/dev.env).
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("NAUTOBOT_URL", "http://localhost:8081").rstrip("/")
TOKEN = os.environ.get("NAUTOBOT_SUPERUSER_API_TOKEN", "")
API = f"{BASE}/api"
PLUGIN = f"{API}/plugins/spare-parts"

failures = []
checks = 0


def call(method, url, body=None, expect=None):
    """Make an API call and return (status, parsed body)."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Token {TOKEN}")
    request.add_header("Accept", "application/json")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:500].decode(errors="replace")}
    except urllib.error.URLError as exc:
        print(f"\nCannot reach {url}: {exc.reason}")
        print("Is the stack up? Try ./dev up")
        sys.exit(2)


def check(label, condition, detail=""):
    """Record and print one assertion."""
    global checks
    checks += 1
    if condition:
        print(f"PASS  {label}")
    else:
        print(f"FAIL  {label}" + (f"\n        {detail}" if detail else ""))
        failures.append(label)
    return bool(condition)


def first_id(url):
    """Id of the first result from a list endpoint, or None."""
    status, body = call("GET", url)
    if status != 200 or not body.get("results"):
        return None
    return body["results"][0]["id"]


print(f"Target: {BASE}\n")

status, body = call("GET", f"{API}/status/")
check("API reachable and token accepted", status == 200, f"{status} {body}")
if status != 200:
    sys.exit(2)
check(
    "app is installed",
    "nautobot_spare_parts" in (body.get("plugins") or {}),
    f"plugins: {body.get('plugins')}",
)

print("\n--- read endpoints ---")
for name, url in [
    ("part types list", f"{PLUGIN}/spare-part-types/"),
    ("inventory list", f"{PLUGIN}/spare-part-inventory/"),
    ("transactions list", f"{PLUGIN}/spare-part-transactions/"),
    ("search filter (?q=)", f"{PLUGIN}/spare-part-types/?q=samsung"),
    ("low stock filter", f"{PLUGIN}/spare-part-inventory/?low_stock=true"),
    ("out of stock filter", f"{PLUGIN}/spare-part-inventory/?out_of_stock=true"),
    ("nested depth=1", f"{PLUGIN}/spare-part-inventory/?depth=1"),
]:
    status, body = call("GET", url)
    check(name, status == 200, f"{status} {str(body)[:200]}")

print("\n--- create through the API ---")
manufacturer_id = first_id(f"{API}/dcim/manufacturers/")
location_id = first_id(f"{API}/dcim/locations/")

# Fixed names, not a random suffix: this script is the pre-deploy gate and gets
# run repeatedly, so it reuses one part type and one stock record instead of
# leaving a new pair behind every time. The API cannot clean up after itself --
# transactions are deliberately undeletable -- so not making a mess is the only
# option available.
SMOKE_PART = "Smoke test part (safe to delete)"
SMOKE_PART_NUMBER = "SMOKE-TEST-1"

status, existing = call("GET", f"{PLUGIN}/spare-part-types/?name={SMOKE_PART.replace(' ', '%20')}")
reused_part = existing["results"][0] if status == 200 and existing.get("results") else None

if reused_part:
    part_id = reused_part["id"]
    check("reuse the existing smoke test part type", True)
else:
    status, part = call(
        "POST",
        f"{PLUGIN}/spare-part-types/",
        {
            "name": SMOKE_PART,
            "part_number": SMOKE_PART_NUMBER,
            "category": "psu",
            "manufacturer": manufacturer_id,
            "unit_cost": "12.50",
        },
    )
    if not check("create part type", status == 201, f"{status} {part}"):
        sys.exit(1)
    part_id = part["id"]

status, existing = call("GET", f"{PLUGIN}/spare-part-inventory/?spare_part_type={part_id}&location={location_id}")
reused_record = existing["results"][0] if status == 200 and existing.get("results") else None

if reused_record:
    inventory_id = reused_record["id"]
    check("reuse the existing smoke test stock record", True)
    # Bring it back to the state the rest of the script expects.
    on_hand = reused_record["quantity_on_hand"]
    reserved = reused_record["quantity_reserved"]
    if reserved:
        call(
            "POST",
            f"{PLUGIN}/spare-part-inventory/{inventory_id}/deallocate/",
            {"quantity": reserved, "reason": "smoke test reset"},
        )
    if on_hand != 10:
        call(
            "POST",
            f"{PLUGIN}/spare-part-inventory/{inventory_id}/adjust/",
            {"quantity": 10 - on_hand, "reason": "smoke test reset to a known state"},
        )
    status, inventory = call("GET", f"{PLUGIN}/spare-part-inventory/{inventory_id}/")
    check(
        "reset to a known state",
        inventory["quantity_on_hand"] == 10 and inventory["quantity_reserved"] == 0,
        f"on hand {inventory['quantity_on_hand']}, reserved {inventory['quantity_reserved']}",
    )
else:
    status, inventory = call(
        "POST",
        f"{PLUGIN}/spare-part-inventory/",
        {
            "spare_part_type": part_id,
            "location": location_id,
            "quantity_on_hand": 10,
            "minimum_quantity": 4,
            "reorder_quantity": 10,
            "storage_location_detail": "Smoke test shelf",
        },
    )
    if not check("create inventory record", status == 201, f"{status} {inventory}"):
        sys.exit(1)
    inventory_id = inventory["id"]
    check("opening balance is set", inventory["quantity_on_hand"] == 10, str(inventory.get("quantity_on_hand")))

    status, body = call("GET", f"{PLUGIN}/spare-part-transactions/?spare_part_inventory={inventory_id}")
    check(
        "opening balance wrote an audit record",
        status == 200 and body["count"] == 1,
        f"{status} count={body.get('count')}",
    )

print("\n--- movements ---")
inv_url = f"{PLUGIN}/spare-part-inventory/{inventory_id}"

status, body = call("POST", f"{inv_url}/check-in/", {"quantity": 5, "reason": "Smoke test delivery"})
check(
    "check-in",
    status == 200 and body["inventory"]["quantity_on_hand"] == 15,
    f"{status} {str(body)[:200]}",
)

status, body = call(
    "POST",
    f"{inv_url}/check-out/",
    {"quantity": 3, "reason": "Smoke test consumption", "jira_ticket": "INFRA2-9999"},
)
check(
    "check-out",
    status == 200 and body["inventory"]["quantity_on_hand"] == 12,
    f"{status} {str(body)[:200]}",
)
check(
    "check-out kept the jira reference",
    body.get("transaction", {}).get("jira_ticket") == "INFRA2-9999",
    str(body.get("transaction", {}).get("jira_ticket")),
)

status, body = call("POST", f"{inv_url}/allocate/", {"quantity": 4, "reason": "Smoke test reservation"})
check(
    "allocate reserves without moving stock",
    status == 200
    and body["inventory"]["quantity_reserved"] == 4
    and body["inventory"]["quantity_on_hand"] == 12
    and body["inventory"]["quantity_available"] == 8,
    f"{status} {str(body)[:200]}",
)

status, body = call("POST", f"{inv_url}/deallocate/", {"quantity": 1, "reason": "Smoke test release"})
check(
    "deallocate",
    status == 200 and body["inventory"]["quantity_reserved"] == 3,
    f"{status} {str(body)[:200]}",
)

status, body = call(
    "POST",
    f"{inv_url}/check-out/",
    {"quantity": 2, "reason": "Smoke test fulfil", "fulfil_reservation": True},
)
check(
    "check-out against a reservation drops both counters",
    status == 200 and body["inventory"]["quantity_on_hand"] == 10 and body["inventory"]["quantity_reserved"] == 1,
    f"{status} {str(body)[:200]}",
)

status, body = call("POST", f"{inv_url}/adjust/", {"quantity": -1, "reason": "Smoke test stock take"})
check("adjust", status == 200 and body["inventory"]["quantity_on_hand"] == 9, f"{status} {str(body)[:200]}")

print("\n--- refusals (these must fail cleanly, not corrupt the count) ---")
status, body = call("POST", f"{inv_url}/check-out/", {"quantity": 999, "reason": "Too many"})
check("over-check-out is rejected", status == 400, f"{status} {str(body)[:200]}")

status, body = call("POST", f"{inv_url}/check-in/", {"quantity": 0, "reason": "Zero"})
check("zero quantity is rejected", status == 400, f"{status} {str(body)[:200]}")

status, body = call("POST", f"{inv_url}/check-in/", {"quantity": -5, "reason": "Negative"})
check("negative check-in is rejected", status == 400, f"{status} {str(body)[:200]}")

status, body = call("POST", f"{inv_url}/check-in/", {"quantity": 1, "reason": "   "})
check("blank reason is rejected", status == 400, f"{status} {str(body)[:200]}")

status, body = call("POST", f"{inv_url}/adjust/", {"quantity": 0, "reason": "No-op"})
check("zero adjustment is rejected", status == 400, f"{status} {str(body)[:200]}")

status, body = call("POST", f"{inv_url}/check-out/", {"quantity": 1, "reason": "Bad ticket", "jira_ticket": "nope"})
check("malformed jira ticket is rejected", status == 400, f"{status} {str(body)[:200]}")

status, body = call("POST", f"{inv_url}/allocate/", {"quantity": 500, "reason": "Over-reserve"})
check("over-allocation is rejected", status == 400, f"{status} {str(body)[:200]}")

status, body = call("GET", inv_url + "/")
check("count survived every refusal", body.get("quantity_on_hand") == 9, str(body.get("quantity_on_hand")))

print("\n--- audit trail integrity ---")
status, body = call("PATCH", f"{inv_url}/", {"quantity_on_hand": 500})
after = call("GET", inv_url + "/")[1].get("quantity_on_hand")
check(
    "PATCH cannot move stock behind the audit trail",
    after == 9,
    f"PATCH returned {status}; quantity is now {after}",
)

txn_id = first_id(f"{PLUGIN}/spare-part-transactions/?spare_part_inventory={inventory_id}")
status, body = call("PATCH", f"{PLUGIN}/spare-part-transactions/{txn_id}/", {"reason": "rewritten"})
check("transactions cannot be edited", status in (403, 405), f"{status} {str(body)[:200]}")

status, body = call("DELETE", f"{PLUGIN}/spare-part-transactions/{txn_id}/")
check("transactions cannot be deleted", status in (403, 405), f"{status} {str(body)[:200]}")

print("\n--- idempotency ---")
request_id = str(uuid.uuid4())
status_a, body_a = call(
    "POST", f"{inv_url}/check-in/", {"quantity": 7, "reason": "Idempotency probe", "request_id": request_id}
)
status_b, body_b = call(
    "POST", f"{inv_url}/check-in/", {"quantity": 7, "reason": "Idempotency probe", "request_id": request_id}
)
check(
    "repeating a request_id does not apply the movement twice",
    status_a == 200 and status_b == 200 and body_b["inventory"]["quantity_on_hand"] == 16,
    f"first={body_a['inventory']['quantity_on_hand']} second={body_b['inventory']['quantity_on_hand']}",
)
check(
    "the repeat returns the original transaction",
    body_a["transaction"]["id"] == body_b["transaction"]["id"],
    f"{body_a['transaction']['id']} vs {body_b['transaction']['id']}",
)

print("\n--- transfer ---")
status, locations = call("GET", f"{API}/dcim/locations/?limit=5")
other = [row["id"] for row in locations["results"] if row["id"] != location_id]
if other:
    # Measure the destination before and after: on a repeat run the record is
    # already there, so what matters is that it gained exactly what was sent.
    status, body = call("GET", f"{PLUGIN}/spare-part-inventory/?spare_part_type={part_id}&location={other[0]}")
    before = body["results"][0]["quantity_on_hand"] if body.get("results") else 0

    status, body = call(
        "POST",
        f"{inv_url}/transfer/",
        {"quantity": 4, "destination_location": other[0], "reason": "Smoke test transfer"},
    )
    check("transfer out", status == 200 and body["inventory"]["quantity_on_hand"] == 12, f"{status} {str(body)[:200]}")

    status, body = call("GET", f"{PLUGIN}/spare-part-inventory/?spare_part_type={part_id}&location={other[0]}")
    after = body["results"][0]["quantity_on_hand"] if body.get("results") else None
    check(
        "the destination record gained the transferred stock",
        after == before + 4,
        f"before={before} after={after}",
    )

    status, body = call(
        "POST",
        f"{inv_url}/transfer/",
        {"quantity": 1, "destination_location": location_id, "reason": "Same place"},
    )
    check("transfer to the same location is rejected", status == 400, f"{status} {str(body)[:200]}")
else:
    print("SKIP  transfer (needs a second location)")

print("\n--- cleanup ---")
# Inventory records are protected by their transactions, which is intentional:
# deleting stock history is not something the API should make easy.
status, body = call("DELETE", f"{inv_url}/")
check("inventory with history is protected from deletion", status in (400, 409, 403), f"{status} {str(body)[:200]}")

print()
print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("\nFailed:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("\nSmoke test clean.")
