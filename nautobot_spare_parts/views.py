"""Views for Spare Parts Inventory plugin."""

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import View

from nautobot.apps.views import (
    NautobotUIViewSet,
    ObjectDetailViewMixin,
)

from nautobot_spare_parts import filters, forms, tables
from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType


class SparePartTypeUIViewSet(NautobotUIViewSet):
    """ViewSet for SparePartType."""

    queryset = SparePartType.objects.all()
    filterset_class = filters.SparePartTypeFilterSet
    filterset_form_class = forms.SparePartTypeFilterForm
    form_class = forms.SparePartTypeForm
    serializer_class = None  # Will be defined in API views
    table_class = tables.SparePartTypeTable
    bulk_update_form_class = forms.SparePartTypeBulkEditForm

    def get_extra_context(self, request, instance=None):
        """Add extra context for detail view."""
        context = super().get_extra_context(request, instance)
        if instance:
            # Add inventory records for this part type
            context["inventory_records"] = SparePartInventory.objects.filter(
                spare_part_type=instance
            ).select_related("location")
        return context


class SparePartInventoryUIViewSet(NautobotUIViewSet):
    """ViewSet for SparePartInventory."""

    queryset = SparePartInventory.objects.select_related(
        "spare_part_type",
        "spare_part_type__manufacturer",
        "location",
    )
    filterset_class = filters.SparePartInventoryFilterSet
    filterset_form_class = forms.SparePartInventoryFilterForm
    form_class = forms.SparePartInventoryForm
    serializer_class = None  # Will be defined in API views
    table_class = tables.SparePartInventoryTable
    bulk_update_form_class = forms.SparePartInventoryBulkEditForm

    def get_extra_context(self, request, instance=None):
        """Add extra context for detail view."""
        context = super().get_extra_context(request, instance)
        if instance:
            # Add recent transactions for this inventory
            context["recent_transactions"] = instance.transactions.all()[:20]

            # Add Check In and Check Out button URLs
            context["check_in_url"] = reverse(
                "plugins:nautobot_spare_parts:sparepartinventory_checkin",
                kwargs={"pk": instance.pk}
            )
            context["check_out_url"] = reverse(
                "plugins:nautobot_spare_parts:sparepartinventory_checkout",
                kwargs={"pk": instance.pk}
            )
        return context


class SparePartTransactionUIViewSet(NautobotUIViewSet):
    """ViewSet for SparePartTransaction (read-only)."""

    queryset = SparePartTransaction.objects.select_related(
        "spare_part_inventory",
        "spare_part_inventory__spare_part_type",
        "spare_part_inventory__location",
        "user",
        "related_device",
    )
    filterset_class = filters.SparePartTransactionFilterSet
    filterset_form_class = None
    form_class = None
    serializer_class = None  # Will be defined in API views
    table_class = tables.SparePartTransactionTable

    # Make this viewset read-only
    action_buttons = ("export",)


class CheckInView(PermissionRequiredMixin, View):
    """View for checking in spare parts (adding stock)."""

    permission_required = "nautobot_spare_parts.change_sparepartinventory"

    def get(self, request, pk):
        """Display check-in form."""
        inventory = get_object_or_404(SparePartInventory, pk=pk)
        form = forms.CheckInForm()
        return render(
            request,
            "nautobot_spare_parts/sparepartinventory_checkin.html",
            {
                "inventory": inventory,
                "form": form,
                "action": "Check In",
            },
        )

    def post(self, request, pk):
        """Process check-in form."""
        inventory = get_object_or_404(SparePartInventory, pk=pk)
        form = forms.CheckInForm(request.POST)

        if form.is_valid():
            quantity = form.cleaned_data["quantity"]
            reason = form.cleaned_data["reason"]
            notes = form.cleaned_data.get("notes", "")

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

                messages.success(
                    request,
                    f"Checked in {quantity} units of {inventory.spare_part_type}",
                )
                return redirect(inventory.get_absolute_url())
            except Exception as e:
                messages.error(request, f"Error checking in inventory: {str(e)}")

        return render(
            request,
            "nautobot_spare_parts/sparepartinventory_checkin.html",
            {
                "inventory": inventory,
                "form": form,
                "action": "Check In",
            },
        )


class CheckOutView(PermissionRequiredMixin, View):
    """View for checking out spare parts (removing stock)."""

    permission_required = "nautobot_spare_parts.change_sparepartinventory"

    def get(self, request, pk):
        """Display check-out form."""
        inventory = get_object_or_404(SparePartInventory, pk=pk)
        form = forms.CheckOutForm()
        return render(
            request,
            "nautobot_spare_parts/sparepartinventory_checkout.html",
            {
                "inventory": inventory,
                "form": form,
                "action": "Check Out",
            },
        )

    def post(self, request, pk):
        """Process check-out form."""
        inventory = get_object_or_404(SparePartInventory, pk=pk)
        form = forms.CheckOutForm(request.POST)

        if form.is_valid():
            quantity = form.cleaned_data["quantity"]
            reason = form.cleaned_data["reason"]
            related_device = form.cleaned_data.get("related_device")
            notes = form.cleaned_data.get("notes", "")

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

                messages.success(
                    request,
                    f"Checked out {quantity} units of {inventory.spare_part_type}",
                )
                return redirect(inventory.get_absolute_url())
            except Exception as e:
                messages.error(request, f"Error checking out inventory: {str(e)}")

        return render(
            request,
            "nautobot_spare_parts/sparepartinventory_checkout.html",
            {
                "inventory": inventory,
                "form": form,
                "action": "Check Out",
            },
        )


class LowStockDashboardView(PermissionRequiredMixin, View):
    """Dashboard view for low stock items."""

    permission_required = "nautobot_spare_parts.view_sparepartinventory"
    template_name = "nautobot_spare_parts/low_stock_dashboard.html"

    def get(self, request):
        """Display low stock dashboard."""
        # Filter where quantity_available <= minimum_quantity
        queryset = SparePartInventory.objects.select_related(
            "spare_part_type",
            "spare_part_type__manufacturer",
            "location",
        ).filter(
            quantity_on_hand__lte=F("minimum_quantity") + F("quantity_reserved")
        )

        table = tables.LowStockTable(queryset)

        return render(
            request,
            self.template_name,
            {
                "table": table,
                "low_stock_count": queryset.count(),
            },
        )
