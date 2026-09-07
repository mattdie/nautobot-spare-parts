"""Shared test fixtures.

Run the suite with ``./dev test`` (or ``nautobot-server test nautobot_spare_parts``
inside a Nautobot install).
"""

from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import Role, Status

from nautobot_spare_parts.models import SparePartInventory, SparePartType


def build_dcim():
    """Create the minimum DCIM objects the app hangs off."""
    active = Status.objects.get_for_model(Location).first()
    site_type, _ = LocationType.objects.get_or_create(name="Test Site")
    site_type.content_types.add(*[])

    location_a, _ = Location.objects.get_or_create(
        name="Test Site A", location_type=site_type, defaults={"status": active}
    )
    location_b, _ = Location.objects.get_or_create(
        name="Test Site B", location_type=site_type, defaults={"status": active}
    )

    manufacturer, _ = Manufacturer.objects.get_or_create(name="Test Manufacturer")
    device_type, _ = DeviceType.objects.get_or_create(
        model="Test Model", manufacturer=manufacturer, defaults={"u_height": 1}
    )
    other_device_type, _ = DeviceType.objects.get_or_create(
        model="Other Model", manufacturer=manufacturer, defaults={"u_height": 1}
    )

    device_status = Status.objects.get_for_model(Device).first()
    role, _ = Role.objects.get_or_create(name="Test Role", defaults={"color": "111111"})
    from django.contrib.contenttypes.models import ContentType

    role.content_types.add(ContentType.objects.get_for_model(Device))

    device, _ = Device.objects.get_or_create(
        name="test-device-1",
        defaults={
            "device_type": device_type,
            "role": role,
            "location": location_a,
            "status": device_status,
        },
    )
    other_device, _ = Device.objects.get_or_create(
        name="test-device-2",
        defaults={
            "device_type": other_device_type,
            "role": role,
            "location": location_a,
            "status": device_status,
        },
    )

    return {
        "location_a": location_a,
        "location_b": location_b,
        "manufacturer": manufacturer,
        "device_type": device_type,
        "other_device_type": other_device_type,
        "device": device,
        "other_device": other_device,
    }


def make_part_type(name="Test RAM", **kwargs):
    """Create a spare part type."""
    kwargs.setdefault("category", "ram")
    return SparePartType.objects.create(name=name, **kwargs)


def make_inventory(part_type, location, on_hand=10, reserved=0, minimum=0, reorder=0):
    """Create an inventory record with an exact opening state.

    Bypasses the opening-balance signal's transaction so tests start from a
    clean, empty history: created with 0 and then moved into place.
    """
    record = SparePartInventory.objects.create(
        spare_part_type=part_type,
        location=location,
        quantity_on_hand=0,
        quantity_reserved=0,
        minimum_quantity=minimum,
        reorder_quantity=reorder,
    )
    if on_hand:
        record.check_in(quantity=on_hand, reason="test setup")
    if reserved:
        record.allocate(quantity=reserved, reason="test setup")
    record.transactions.all().delete()
    record.refresh_from_db()
    return record
