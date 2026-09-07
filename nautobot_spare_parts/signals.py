"""Signal handlers for the Spare Parts Inventory app."""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from nautobot_spare_parts.choices import SparePartTransactionTypeChoices
from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=SparePartInventory)
def _stash_previous_low_stock_state(sender, instance, **kwargs):
    """Remember whether the record was already low on stock before this save.

    Stored on the instance rather than in a module-level dict: a dict entry
    leaks whenever a save fails between pre_save and post_save, and is shared
    by every request in the worker process.
    """
    if instance.present_in_database:
        previous = (
            SparePartInventory.objects.filter(pk=instance.pk)
            .values("quantity_on_hand", "quantity_reserved", "minimum_quantity")
            .first()
        )
        if previous is not None:
            available = previous["quantity_on_hand"] - previous["quantity_reserved"]
            instance._was_low_stock = previous["minimum_quantity"] > 0 and available <= previous["minimum_quantity"]
            return
    instance._was_low_stock = False


@receiver(post_save, sender=SparePartInventory)
def _log_low_stock_transition(sender, instance, created, **kwargs):
    """Log once, on the transition into low stock.

    Deliberately not on every save: an edit to the storage detail of an
    already-low record is not news. A webhook or Job hook on
    SparePartInventory is the supported way to turn this into an alert -- it
    does not need app code.
    """
    was_low_stock = getattr(instance, "_was_low_stock", False)
    if instance.is_low_stock and (created or not was_low_stock):
        logger.warning(
            "Low stock: %s at %s - available %s, minimum %s",
            instance.spare_part_type,
            instance.location,
            instance.quantity_available,
            instance.minimum_quantity,
        )


@receiver(post_save, sender=SparePartInventory)
def _record_opening_balance(sender, instance, created, **kwargs):
    """Write an audit record for stock entered on the creation form.

    Without this, opening stock is the one quantity in the system with no
    transaction behind it, and the log stops adding up to the counters.
    """
    if not created or instance.quantity_on_hand == 0:
        return
    SparePartTransaction.objects.create(
        spare_part_inventory=instance,
        transaction_type=SparePartTransactionTypeChoices.ADJUSTMENT,
        quantity=instance.quantity_on_hand,
        reserved_delta=instance.quantity_reserved,
        quantity_before=0,
        quantity_after=instance.quantity_on_hand,
        reserved_before=0,
        reserved_after=instance.quantity_reserved,
        reason="Opening balance recorded when the inventory record was created.",
    )
