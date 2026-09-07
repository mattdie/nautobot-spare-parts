"""Forms for the Spare Parts Inventory app.

The action forms (check in, check out, ...) all inherit from
:class:`MovementForm`, which carries the hidden idempotency key that makes a
double-submitted form a no-op instead of a duplicated movement.
"""

import uuid

from django import forms

from nautobot.apps.forms import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
    NautobotBulkEditForm,
    NautobotFilterForm,
    NautobotModelForm,
    StaticSelect2,
    StaticSelect2Multiple,
    TagsBulkEditFormMixin,
)
from nautobot.dcim.models import Device, DeviceType, Location, Manufacturer

from nautobot_spare_parts.choices import SparePartCategoryChoices, SparePartTransactionTypeChoices
from nautobot_spare_parts.filters import locations_in_datacenter_of
from nautobot_spare_parts.models import (
    JIRA_TICKET_VALIDATOR,
    SparePartInventory,
    SparePartTransaction,
    SparePartType,
)

QUANTITY_HELP = "Whole number of units."


class SparePartTypeForm(NautobotModelForm):
    """Create/edit a spare part type."""

    manufacturer = DynamicModelChoiceField(
        queryset=Manufacturer.objects.all(),
        required=False,
        help_text="Manufacturer of the part. Required if you enter a part number.",
    )
    compatible_device_types = DynamicModelMultipleChoiceField(
        queryset=DeviceType.objects.all(),
        required=False,
        help_text="Device types this part fits. Used to warn about mismatches on check-out.",
    )

    class Meta:
        """Meta class for SparePartTypeForm."""

        model = SparePartType
        fields = [
            "name",
            "manufacturer",
            "part_number",
            "description",
            "category",
            "unit_cost",
            "compatible_device_types",
            "tags",
        ]
        widgets = {"category": StaticSelect2()}


class SparePartTypeFilterForm(NautobotFilterForm):
    """Filter form for the spare part type list."""

    model = SparePartType

    q = forms.CharField(required=False, label="Search")
    manufacturer = DynamicModelMultipleChoiceField(queryset=Manufacturer.objects.all(), required=False)
    category = forms.MultipleChoiceField(
        choices=SparePartCategoryChoices,
        required=False,
        widget=StaticSelect2Multiple(),
    )
    has_stock = forms.NullBooleanField(required=False, label="Has stock somewhere")


class SparePartTypeBulkEditForm(TagsBulkEditFormMixin, NautobotBulkEditForm):
    """Bulk edit spare part types."""

    pk = forms.ModelMultipleChoiceField(
        queryset=SparePartType.objects.all(),
        widget=forms.MultipleHiddenInput,
    )
    manufacturer = DynamicModelChoiceField(queryset=Manufacturer.objects.all(), required=False)
    category = forms.ChoiceField(
        choices=[("", "---------")] + list(SparePartCategoryChoices.CHOICES),
        required=False,
        widget=StaticSelect2(),
    )
    unit_cost = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    class Meta:
        """Meta class for SparePartTypeBulkEditForm."""

        # part_number is deliberately not nullable in bulk: clearing it on many
        # rows at once is the kind of edit nobody means to make.
        nullable_fields = ["manufacturer", "description", "unit_cost"]


class SparePartInventoryForm(NautobotModelForm):
    """Create/edit an inventory record.

    Stock levels are editable only while creating the record. Afterwards they
    are shown read-only and must be moved through the audited actions, so the
    transaction log never drifts from the counters.
    """

    spare_part_type = DynamicModelChoiceField(
        queryset=SparePartType.objects.all(),
        help_text="Type of spare part",
    )
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        help_text="Where the stock physically lives",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        editing = self.instance is not None and self.instance.present_in_database

        self.fields["quantity_on_hand"].help_text = (
            "Opening stock count. Every later change goes through Check In / Check Out / Adjust."
        )
        self.fields["quantity_reserved"].help_text = "Leave at 0 on a new record; use Allocate to reserve stock."
        self.fields["minimum_quantity"].help_text = (
            "Raise a low-stock alert at or below this level. 0 disables alerting for this part."
        )

        if editing:
            for name in ("spare_part_type", "location", "quantity_on_hand", "quantity_reserved"):
                field = self.fields[name]
                field.disabled = True
                field.required = False
            self.fields["quantity_on_hand"].help_text = (
                "Read-only. Use Check In, Check Out or Adjust so the change is recorded."
            )
            self.fields["quantity_reserved"].help_text = "Read-only. Use Allocate or Deallocate."
            self.fields["spare_part_type"].help_text = (
                "Read-only. A record's part type and location are what its history is about -- "
                "create a new record instead, or use Transfer to move stock."
            )
            self.fields["location"].help_text = self.fields["spare_part_type"].help_text

    def clean(self):
        """Keep disabled fields at their stored values and sanity-check the pair."""
        # NautobotModelForm.clean() returns None, so fall back to cleaned_data.
        cleaned = super().clean() or self.cleaned_data
        if self.instance is not None and self.instance.present_in_database:
            for name in ("spare_part_type", "location", "quantity_on_hand", "quantity_reserved"):
                cleaned[name] = getattr(self.instance, name)
        else:
            reserved = cleaned.get("quantity_reserved") or 0
            on_hand = cleaned.get("quantity_on_hand") or 0
            if reserved > on_hand:
                self.add_error("quantity_reserved", f"Cannot reserve {reserved} units out of {on_hand} on hand.")
        return cleaned


class SparePartInventoryFilterForm(NautobotFilterForm):
    """Filter form for the inventory list."""

    model = SparePartInventory

    q = forms.CharField(required=False, label="Search")
    spare_part_type = DynamicModelMultipleChoiceField(queryset=SparePartType.objects.all(), required=False)
    location = DynamicModelMultipleChoiceField(queryset=Location.objects.all(), required=False)
    manufacturer = DynamicModelMultipleChoiceField(queryset=Manufacturer.objects.all(), required=False)
    category = forms.MultipleChoiceField(
        choices=SparePartCategoryChoices,
        required=False,
        widget=StaticSelect2Multiple(),
    )
    low_stock = forms.NullBooleanField(
        required=False,
        label="Low stock",
        help_text="Stock-managed parts at or below their minimum",
    )
    out_of_stock = forms.NullBooleanField(required=False, label="Out of stock")
    has_reservations = forms.NullBooleanField(required=False, label="Has reservations")


class SparePartInventoryBulkEditForm(TagsBulkEditFormMixin, NautobotBulkEditForm):
    """Bulk edit inventory records.

    Only the planning fields are bulk-editable. Quantities are not, on purpose.
    """

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


class SparePartTransactionFilterForm(NautobotFilterForm):
    """Filter form for the transaction list."""

    model = SparePartTransaction

    q = forms.CharField(required=False, label="Search")
    spare_part_type = DynamicModelMultipleChoiceField(queryset=SparePartType.objects.all(), required=False)
    location = DynamicModelMultipleChoiceField(queryset=Location.objects.all(), required=False)
    transaction_type = forms.MultipleChoiceField(
        choices=SparePartTransactionTypeChoices,
        required=False,
        widget=StaticSelect2Multiple(),
    )
    related_device = DynamicModelMultipleChoiceField(queryset=Device.objects.all(), required=False, label="Device")
    jira_ticket = forms.CharField(required=False, label="Jira ticket")


class MovementForm(forms.Form):
    """Base class for the stock action forms.

    ``request_id`` is rendered as a hidden field and generated once per GET.
    Re-posting the same form -- double-clicked button, browser back and resubmit,
    a retried request -- carries the same id, and the model layer then returns
    the original transaction instead of applying the movement twice.
    """

    request_id = forms.UUIDField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["request_id"].initial = uuid.uuid4()

    def clean_request_id(self):
        """Fall back to a fresh id if the hidden field went missing."""
        return self.cleaned_data.get("request_id") or uuid.uuid4()

    def clean_reason(self):
        """Reject whitespace-only reasons."""
        reason = (self.cleaned_data.get("reason") or "").strip()
        if not reason:
            raise forms.ValidationError("Say why -- this ends up in the audit trail.")
        return reason


class CheckInForm(MovementForm):
    """Add received stock."""

    quantity = forms.IntegerField(min_value=1, help_text=f"{QUANTITY_HELP} Units received.")
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Where did these come from? e.g. 'RMA replacement from Supermicro'",
    )
    jira_ticket = forms.CharField(
        max_length=50,
        required=False,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket reference (e.g. INFRA2-1234)",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)


class CheckOutForm(MovementForm):
    """Remove stock that is being consumed."""

    quantity = forms.IntegerField(min_value=1, help_text=f"{QUANTITY_HELP} Units taken out.")
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="What are they for? e.g. 'Replace failed DIMM in slot B2'",
    )
    fulfil_reservation = forms.BooleanField(
        required=False,
        label="These units were reserved",
        help_text="Tick to take the units out of the reserved pool, releasing the reservation as you go.",
    )
    related_device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        required=False,
        label="Device",
        help_text="Device the part is going into.",
    )
    jira_ticket = forms.CharField(
        max_length=50,
        required=False,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket reference (e.g. INFRA2-1234)",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, inventory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory = inventory
        if inventory is None:
            return

        # Devices at the same location first -- that is almost always the right
        # answer -- but do not hard-restrict it: parts get walked between rooms.
        self.fields["related_device"].queryset = Device.objects.all()
        self.fields["related_device"].query_params = {"location": inventory.location_id}
        self.fields["related_device"].help_text = (
            f"Device the part is going into. Defaults to devices at {inventory.location}."
        )
        if inventory.quantity_reserved:
            self.fields["fulfil_reservation"].help_text = (
                f"{inventory.quantity_reserved} unit(s) are reserved here. Tick this if you are "
                "taking reserved stock, so the reservation is released too."
            )
        else:
            self.fields["fulfil_reservation"].widget = forms.HiddenInput()

    def clean(self):
        """Check the requested quantity against what is actually takeable."""
        cleaned = super().clean()
        quantity = cleaned.get("quantity")
        if self.inventory is None or not quantity:
            return cleaned

        if cleaned.get("fulfil_reservation"):
            if quantity > self.inventory.quantity_reserved:
                self.add_error(
                    "quantity",
                    f"Only {self.inventory.quantity_reserved} unit(s) are reserved here.",
                )
        elif quantity > self.inventory.quantity_available:
            available = self.inventory.quantity_available
            hint = ""
            if self.inventory.quantity_reserved:
                hint = (
                    f" {self.inventory.quantity_reserved} of the {self.inventory.quantity_on_hand} on hand are "
                    "reserved — tick 'These units were reserved' if you are taking those."
                )
            self.add_error("quantity", f"Only {available} unit(s) available.{hint}")

        device = cleaned.get("related_device")
        part_type = self.inventory.spare_part_type
        if device is not None and part_type.compatible_device_types.exists():
            if not part_type.compatible_device_types.filter(pk=device.device_type_id).exists():
                self.add_error(
                    "related_device",
                    f"{part_type} is not listed as compatible with {device.device_type}. "
                    "Add the device type to the part's compatibility list if this is correct.",
                )
        return cleaned


class DeviceCheckOutForm(MovementForm):
    """Take a part *for a device*, starting from the device.

    The inverse of :class:`CheckOutForm`: that one starts from a shelf and asks
    which device, this one starts from the device and asks which shelf. The
    second is how the job actually presents itself -- "ca099 needs a drive" --
    so the part picker is chained off the device's own compatibility list and
    the reason writes itself.
    """

    spare_part_type = DynamicModelChoiceField(
        queryset=SparePartType.objects.all(),
        label="Part",
        help_text="Parts that fit this device type, or that carry no compatibility restriction.",
    )
    # Not browser-required on purpose. If the chosen part has no local stock
    # the dropdown is legitimately empty, and an HTML5 "please select an item
    # in the list" tooltip would block the POST -- so the server never gets to
    # say the useful thing, which is *where the part actually is*. Required-ness
    # is enforced in clean() instead, after that check has had its say.
    inventory = DynamicModelChoiceField(
        queryset=SparePartInventory.objects.all(),
        required=False,
        label="Take from",
        help_text="Only stock in this device's own datacenter.",
    )
    quantity = forms.IntegerField(min_value=1, initial=1, help_text=f"{QUANTITY_HELP} Units fitted.")
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Pre-filled from the device. Say what actually failed if it is worth knowing.",
    )
    fulfil_reservation = forms.BooleanField(
        required=False,
        label="These units were reserved",
        help_text="Tick if the stock was reserved for this work, so the reservation is released too.",
    )
    jira_ticket = forms.CharField(
        max_length=50,
        required=False,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket reference (e.g. INFRA2-1234)",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def __init__(self, *args, device=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.device = device
        if device is None:
            return

        self.fields["spare_part_type"].query_params = {
            "fits_device_type": str(device.device_type_id),
            "has_stock": True,
        }
        # Hard scope, not a hint: nobody carries a drive from Austin to
        # Frankfurt, so stock at another datacenter is never the right answer.
        self.fields["inventory"].query_params = {
            "spare_part_type": "$spare_part_type",
            "out_of_stock": False,
            "for_device": str(device.pk),
        }
        # The queryset stays broad on purpose. Narrowing it makes Django reject
        # an out-of-datacenter pick with its generic "not one of the available
        # choices", which tells the user nothing; clean() below refuses the same
        # thing and can name the location and what to do about it.
        if device.location is not None:
            datacenter = device.location.ancestors(include_self=True).first() or device.location
            self.fields["inventory"].help_text = f"Only stock at {datacenter}."
        if not self.is_bound:
            self.fields["reason"].initial = f"Replaced part in {device.name}"

    def clean(self):
        """Check the datacenter scope and the requested quantity."""
        cleaned = super().clean()
        inventory = cleaned.get("inventory")
        quantity = cleaned.get("quantity")

        if inventory is None:
            # Only nag about the empty dropdown if the part type itself was
            # acceptable; otherwise clean_spare_part_type has already explained
            # why there is nothing to choose.
            if "spare_part_type" in cleaned:
                self.add_error("inventory", "Choose where to take it from.")
            return cleaned

        if self.device is not None:
            allowed = locations_in_datacenter_of(self.device)
            if not allowed.filter(pk=inventory.location_id).exists():
                self.add_error(
                    "inventory",
                    f"{inventory.location} is not in the same datacenter as {self.device.name}. "
                    "Transfer the stock there first, or take it from local stock.",
                )
                return cleaned

        if not quantity:
            return cleaned

        if cleaned.get("fulfil_reservation"):
            if quantity > inventory.quantity_reserved:
                self.add_error("quantity", f"Only {inventory.quantity_reserved} unit(s) are reserved there.")
        elif quantity > inventory.quantity_available:
            hint = ""
            if inventory.quantity_reserved:
                hint = (
                    f" {inventory.quantity_reserved} of the {inventory.quantity_on_hand} on hand are reserved"
                    " — tick 'These units were reserved' if you are taking those."
                )
            self.add_error(
                "quantity",
                f"Only {inventory.quantity_available} unit(s) available at {inventory.location}.{hint}",
            )
        return cleaned

    def clean_spare_part_type(self):
        """Say where the part actually is when this datacenter has none.

        The alternative is an empty "Take from" dropdown and no explanation,
        which reads as a broken form rather than an empty shelf.
        """
        part_type = self.cleaned_data["spare_part_type"]
        if self.device is None:
            return part_type

        local = SparePartInventory.objects.filter(
            spare_part_type=part_type,
            location__in=locations_in_datacenter_of(self.device),
            quantity_on_hand__gt=0,
        )
        if local.exists():
            return part_type

        elsewhere = (
            SparePartInventory.objects.filter(spare_part_type=part_type, quantity_on_hand__gt=0)
            .select_related("location")
            .order_by("-quantity_on_hand")[:3]
        )
        if elsewhere:
            where = ", ".join(f"{record.location} ({record.quantity_available} available)" for record in elsewhere)
            raise forms.ValidationError(f"None here. It is stocked at: {where}. Transfer some over first.")
        raise forms.ValidationError("None in stock anywhere. Check it in when it arrives.")


class AdjustmentForm(MovementForm):
    """Correct a count after a physical stock take."""

    quantity = forms.IntegerField(
        help_text="Signed correction: 3 to add three units, -3 to remove three.",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Why is the recorded count wrong? e.g. 'Stock take 2026-09-01, two units unaccounted for'",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def clean_quantity(self):
        """Reject a no-op adjustment."""
        quantity = self.cleaned_data["quantity"]
        if quantity == 0:
            raise forms.ValidationError("An adjustment of 0 changes nothing.")
        return quantity


class AllocationForm(MovementForm):
    """Reserve available stock."""

    quantity = forms.IntegerField(min_value=1, help_text=f"{QUANTITY_HELP} Units to reserve.")
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="What is this reserved for? e.g. 'INFRA2-1234 planned maintenance on ca099'",
    )
    jira_ticket = forms.CharField(
        max_length=50,
        required=False,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket reference (e.g. INFRA2-1234)",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, inventory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory = inventory
        if inventory is not None:
            self.fields["quantity"].widget.attrs["max"] = inventory.quantity_available
            self.fields["quantity"].help_text = f"{inventory.quantity_available} unit(s) available to reserve."

    def clean_quantity(self):
        """Check against what is available right now."""
        quantity = self.cleaned_data["quantity"]
        if self.inventory is not None and quantity > self.inventory.quantity_available:
            raise forms.ValidationError(f"Only {self.inventory.quantity_available} unit(s) available to reserve.")
        return quantity


class DeallocationForm(MovementForm):
    """Release a reservation."""

    quantity = forms.IntegerField(min_value=1, help_text=f"{QUANTITY_HELP} Reserved units to release.")
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Why is the reservation no longer needed? e.g. 'Maintenance window cancelled'",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, inventory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory = inventory
        if inventory is not None:
            self.fields["quantity"].widget.attrs["max"] = inventory.quantity_reserved
            self.fields["quantity"].help_text = f"{inventory.quantity_reserved} unit(s) currently reserved."

    def clean_quantity(self):
        """Check against what is reserved right now."""
        quantity = self.cleaned_data["quantity"]
        if self.inventory is not None and quantity > self.inventory.quantity_reserved:
            raise forms.ValidationError(f"Only {self.inventory.quantity_reserved} unit(s) are reserved.")
        return quantity


class TransferForm(MovementForm):
    """Move stock to another location."""

    quantity = forms.IntegerField(min_value=1, help_text=f"{QUANTITY_HELP} Units to move.")
    destination_location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        label="Destination",
        help_text="Where the stock is going. An inventory record is created there if needed.",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Why move it? e.g. 'Rebalancing DIMM stock towards FRA1'",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, inventory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory = inventory
        if inventory is not None:
            self.fields["destination_location"].queryset = Location.objects.exclude(pk=inventory.location_id)
            self.fields["quantity"].widget.attrs["max"] = inventory.quantity_available
            self.fields["quantity"].help_text = f"{inventory.quantity_available} unit(s) available to move."

    def clean(self):
        """Reject same-location transfers and over-transfers."""
        cleaned = super().clean()
        if self.inventory is None:
            return cleaned
        destination = cleaned.get("destination_location")
        if destination is not None and destination.pk == self.inventory.location_id:
            self.add_error("destination_location", "Source and destination location must differ.")
        quantity = cleaned.get("quantity")
        if quantity and quantity > self.inventory.quantity_available:
            self.add_error(
                "quantity",
                f"Only {self.inventory.quantity_available} unit(s) available to move "
                f"({self.inventory.quantity_reserved} reserved).",
            )
        return cleaned


class BinLabelPickerForm(forms.Form):
    """Choose which shelf labels to print.

    A GET form on purpose: the resulting URL is the whole recipe, so "print the
    AUS1 cage again" is a bookmark rather than a re-tick of eight boxes.
    """

    inventory = DynamicModelMultipleChoiceField(
        queryset=SparePartInventory.objects.all(),
        required=False,
        label="Specific records",
        help_text="Pick exact bins. Anything chosen here wins over the filters below.",
    )
    location = DynamicModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label="Whole location",
        help_text="Every bin at these locations. Leave the field above empty to use this.",
    )
    spare_part_type = DynamicModelMultipleChoiceField(
        queryset=SparePartType.objects.all(),
        required=False,
        label="Only these part types",
    )
    low_stock = forms.BooleanField(
        required=False,
        label="Only what is low on stock",
        help_text="Useful for a reorder walk-round.",
    )
    copies = forms.IntegerField(
        min_value=1,
        max_value=10,
        initial=1,
        required=False,
        label="Copies of each",
        help_text="Two is usual: one on the bin, one on the shelf edge.",
    )

    def selected_records(self):
        """The records to print, honouring the precedence documented above."""
        if not self.is_valid():
            return SparePartInventory.objects.none()

        data = self.cleaned_data
        if data.get("inventory"):
            queryset = SparePartInventory.objects.filter(pk__in=[record.pk for record in data["inventory"]])
        else:
            queryset = SparePartInventory.objects.all()
            if data.get("location"):
                queryset = queryset.filter(location__in=data["location"])
            if data.get("spare_part_type"):
                queryset = queryset.filter(spare_part_type__in=data["spare_part_type"])
            if data.get("low_stock"):
                from nautobot_spare_parts.filters import SparePartInventoryFilterSet

                queryset = queryset.filter(SparePartInventoryFilterSet.low_stock_q())
        return queryset

    def copy_count(self):
        """How many of each label to print."""
        if not self.is_valid():
            return 1
        return self.cleaned_data.get("copies") or 1


class BulkReceiveLineForm(forms.Form):
    """One line of a bulk receive."""

    inventory = DynamicModelChoiceField(
        queryset=SparePartInventory.objects.all(),
        label="Part / Location",
        required=False,
        help_text="Inventory record to receive into",
    )
    quantity = forms.IntegerField(min_value=1, required=False, label="Qty received")

    def clean(self):
        """Require both fields together, or neither (an untouched line)."""
        cleaned = super().clean()
        inventory = cleaned.get("inventory")
        quantity = cleaned.get("quantity")
        if inventory and not quantity:
            self.add_error("quantity", "How many did you receive?")
        if quantity and not inventory:
            self.add_error("inventory", "Which part is this?")
        return cleaned


class BulkReceiveBaseFormSet(forms.BaseFormSet):
    """Formset that rejects duplicate lines and empty submissions."""

    def clean(self):
        """Validate the set as a whole."""
        super().clean()
        if any(self.errors):
            return

        seen = {}
        filled = 0
        for index, form in enumerate(self.forms):
            if self.can_delete and self._should_delete_form(form):
                continue
            inventory = form.cleaned_data.get("inventory")
            if not inventory:
                continue
            filled += 1
            if inventory.pk in seen:
                form.add_error(
                    "inventory",
                    f"Same inventory record as line {seen[inventory.pk] + 1}. "
                    "Put the whole amount on one line instead.",
                )
            seen[inventory.pk] = index

        if not filled:
            raise forms.ValidationError("Nothing to receive -- fill in at least one line.")


class BulkReceiveHeaderForm(forms.Form):
    """Shipment-level fields shared by every line of a bulk receive.

    No idempotency key here: the submit button disables itself, and a
    re-submitted shipment is caught by the duplicate-line check rather than by
    a per-line key derived from a shipment key, which was more machinery than
    the problem deserved.
    """

    reason = forms.CharField(
        initial="Bulk receive",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Applies to every line. e.g. 'Shipment 4711 from Arrow, delivered 2026-09-05'",
    )
    jira_ticket = forms.CharField(
        max_length=50,
        required=False,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket reference (e.g. INFRA2-1234)",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)


BulkReceiveFormSet = forms.formset_factory(
    BulkReceiveLineForm,
    formset=BulkReceiveBaseFormSet,
    extra=5,
    can_delete=True,
)
