# Nautobot Spare Parts Inventory

Track spare parts stock across datacenter locations, with reservations,
transfers between sites, and an audit trail that always adds up.

Built for the way spares actually get used in a DC: a drive fails, someone
walks to the cage, takes a replacement, fits it, and the ticket needs to say
what was consumed.

## What it does

- **Catalogue** — part types with manufacturer, part number, category, unit
  cost and the device types they fit.
- **Stock per location** — how many are on hand, how many are promised to a
  job, how many are actually available, and when to reorder.
- **Six movements** — check in, check out, adjust, allocate, deallocate,
  transfer. Nothing else can change a stock level.
- **Reservations that close the loop** — allocate stock for planned work, then
  check it out against the reservation when the work happens.
- **Audit trail** — every movement records both counters before and after, who
  did it, why, which device and which Jira ticket. Records cannot be edited or
  deleted.
- **Per-ticket view** — `/plugins/spare-parts/jira/INFRA2-1234/` shows every
  part booked against a ticket, and whether anything is still reserved for it.
- **Device panel** — a device's page lists the spares fitted to it.
- **Low stock dashboard** — only for parts you asked to be tracked.
- **Full REST API** — every UI action has an API equivalent, with idempotency
  keys so retries are safe.

## Requirements

Nautobot 3.0.x, Python 3.10+. See [COMPATIBILITY.md](COMPATIBILITY.md).

## Install

```bash
pip install nautobot-spare-parts
```

Then in `nautobot_config.py`:

```python
PLUGINS = ["nautobot_spare_parts"]
```

and:

```bash
nautobot-server migrate
nautobot-server post_upgrade
```

Restart Nautobot and its Celery workers.

## Try it locally

```bash
./dev up      # Nautobot 3.0.11 in Docker, on http://localhost:8081
./dev seed    # demo parts, stock and history
```

See [development/README.md](development/README.md).

## The one rule

Stock levels move **only** through the six actions, because each one writes a
transaction. The edit form shows the quantity fields read-only, bulk edit does
not offer them, an API `PATCH` ignores them, and the model itself refuses a
save that changes a counter without a movement behind it.

If a count is wrong, that is what **Adjust** is for — it records the correction
and the reason, so the history explains itself later.

## Reservations

```
Allocate 2  ->  on hand 10, reserved 2, available 8
Check out 2 with "these units were reserved"
            ->  on hand 8,  reserved 0, available 8
```

Checking out reserved stock *without* saying so is refused, and the error says
what to do about it. Reserved stock also cannot be transferred away.

## API

```bash
TOKEN=...
BASE=https://nautobot.example.com/api/plugins/spare-parts

# what is low
curl -sH "Authorization: Token $TOKEN" \
  "$BASE/spare-part-inventory/?low_stock=true"

# take two drives for a ticket
curl -sX POST -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  "$BASE/spare-part-inventory/$ID/check-out/" \
  -d '{"quantity": 2,
       "reason": "Replaced failed OSD drives",
       "related_device": "'"$DEVICE_ID"'",
       "jira_ticket": "INFRA2-4821",
       "request_id": "'"$(uuidgen)"'"}'
```

Actions: `check-in`, `check-out`, `adjust`, `allocate`, `deallocate`,
`transfer`. Each returns the updated record and the transaction it wrote.
Sending the same `request_id` twice applies the movement once — safe to retry.

Full reference: [PLUGIN_DOCUMENTATION.md](PLUGIN_DOCUMENTATION.md).

## Permissions

Standard Nautobot object permissions on `spareparttype`, `sparepartinventory`
and `spareparttransaction`. `change_sparepartinventory` is what gates every
movement, in the UI and the API alike. Object-level constraints work too, so a
team can be limited to the locations they look after.

## License

Apache-2.0
