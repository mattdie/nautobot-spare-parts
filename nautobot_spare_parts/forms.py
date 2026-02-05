"""Forms for Spare Parts Inventory plugin."""

from django import forms

from nautobot.apps.forms import (
    NautobotBulkEditForm,
    NautobotFilterForm,
    NautobotModelForm,
    TagsBulkEditFormMixin,
)
from nautobot.dcim.models import Device, DeviceType, Location, Manufacturer
from nautobot.extras.forms import NautobotBulkEditForm as ExtrasNautobotBulkEditForm

from nautobot_spare_parts.models import SparePartInventory, SparePartType


class SparePartTypeForm(NautobotModelForm):
    """Form for creating/editing SparePartType."""

    manufacturer = forms.ModelChoiceField(
        queryset=Manufacturer.objects.all(),
        required=False,
        help_text="Manufacturer of the part",
    )
    compatible_device_types = forms.ModelMultipleChoiceField(
        queryset=DeviceType.objects.all(),
        required=False,
        help_text="Device types this part is compatible with",
    )

    class Meta:
        """Meta class for SparePartTypeForm."""

        model = SparePartType
        fields = [
            "name",
            "slug",
            "manufacturer",
            "part_number",
            "description",
            "category",
            "unit_cost",
            "compatible_device_types",
            "tags",
        ]


class SparePartTypeFilterForm(NautobotFilterForm):
    """Filter form for SparePartType list view."""

    model = SparePartType

    q = forms.CharField(required=False, label="Search")
    manufacturer = forms.ModelMultipleChoiceField(
        queryset=Manufacturer.objects.all(),
        required=False,
    )
    category = forms.MultipleChoiceField(
        choices=SparePartType.CATEGORY_CHOICES,
        required=False,
    )


class SparePartTypeBulkEditForm(TagsBulkEditFormMixin, NautobotBulkEditForm):
    """Bulk edit form for SparePartType."""

    pk = forms.ModelMultipleChoiceField(
        queryset=SparePartType.objects.all(),
        widget=forms.MultipleHiddenInput,
    )
    manufacturer = forms.ModelChoiceField(
        queryset=Manufacturer.objects.all(),
        required=False,
    )
    category = forms.ChoiceField(
        choices=SparePartType.CATEGORY_CHOICES,
        required=False,
    )
    unit_cost = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
    )

    class Meta:
        """Meta class for SparePartTypeBulkEditForm."""

        nullable_fields = ["manufacturer", "part_number", "description", "unit_cost"]


class SparePartInventoryForm(NautobotModelForm):
    """Form for creating/editing SparePartInventory."""

    spare_part_type = forms.ModelChoiceField(
        queryset=SparePartType.objects.all(),
        help_text="Type of spare part",
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        help_text="Storage location",
    )

    class Meta:
        """Meta class for SparePartInventoryForm."""

        model = SparePartInventory
        fields = [
            "spare_part_type",
            "location",
            "quantity_on_hand",
            "quantity_reserved",
            "minimum_quantity",
            "reorder_quantity",
            "storage_location_detail",
            "notes",
            "tags",
        ]


class SparePartInventoryFilterForm(NautobotFilterForm):
    """Filter form for SparePartInventory list view."""

    model = SparePartInventory

    q = forms.CharField(required=False, label="Search")
    spare_part_type = forms.ModelMultipleChoiceField(
        queryset=SparePartType.objects.all(),
        required=False,
    )
    location = forms.ModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=False,
    )
    category = forms.MultipleChoiceField(
        choices=SparePartType.CATEGORY_CHOICES,
        required=False,
    )
    low_stock = forms.BooleanField(
        required=False,
        label="Low Stock Only",
        help_text="Show only items at or below minimum quantity",
    )


class SparePartInventoryBulkEditForm(TagsBulkEditFormMixin, NautobotBulkEditForm):
    """Bulk edit form for SparePartInventory."""

    pk = forms.ModelMultipleChoiceField(
        queryset=SparePartInventory.objects.all(),
        widget=forms.MultipleHiddenInput,
    )
    minimum_quantity = forms.IntegerField(required=False, min_value=0)
    reorder_quantity = forms.IntegerField(required=False, min_value=0)
    storage_location_detail = forms.CharField(max_length=100, required=False)

    class Meta:
        """Meta class for SparePartInventoryBulkEditForm."""

        nullable_fields = ["storage_location_detail", "notes"]


class CheckInForm(forms.Form):
    """Form for checking in spare parts (adding stock)."""

    quantity = forms.IntegerField(
        min_value=1,
        help_text="Number of units to add to inventory",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Reason for check-in (e.g., 'Received shipment from vendor')",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="Additional notes (optional)",
    )


class CheckOutForm(forms.Form):
    """Form for checking out spare parts (removing stock)."""

    quantity = forms.IntegerField(
        min_value=1,
        help_text="Number of units to remove from inventory",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Reason for check-out (e.g., 'Replace failed component')",
    )
    related_device = forms.ModelChoiceField(
        queryset=Device.objects.all(),
        required=False,
        help_text="Device this part is being used for (optional)",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="Additional notes (optional)",
    )


class AdjustmentForm(forms.Form):
    """Form for inventory adjustments (corrections)."""

    quantity = forms.IntegerField(
        help_text="Adjustment amount (positive to add, negative to remove)",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Reason for adjustment (e.g., 'Inventory count correction')",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="Additional notes (optional)",
    )
