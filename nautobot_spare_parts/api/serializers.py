"""API serializers for Spare Parts Inventory plugin."""

from rest_framework import serializers

from nautobot.apps.api import NautobotModelSerializer
from nautobot.dcim.api.serializers import (
    DeviceSerializer,
    DeviceTypeSerializer,
    LocationSerializer,
    ManufacturerSerializer,
)
from nautobot.users.api.serializers import UserSerializer

from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType


class SparePartTypeSerializer(NautobotModelSerializer):
    """Serializer for SparePartType."""

    manufacturer = ManufacturerSerializer(read_only=True)
    compatible_device_types = DeviceTypeSerializer(many=True, read_only=True)
    total_quantity = serializers.IntegerField(read_only=True, source="get_total_quantity")

    class Meta:
        """Meta class for SparePartTypeSerializer."""

        model = SparePartType
        fields = [
            "id",
            "url",
            "name",
            "slug",
            "manufacturer",
            "part_number",
            "description",
            "category",
            "unit_cost",
            "compatible_device_types",
            "total_quantity",
            "tags",
            "created",
            "last_updated",
        ]


class SparePartInventorySerializer(NautobotModelSerializer):
    """Serializer for SparePartInventory."""

    spare_part_type = SparePartTypeSerializer(read_only=True)
    location = LocationSerializer(read_only=True)
    quantity_available = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)

    class Meta:
        """Meta class for SparePartInventorySerializer."""

        model = SparePartInventory
        fields = [
            "id",
            "url",
            "spare_part_type",
            "location",
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
            "minimum_quantity",
            "reorder_quantity",
            "is_low_stock",
            "needs_reorder",
            "storage_location_detail",
            "notes",
            "tags",
            "created",
            "last_updated",
        ]


class SparePartTransactionSerializer(serializers.ModelSerializer):
    """Serializer for SparePartTransaction."""

    spare_part_inventory = SparePartInventorySerializer(read_only=True)
    user = UserSerializer(read_only=True)
    related_device = DeviceSerializer(required=False, allow_null=True, read_only=True)

    class Meta:
        """Meta class for SparePartTransactionSerializer."""

        model = SparePartTransaction
        fields = [
            "id",
            "url",
            "spare_part_inventory",
            "transaction_type",
            "quantity",
            "quantity_before",
            "quantity_after",
            "user",
            "timestamp",
            "reason",
            "related_device",
            "notes",
        ]
        read_only_fields = [
            "id",
            "url",
            "spare_part_inventory",
            "transaction_type",
            "quantity",
            "quantity_before",
            "quantity_after",
            "user",
            "timestamp",
        ]


class CheckInSerializer(serializers.Serializer):
    """Serializer for check-in action."""

    quantity = serializers.IntegerField(min_value=1, help_text="Number of units to add")
    reason = serializers.CharField(help_text="Reason for check-in")
    notes = serializers.CharField(required=False, allow_blank=True, help_text="Additional notes")


class CheckOutSerializer(serializers.Serializer):
    """Serializer for check-out action."""

    quantity = serializers.IntegerField(min_value=1, help_text="Number of units to remove")
    reason = serializers.CharField(help_text="Reason for check-out")
    related_device_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="ID of device this part is being used for",
    )
    notes = serializers.CharField(required=False, allow_blank=True, help_text="Additional notes")


class AdjustmentSerializer(serializers.Serializer):
    """Serializer for adjustment action."""

    quantity = serializers.IntegerField(help_text="Adjustment amount (positive or negative)")
    reason = serializers.CharField(help_text="Reason for adjustment")
    notes = serializers.CharField(required=False, allow_blank=True, help_text="Additional notes")
