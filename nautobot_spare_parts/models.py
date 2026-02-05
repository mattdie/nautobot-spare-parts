"""Data models for Spare Parts Inventory plugin."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from nautobot.apps.models import PrimaryModel, BaseModel
from nautobot.dcim.models import Device, DeviceType, Location, Manufacturer
from nautobot.extras.utils import extras_features


User = get_user_model()


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
    """Template/definition for types of spare parts."""

    CATEGORY_CHOICES = (
        ("ram", "RAM"),
        ("cable", "Cable"),
        ("transceiver", "Transceiver"),
        ("psu", "PSU"),
        ("hdd", "HDD"),
        ("ssd", "SSD"),
        ("nic", "NIC"),
        ("fan", "Fan"),
        ("motherboard", "Motherboard"),
        ("cpu", "CPU"),
        ("other", "Other"),
    )

    name = models.CharField(max_length=100, help_text="Display name for the spare part type")
    slug = models.SlugField(max_length=100, unique=True)
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
        help_text="Manufacturer part number",
    )
    description = models.TextField(blank=True, help_text="Detailed description of the part")
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="other",
        help_text="Category of spare part",
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
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

        ordering = ["category", "manufacturer", "name"]
        unique_together = [["manufacturer", "part_number"]]
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
        if self.part_number and not self.manufacturer:
            raise ValidationError({"manufacturer": "Manufacturer is required when part number is specified"})

    def get_total_quantity(self):
        """Get total quantity across all locations."""
        return self.inventory_records.aggregate(total=models.Sum("quantity_on_hand"))["total"] or 0

    def get_locations_with_stock(self):
        """Get list of locations that have this part in stock."""
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
    """Track actual spare parts inventory at specific locations."""

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
        help_text="Current stock level",
    )
    quantity_reserved = models.PositiveIntegerField(
        default=0,
        help_text="Parts reserved for allocation",
    )
    minimum_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Reorder threshold - alerts when stock falls below this level",
    )
    reorder_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Suggested quantity to reorder",
    )
    storage_location_detail = models.CharField(
        max_length=100,
        blank=True,
        help_text="Specific storage location (e.g., Rack A, Shelf 3)",
    )
    notes = models.TextField(blank=True)

    class Meta:
        """Meta class for SparePartInventory."""

        ordering = ["location", "spare_part_type"]
        unique_together = [["spare_part_type", "location"]]
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

    @property
    def quantity_available(self):
        """Compute available quantity (on hand minus reserved)."""
        return self.quantity_on_hand - self.quantity_reserved

    @property
    def is_low_stock(self):
        """Check if inventory is at or below minimum quantity."""
        return self.quantity_available <= self.minimum_quantity

    @property
    def needs_reorder(self):
        """Check if part needs to be reordered."""
        return self.is_low_stock and self.reorder_quantity > 0

    def clean(self):
        """Validate model data."""
        super().clean()
        if self.quantity_reserved > self.quantity_on_hand:
            raise ValidationError(
                {"quantity_reserved": "Reserved quantity cannot exceed quantity on hand"}
            )
        if self.quantity_on_hand < 0:
            raise ValidationError({"quantity_on_hand": "Quantity on hand cannot be negative"})
        if self.quantity_reserved < 0:
            raise ValidationError({"quantity_reserved": "Reserved quantity cannot be negative"})

    def allocate(self, quantity, reason, user=None):
        """Reserve parts for use."""
        if quantity <= 0:
            raise ValidationError("Allocation quantity must be positive")
        if self.quantity_available < quantity:
            raise ValidationError(
                f"Cannot allocate {quantity} units. Only {self.quantity_available} available."
            )

        quantity_before = self.quantity_reserved
        self.quantity_reserved += quantity
        self.validated_save()

        # Create transaction record
        SparePartTransaction.objects.create(
            spare_part_inventory=self,
            transaction_type="allocation",
            quantity=quantity,
            quantity_before=quantity_before,
            quantity_after=self.quantity_reserved,
            user=user,
            reason=reason,
        )

        return self

    def deallocate(self, quantity, reason, user=None):
        """Release reserved parts."""
        if quantity <= 0:
            raise ValidationError("Deallocation quantity must be positive")
        if self.quantity_reserved < quantity:
            raise ValidationError(
                f"Cannot deallocate {quantity} units. Only {self.quantity_reserved} reserved."
            )

        quantity_before = self.quantity_reserved
        self.quantity_reserved -= quantity
        self.validated_save()

        # Create transaction record
        SparePartTransaction.objects.create(
            spare_part_inventory=self,
            transaction_type="deallocation",
            quantity=-quantity,
            quantity_before=quantity_before,
            quantity_after=self.quantity_reserved,
            user=user,
            reason=reason,
        )

        return self

    def adjust_stock(self, quantity, transaction_type, reason, user=None, related_device=None):
        """Modify stock levels and create transaction record."""
        if transaction_type not in ["check_in", "check_out", "adjustment"]:
            raise ValidationError("Invalid transaction type for stock adjustment")

        quantity_before = self.quantity_on_hand
        new_quantity = quantity_before + quantity

        if new_quantity < 0:
            raise ValidationError(
                f"Cannot adjust stock by {quantity}. Would result in negative inventory."
            )

        self.quantity_on_hand = new_quantity
        self.validated_save()

        # Create transaction record
        SparePartTransaction.objects.create(
            spare_part_inventory=self,
            transaction_type=transaction_type,
            quantity=quantity,
            quantity_before=quantity_before,
            quantity_after=self.quantity_on_hand,
            user=user,
            reason=reason,
            related_device=related_device,
        )

        return self


class SparePartTransaction(BaseModel):
    """Audit trail for all stock movements."""

    TRANSACTION_TYPE_CHOICES = (
        ("check_in", "Check In"),
        ("check_out", "Check Out"),
        ("adjustment", "Adjustment"),
        ("allocation", "Allocation"),
        ("deallocation", "Deallocation"),
        ("transfer", "Transfer"),
    )

    spare_part_inventory = models.ForeignKey(
        SparePartInventory,
        on_delete=models.PROTECT,
        related_name="transactions",
        help_text="Inventory record this transaction affects",
    )
    transaction_type = models.CharField(
        max_length=50,
        choices=TRANSACTION_TYPE_CHOICES,
        help_text="Type of transaction",
    )
    quantity = models.IntegerField(help_text="Amount changed (positive or negative)")
    quantity_before = models.PositiveIntegerField(help_text="Stock level before transaction")
    quantity_after = models.PositiveIntegerField(help_text="Stock level after transaction")
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="spare_part_transactions",
        help_text="User who performed the transaction",
    )
    timestamp = models.DateTimeField(auto_now_add=True, help_text="When the transaction occurred")
    reason = models.TextField(help_text="Reason for the transaction")
    related_device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="spare_part_transactions",
        help_text="Device associated with this transaction",
    )
    notes = models.TextField(blank=True)

    class Meta:
        """Meta class for SparePartTransaction."""

        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["spare_part_inventory", "timestamp"]),
            models.Index(fields=["transaction_type"]),
        ]
        verbose_name = "Spare Part Transaction"
        verbose_name_plural = "Spare Part Transactions"

    def __str__(self):
        """String representation."""
        return f"{self.get_transaction_type_display()} - {self.spare_part_inventory} ({self.quantity:+d})"

    def get_absolute_url(self, api=False):
        """Return absolute URL for detail view."""
        if api:
            return reverse("plugins-api:nautobot_spare_parts-api:spareparttransaction-detail", kwargs={"pk": self.pk})
        return reverse("plugins:nautobot_spare_parts:spareparttransaction", args=[self.pk])
