"""Signal handlers for Spare Parts Inventory plugin."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from nautobot_spare_parts.models import SparePartInventory

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SparePartInventory)
def check_low_stock(sender, instance, created, **kwargs):
    """Check if inventory is low and log warning."""
    if instance.is_low_stock:
        logger.warning(
            f"Low stock alert: {instance.spare_part_type} at {instance.location} "
            f"- Available: {instance.quantity_available}, Minimum: {instance.minimum_quantity}"
        )

        # Future enhancement: Create webhook event or send notification
        # For now, just log the warning
        # You could add custom logic here to:
        # - Create a Job to send email notifications
        # - Trigger a webhook to external systems
        # - Create a custom event log entry
        # - Update a dashboard metric
