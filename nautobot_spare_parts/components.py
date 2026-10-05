"""Keeping a device's Nautobot InventoryItems in step with what was checked out.

A check-out against a device for a part category that physically lives inside
it (a DIMM, a drive, a PSU...) is also a statement about that device's own
hardware record. :func:`sync_device_component` is the one place that turns a
check-out into the matching InventoryItem change -- replace, in one step, so
the device page is never caught showing both the dead part and its
replacement, or neither.
"""

from nautobot.dcim.models import InventoryItem


def sync_device_component(*, device, spare_part_type, slot, serial):
    """Replace the InventoryItem named ``slot`` on ``device`` with this part.

    Any existing item with that name is deleted first -- this is a swap, not
    an append, so a slot never ends up with more than one occupant. Nothing
    about *why* (the ticket, the failure reason) is written here; that lives
    on the :class:`SparePartTransaction` already, and duplicating it onto the
    InventoryItem would just be a second place for it to drift out of sync.
    """
    InventoryItem.objects.filter(device=device, name=slot).delete()

    return InventoryItem.objects.create(
        device=device,
        name=slot,
        label=spare_part_type.get_category_display(),
        manufacturer=spare_part_type.manufacturer,
        part_id=spare_part_type.part_number,
        serial=serial,
        description=spare_part_type.description or spare_part_type.name,
    )
