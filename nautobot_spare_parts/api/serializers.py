"""API serializers for the Spare Parts Inventory app.

Related fields are deliberately *not* declared as nested read-only
serializers. Nautobot renders related objects itself and honours the ``?depth=``
query parameter, and leaving them alone is what keeps them writable -- a nested
``read_only=True`` serializer makes the field impossible to set, so POST and
PATCH silently stop working.
"""

from rest_framework import serializers

from nautobot.apps.api import BaseModelSerializer, NautobotModelSerializer

from nautobot_spare_parts.models import (
    JIRA_TICKET_VALIDATOR,
    SparePartInventory,
    SparePartTransaction,
    SparePartType,
)


class SparePartTypeSerializer(NautobotModelSerializer):
    """Serializer for SparePartType."""

    total_quantity_on_hand = serializers.IntegerField(read_only=True)
    part_number = serializers.CharField(max_length=100, required=False, allow_blank=True)

    class Meta:
        """Meta class for SparePartTypeSerializer."""

        model = SparePartType
        fields = "__all__"
        # DRF turns the (manufacturer, part_number) unique constraint into a
        # validator that marks both fields required, which would make it
        # impossible to create a part type without a part number. The model's
        # own clean() enforces the same rule -- with a message that names the
        # clashing part -- and the database constraint backs it up, so the
        # generated validator is redundant here.
        validators = []


class SparePartInventorySerializer(NautobotModelSerializer):
    """Serializer for SparePartInventory.

    The quantity fields are writable only on create. Afterwards they are
    read-only here as well as in the UI, because moving stock without writing a
    transaction would break the audit trail -- use the ``check-in``,
    ``check-out``, ``adjust``, ``allocate``, ``deallocate`` and ``transfer``
    actions instead.
    """

    quantity_available = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)

    class Meta:
        """Meta class for SparePartInventorySerializer."""

        model = SparePartInventory
        fields = "__all__"

    def get_fields(self):
        """Freeze identity and quantity fields once the record exists."""
        fields = super().get_fields()
        if self.instance is not None and not isinstance(self.instance, list):
            for name in ("spare_part_type", "location", "quantity_on_hand", "quantity_reserved"):
                if name in fields:
                    fields[name].read_only = True
        return fields


class SparePartTransactionSerializer(BaseModelSerializer):
    """Serializer for SparePartTransaction (read-only -- it is an audit trail)."""

    class Meta:
        """Meta class for SparePartTransactionSerializer."""

        model = SparePartTransaction
        fields = "__all__"
        read_only_fields = [
            "spare_part_inventory",
            "transaction_type",
            "quantity",
            "reserved_delta",
            "quantity_before",
            "quantity_after",
            "reserved_before",
            "reserved_after",
            "user",
            "timestamp",
            "reason",
            "related_device",
            "jira_ticket",
            "transfer_group",
            "request_id",
            "notes",
        ]


class MovementSerializer(serializers.Serializer):
    """Fields every stock action accepts."""

    quantity = serializers.IntegerField(min_value=1, help_text="Units to move. Positive whole number.")
    reason = serializers.CharField(help_text="Why -- goes into the audit trail. Required.")
    notes = serializers.CharField(required=False, allow_blank=True, help_text="Free-text notes")
    request_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text=(
            "Idempotency key. Send the same UUID again and the original transaction is returned "
            "instead of the movement being applied twice. Strongly recommended for retried calls."
        ),
    )

    def validate_reason(self, value):
        """Reject whitespace-only reasons."""
        if not value.strip():
            raise serializers.ValidationError("A reason is required.")
        return value.strip()


class CheckInSerializer(MovementSerializer):
    """Body for the check-in action."""

    jira_ticket = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket reference (e.g. INFRA2-1234)",
    )


class CheckOutSerializer(MovementSerializer):
    """Body for the check-out action."""

    related_device = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID of the device the part is going into",
    )
    fulfil_reservation = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Take the units out of the reserved pool, releasing the reservation as well",
    )
    jira_ticket = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket reference (e.g. INFRA2-1234)",
    )


class AdjustmentSerializer(MovementSerializer):
    """Body for the adjust action -- the one place a signed quantity is allowed."""

    quantity = serializers.IntegerField(
        help_text="Signed correction: 3 adds three units, -3 removes three. 0 is rejected."
    )

    def validate_quantity(self, value):
        """Reject a no-op adjustment."""
        if value == 0:
            raise serializers.ValidationError("An adjustment of 0 changes nothing.")
        return value


class AllocationSerializer(MovementSerializer):
    """Body for the allocate action."""

    jira_ticket = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[JIRA_TICKET_VALIDATOR],
        help_text="Jira ticket the stock is reserved for (e.g. INFRA2-1234)",
    )


class DeallocationSerializer(MovementSerializer):
    """Body for the deallocate action."""


class TransferSerializer(MovementSerializer):
    """Body for the transfer action."""

    destination_location = serializers.UUIDField(help_text="UUID of the destination location")
