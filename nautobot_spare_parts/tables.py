"""Tables for Spare Parts Inventory plugin."""

import django_tables2 as tables

from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn, TagColumn

from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType


class SparePartTypeTable(BaseTable):
    """Table for displaying SparePartType objects."""

    name = tables.Column(linkify=True)
    manufacturer = tables.Column(linkify=True)
    category = tables.Column()
    part_number = tables.Column()
    unit_cost = tables.Column()
    total_quantity = tables.Column(
        accessor="get_total_quantity",
        verbose_name="Total Qty",
        orderable=False,
    )
    tags = TagColumn(url_name="plugins:nautobot_spare_parts:spareparttype_list")
    actions = ButtonsColumn(SparePartType)

    class Meta(BaseTable.Meta):
        """Meta class for SparePartTypeTable."""

        model = SparePartType
        fields = (
            "name",
            "manufacturer",
            "category",
            "part_number",
            "unit_cost",
            "total_quantity",
            "tags",
            "actions",
        )
        default_columns = (
            "name",
            "manufacturer",
            "category",
            "part_number",
            "total_quantity",
            "actions",
        )


class SparePartInventoryTable(BaseTable):
    """Table for displaying SparePartInventory objects."""

    spare_part_type = tables.Column(
        linkify=lambda record: record.get_absolute_url()
    )
    location = tables.Column(linkify=True)
    quantity_on_hand = tables.Column(verbose_name="On Hand")
    quantity_reserved = tables.Column(verbose_name="Reserved")
    quantity_available = tables.Column(
        accessor="quantity_available",
        verbose_name="Available",
        orderable=False,
    )
    minimum_quantity = tables.Column(verbose_name="Min Qty")
    is_low_stock = BooleanColumn(
        accessor="is_low_stock",
        verbose_name="Low Stock",
        orderable=False,
    )
    storage_location_detail = tables.Column(verbose_name="Storage Detail")
    tags = TagColumn(url_name="plugins:nautobot_spare_parts:sparepartinventory_list")
    actions = ButtonsColumn(SparePartInventory)

    class Meta(BaseTable.Meta):
        """Meta class for SparePartInventoryTable."""

        model = SparePartInventory
        fields = (
            "spare_part_type",
            "location",
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
            "minimum_quantity",
            "is_low_stock",
            "storage_location_detail",
            "tags",
            "actions",
        )
        default_columns = (
            "spare_part_type",
            "location",
            "quantity_on_hand",
            "quantity_available",
            "minimum_quantity",
            "is_low_stock",
            "actions",
        )


class SparePartTransactionTable(BaseTable):
    """Table for displaying SparePartTransaction objects."""

    spare_part_inventory = tables.Column(
        linkify=True,
        verbose_name="Inventory",
    )
    transaction_type = tables.Column()
    quantity = tables.Column()
    quantity_before = tables.Column(verbose_name="Qty Before")
    quantity_after = tables.Column(verbose_name="Qty After")
    user = tables.Column(linkify=False)
    timestamp = tables.DateTimeColumn()
    reason = tables.Column(orderable=False)
    related_device = tables.Column(linkify=True)

    class Meta(BaseTable.Meta):
        """Meta class for SparePartTransactionTable."""

        model = SparePartTransaction
        fields = (
            "spare_part_inventory",
            "transaction_type",
            "quantity",
            "quantity_before",
            "quantity_after",
            "user",
            "timestamp",
            "reason",
            "related_device",
        )
        default_columns = (
            "spare_part_inventory",
            "transaction_type",
            "quantity",
            "quantity_after",
            "user",
            "timestamp",
            "reason",
        )


class LowStockTable(BaseTable):
    """Table for displaying low stock items."""

    spare_part_type = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    quantity_available = tables.Column(
        accessor="quantity_available",
        verbose_name="Available",
        orderable=False,
    )
    minimum_quantity = tables.Column(verbose_name="Min Qty")
    reorder_quantity = tables.Column(verbose_name="Reorder Qty")
    needs_reorder = BooleanColumn(
        accessor="needs_reorder",
        verbose_name="Needs Reorder",
        orderable=False,
    )
    actions = ButtonsColumn(SparePartInventory)

    class Meta(BaseTable.Meta):
        """Meta class for LowStockTable."""

        model = SparePartInventory
        fields = (
            "spare_part_type",
            "location",
            "quantity_available",
            "minimum_quantity",
            "reorder_quantity",
            "needs_reorder",
            "actions",
        )
        default_columns = (
            "spare_part_type",
            "location",
            "quantity_available",
            "minimum_quantity",
            "reorder_quantity",
            "needs_reorder",
            "actions",
        )
