"""Filters for the Spare Parts Inventory app."""

import django_filters
from django.db.models import F, Q

from nautobot.apps.filters import NautobotFilterSet
from nautobot.dcim.models import Device, DeviceType, Location, Manufacturer

from nautobot_spare_parts.choices import SparePartCategoryChoices, SparePartTransactionTypeChoices
from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType


def locations_in_datacenter_of(device):
    """Every Location in the same datacenter as ``device``.

    Nautobot Locations are a tree, so "the datacenter" is the device's
    root-most ancestor and everything beneath it. Returns an empty queryset
    for a device with no location, which correctly offers no stock at all
    rather than silently offering everything.
    """
    if device is None or device.location_id is None:
        return Location.objects.none()
    root = device.location.ancestors(include_self=True).first() or device.location
    return root.descendants(include_self=True)


class SparePartTypeFilterSet(NautobotFilterSet):
    """Filter set for SparePartType."""

    q = django_filters.CharFilter(method="search", label="Search")
    manufacturer = django_filters.ModelMultipleChoiceFilter(
        queryset=Manufacturer.objects.all(),
        label="Manufacturer",
    )
    category = django_filters.MultipleChoiceFilter(
        choices=SparePartCategoryChoices,
        label="Category",
    )
    compatible_device_types = django_filters.ModelMultipleChoiceFilter(
        queryset=DeviceType.objects.all(),
        label="Compatible Device Type",
    )
    has_stock = django_filters.BooleanFilter(
        method="filter_has_stock",
        label="Has stock somewhere",
    )
    fits_device_type = django_filters.ModelChoiceFilter(
        queryset=DeviceType.objects.all(),
        method="filter_fits_device_type",
        label="Fits device type",
    )

    class Meta:
        """Meta class for SparePartTypeFilterSet."""

        model = SparePartType
        fields = ["id", "name", "manufacturer", "part_number", "category", "unit_cost"]

    def search(self, queryset, name, value):
        """Search name, part number, description and manufacturer."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(part_number__icontains=value)
            | Q(description__icontains=value)
            | Q(manufacturer__name__icontains=value)
        )

    def filter_has_stock(self, queryset, name, value):
        """Restrict to part types that are (or are not) held anywhere."""
        if value is None:
            return queryset
        held = Q(inventory_records__quantity_on_hand__gt=0)
        return queryset.filter(held).distinct() if value else queryset.exclude(held).distinct()

    def filter_fits_device_type(self, queryset, name, value):
        """Part types that fit a device type, plus the ones with no restriction.

        An empty compatibility list means "no opinion", not "fits nothing" --
        otherwise the device-side part picker would hide every part nobody has
        got round to tagging yet, which is most of them.
        """
        if value is None:
            return queryset
        return queryset.filter(Q(compatible_device_types=value) | Q(compatible_device_types__isnull=True)).distinct()


class SparePartInventoryFilterSet(NautobotFilterSet):
    """Filter set for SparePartInventory."""

    q = django_filters.CharFilter(method="search", label="Search")
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
        choices=SparePartCategoryChoices,
        label="Category",
    )
    manufacturer = django_filters.ModelMultipleChoiceFilter(
        field_name="spare_part_type__manufacturer",
        queryset=Manufacturer.objects.all(),
        label="Manufacturer",
    )
    low_stock = django_filters.BooleanFilter(method="filter_low_stock", label="Low stock")
    out_of_stock = django_filters.BooleanFilter(method="filter_out_of_stock", label="Out of stock")
    has_reservations = django_filters.BooleanFilter(method="filter_has_reservations", label="Has reservations")
    for_device = django_filters.ModelChoiceFilter(
        queryset=Device.objects.all(),
        method="filter_for_device",
        label="Stocked in the same datacenter as this device",
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
            "reorder_quantity",
            "storage_location_detail",
        ]

    def search(self, queryset, name, value):
        """Search part name/number, location and storage detail."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(spare_part_type__name__icontains=value)
            | Q(spare_part_type__part_number__icontains=value)
            | Q(spare_part_type__manufacturer__name__icontains=value)
            | Q(location__name__icontains=value)
            | Q(storage_location_detail__icontains=value)
        )

    @staticmethod
    def low_stock_q():
        """Q object matching stock-managed records at or below their threshold.

        Mirrors ``SparePartInventory.is_low_stock`` -- keep the two in step.
        """
        return Q(minimum_quantity__gt=0) & Q(quantity_on_hand__lte=F("minimum_quantity") + F("quantity_reserved"))

    def filter_low_stock(self, queryset, name, value):
        """Restrict to (or exclude) low-stock records."""
        if value is None:
            return queryset
        return queryset.filter(self.low_stock_q()) if value else queryset.exclude(self.low_stock_q())

    def filter_out_of_stock(self, queryset, name, value):
        """Restrict to (or exclude) records with nothing available."""
        if value is None:
            return queryset
        empty = Q(quantity_on_hand__lte=F("quantity_reserved"))
        return queryset.filter(empty) if value else queryset.exclude(empty)

    def filter_has_reservations(self, queryset, name, value):
        """Restrict to (or exclude) records with stock reserved."""
        if value is None:
            return queryset
        return queryset.filter(quantity_reserved__gt=0) if value else queryset.filter(quantity_reserved=0)

    def filter_for_device(self, queryset, name, value):
        """Only stock held in the same datacenter as the device.

        You do not fly a drive from Austin to Frankfurt to fix a node, so a
        device-side part picker that offers stock at another site is offering
        the wrong answer. "Same datacenter" is the whole location tree under
        the device's root location, which covers both shapes people use: stock
        recorded against the site itself, and stock recorded against a room or
        cage beneath it.
        """
        if value is None:
            return queryset
        return queryset.filter(location__in=locations_in_datacenter_of(value))


class SparePartTransactionFilterSet(NautobotFilterSet):
    """Filter set for SparePartTransaction."""

    q = django_filters.CharFilter(method="search", label="Search")
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
    related_device = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(),
        label="Related Device",
    )
    transaction_type = django_filters.MultipleChoiceFilter(
        choices=SparePartTransactionTypeChoices,
        label="Transaction Type",
    )
    timestamp = django_filters.DateTimeFromToRangeFilter(label="Timestamp")
    jira_ticket = django_filters.CharFilter(lookup_expr="iexact", label="Jira ticket")

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
            "jira_ticket",
        ]

    def search(self, queryset, name, value):
        """Search part name, location, reason, notes and Jira ticket."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(spare_part_inventory__spare_part_type__name__icontains=value)
            | Q(spare_part_inventory__location__name__icontains=value)
            | Q(reason__icontains=value)
            | Q(notes__icontains=value)
            | Q(jira_ticket__icontains=value)
        )
