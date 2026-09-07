"""API views for the Spare Parts Inventory app.

The six stock actions mirror the UI one-for-one, so anything that can be done
by hand can be scripted:

    POST /api/plugins/spare-parts/spare-part-inventory/<id>/check-in/
    POST /api/plugins/spare-parts/spare-part-inventory/<id>/check-out/
    POST /api/plugins/spare-parts/spare-part-inventory/<id>/adjust/
    POST /api/plugins/spare-parts/spare-part-inventory/<id>/allocate/
    POST /api/plugins/spare-parts/spare-part-inventory/<id>/deallocate/
    POST /api/plugins/spare-parts/spare-part-inventory/<id>/transfer/

Each one returns the updated inventory record plus the transaction it wrote,
takes an optional ``request_id`` idempotency key, and reports a refused
movement as 400 with the reason -- never as a partially applied change.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from nautobot.apps.api import NautobotModelViewSet, ReadOnlyModelViewSet
from nautobot.dcim.models import Device, Location

from nautobot_spare_parts import filters
from nautobot_spare_parts.api import serializers
from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType

logger = logging.getLogger(__name__)

CHANGE_PERMISSION = "nautobot_spare_parts.change_sparepartinventory"


class SparePartTypeViewSet(NautobotModelViewSet):
    """Spare part types (the catalogue)."""

    queryset = SparePartType.objects.select_related("manufacturer").prefetch_related("compatible_device_types", "tags")
    serializer_class = serializers.SparePartTypeSerializer
    filterset_class = filters.SparePartTypeFilterSet


class SparePartInventoryViewSet(NautobotModelViewSet):
    """Stock records, plus the actions that move stock."""

    queryset = SparePartInventory.annotate_available(
        SparePartInventory.objects.select_related(
            "spare_part_type",
            "spare_part_type__manufacturer",
            "location",
        ).prefetch_related("tags")
    )
    serializer_class = serializers.SparePartInventorySerializer
    filterset_class = filters.SparePartInventoryFilterSet

    # --- helpers -------------------------------------------------------------

    def _require_change_permission(self):
        """Reject callers who may read inventory but not move it."""
        if not self.request.user.has_perm(CHANGE_PERMISSION):
            raise PermissionDenied("You do not have permission to move spare part inventory.")

    def _movement_response(self, inventory, txn, message):
        """Uniform success payload for every action."""
        inventory.refresh_from_db()
        return Response(
            {
                "status": "success",
                "message": message,
                "transaction": serializers.SparePartTransactionSerializer(
                    txn, context=self.get_serializer_context()
                ).data,
                "inventory": self.get_serializer(inventory).data,
            },
            status=status.HTTP_200_OK,
        )

    def _run(self, request, body_serializer_class, apply):
        """Validate the body, apply the movement, and shape the response.

        ``apply(inventory, data)`` must return ``(transaction, message)``.
        """
        self._require_change_permission()
        inventory = self.get_object()
        body = body_serializer_class(data=request.data)
        body.is_valid(raise_exception=True)

        try:
            txn, message = apply(inventory, body.validated_data)
        except ValidationError as exc:
            return Response(
                {"status": "error", "message": "; ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ObjectDoesNotExist as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:  # noqa: BLE001 - last-resort guard, logged with traceback
            logger.exception("Unexpected error on inventory %s", inventory.pk)
            return Response(
                {"status": "error", "message": "An unexpected error occurred. Nothing was changed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return self._movement_response(inventory, txn, message)

    @staticmethod
    def _common(data):
        """Kwargs shared by every movement call."""
        return {
            "reason": data["reason"],
            "notes": data.get("notes", ""),
            "request_id": data.get("request_id"),
        }

    # --- actions -------------------------------------------------------------

    @extend_schema(request=serializers.CheckInSerializer, responses={200: None})
    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        """Add received stock."""

        def apply(inventory, data):
            txn = inventory.check_in(
                quantity=data["quantity"],
                user=request.user,
                jira_ticket=data.get("jira_ticket", ""),
                **self._common(data),
            )
            return txn, f"Checked in {data['quantity']} unit(s); {inventory.quantity_on_hand} now on hand."

        return self._run(request, serializers.CheckInSerializer, apply)

    @extend_schema(request=serializers.CheckOutSerializer, responses={200: None})
    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, pk=None):
        """Remove stock that is being used."""

        def apply(inventory, data):
            device = None
            if data.get("related_device"):
                try:
                    device = Device.objects.restrict(request.user, "view").get(pk=data["related_device"])
                except Device.DoesNotExist:
                    raise ObjectDoesNotExist(f"No device with id {data['related_device']}.")
            txn = inventory.check_out(
                quantity=data["quantity"],
                fulfil_reservation=data.get("fulfil_reservation", False),
                user=request.user,
                related_device=device,
                jira_ticket=data.get("jira_ticket", ""),
                **self._common(data),
            )
            return txn, f"Checked out {data['quantity']} unit(s); {inventory.quantity_available} still available."

        return self._run(request, serializers.CheckOutSerializer, apply)

    @extend_schema(request=serializers.AdjustmentSerializer, responses={200: None})
    @action(detail=True, methods=["post"], url_path="adjust")
    def adjust(self, request, pk=None):
        """Correct the count after a stock take."""

        def apply(inventory, data):
            txn = inventory.adjust(quantity=data["quantity"], user=request.user, **self._common(data))
            return txn, f"Adjusted by {data['quantity']:+d}; {inventory.quantity_on_hand} now on hand."

        return self._run(request, serializers.AdjustmentSerializer, apply)

    @extend_schema(request=serializers.AllocationSerializer, responses={200: None})
    @action(detail=True, methods=["post"], url_path="allocate")
    def allocate(self, request, pk=None):
        """Reserve available stock."""

        def apply(inventory, data):
            txn = inventory.allocate(
                quantity=data["quantity"],
                user=request.user,
                jira_ticket=data.get("jira_ticket", ""),
                **self._common(data),
            )
            return txn, f"Reserved {data['quantity']} unit(s); {inventory.quantity_available} still available."

        return self._run(request, serializers.AllocationSerializer, apply)

    @extend_schema(request=serializers.DeallocationSerializer, responses={200: None})
    @action(detail=True, methods=["post"], url_path="deallocate")
    def deallocate(self, request, pk=None):
        """Release a reservation."""

        def apply(inventory, data):
            txn = inventory.deallocate(quantity=data["quantity"], user=request.user, **self._common(data))
            return txn, f"Released {data['quantity']} unit(s); {inventory.quantity_reserved} still reserved."

        return self._run(request, serializers.DeallocationSerializer, apply)

    @extend_schema(request=serializers.TransferSerializer, responses={200: None})
    @action(detail=True, methods=["post"], url_path="transfer")
    def transfer(self, request, pk=None):
        """Move stock to another location."""

        def apply(inventory, data):
            try:
                destination = Location.objects.restrict(request.user, "view").get(pk=data["destination_location"])
            except Location.DoesNotExist:
                raise ObjectDoesNotExist(f"No location with id {data['destination_location']}.")
            out_txn, _in_txn = inventory.transfer_to(
                destination_location=destination,
                quantity=data["quantity"],
                user=request.user,
                **self._common(data),
            )
            return out_txn, f"Transferred {data['quantity']} unit(s) to {destination}."

        return self._run(request, serializers.TransferSerializer, apply)


class SparePartTransactionViewSet(ReadOnlyModelViewSet):
    """The audit trail. Read-only by design -- movements are created through
    the inventory actions, and existing records are never edited."""

    queryset = SparePartTransaction.objects.select_related(
        "spare_part_inventory",
        "spare_part_inventory__spare_part_type",
        "spare_part_inventory__spare_part_type__manufacturer",
        "spare_part_inventory__location",
        "user",
        "related_device",
    )
    serializer_class = serializers.SparePartTransactionSerializer
    filterset_class = filters.SparePartTransactionFilterSet
