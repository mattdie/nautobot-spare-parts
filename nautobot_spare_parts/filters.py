"""Filters for Spare Parts Inventory plugin."""

import django_filters

from nautobot.apps.filters import NautobotFilterSet
from nautobot.dcim.models import DeviceType, Location, Manufacturer

from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType


class SparePartTypeFilterSet(NautobotFilterSet):
    """Filter set for SparePartType."""

    q = django_filters.CharFilter(
        method="search",
        label="Search",
    )
    manufacturer = django_filters.ModelMultipleChoiceFilter(
        queryset=Manufacturer.objects.all(),
        label="Manufacturer",
    )
    category = django_filters.MultipleChoiceFilter(
        choices=SparePartType.CATEGORY_CHOICES,
        label="Category",
    )
    compatible_device_types = django_filters.ModelMultipleChoiceFilter(
        queryset=DeviceType.objects.all(),
        label="Compatible Device Type",
    )

    class Meta:
        """Meta class for SparePartTypeFilterSet."""

        model = SparePartType
        fields = ["id", "name", "slug", "manufacturer", "part_number", "category"]

    def search(self, queryset, name, value):
        """Perform search across multiple fields."""
        if not value.strip():
            return queryset
        return queryset.filter(
            django_filters.Q(name__icontains=value)
            | django_filters.Q(part_number__icontains=value)
            | django_filters.Q(description__icontains=value)
            | django_filters.Q(manufacturer__name__icontains=value)
        )


class SparePartInventoryFilterSet(NautobotFilterSet):
    """Filter set for SparePartInventory."""

    q = django_filters.CharFilter(
        method="search",
        label="Search",
    )
    spare_part_type = django_filters.ModelMultipleChoiceFilter(
        queryset=SparePartType.objects.all(),
        label="Spare Part Type",
    )
    location = django_filters.ModelMultipleChoiceFilter(
        queryset=Location.objects.all(),
        label="Location",
    )
    category = django_filters.MultipleChoiceFilter(
        field_name="spare_part_type__category",
        choices=SparePartType.CATEGORY_CHOICES,
        label="Category",
    )
    manufacturer = django_filters.ModelMultipleChoiceFilter(
        field_name="spare_part_type__manufacturer",
        queryset=Manufacturer.objects.all(),
        label="Manufacturer",
    )
    low_stock = django_filters.BooleanFilter(
        method="filter_low_stock",
        label="Low Stock",
    )

    class Meta:
        """Meta class for SparePartInventoryFilterSet."""

        model = SparePartInventory
        fields = [
            "id",
            "spare_part_type",
            "location",
            "quantity_on_hand",
            "quantity_reserved",
            "minimum_quantity",
        ]

    def search(self, queryset, name, value):
        """Perform search across multiple fields."""
        if not value.strip():
            return queryset
        return queryset.filter(
            django_filters.Q(spare_part_type__name__icontains=value)
            | django_filters.Q(spare_part_type__part_number__icontains=value)
            | django_filters.Q(location__name__icontains=value)
            | django_filters.Q(storage_location_detail__icontains=value)
        )

    def filter_low_stock(self, queryset, name, value):
        """Filter for low stock items."""
        if value:
            # Use raw SQL or annotations to filter where quantity_available <= minimum_quantity
            from django.db.models import F

            return queryset.filter(
                quantity_on_hand__lte=F("minimum_quantity") + F("quantity_reserved")
            )
        return queryset


class SparePartTransactionFilterSet(NautobotFilterSet):
    """Filter set for SparePartTransaction."""

    q = django_filters.CharFilter(
        method="search",
        label="Search",
    )
    spare_part_inventory = django_filters.ModelMultipleChoiceFilter(
        queryset=SparePartInventory.objects.all(),
        label="Inventory",
    )
    spare_part_type = django_filters.ModelMultipleChoiceFilter(
        field_name="spare_part_inventory__spare_part_type",
        queryset=SparePartType.objects.all(),
        label="Spare Part Type",
    )
    location = django_filters.ModelMultipleChoiceFilter(
        field_name="spare_part_inventory__location",
        queryset=Location.objects.all(),
        label="Location",
    )
    transaction_type = django_filters.MultipleChoiceFilter(
        choices=SparePartTransaction.TRANSACTION_TYPE_CHOICES,
        label="Transaction Type",
    )
    timestamp = django_filters.DateTimeFromToRangeFilter(
        label="Timestamp",
    )

    class Meta:
        """Meta class for SparePartTransactionFilterSet."""

        model = SparePartTransaction
        fields = [
            "id",
            "spare_part_inventory",
            "transaction_type",
            "user",
            "timestamp",
            "related_device",
        ]

    def search(self, queryset, name, value):
        """Perform search across multiple fields."""
        if not value.strip():
            return queryset
        return queryset.filter(
            django_filters.Q(spare_part_inventory__spare_part_type__name__icontains=value)
            | django_filters.Q(spare_part_inventory__location__name__icontains=value)
            | django_filters.Q(reason__icontains=value)
            | django_filters.Q(notes__icontains=value)
        )
