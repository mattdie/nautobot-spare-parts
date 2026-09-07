# Spare Parts Inventory — reference

Complete reference for the data model, the movements, the UI and the REST API.
For a quick tour see [README.md](README.md); for the test environment see
[development/README.md](development/README.md).

---

## 1. Data model

Three models. The first two are Nautobot `PrimaryModel`s (change-logged,
taggable, custom fields, GraphQL, webhooks); the third is an append-only event
log.

### SparePartType — the catalogue

One row per *kind* of part. Not stock.

| Field | Notes |
|---|---|
| `name` | Required. e.g. "32GB DDR4-2666 ECC RDIMM" |
| `manufacturer` | Optional FK to `dcim.Manufacturer`. Required if a part number is set. |
| `part_number` | Optional. Unique per manufacturer when set; any number of part types may have none. |
| `description` | Free text |
| `category` | One of the categories in `choices.py` (dimm, hdd, ssd, nvme, nic, psu, fan, transceiver, cables, cpu, gpu, raid_card, riser, motherboard, other) |
| `unit_cost` | Optional decimal, must be >= 0. Drives the estimated-value figure on the overview. |
| `compatible_device_types` | M2M to `dcim.DeviceType`. When set, check-out warns if the part is being fitted to a device type not on the list. |

### SparePartInventory — stock at a location

One row per (part type, location). Enforced unique.

| Field | Notes |
|---|---|
| `spare_part_type`, `location` | The identity of the record. Read-only after creation — its history is about this pair. |
| `quantity_on_hand` | Units physically present. Only movements change it. |
| `quantity_reserved` | Units on hand already promised to a job. Only allocate/deallocate change it. Database constraint: never greater than on hand. |
| `minimum_quantity` | Reorder threshold. **0 means the part is not stock-managed and never raises a low-stock alert.** |
| `reorder_quantity` | Suggested purchase quantity |
| `storage_location_detail` | Free text: "Cage B, shelf 2, bin 4" |
| `notes` | Free text |

Derived, not stored:

| Property | Meaning |
|---|---|
| `quantity_available` | `on_hand - reserved` — what you can actually take |
| `is_out_of_stock` | `available <= 0` |
| `is_low_stock` | `minimum_quantity > 0 and available <= minimum_quantity` |
| `needs_reorder` | `is_low_stock and reorder_quantity > 0` |

`SparePartInventory.annotate_available(queryset)` adds `available` as a
database expression, so lists can sort and filter on it.

### SparePartTransaction — the audit trail

One row per movement. Append-only: `save()` refuses to update an existing row
and `delete()` refuses outright.

| Field | Notes |
|---|---|
| `spare_part_inventory` | Which record moved |
| `transaction_type` | check_in / check_out / adjustment / allocation / deallocation / transfer |
| `quantity` | Signed change to on hand (0 for pure reservations) |
| `reserved_delta` | Signed change to reserved (0 for pure stock moves) |
| `quantity_before` / `quantity_after` | On hand around the movement |
| `reserved_before` / `reserved_after` | Reserved around the movement |
| `user` | Who did it (null for automation) |
| `timestamp` | Set on creation |
| `reason` | Required, and required to be non-blank |
| `related_device` | Optional FK to `dcim.Device` |
| `jira_ticket` | Optional, validated against `^[A-Z][A-Z0-9]*-\d+$` |
| `transfer_group` | Shared by both legs of a transfer; `other_transfer_leg` resolves the other side |
| `request_id` | Idempotency key, unique |
| `notes` | Free text. The only field that can be corrected afterwards, via `set_notes()`. |

Because both counters are recorded before and after, history can be replayed
without knowing the type, and every row can be checked in isolation:
`quantity_before + quantity == quantity_after`, same for reserved.

---

## 2. The movements

All six go through `SparePartInventory.record_movement()`, which takes a row
lock, validates, writes the counters and the transaction in one database
transaction, and returns the transaction.

| Method | Changes | Refuses when |
|---|---|---|
| `check_in(quantity, reason)` | on hand `+n` | quantity <= 0 |
| `check_out(quantity, reason, fulfil_reservation=False)` | on hand `-n`, and reserved `-n` when fulfilling | more than available; or more than reserved when fulfilling |
| `adjust(quantity, reason)` | on hand `±n` | quantity == 0; result negative; result below reserved |
| `allocate(quantity, reason)` | reserved `+n` | more than available |
| `deallocate(quantity, reason)` | reserved `-n` | more than reserved |
| `transfer_to(destination_location, quantity, reason)` | on hand `-n` here, `+n` there | same location; more than available |

Every method also accepts `user`, `notes`, `request_id`; check in/out and
allocate also accept `jira_ticket`, and check out accepts `related_device`.

On refusal a `ValidationError` is raised and **nothing changes** — no counter
moves, no transaction is written, and for a transfer no destination record is
created.

### Reservations

```
start              on hand 10   reserved 0   available 10
allocate(2)        on hand 10   reserved 2   available 8
check_out(2, fulfil_reservation=True)
                   on hand  8   reserved 0   available 8
```

`check_out(2)` without `fulfil_reservation` takes from unreserved stock, and is
refused if there is not enough. Reserved stock cannot be transferred.

### Transfers

Two transactions, one per side, sharing a `transfer_group` id, both inside one
database transaction. Either side resolves the other with
`transaction.other_transfer_leg`. The destination record is created if it does
not exist (with `minimum_quantity=0`, so it does not immediately alert).

### Idempotency

Pass a `request_id` (UUID) and the movement becomes safe to repeat: if a
transaction with that id already exists, it is returned and nothing is applied.

- UI forms carry a hidden `request_id` generated per GET, so a double-clicked
  button, a browser resubmit, or a refresh cannot double-book. The submit
  button also disables itself.
- API clients should send one per logical operation. Generate it before the
  first attempt, and reuse it on retries.

---

## 3. UI

| Page | Path |
|---|---|
| Overview | `/plugins/spare-parts/` |
| Stock | `/plugins/spare-parts/spare-part-inventory/` |
| Part types | `/plugins/spare-parts/spare-part-types/` |
| Transaction log | `/plugins/spare-parts/spare-part-transactions/` |
| Low stock | `/plugins/spare-parts/low-stock/` |
| Bulk receive | `/plugins/spare-parts/spare-part-inventory/bulk-receive/` |
| CSV export | `/plugins/spare-parts/export/inventory.csv` (honours list filters) |
| Parts for a ticket | `/plugins/spare-parts/jira/INFRA2-1234/` |

Every stock record's page carries all six action buttons. A device's page shows
the spares fitted to it.

### Filters

Stock: `q`, `spare_part_type`, `location`, `manufacturer`, `category`,
`low_stock`, `out_of_stock`, `has_reservations`, plus the quantity fields.

Part types: `q`, `manufacturer`, `category`, `part_number`, `unit_cost`,
`has_stock`.

Transactions: `q`, `spare_part_inventory`, `spare_part_type`, `location`,
`transaction_type`, `user`, `related_device`, `jira_ticket`, `timestamp` (range).

`q` searches part name, part number, manufacturer, location, storage detail,
and — for transactions — reason, notes and ticket.

---

## 4. REST API

Base: `/api/plugins/spare-parts/`

| Endpoint | Methods |
|---|---|
| `spare-part-types/` | GET, POST, PATCH, PUT, DELETE |
| `spare-part-inventory/` | GET, POST, PATCH, PUT, DELETE |
| `spare-part-transactions/` | GET only |

All the list filters above work as query parameters, and `?depth=1` expands
related objects.

### Creating

```bash
curl -sX POST "$BASE/spare-part-types/" \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "8TB SATA 7.2k 3.5in",
       "manufacturer": "'"$SEAGATE_ID"'",
       "part_number": "ST8000NM000A",
       "category": "hdd",
       "unit_cost": "175.00"}'

curl -sX POST "$BASE/spare-part-inventory/" \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"spare_part_type": "'"$PART_ID"'",
       "location": "'"$LOCATION_ID"'",
       "quantity_on_hand": 14,
       "minimum_quantity": 10,
       "reorder_quantity": 20,
       "storage_location_detail": "Cage A, shelf 4"}'
```

Opening stock given at creation is recorded as an `adjustment` transaction, so
even the first number has an audit record.

### Movements

`POST /spare-part-inventory/<id>/<action>/` where `<action>` is one of
`check-in`, `check-out`, `adjust`, `allocate`, `deallocate`, `transfer`.

Body, common to all:

| Field | Required | Notes |
|---|---|---|
| `quantity` | yes | Positive integer, except `adjust` where it is signed and non-zero |
| `reason` | yes | Non-blank |
| `notes` | no | |
| `request_id` | no | UUID idempotency key — recommended |

Extra fields:

| Action | Extra |
|---|---|
| `check-in` | `jira_ticket` |
| `check-out` | `related_device` (UUID), `fulfil_reservation` (bool), `jira_ticket` |
| `allocate` | `jira_ticket` |
| `transfer` | `destination_location` (UUID, required) |

Response, 200:

```json
{
  "status": "success",
  "message": "Checked out 2 unit(s); 10 still available.",
  "transaction": { "...": "the record that was written" },
  "inventory":   { "...": "the record after the movement" }
}
```

Errors:

| Status | Meaning |
|---|---|
| 400 | Refused. `{"status": "error", "message": "..."}` for a rejected movement, or DRF field errors for a malformed body. Nothing changed. |
| 403 | Caller lacks `change_sparepartinventory` |
| 404 | No such record, or an action path with underscores instead of dashes |

### What the API will not let you do

- Move stock by `PATCH`ing `quantity_on_hand` or `quantity_reserved`. Those
  fields are read-only on an existing record; the request succeeds and the
  quantities are unchanged. Use the actions.
- Change a record's part type or location after creation.
- Edit or delete a transaction.
- Delete a stock record that has history (protected FK).

### Scripting example

```python
"""Book the parts used on a ticket."""
import os
import uuid

import requests

BASE = "https://nautobot.example.com/api/plugins/spare-parts"
SESSION = requests.Session()
SESSION.headers["Authorization"] = f"Token {os.environ['NAUTOBOT_TOKEN']}"


def check_out(inventory_id, quantity, reason, device_id=None, ticket=""):
    response = SESSION.post(
        f"{BASE}/spare-part-inventory/{inventory_id}/check-out/",
        json={
            "quantity": quantity,
            "reason": reason,
            "related_device": device_id,
            "jira_ticket": ticket,
            "request_id": str(uuid.uuid4()),
        },
        timeout=30,
    )
    if response.status_code == 400:
        raise SystemExit(f"Refused: {response.json().get('message')}")
    response.raise_for_status()
    return response.json()


for record in SESSION.get(f"{BASE}/spare-part-inventory/?low_stock=true", timeout=30).json()["results"]:
    print(record["display"], record["quantity_available"], "of", record["minimum_quantity"])
```

---

## 5. Permissions

Nautobot object permissions on the three models. The important one:

| Permission | Grants |
|---|---|
| `nautobot_spare_parts.view_sparepartinventory` | Read stock, overview, low stock dashboard, CSV export |
| `nautobot_spare_parts.change_sparepartinventory` | **All six movements**, UI and API |
| `nautobot_spare_parts.add_sparepartinventory` | Create stock records |
| `nautobot_spare_parts.view_spareparttransaction` | Read the audit trail and the per-ticket view |
| `..._spareparttype` | The catalogue |

Object-level constraints are honoured: a permission constrained to
`{"location": {"name": "AUS1 Spares Cage"}}` limits that user to that cage,
including the movement pages.

Transactions have no add/change/delete path at all — they are only ever written
by a movement.

---

## 6. Alerting

Crossing into low stock logs a warning to the `nautobot_spare_parts` logger:

```
WARNING nautobot_spare_parts.signals Low stock: Supermicro 1000W redundant PSU
        at AUS1 Spares Cage - available 3, minimum 4
```

It fires on the *transition* into low stock, not on every save, so an edit to
an already-low record is not repeated noise.

For anything beyond a log line, use Nautobot's own machinery rather than app
code:

- **Webhook** on `SparePartInventory` update — payload includes the quantities.
- **Job Hook** on `SparePartInventory` update — a Job can check `is_low_stock`
  and open a Jira ticket.
- **Scheduled Job** querying `?low_stock=true` for a daily digest, which is
  usually the version people actually want.

Metrics are deliberately not exposed here. Nautobot app metrics belong in
`nautobot-capacity-metrics`, which can expose any queryset count without this
app carrying a Prometheus dependency.

---

## 7. Migrations

| Migration | What |
|---|---|
| `0001_initial` | Original three models |
| `0002_spareparttransaction_jira_ticket` | Jira reference |
| `0003_add_field_validators` | Cost and ticket validators |
| `0004_audit_trail_and_constraints` | Splits reserved from stock counters, adds `request_id` and `transfer_group`, adds the reserved <= on hand check constraint and the conditional part-number uniqueness, drops `slug` |
| `0005_backfill_reserved_columns` | Moves historical allocation/deallocation numbers into the new reserved columns |

Upgrading from 1.x:

1. Back up the database.
2. `nautobot-server migrate`.
3. `SparePartType.slug` is dropped. Nothing references it (URLs use the UUID),
   but if you built export templates or scripts around it, change them first.
4. Historical allocation rows get their on-hand figures set to the record's
   current on-hand with a zero delta — those numbers were never recorded, and
   this keeps every row internally consistent rather than inventing a movement.
5. If migration `0004` fails on the check constraint, some record already has
   more reserved than on hand. Find them and fix them first:

   ```python
   SparePartInventory.objects.filter(quantity_reserved__gt=F("quantity_on_hand"))
   ```
