"""Tables for the Spare Parts Inventory app."""

import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html

from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn, TagColumn, ToggleColumn

from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType


class SparePartTypeTable(BaseTable):
    """Spare part types."""

    pk = ToggleColumn()
    name = tables.Column(linkify=True)
    manufacturer = tables.Column(linkify=True)
    category = tables.Column()
    part_number = tables.Column()
    unit_cost = tables.Column()
    total_quantity = tables.Column(verbose_name="Total On Hand", orderable=True)
    location_count = tables.Column(verbose_name="Locations", orderable=True)
    tags = TagColumn(url_name="plugins:nautobot_spare_parts:spareparttype_list")
    actions = ButtonsColumn(SparePartType)

    class Meta(BaseTable.Meta):
        """Meta class for SparePartTypeTable."""

        model = SparePartType
        fields = (
            "pk",
            "name",
            "manufacturer",
            "category",
            "part_number",
            "unit_cost",
            "total_quantity",
            "location_count",
            "tags",
            "actions",
        )
        default_columns = (
            "pk",
            "name",
            "manufacturer",
            "category",
            "part_number",
            "total_quantity",
            "location_count",
            "actions",
        )


class SparePartInventoryTable(BaseTable):
    """Inventory records."""

    pk = ToggleColumn()
    location = tables.Column(linkify=True)
    spare_part_type = tables.Column(linkify=True, verbose_name="Part Type")
    storage_location_detail = tables.Column(verbose_name="Storage Detail")
    quantity_on_hand = tables.Column(verbose_name="On Hand")
    quantity_reserved = tables.Column(verbose_name="Reserved")
    # The Low Stock column already says whether this number is a problem, so it
    # does not need colouring too.
    available = tables.Column(verbose_name="Available", orderable=True)
    minimum_quantity = tables.Column(verbose_name="Min")
    reorder_quantity = tables.Column(verbose_name="Reorder")
    is_low_stock = BooleanColumn(accessor="is_low_stock", verbose_name="Low Stock", orderable=False)
    tags = TagColumn(url_name="plugins:nautobot_spare_parts:sparepartinventory_list")
    actions = ButtonsColumn(SparePartInventory)

    class Meta(BaseTable.Meta):
        """Meta class for SparePartInventoryTable."""

        model = SparePartInventory
        fields = (
            "pk",
            "spare_part_type",
            "location",
            "storage_location_detail",
            "quantity_on_hand",
            "quantity_reserved",
            "available",
            "minimum_quantity",
            "reorder_quantity",
            "is_low_stock",
            "tags",
            "actions",
        )
        default_columns = (
            "pk",
            "spare_part_type",
            "location",
            "quantity_on_hand",
            "quantity_reserved",
            "available",
            "minimum_quantity",
            "is_low_stock",
            "actions",
        )


class SparePartTypeInventoryTable(BaseTable):
    """Where one part type is stocked -- embedded on the part type page."""

    location = tables.Column(linkify=True)
    storage_location_detail = tables.Column(verbose_name="Storage Detail")
    quantity_on_hand = tables.Column(verbose_name="On Hand")
    quantity_reserved = tables.Column(verbose_name="Reserved")
    available = tables.Column(verbose_name="Available")
    minimum_quantity = tables.Column(verbose_name="Min")
    actions = ButtonsColumn(SparePartInventory, buttons=("edit",))

    class Meta(BaseTable.Meta):
        """Meta class for SparePartTypeInventoryTable."""

        model = SparePartInventory
        fields = (
            "location",
            "storage_location_detail",
            "quantity_on_hand",
            "quantity_reserved",
            "available",
            "minimum_quantity",
            "actions",
        )


class SparePartTransactionTable(BaseTable):
    """The audit trail."""

    timestamp = tables.DateTimeColumn(linkify=True, format="Y-m-d H:i", verbose_name="When")
    spare_part_inventory = tables.Column(linkify=True, verbose_name="Part / Location")
    transaction_type = tables.Column(verbose_name="Type")
    quantity = tables.Column(verbose_name="Stock Δ")
    reserved_delta = tables.Column(verbose_name="Reserved Δ")
    quantity_before = tables.Column(verbose_name="On Hand Before")
    quantity_after = tables.Column(verbose_name="On Hand After")
    user = tables.Column(verbose_name="By")
    reason = tables.Column(orderable=False)
    related_device = tables.Column(linkify=True, verbose_name="Device")
    jira_ticket = tables.Column(verbose_name="Jira")

    class Meta(BaseTable.Meta):
        """Meta class for SparePartTransactionTable."""

        model = SparePartTransaction
        fields = (
            "timestamp",
            "spare_part_inventory",
            "transaction_type",
            "quantity",
            "reserved_delta",
            "quantity_before",
            "quantity_after",
            "user",
            "reason",
            "related_device",
            "jira_ticket",
        )
        default_columns = (
            "timestamp",
            "spare_part_inventory",
            "transaction_type",
            "quantity",
            "reserved_delta",
            "quantity_after",
            "user",
            "reason",
            "jira_ticket",
        )

    def render_jira_ticket(self, value):
        """Link a ticket reference to its per-ticket parts view."""
        if not value:
            return "—"
        url = reverse("plugins:nautobot_spare_parts:jira_ticket_parts", args=[value])
        return format_html('<a href="{}">{}</a>', url, value)


class LowStockTable(BaseTable):
    """Low-stock dashboard."""

    spare_part_type = tables.Column(linkify=True, verbose_name="Part Type")
    location = tables.Column(linkify=True)
    storage_location_detail = tables.Column(verbose_name="Storage Detail")
    available = tables.Column(verbose_name="Available")
    minimum_quantity = tables.Column(verbose_name="Min")
    shortfall = tables.Column(accessor="pk", verbose_name="Short By", orderable=False)
    reorder_quantity = tables.Column(verbose_name="Reorder Qty")
    needs_reorder = BooleanColumn(accessor="needs_reorder", verbose_name="Reorder Set", orderable=False)
    actions = ButtonsColumn(SparePartInventory, buttons=("edit",))

    class Meta(BaseTable.Meta):
        """Meta class for LowStockTable."""

        model = SparePartInventory
        fields = (
            "spare_part_type",
            "location",
            "storage_location_detail",
            "available",
            "minimum_quantity",
            "shortfall",
            "reorder_quantity",
            "needs_reorder",
            "actions",
        )
        default_columns = (
            "spare_part_type",
            "location",
            "available",
            "minimum_quantity",
            "shortfall",
            "reorder_quantity",
            "needs_reorder",
            "actions",
        )

    def render_shortfall(self, record):
        """How many units short of the minimum this record is."""
        return max(record.minimum_quantity - record.quantity_available, 0)
