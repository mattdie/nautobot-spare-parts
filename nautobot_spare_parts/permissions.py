"""Object-level permission checks for records picked in a form or request body.

A view's own lookup honours Nautobot's object permissions, but a choice field
or an id in a request body accepts any record. Without these checks a user
whose permission is constrained to one location could check stock into, or
transfer stock to, another location's record by naming it.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from nautobot_spare_parts.models import SparePartInventory


def require_change(user, inventory):
    """Refuse to move stock on a record the user may not change."""
    if not SparePartInventory.objects.restrict(user, "change").filter(pk=inventory.pk).exists():
        raise ValidationError(f"You do not have permission to change stock of {inventory}.")


def transfer_as(user, inventory, **kwargs):
    """Transfer stock, refusing a destination record the user may not change.

    The destination record may not exist until the transfer creates it, so it
    is checked after the write, inside the same transaction -- the way Nautobot
    itself enforces constraints on a new object.
    """
    with transaction.atomic():
        out_txn, in_txn = inventory.transfer_to(user=user, **kwargs)
        require_change(user, in_txn.spare_part_inventory)
    return out_txn, in_txn
