"""API views for Spare Parts Inventory plugin."""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from nautobot.apps.api import NautobotModelViewSet
from nautobot.dcim.models import Device

from nautobot_spare_parts import filters
from nautobot_spare_parts.api import serializers
from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType


class SparePartTypeViewSet(NautobotModelViewSet):
    """API viewset for SparePartType."""

    queryset = SparePartType.objects.all()
    serializer_class = serializers.SparePartTypeSerializer
    filterset_class = filters.SparePartTypeFilterSet


class SparePartInventoryViewSet(NautobotModelViewSet):
    """API viewset for SparePartInventory."""

    queryset = SparePartInventory.objects.select_related(
        "spare_part_type",
        "spare_part_type__manufacturer",
        "location",
    )
    serializer_class = serializers.SparePartInventorySerializer
    filterset_class = filters.SparePartInventoryFilterSet

    @action(detail=True, methods=["post"])
    def check_in(self, request, pk=None):
        """Check in spare parts (add stock)."""
        inventory = self.get_object()
        serializer = serializers.CheckInSerializer(data=request.data)

        if serializer.is_valid():
            quantity = serializer.validated_data["quantity"]
            reason = serializer.validated_data["reason"]
            notes = serializer.validated_data.get("notes", "")

            try:
                inventory.adjust_stock(
                    quantity=quantity,
                    transaction_type="check_in",
                    reason=reason,
                    user=request.user,
                )
                if notes:
                    # Add notes to the most recent transaction
                    transaction = inventory.transactions.first()
                    transaction.notes = notes
                    transaction.save()

                return Response(
                    {
                        "status": "success",
                        "message": f"Checked in {quantity} units",
                        "inventory": serializers.SparePartInventorySerializer(
                            inventory, context={"request": request}
                        ).data,
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"status": "error", "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def check_out(self, request, pk=None):
        """Check out spare parts (remove stock)."""
        inventory = self.get_object()
        serializer = serializers.CheckOutSerializer(data=request.data)

        if serializer.is_valid():
            quantity = serializer.validated_data["quantity"]
            reason = serializer.validated_data["reason"]
            related_device_id = serializer.validated_data.get("related_device_id")
            notes = serializer.validated_data.get("notes", "")

            related_device = None
            if related_device_id:
                try:
                    related_device = Device.objects.get(pk=related_device_id)
                except Device.DoesNotExist:
                    return Response(
                        {"status": "error", "message": "Device not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

            try:
                inventory.adjust_stock(
                    quantity=-quantity,
                    transaction_type="check_out",
                    reason=reason,
                    user=request.user,
                    related_device=related_device,
                )
                if notes:
                    # Add notes to the most recent transaction
                    transaction = inventory.transactions.first()
                    transaction.notes = notes
                    transaction.save()

                return Response(
                    {
                        "status": "success",
                        "message": f"Checked out {quantity} units",
                        "inventory": serializers.SparePartInventorySerializer(
                            inventory, context={"request": request}
                        ).data,
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"status": "error", "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        """Adjust inventory (correction)."""
        inventory = self.get_object()
        serializer = serializers.AdjustmentSerializer(data=request.data)

        if serializer.is_valid():
            quantity = serializer.validated_data["quantity"]
            reason = serializer.validated_data["reason"]
            notes = serializer.validated_data.get("notes", "")

            try:
                inventory.adjust_stock(
                    quantity=quantity,
                    transaction_type="adjustment",
                    reason=reason,
                    user=request.user,
                )
                if notes:
                    # Add notes to the most recent transaction
                    transaction = inventory.transactions.first()
                    transaction.notes = notes
                    transaction.save()

                return Response(
                    {
                        "status": "success",
                        "message": f"Adjusted inventory by {quantity:+d} units",
                        "inventory": serializers.SparePartInventorySerializer(
                            inventory, context={"request": request}
                        ).data,
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"status": "error", "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SparePartTransactionViewSet(NautobotModelViewSet):
    """API viewset for SparePartTransaction (read-only)."""

    queryset = SparePartTransaction.objects.select_related(
        "spare_part_inventory",
        "spare_part_inventory__spare_part_type",
        "spare_part_inventory__location",
        "user",
        "related_device",
    )
    serializer_class = serializers.SparePartTransactionSerializer
    filterset_class = filters.SparePartTransactionFilterSet
    http_method_names = ["get", "head", "options"]  # Read-only
