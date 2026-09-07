"""Data models for the Spare Parts Inventory app.

Design rules that the rest of the app depends on:

* ``quantity_on_hand`` and ``quantity_reserved`` are only ever changed through
  :meth:`SparePartInventory.record_movement` (or one of the thin wrappers around
  it). Every change takes a row lock and writes a
  :class:`SparePartTransaction`, so the transaction log always adds up to the
  current counters.
* :class:`SparePartTransaction` rows are append-only. Once written they cannot
  be edited or deleted through the ORM.
* A transaction records both counters before and after the change, so history
  can be replayed without knowing which kind of movement it was.
"""

import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.urls import reverse

from nautobot.apps.models import BaseModel, PrimaryModel
from nautobot.dcim.models import Device, DeviceType, Location, Manufacturer
from nautobot.extras.utils import extras_features

from nautobot_spare_parts.choices import SparePartCategoryChoices, SparePartTransactionTypeChoices

User = get_user_model()

JIRA_TICKET_VALIDATOR = RegexValidator(
    regex=r"^[A-Z][A-Z0-9]*-\d+$",
    message="Jira ticket must look like INFRA2-1234.",
)


@extras_features(
    "custom_fields",
    "custom_links",
    "custom_validators",
    "export_templates",
    "graphql",
    "relationships",
    "webhooks",
)
class SparePartType(PrimaryModel):
    """A kind of spare part -- the catalogue entry, not the physical stock."""

    name = models.CharField(max_length=100, db_index=True, help_text="Display name for the spare part type")
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="spare_part_types",
        blank=True,
        null=True,
        help_text="Manufacturer of the part",
    )
    part_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Manufacturer part number",
    )
    description = models.TextField(blank=True, help_text="Detailed description of the part")
    category = models.CharField(
        max_length=50,
        choices=SparePartCategoryChoices,
        default=SparePartCategoryChoices.OTHER,
        db_index=True,
        help_text="Category of spare part",
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text="Cost per unit in local currency",
    )
    compatible_device_types = models.ManyToManyField(
        DeviceType,
        related_name="compatible_spare_parts",
        blank=True,
        help_text="Device types this part is compatible with",
    )

    class Meta:
        """Meta class for SparePartType."""

        ordering = ["category", "manufacturer__name", "name"]
        constraints = [
            # Two parts from the same manufacturer must not share a part number.
            # Scoped to rows that actually have a part number, so any number of
            # part types without one can coexist.
            models.UniqueConstraint(
                fields=["manufacturer", "part_number"],
                condition=~Q(part_number=""),
                name="spare_parts_unique_manufacturer_part_number",
            ),
        ]
        verbose_name = "Spare Part Type"
        verbose_name_plural = "Spare Part Types"

    def __str__(self):
        """String representation."""
        if self.manufacturer:
            return f"{self.manufacturer.name} {self.name}"
        return self.name

    def get_absolute_url(self, api=False):
        """Return absolute URL for detail view."""
        if api:
            return reverse("plugins-api:nautobot_spare_parts-api:spareparttype-detail", kwargs={"pk": self.pk})
        return reverse("plugins:nautobot_spare_parts:spareparttype", args=[self.pk])

    def clean(self):
        """Validate model data."""
        super().clean()
        self.name = (self.name or "").strip()
        self.part_number = (self.part_number or "").strip()
        if self.part_number and not self.manufacturer:
            raise ValidationError({"manufacturer": "Manufacturer is required when a part number is specified."})
        if self.part_number:
            clash = SparePartType.objects.filter(
                manufacturer=self.manufacturer, part_number__iexact=self.part_number
            ).exclude(pk=self.pk)
            if clash.exists():
                raise ValidationError(
                    {"part_number": f"{self.manufacturer} already has a part type with part number {self.part_number}."}
                )

    @property
    def total_quantity_on_hand(self):
        """Total stock across every location."""
        return self.inventory_records.aggregate(total=models.Sum("quantity_on_hand"))["total"] or 0

    # Kept under the original name because export templates and Jobs may call it.
    def get_total_quantity(self):
        """Total stock across every location (alias of total_quantity_on_hand)."""
        return self.total_quantity_on_hand

    def get_locations_with_stock(self):
        """Locations that currently hold this part."""
        return Location.objects.filter(
            spare_part_inventories__spare_part_type=self,
            spare_part_inventories__quantity_on_hand__gt=0,
        ).distinct()


@extras_features(
    "custom_fields",
    "custom_links",
    "custom_validators",
    "export_templates",
    "graphql",
    "relationships",
    "webhooks",
)
class SparePartInventory(PrimaryModel):
    """Physical stock of one part type at one location."""

    spare_part_type = models.ForeignKey(
        SparePartType,
        on_delete=models.PROTECT,
        related_name="inventory_records",
        help_text="Type of spare part",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="spare_part_inventories",
        help_text="Storage location",
    )
    quantity_on_hand = models.PositiveIntegerField(
        default=0,
        help_text="Units physically present. Changed by check in / check out / adjust / transfer only.",
    )
    quantity_reserved = models.PositiveIntegerField(
        default=0,
        help_text="Units on hand that are already promised to a job. Changed by allocate / deallocate only.",
    )
    minimum_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Reorder threshold. 0 means this part is not stock-managed and never raises a low-stock alert.",
    )
    reorder_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Suggested quantity to reorder when stock runs low",
    )
    storage_location_detail = models.CharField(
        max_length=100,
        blank=True,
        help_text="Specific storage location (e.g. Rack A, Shelf 3)",
    )
    notes = models.TextField(blank=True)

    class Meta:
        """Meta class for SparePartInventory."""

        ordering = ["location__name", "spare_part_type__name"]
        unique_together = [["spare_part_type", "location"]]
        constraints = [
            models.CheckConstraint(
                check=Q(quantity_reserved__lte=F("quantity_on_hand")),
                name="spare_parts_reserved_lte_on_hand",
            ),
        ]
        verbose_name = "Spare Part Inventory"
        verbose_name_plural = "Spare Part Inventories"

    def __str__(self):
        """String representation."""
        return f"{self.spare_part_type} at {self.location}"

    def get_absolute_url(self, api=False):
        """Return absolute URL for detail view."""
        if api:
            return reverse("plugins-api:nautobot_spare_parts-api:sparepartinventory-detail", kwargs={"pk": self.pk})
        return reverse("plugins:nautobot_spare_parts:sparepartinventory", args=[self.pk])

    # --- derived state -------------------------------------------------------

    @staticmethod
    def annotate_available(queryset):
        """Annotate ``available`` so it can be sorted and filtered in the database."""
        return queryset.annotate(available=F("quantity_on_hand") - F("quantity_reserved"))

    @property
    def quantity_available(self):
        """Units that can still be handed out (on hand minus reserved)."""
        return self.quantity_on_hand - self.quantity_reserved

    @property
    def is_out_of_stock(self):
        """Nothing available at all."""
        return self.quantity_available <= 0

    @property
    def is_low_stock(self):
        """At or below the reorder threshold.

        Only meaningful for stock-managed parts: a record with
        ``minimum_quantity == 0`` is not tracked against a threshold and is
        deliberately excluded, otherwise every empty shelf entry would sit in
        the low-stock dashboard forever.
        """
        return self.minimum_quantity > 0 and self.quantity_available <= self.minimum_quantity

    @property
    def needs_reorder(self):
        """Low on stock and someone told us how many to buy."""
        return self.is_low_stock and self.reorder_quantity > 0

    def clean(self):
        """Validate model data."""
        super().clean()
        if self.quantity_reserved > self.quantity_on_hand:
            raise ValidationError(
                {
                    "quantity_reserved": (
                        f"Reserved ({self.quantity_reserved}) cannot exceed on hand ({self.quantity_on_hand})."
                    )
                }
            )

    def save(self, *args, **kwargs):
        """Refuse silent edits to the counters.

        Stock levels are only allowed to move through
        :meth:`record_movement`, which writes the matching audit record. This
        catches every other route -- the edit form, a bulk edit, an API PATCH,
        a Job or an nbshell one-liner -- instead of letting the transaction log
        drift away from reality.
        """
        if self.present_in_database and not getattr(self, "_movement_in_progress", False):
            previous = (
                SparePartInventory.objects.filter(pk=self.pk).values("quantity_on_hand", "quantity_reserved").first()
            )
            if previous is not None and (
                previous["quantity_on_hand"] != self.quantity_on_hand
                or previous["quantity_reserved"] != self.quantity_reserved
            ):
                raise ValidationError(
                    {
                        "quantity_on_hand": (
                            "Stock levels cannot be edited directly, because that would leave no audit "
                            "record. Use Check In, Check Out, Adjust, Transfer, Allocate or Deallocate."
                        )
                    }
                )
        return super().save(*args, **kwargs)

    # --- the single write path ----------------------------------------------

    def record_movement(
        self,
        *,
        transaction_type,
        quantity=0,
        reserved_delta=0,
        reason,
        user=None,
        related_device=None,
        jira_ticket="",
        notes="",
        request_id=None,
        transfer_group=None,
    ):
        """Apply a stock movement and write its audit record, atomically.

        ``quantity`` is the signed change to ``quantity_on_hand``;
        ``reserved_delta`` the signed change to ``quantity_reserved``. Every
        other mutation helper on this model is a wrapper around this method.

        Passing a ``request_id`` makes the call idempotent: if a transaction
        with that id already exists it is returned untouched instead of
        applying the movement a second time. That is what stops a double-clicked
        form or a retried API call from checking the same shipment in twice.

        Raises ``django.core.exceptions.ValidationError`` and changes nothing if
        the movement is not allowed.
        """
        if transaction_type not in SparePartTransactionTypeChoices.values():
            raise ValidationError(f"Unknown transaction type '{transaction_type}'.")
        if quantity == 0 and reserved_delta == 0:
            raise ValidationError("A movement must change either stock on hand or reserved quantity.")
        if quantity and transaction_type not in SparePartTransactionTypeChoices.STOCK_TYPES:
            raise ValidationError(f"A {transaction_type} transaction cannot change quantity on hand.")
        if transaction_type == SparePartTransactionTypeChoices.CHECK_IN and quantity < 0:
            raise ValidationError("A check-in must add stock. Use check out or adjust to remove stock.")
        if transaction_type == SparePartTransactionTypeChoices.CHECK_OUT and quantity > 0:
            raise ValidationError("A check-out must remove stock. Use check in or adjust to add stock.")
        if reserved_delta > 0 and transaction_type != SparePartTransactionTypeChoices.ALLOCATION:
            raise ValidationError("Only an allocation can increase the reserved quantity.")
        if not (reason or "").strip():
            raise ValidationError({"reason": "A reason is required so the audit trail stays useful."})

        with transaction.atomic():
            if request_id is not None:
                existing = SparePartTransaction.objects.filter(request_id=request_id).first()
                if existing is not None:
                    return existing

            locked = SparePartInventory.objects.select_for_update().get(pk=self.pk)

            quantity_before = locked.quantity_on_hand
            reserved_before = locked.quantity_reserved
            quantity_after = quantity_before + quantity
            reserved_after = reserved_before + reserved_delta

            if quantity_after < 0:
                raise ValidationError(
                    f"Cannot remove {abs(quantity)} units: only {quantity_before} on hand at {locked.location}."
                )
            if reserved_after < 0:
                raise ValidationError(
                    f"Cannot release {abs(reserved_delta)} units: only {reserved_before} reserved at {locked.location}."
                )
            if reserved_after > quantity_after:
                if reserved_delta > 0:
                    raise ValidationError(
                        f"Cannot reserve {reserved_delta} units: only "
                        f"{quantity_before - reserved_before} available at {locked.location}."
                    )
                raise ValidationError(
                    f"Cannot remove {abs(quantity)} units: that would leave {quantity_after} on hand "
                    f"but {reserved_after} are reserved. Release the reservation first, or check out "
                    f"against it."
                )

            locked.quantity_on_hand = quantity_after
            locked.quantity_reserved = reserved_after
            locked._movement_in_progress = True
            locked.validated_save()

            txn = SparePartTransaction(
                spare_part_inventory=locked,
                transaction_type=transaction_type,
                quantity=quantity,
                reserved_delta=reserved_delta,
                quantity_before=quantity_before,
                quantity_after=quantity_after,
                reserved_before=reserved_before,
                reserved_after=reserved_after,
                user=user,
                reason=reason.strip(),
                related_device=related_device,
                jira_ticket=(jira_ticket or "").strip(),
                notes=notes or "",
                request_id=request_id,
                transfer_group=transfer_group,
            )
            txn.validated_save()

        # Keep the in-memory object consistent with what was just committed.
        self.quantity_on_hand = quantity_after
        self.quantity_reserved = reserved_after
        return txn

    # --- wrappers, one per user-facing action --------------------------------

    def check_in(self, quantity, reason, **kwargs):
        """Add received stock."""
        self._require_positive(quantity, "Check-in")
        return self.record_movement(
            transaction_type=SparePartTransactionTypeChoices.CHECK_IN,
            quantity=quantity,
            reason=reason,
            **kwargs,
        )

    def check_out(self, quantity, reason, fulfil_reservation=False, **kwargs):
        """Remove stock that is being used.

        With ``fulfil_reservation=True`` the units come out of the reserved
        pool: on hand and reserved both drop. That is the path to use after an
        allocation, and it is the only way to check out stock that is fully
        reserved.
        """
        self._require_positive(quantity, "Check-out")
        return self.record_movement(
            transaction_type=SparePartTransactionTypeChoices.CHECK_OUT,
            quantity=-quantity,
            reserved_delta=-quantity if fulfil_reservation else 0,
            reason=reason,
            **kwargs,
        )

    def adjust(self, quantity, reason, **kwargs):
        """Correct the count after a physical stock take."""
        if quantity == 0:
            raise ValidationError("An adjustment of 0 changes nothing -- enter a positive or negative amount.")
        return self.record_movement(
            transaction_type=SparePartTransactionTypeChoices.ADJUSTMENT,
            quantity=quantity,
            reason=reason,
            **kwargs,
        )

    def allocate(self, quantity, reason, **kwargs):
        """Reserve available stock for planned work."""
        self._require_positive(quantity, "Allocation")
        return self.record_movement(
            transaction_type=SparePartTransactionTypeChoices.ALLOCATION,
            reserved_delta=quantity,
            reason=reason,
            **kwargs,
        )

    def deallocate(self, quantity, reason, **kwargs):
        """Release a reservation without consuming the stock."""
        self._require_positive(quantity, "Deallocation")
        return self.record_movement(
            transaction_type=SparePartTransactionTypeChoices.DEALLOCATION,
            reserved_delta=-quantity,
            reason=reason,
            **kwargs,
        )

    def transfer_to(self, destination_location, quantity, reason, user=None, notes="", request_id=None):
        """Move stock to another location, writing one transaction on each side.

        Both legs are written in a single database transaction: either the
        destination gains the stock and the source loses it, or nothing happens.
        They share a ``transfer_group`` id, which is how each side finds the
        other.
        """
        self._require_positive(quantity, "Transfer")
        if destination_location is None:
            raise ValidationError({"destination_location": "A destination location is required."})
        if destination_location.pk == self.location_id:
            raise ValidationError({"destination_location": "Source and destination location must differ."})

        with transaction.atomic():
            if request_id is not None:
                existing = SparePartTransaction.objects.filter(request_id=request_id).first()
                if existing is not None:
                    return existing, existing.other_transfer_leg

            destination, _ = SparePartInventory.objects.get_or_create(
                spare_part_type=self.spare_part_type,
                location=destination_location,
                defaults={
                    "minimum_quantity": 0,
                    "reorder_quantity": 0,
                    "storage_location_detail": "",
                },
            )
            group = uuid.uuid4()
            out_txn = self.record_movement(
                transaction_type=SparePartTransactionTypeChoices.TRANSFER,
                quantity=-quantity,
                reason=f"Transfer to {destination_location}: {reason}",
                user=user,
                notes=notes,
                request_id=request_id,
                transfer_group=group,
            )
            in_txn = destination.record_movement(
                transaction_type=SparePartTransactionTypeChoices.TRANSFER,
                quantity=quantity,
                reason=f"Transfer from {self.location}: {reason}",
                user=user,
                notes=notes,
                transfer_group=group,
            )

        return out_txn, in_txn

    @staticmethod
    def _require_positive(quantity, label):
        """Reject zero and negative quantities with a message that names the action."""
        if quantity is None or quantity <= 0:
            raise ValidationError(f"{label} quantity must be a positive whole number.")

    # --- backwards-compatible aliases ---------------------------------------

    def adjust_stock(self, quantity, transaction_type, reason, user=None, related_device=None, jira_ticket=""):
        """Deprecated. Use check_in/check_out/adjust/transfer_to instead."""
        if transaction_type not in SparePartTransactionTypeChoices.STOCK_TYPES:
            raise ValidationError(f"'{transaction_type}' does not change stock on hand.")
        return self.record_movement(
            transaction_type=transaction_type,
            quantity=quantity,
            reason=reason,
            user=user,
            related_device=related_device,
            jira_ticket=jira_ticket,
        )


class SparePartTransaction(BaseModel):
    """Append-only audit record of one stock movement."""

    spare_part_inventory = models.ForeignKey(
        SparePartInventory,
        on_delete=models.PROTECT,
        related_name="transactions",
        help_text="Inventory record this transaction affects",
    )
    transaction_type = models.CharField(
        max_length=50,
        choices=SparePartTransactionTypeChoices,
        db_index=True,
        help_text="Type of transaction",
    )
    quantity = models.IntegerField(default=0, help_text="Signed change to quantity on hand")
    reserved_delta = models.IntegerField(default=0, help_text="Signed change to reserved quantity")
    quantity_before = models.PositiveIntegerField(help_text="Quantity on hand before the movement")
    quantity_after = models.PositiveIntegerField(help_text="Quantity on hand after the movement")
    reserved_before = models.PositiveIntegerField(default=0, help_text="Reserved quantity before the movement")
    reserved_after = models.PositiveIntegerField(default=0, help_text="Reserved quantity after the movement")
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="spare_part_transactions",
        help_text="User who performed the transaction",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, help_text="When the transaction occurred")
    reason = models.TextField(help_text="Reason for the transaction")
    related_device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="spare_part_transactions",
        help_text="Device this part was fitted to or removed from",
    )
    jira_ticket = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket reference (e.g. INFRA2-1234)",
    )
    transfer_group = models.UUIDField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Shared by both legs of a transfer",
    )
    request_id = models.UUIDField(
        blank=True,
        null=True,
        unique=True,
        help_text="Client-supplied idempotency key; a repeat of the same id is ignored",
    )
    notes = models.TextField(blank=True)

    # Nautobot derives a natural key from the model's unique fields, which here
    # would be the nullable `request_id`. A transaction has no business key: it
    # is an event, identified by its id.
    natural_key_field_names = ["id"]

    class Meta:
        """Meta class for SparePartTransaction."""

        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["spare_part_inventory", "-timestamp"]),
            models.Index(fields=["transaction_type", "-timestamp"]),
        ]
        verbose_name = "Spare Part Transaction"
        verbose_name_plural = "Spare Part Transactions"

    def __str__(self):
        """String representation."""
        delta = self.quantity if self.quantity else self.reserved_delta
        return f"{self.get_transaction_type_display()} - {self.spare_part_inventory} ({delta:+d})"

    def get_absolute_url(self, api=False):
        """Return absolute URL for detail view."""
        if api:
            return reverse("plugins-api:nautobot_spare_parts-api:spareparttransaction-detail", kwargs={"pk": self.pk})
        return reverse("plugins:nautobot_spare_parts:spareparttransaction", args=[self.pk])

    @property
    def is_transfer_leg(self):
        """True when this row is one half of a transfer."""
        return self.transaction_type == SparePartTransactionTypeChoices.TRANSFER

    @property
    def other_transfer_leg(self):
        """The transaction on the other side of this transfer, if any."""
        if self.transfer_group is None:
            return None
        return (
            SparePartTransaction.objects.filter(transfer_group=self.transfer_group)
            .exclude(pk=self.pk)
            .select_related("spare_part_inventory__location")
            .first()
        )

    def clean(self):
        """Validate the audit record against the counters it claims to have moved."""
        super().clean()
        if self.quantity_before + self.quantity != self.quantity_after:
            raise ValidationError("quantity_before + quantity must equal quantity_after.")
        if self.reserved_before + self.reserved_delta != self.reserved_after:
            raise ValidationError("reserved_before + reserved_delta must equal reserved_after.")

    def save(self, *args, allow_note_update=False, **kwargs):
        """Block edits: the audit trail is append-only.

        ``allow_note_update=True`` permits a notes-only correction, which is the
        one change that cannot rewrite history.
        """
        if self.present_in_database and not allow_note_update:
            raise ValidationError(
                "Spare part transactions are an audit trail and cannot be edited. "
                "Record a correcting adjustment instead."
            )
        if self.present_in_database and allow_note_update:
            kwargs["update_fields"] = ["notes"]
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Block deletes: the audit trail is append-only."""
        raise ValidationError(
            "Spare part transactions are an audit trail and cannot be deleted. "
            "Record a correcting adjustment instead."
        )

    def set_notes(self, notes):
        """Update only the free-text notes on an existing record."""
        self.notes = notes or ""
        self.save(allow_note_update=True)


def new_request_id():
    """Fresh idempotency key for a form or API call."""
    return uuid.uuid4()
