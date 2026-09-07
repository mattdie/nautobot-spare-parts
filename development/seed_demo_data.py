"""Load demo data into the test environment.

Run with ``./dev seed``. Safe to run repeatedly: everything is get_or_create'd
and stock movements carry fixed idempotency keys, so a second run does not
double the numbers.

The data is shaped like a small EEN-style estate -- a few sites, a rack of
Supermicro nodes, and the spares you actually keep on a shelf -- so the low
stock dashboard, transfers and the Jira views all have something to show.
"""

import uuid

from django.contrib.auth import get_user_model

from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer, Platform
from nautobot.extras.models import Role, Status

from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType

SEED_NAMESPACE = uuid.UUID("5eed5eed-0000-4000-8000-000000000000")


def key(label):
    """Stable idempotency key so re-seeding does not re-apply movements."""
    return uuid.uuid5(SEED_NAMESPACE, label)


User = get_user_model()
admin = User.objects.filter(username="admin").first()

active = Status.objects.get(name="Active")

site_type, _ = LocationType.objects.get_or_create(name="Site")
site_type.content_types.add(*[])

sites = {}
for name in ("AUS1", "FRA1", "AMS1"):
    sites[name], _ = Location.objects.get_or_create(name=name, location_type=site_type, defaults={"status": active})

# Spares live in the same datacenter as the nodes -- there is no separate
# "spares site". The shelf/cage detail goes in storage_location_detail, which
# is what that field is for, and it keeps the device-side part picker able to
# scope stock to the device's own datacenter.
store_rooms = {"AUS1": sites["AUS1"], "FRA1": sites["FRA1"]}

supermicro, _ = Manufacturer.objects.get_or_create(name="Supermicro")
samsung, _ = Manufacturer.objects.get_or_create(name="Samsung")
intel, _ = Manufacturer.objects.get_or_create(name="Intel")
seagate, _ = Manufacturer.objects.get_or_create(name="Seagate")

device_type, _ = DeviceType.objects.get_or_create(
    model="SYS-6019U-TRT",
    manufacturer=supermicro,
    defaults={"u_height": 1},
)
device_role, _ = Role.objects.get_or_create(name="Ceph Node", defaults={"color": "9e9e9e"})
device_role.content_types.add(
    *[ct for ct in device_role.content_types.model.objects.filter(app_label="dcim", model="device")]
)

platform, _ = Platform.objects.get_or_create(name="Flatcar", defaults={"manufacturer": supermicro})

# One node in FRA1 as well as AUS1, so the device-side part picker's
# "same datacenter only" rule is visible in the demo data rather than theory.
nodes = {}
for node_name, site_name in (("ca099", "AUS1"), ("ca100", "AUS1"), ("s807", "AUS1"), ("fr412", "FRA1")):
    nodes[node_name], _ = Device.objects.get_or_create(
        name=node_name,
        defaults={
            "device_type": device_type,
            "role": device_role,
            "location": sites[site_name],
            "status": active,
            "platform": platform,
        },
    )

# --- catalogue ---------------------------------------------------------------

catalogue = [
    # (name, manufacturer, part_number, category, unit_cost, description)
    ("32GB DDR4-2666 ECC RDIMM", samsung, "M393A4K40CB2-CTD", "dimm", 95.00, "Registered ECC DIMM"),
    ("64GB DDR4-3200 ECC RDIMM", samsung, "M393A8G40AB2-CWE", "dimm", 210.00, "Registered ECC DIMM"),
    ("8TB SATA 7.2k 3.5in", seagate, "ST8000NM000A", "hdd", 175.00, "Ceph OSD data drive"),
    ("960GB SATA SSD", samsung, "MZ7L3960HCJR", "ssd", 130.00, "Boot / journal SSD"),
    ("X710-DA2 10G SFP+ NIC", intel, "X710DA2", "nic", 240.00, "Dual port 10G"),
    ("10G SFP+ SR transceiver", intel, "E10GSFPSR", "transceiver", 45.00, "850nm multimode"),
    ("1000W redundant PSU", supermicro, "PWS-1K02A-1R", "psu", 190.00, "Hot-swap PSU"),
    ("80mm chassis fan", supermicro, "FAN-0126L4", "fan", 22.00, "Hot-swap middle fan"),
    ("SFP+ DAC 2m", intel, "XDACBL2M", "cable_copper", 30.00, "Direct attach copper"),
    ("LC-LC OM4 fibre 3m", None, "", "cable_fiber", 12.00, "Duplex multimode patch"),
]

types = {}
for name, manufacturer, part_number, category, cost, description in catalogue:
    obj, created = SparePartType.objects.get_or_create(
        name=name,
        manufacturer=manufacturer,
        defaults={
            "part_number": part_number,
            "category": category,
            "unit_cost": cost,
            "description": description,
        },
    )
    types[name] = obj
    if created and category in ("dimm", "psu", "fan", "nic"):
        obj.compatible_device_types.add(device_type)

# --- stock -------------------------------------------------------------------

# (part, location, on_hand, minimum, reorder, storage detail)
stock = [
    ("32GB DDR4-2666 ECC RDIMM", "AUS1", 24, 8, 16, "Spares cage A, shelf 2, bin 4"),
    ("64GB DDR4-3200 ECC RDIMM", "AUS1", 6, 6, 12, "Spares cage A, shelf 2, bin 5"),
    ("8TB SATA 7.2k 3.5in", "AUS1", 14, 10, 20, "Spares cage A, shelf 4"),
    ("960GB SATA SSD", "AUS1", 9, 4, 10, "Spares cage A, shelf 3"),
    ("X710-DA2 10G SFP+ NIC", "AUS1", 3, 2, 4, "Spares cage B, shelf 1"),
    ("10G SFP+ SR transceiver", "AUS1", 40, 20, 40, "Spares cage B, drawer 2"),
    ("1000W redundant PSU", "AUS1", 5, 4, 6, "Spares cage B, shelf 2"),
    ("80mm chassis fan", "AUS1", 2, 6, 12, "Spares cage B, drawer 3"),
    ("SFP+ DAC 2m", "AUS1", 18, 0, 0, "Spares cage B, drawer 4"),
    ("LC-LC OM4 fibre 3m", "AUS1", 30, 10, 25, "Spares cage B, drawer 5"),
    ("32GB DDR4-2666 ECC RDIMM", "FRA1", 8, 8, 16, "Spares rack 12, shelf 1"),
    ("8TB SATA 7.2k 3.5in", "FRA1", 4, 6, 12, "Spares rack 12, shelf 2"),
    ("1000W redundant PSU", "FRA1", 1, 2, 4, "Spares rack 12, shelf 3"),
]

records = {}
for part_name, room_name, on_hand, minimum, reorder, detail in stock:
    record, created = SparePartInventory.objects.get_or_create(
        spare_part_type=types[part_name],
        location=store_rooms[room_name],
        defaults={
            "quantity_on_hand": on_hand,
            "minimum_quantity": minimum,
            "reorder_quantity": reorder,
            "storage_location_detail": detail,
        },
    )
    records[(part_name, room_name)] = record

# --- some history ------------------------------------------------------------

history = [
    # (part, location, action, kwargs)
    (
        ("8TB SATA 7.2k 3.5in", "AUS1"),
        "check_out",
        {
            "quantity": 2,
            "reason": "Replaced two failed OSD drives",
            "related_device": nodes["ca099"],
            "jira_ticket": "INFRA2-4821",
        },
    ),
    (
        ("32GB DDR4-2666 ECC RDIMM", "AUS1"),
        "check_out",
        {
            "quantity": 1,
            "reason": "ECC errors on DIMM B2",
            "related_device": nodes["s807"],
            "jira_ticket": "INFRA2-4903",
        },
    ),
    (
        ("1000W redundant PSU", "AUS1"),
        "allocate",
        {
            "quantity": 2,
            "reason": "Reserved for planned PSU swap in rack ND14",
            "jira_ticket": "INFRA2-5010",
        },
    ),
    (
        ("960GB SATA SSD", "AUS1"),
        "check_in",
        {"quantity": 4, "reason": "Shipment 88213 from Arrow", "jira_ticket": "INFRA2-4700"},
    ),
    (
        ("80mm chassis fan", "AUS1"),
        "adjust",
        {"quantity": -1, "reason": "Stock take: one fan found broken in its box"},
    ),
]

for record_key, method, kwargs in history:
    record = records[record_key]
    getattr(record, method)(
        user=admin,
        request_id=key(f"{record_key}-{method}-{kwargs['quantity']}"),
        **kwargs,
    )

# A transfer, so both legs of one exist in the log.
records[("10G SFP+ SR transceiver", "AUS1")].transfer_to(
    destination_location=store_rooms["FRA1"],
    quantity=10,
    reason="Rebalancing optics towards EMEA",
    user=admin,
    request_id=key("transfer-optics-aus1-fra1"),
)

print("Seeded:")
print(f"  part types      {SparePartType.objects.count()}")
print(f"  stock records   {SparePartInventory.objects.count()}")
print(f"  low stock       {sum(1 for r in SparePartInventory.objects.all() if r.is_low_stock)}")
print(f"  movements       {SparePartTransaction.objects.count()}")
print()
print("Look at:")
print("  /plugins/spare-parts/")
print("  /plugins/spare-parts/low-stock/")
print("  /plugins/spare-parts/jira/INFRA2-4821/")
