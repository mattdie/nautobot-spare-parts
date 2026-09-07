"""Extensions to core Nautobot tables.

Adds a "Spares Used" column to the Device table. It is opt-in per user (not in
the default column set), but it means a device list can be sorted by how many
spare parts a box has eaten, which is the question behind "should we RMA the
whole node".
"""

import django_tables2 as tables
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html

from nautobot.apps.tables import TableExtension

from nautobot_spare_parts.choices import SparePartTransactionTypeChoices


class SparesUsedColumn(tables.Column):
    """Count of spare part units consumed by this device, linked to the log."""

    def render(self, record, value):
        """Link the count to the filtered movement log."""
        if not value:
            return "—"
        url = reverse("plugins:nautobot_spare_parts:spareparttransaction_list") + f"?related_device={record.pk}"
        return format_html('<a href="{}">{}</a>', url, value)


class DeviceTableExtension(TableExtension):
    """Add spare part usage to the Device table."""

    model = "dcim.device"

    # Nautobot requires app-provided column keys to be prefixed with the app
    # name, so they can never collide with a core column.
    table_columns = {
        "nautobot_spare_parts_spares_used": SparesUsedColumn(
            accessor="spares_used",
            verbose_name="Spares Used",
            orderable=True,
            default="—",
        ),
    }

    @classmethod
    def alter_queryset(cls, queryset):
        """Annotate the units consumed, so the column can be sorted in the database."""
        return queryset.annotate(
            spares_used=Count(
                "spare_part_transactions",
                filter=Q(spare_part_transactions__transaction_type=SparePartTransactionTypeChoices.CHECK_OUT),
                distinct=True,
            )
        )


table_extensions = [DeviceTableExtension]
