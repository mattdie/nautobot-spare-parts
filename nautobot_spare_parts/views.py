"""Views for the Spare Parts Inventory app.

The three record types use Nautobot's UI component framework
(``object_detail_content``) rather than hand-written templates, so their detail
pages are built from the same panels, buttons and tabs as core Nautobot pages
and pick up table config, pagination and permission handling for free.

The six stock actions are custom pages, because they are forms over a domain
operation rather than plain object edits. They all share one base class,
:class:`InventoryActionView`, so the whole set behaves the same way: the same
permission check, the same object lookup, the same "form errors come back on
the form, movement errors come back as a message" handling, and the same
redirect on success.
"""

import csv
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django_tables2 import RequestConfig

from nautobot.apps.ui import (
    Button,
    DropdownButton,
    ObjectDetailContent,
    ObjectFieldsPanel,
    ObjectsTablePanel,
    SectionChoices,
)
from nautobot.apps.views import GenericView, NautobotUIViewSet, ObjectPermissionRequiredMixin
from nautobot.dcim.models import Device
from nautobot.dcim.tables import DeviceTypeTable
from nautobot.core.views.paginator import EnhancedPaginator, get_paginate_count

from nautobot_spare_parts import filters, forms, tables
from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType

logger = logging.getLogger(__name__)

CHANGE_INVENTORY = "nautobot_spare_parts.change_sparepartinventory"
VIEW_INVENTORY = "nautobot_spare_parts.view_sparepartinventory"

#: The six stock actions, as detail-page buttons. Check In and Check Out are the
#: everyday ones and get their own buttons; the rest live in a dropdown, which is
#: how core Nautobot handles a long action list.
PRIMARY_ACTION_BUTTONS = (
    ("sparepartinventory_checkin", "Check In", "success", "mdi-plus-box"),
    ("sparepartinventory_checkout", "Check Out", "warning", "mdi-minus-box"),
)
SECONDARY_ACTION_BUTTONS = (
    ("sparepartinventory_allocate", "Allocate", "mdi-bookmark-plus"),
    ("sparepartinventory_deallocate", "Deallocate", "mdi-bookmark-minus"),
    ("sparepartinventory_transfer", "Transfer", "mdi-swap-horizontal"),
    ("sparepartinventory_adjust", "Adjust", "mdi-tune"),
)


def _paginate(request, table):
    """Apply Nautobot's paginator to a table built in get_extra_context."""
    RequestConfig(
        request,
        {"paginator_class": EnhancedPaginator, "per_page": get_paginate_count(request)},
    ).configure(table)
    return table


class SparePartTypeUIViewSet(NautobotUIViewSet):
    """ViewSet for SparePartType."""

    queryset = SparePartType.objects.select_related("manufacturer").annotate(
        total_quantity=Coalesce(Sum("inventory_records__quantity_on_hand"), Value(0)),
        location_count=Count("inventory_records__location", distinct=True),
    )
    filterset_class = filters.SparePartTypeFilterSet
    filterset_form_class = forms.SparePartTypeFilterForm
    form_class = forms.SparePartTypeForm
    serializer_class = None  # UI ViewSets render templates, not serializers.
    table_class = tables.SparePartTypeTable
    bulk_update_form_class = forms.SparePartTypeBulkEditForm

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                label="Spare Part Type",
                section=SectionChoices.LEFT_HALF,
                weight=100,
                fields=[
                    "name",
                    "manufacturer",
                    "part_number",
                    "category",
                    "unit_cost",
                    "description",
                ],
            ),
            ObjectsTablePanel(
                section=SectionChoices.LEFT_HALF,
                weight=200,
                table_title="Compatible Device Types",
                context_table_key="device_type_table",
                add_button_route=None,
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF,
                weight=100,
                table_title="Stocked At",
                context_table_key="inventory_table",
                related_field_name="spare_part_type",
            ),
        ),
    )

    def get_extra_context(self, request, instance=None):
        """Build the tables the detail panels render."""
        context = super().get_extra_context(request, instance)
        if self.action == "retrieve" and instance is not None:
            records = SparePartInventory.annotate_available(
                SparePartInventory.objects.restrict(request.user, "view")
                .filter(spare_part_type=instance)
                .select_related("location")
            )
            context["inventory_table"] = _paginate(request, tables.SparePartTypeInventoryTable(records))
            context["device_type_table"] = DeviceTypeTable(
                instance.compatible_device_types.restrict(request.user, "view").select_related("manufacturer")
            )
            context["total_on_hand"] = instance.total_quantity_on_hand
        return context


class SparePartInventoryUIViewSet(NautobotUIViewSet):
    """ViewSet for SparePartInventory."""

    queryset = SparePartInventory.annotate_available(
        SparePartInventory.objects.select_related(
            "spare_part_type",
            "spare_part_type__manufacturer",
            "location",
        )
    )
    filterset_class = filters.SparePartInventoryFilterSet
    filterset_form_class = forms.SparePartInventoryFilterForm
    form_class = forms.SparePartInventoryForm
    serializer_class = None
    table_class = tables.SparePartInventoryTable
    bulk_update_form_class = forms.SparePartInventoryBulkEditForm

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                label="Stock",
                section=SectionChoices.LEFT_HALF,
                weight=100,
                fields=[
                    "spare_part_type",
                    "location",
                    "storage_location_detail",
                    "quantity_on_hand",
                    "quantity_reserved",
                    "quantity_available",
                    "minimum_quantity",
                    "reorder_quantity",
                    "is_low_stock",
                    "needs_reorder",
                    "notes",
                ],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF,
                weight=100,
                table_title="Movements",
                context_table_key="transaction_table",
                related_field_name="spare_part_inventory",
                related_list_url_name="plugins:nautobot_spare_parts:spareparttransaction_list",
                # Movements are only ever written by a stock action, so the
                # panel's built-in "Add" button would be a dead end.
                add_button_route=None,
            ),
        ),
        extra_buttons=(
            *(
                Button(
                    weight=(index + 1) * 100,
                    label=label,
                    color=color,
                    icon=icon,
                    link_name=f"plugins:nautobot_spare_parts:{url_name}",
                    required_permissions=[CHANGE_INVENTORY],
                )
                for index, (url_name, label, color, icon) in enumerate(PRIMARY_ACTION_BUTTONS)
            ),
            DropdownButton(
                weight=300,
                label="Reserve / Move",
                color="primary",
                icon="mdi-tune",
                required_permissions=[CHANGE_INVENTORY],
                children=tuple(
                    Button(
                        weight=(index + 1) * 100,
                        label=label,
                        icon=icon,
                        link_name=f"plugins:nautobot_spare_parts:{url_name}",
                        required_permissions=[CHANGE_INVENTORY],
                    )
                    for index, (url_name, label, icon) in enumerate(SECONDARY_ACTION_BUTTONS)
                ),
            ),
        ),
    )

    def get_extra_context(self, request, instance=None):
        """Build the movements table the detail panel renders."""
        context = super().get_extra_context(request, instance)
        if self.action == "retrieve" and instance is not None:
            transactions = instance.transactions.restrict(request.user, "view").select_related(
                "user", "related_device", "spare_part_inventory__spare_part_type"
            )
            table = tables.SparePartTransactionTable(transactions)
            table.columns.hide("spare_part_inventory")
            context["transaction_table"] = _paginate(request, table)
        return context


class SparePartTransactionUIViewSet(NautobotUIViewSet):
    """Read-only ViewSet for the audit trail."""

    queryset = SparePartTransaction.objects.select_related(
        "spare_part_inventory",
        "spare_part_inventory__spare_part_type",
        "spare_part_inventory__spare_part_type__manufacturer",
        "spare_part_inventory__location",
        "user",
        "related_device",
    )
    filterset_class = filters.SparePartTransactionFilterSet
    filterset_form_class = forms.SparePartTransactionFilterForm
    form_class = None
    serializer_class = None
    table_class = tables.SparePartTransactionTable
    action_buttons = ("export",)

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                label="Movement",
                section=SectionChoices.LEFT_HALF,
                weight=100,
                fields=[
                    "timestamp",
                    "transaction_type",
                    "spare_part_inventory",
                    "user",
                    "related_device",
                    "jira_ticket",
                    "reason",
                    "notes",
                ],
            ),
            ObjectFieldsPanel(
                label="Counters",
                section=SectionChoices.RIGHT_HALF,
                weight=100,
                fields=[
                    "quantity_before",
                    "quantity",
                    "quantity_after",
                    "reserved_before",
                    "reserved_delta",
                    "reserved_after",
                ],
            ),
            ObjectFieldsPanel(
                label="Transfer",
                section=SectionChoices.RIGHT_HALF,
                weight=200,
                # "other_transfer_leg" is a property rather than a model field;
                # ObjectFieldsPanel renders either, but additional_fields is
                # only allowed alongside fields="__all__", so list it here.
                fields=["transfer_group", "other_transfer_leg"],
            ),
        ),
    )


def _action_urls(inventory):
    """Named URLs for every action available on an inventory record."""
    names = {
        "check_in": ("sparepartinventory_checkin", "Check In"),
        "check_out": ("sparepartinventory_checkout", "Check Out"),
        "allocate": ("sparepartinventory_allocate", "Allocate"),
        "deallocate": ("sparepartinventory_deallocate", "Deallocate"),
        "adjust": ("sparepartinventory_adjust", "Adjust"),
        "transfer": ("sparepartinventory_transfer", "Transfer"),
    }
    return {
        key: {
            "url": reverse(f"plugins:nautobot_spare_parts:{url_name}", args=[inventory.pk]),
            "label": label,
        }
        for key, (url_name, label) in names.items()
    }


class InventoryActionView(ObjectPermissionRequiredMixin, GenericView):
    """Base class for the single-record stock actions.

    Subclasses set :attr:`form_class`, :attr:`template_name`, :attr:`action`
    and implement :meth:`perform`.
    """

    queryset = SparePartInventory.objects.select_related("spare_part_type", "location")
    form_class = None
    template_name = None
    action = None
    #: Set on subclasses whose form needs to know the record it acts on.
    form_needs_inventory = True

    def get_required_permission(self):
        """Every stock action is a change to the inventory record."""
        return CHANGE_INVENTORY

    def get_inventory(self, request, pk):
        """Fetch the record, honouring Nautobot object-level permissions."""
        return get_object_or_404(self.queryset.restrict(request.user, "change"), pk=pk)

    def build_form(self, inventory, data=None):
        """Instantiate the action form."""
        kwargs = {"inventory": inventory} if self.form_needs_inventory else {}
        return self.form_class(data, **kwargs) if data is not None else self.form_class(**kwargs)

    def render_form(self, request, inventory, form):
        """Render the action page."""
        return render(
            request,
            self.template_name,
            {
                "object": inventory,
                "inventory": inventory,
                "form": form,
                "action": self.action,
                "action_urls": _action_urls(inventory),
                "return_url": inventory.get_absolute_url(),
            },
        )

    def get(self, request, pk):
        """Show the form."""
        inventory = self.get_inventory(request, pk)
        return self.render_form(request, inventory, self.build_form(inventory))

    def post(self, request, pk):
        """Validate and apply the movement."""
        inventory = self.get_inventory(request, pk)
        form = self.build_form(inventory, request.POST)

        if form.is_valid():
            try:
                message = self.perform(request, inventory, form.cleaned_data)
            except ValidationError as exc:
                for text in exc.messages:
                    messages.error(request, text)
            except Exception:  # noqa: BLE001 - last-resort guard, logged with traceback
                logger.exception("Unexpected error during %s on inventory %s", self.action, inventory.pk)
                messages.error(
                    request,
                    f"{self.action} failed unexpectedly. Nothing was changed. "
                    "Check the Nautobot logs for the full error.",
                )
            else:
                messages.success(request, message)
                return redirect(inventory.get_absolute_url())

        return self.render_form(request, inventory, form)

    def perform(self, request, inventory, data):
        """Apply the movement and return the success message."""
        raise NotImplementedError


class CheckInView(InventoryActionView):
    """Add received stock."""

    form_class = forms.CheckInForm
    template_name = "nautobot_spare_parts/sparepartinventory_checkin.html"
    action = "Check In"
    form_needs_inventory = False

    def perform(self, request, inventory, data):
        """Record the check-in."""
        inventory.check_in(
            quantity=data["quantity"],
            reason=data["reason"],
            user=request.user,
            jira_ticket=data.get("jira_ticket", ""),
            notes=data.get("notes", ""),
            request_id=data.get("request_id"),
        )
        return (
            f"Checked in {data['quantity']}x {inventory.spare_part_type} at {inventory.location}. "
            f"Now {inventory.quantity_on_hand} on hand."
        )


class CheckOutView(InventoryActionView):
    """Remove stock that is being consumed."""

    form_class = forms.CheckOutForm
    template_name = "nautobot_spare_parts/sparepartinventory_checkout.html"
    action = "Check Out"

    def perform(self, request, inventory, data):
        """Record the check-out."""
        inventory.check_out(
            quantity=data["quantity"],
            reason=data["reason"],
            fulfil_reservation=data.get("fulfil_reservation", False),
            user=request.user,
            related_device=data.get("related_device"),
            jira_ticket=data.get("jira_ticket", ""),
            notes=data.get("notes", ""),
            request_id=data.get("request_id"),
        )
        return (
            f"Checked out {data['quantity']}x {inventory.spare_part_type} from {inventory.location}. "
            f"{inventory.quantity_available} still available."
        )


class AllocationView(InventoryActionView):
    """Reserve available stock."""

    form_class = forms.AllocationForm
    template_name = "nautobot_spare_parts/sparepartinventory_allocate.html"
    action = "Allocate"

    def perform(self, request, inventory, data):
        """Record the allocation."""
        inventory.allocate(
            quantity=data["quantity"],
            reason=data["reason"],
            user=request.user,
            jira_ticket=data.get("jira_ticket", ""),
            notes=data.get("notes", ""),
            request_id=data.get("request_id"),
        )
        return (
            f"Reserved {data['quantity']}x {inventory.spare_part_type} at {inventory.location}. "
            f"{inventory.quantity_available} still available."
        )


class DeallocationView(InventoryActionView):
    """Release a reservation."""

    form_class = forms.DeallocationForm
    template_name = "nautobot_spare_parts/sparepartinventory_deallocate.html"
    action = "Deallocate"

    def perform(self, request, inventory, data):
        """Record the deallocation."""
        inventory.deallocate(
            quantity=data["quantity"],
            reason=data["reason"],
            user=request.user,
            notes=data.get("notes", ""),
            request_id=data.get("request_id"),
        )
        return (
            f"Released {data['quantity']}x {inventory.spare_part_type} at {inventory.location}. "
            f"{inventory.quantity_reserved} still reserved."
        )


class AdjustmentView(InventoryActionView):
    """Correct a count after a stock take."""

    form_class = forms.AdjustmentForm
    template_name = "nautobot_spare_parts/sparepartinventory_adjustment.html"
    action = "Adjust"
    form_needs_inventory = False

    def perform(self, request, inventory, data):
        """Record the adjustment."""
        inventory.adjust(
            quantity=data["quantity"],
            reason=data["reason"],
            user=request.user,
            notes=data.get("notes", ""),
            request_id=data.get("request_id"),
        )
        return (
            f"Adjusted {inventory.spare_part_type} at {inventory.location} by {data['quantity']:+d}. "
            f"Now {inventory.quantity_on_hand} on hand."
        )


class TransferView(InventoryActionView):
    """Move stock to another location."""

    form_class = forms.TransferForm
    template_name = "nautobot_spare_parts/sparepartinventory_transfer.html"
    action = "Transfer"

    def perform(self, request, inventory, data):
        """Record both legs of the transfer."""
        inventory.transfer_to(
            destination_location=data["destination_location"],
            quantity=data["quantity"],
            reason=data["reason"],
            user=request.user,
            notes=data.get("notes", ""),
            request_id=data.get("request_id"),
        )
        return (
            f"Transferred {data['quantity']}x {inventory.spare_part_type} from {inventory.location} "
            f"to {data['destination_location']}."
        )


class BulkReceiveView(ObjectPermissionRequiredMixin, GenericView):
    """Check in several part types at once from one shipment.

    All lines are applied in a single database transaction: if any line fails,
    nothing is received. Partially receiving a shipment and reporting an error
    at the same time is the worst of both worlds.
    """

    queryset = SparePartInventory.objects.all()
    template_name = "nautobot_spare_parts/sparepartinventory_bulk_receive.html"

    def get_required_permission(self):
        """Bulk receive changes inventory records."""
        return CHANGE_INVENTORY

    def render_page(self, request, header_form, formset):
        """Render the bulk receive page."""
        return render(
            request,
            self.template_name,
            {
                "header_form": header_form,
                "formset": formset,
                "return_url": reverse("plugins:nautobot_spare_parts:sparepartinventory_list"),
            },
        )

    def get(self, request):
        """Show empty lines."""
        return self.render_page(request, forms.BulkReceiveHeaderForm(), forms.BulkReceiveFormSet())

    def post(self, request):
        """Apply every line, or none of them."""
        header_form = forms.BulkReceiveHeaderForm(request.POST)
        formset = forms.BulkReceiveFormSet(request.POST)

        if header_form.is_valid() and formset.is_valid():
            lines = [
                form.cleaned_data
                for form in formset
                if form.cleaned_data.get("inventory") and not form.cleaned_data.get("DELETE")
            ]
            try:
                received = self._receive(request, header_form.cleaned_data, lines)
            except ValidationError as exc:
                for text in exc.messages:
                    messages.error(request, text)
            except Exception:  # noqa: BLE001
                logger.exception("Unexpected error during bulk receive")
                messages.error(
                    request,
                    "Bulk receive failed unexpectedly. Nothing was received. "
                    "Check the Nautobot logs for the full error.",
                )
            else:
                messages.success(
                    request,
                    f"Received {len(received)} line(s): " + ", ".join(received),
                )
                return redirect(reverse("plugins:nautobot_spare_parts:sparepartinventory_list"))

        return self.render_page(request, header_form, formset)

    @staticmethod
    def _receive(request, header, lines):
        """Apply all lines inside one database transaction."""
        received = []
        with db_transaction.atomic():
            for line in lines:
                inventory = line["inventory"]
                inventory.check_in(
                    quantity=line["quantity"],
                    reason=header["reason"],
                    user=request.user,
                    jira_ticket=header.get("jira_ticket", ""),
                    notes=header.get("notes", ""),
                )
                received.append(f"{line['quantity']}x {inventory.spare_part_type} at {inventory.location}")
        return received


class DeviceCheckOutView(ObjectPermissionRequiredMixin, GenericView):
    """Take a part for a device, starting from the device page.

    Same movement as the ordinary check-out -- one code path, one audit record
    -- but the journey starts where the problem is.
    """

    queryset = SparePartInventory.objects.all()
    template_name = "nautobot_spare_parts/device_checkout.html"

    def get_required_permission(self):
        """Taking a part is a change to the inventory record."""
        return CHANGE_INVENTORY

    def get_device(self, request, device_pk):
        """Fetch the device, honouring object-level permissions."""
        return get_object_or_404(Device.objects.restrict(request.user, "view"), pk=device_pk)

    def render_page(self, request, device, form):
        """Render the page."""
        return render(
            request,
            self.template_name,
            {
                "object": device,
                "device": device,
                "form": form,
                "return_url": device.get_absolute_url(),
                "previous_parts": SparePartTransaction.objects.filter(
                    related_device=device, transaction_type="check_out"
                ).select_related("spare_part_inventory__spare_part_type")[:5],
            },
        )

    def get(self, request, device_pk):
        """Show the form."""
        device = self.get_device(request, device_pk)
        return self.render_page(request, device, forms.DeviceCheckOutForm(device=device))

    def post(self, request, device_pk):
        """Apply the check-out against this device."""
        device = self.get_device(request, device_pk)
        form = forms.DeviceCheckOutForm(request.POST, device=device)

        if form.is_valid():
            data = form.cleaned_data
            inventory = data["inventory"]
            try:
                inventory.check_out(
                    quantity=data["quantity"],
                    reason=data["reason"],
                    fulfil_reservation=data.get("fulfil_reservation", False),
                    user=request.user,
                    related_device=device,
                    jira_ticket=data.get("jira_ticket", ""),
                    notes=data.get("notes", ""),
                    request_id=data.get("request_id"),
                )
            except ValidationError as exc:
                for text in exc.messages:
                    messages.error(request, text)
            except Exception:  # noqa: BLE001
                logger.exception("Unexpected error taking a part for device %s", device.pk)
                messages.error(
                    request,
                    "Taking the part failed unexpectedly. Nothing was changed. "
                    "Check the Nautobot logs for the full error.",
                )
            else:
                messages.success(
                    request,
                    f"Took {data['quantity']}x {inventory.spare_part_type} from {inventory.location} "
                    f"for {device.name}.",
                )
                return redirect(device.get_absolute_url())

        return self.render_page(request, device, form)


def _qr_svg(data):
    """Inline SVG QR code for a string, or None if the QR library is missing.

    Optional on purpose: a missing dependency should degrade the label sheet to
    text rather than 500 a page somebody is standing at a printer waiting for.
    """
    try:
        import segno
    except ImportError:
        return None
    # error="m" (~15% recovery) survives a scuffed sticker without making the
    # symbol dense enough to need a good camera.
    return mark_safe(segno.make(str(data), error="m").svg_inline(scale=3, border=1))  # noqa: S308


class BinLabelsView(ObjectPermissionRequiredMixin, GenericView):
    """A printable sheet of shelf labels, each with a QR to its check-out form.

    Scanning a label on a phone lands on the check-out form for exactly that
    part at that location, which removes the "find the right record first" step
    that otherwise has to happen at a desk.

    Honours the stock list's filters, so ?location=<id> prints one cage.
    """

    queryset = SparePartInventory.objects.all()
    template_name = "nautobot_spare_parts/bin_labels.html"
    #: A sheet beyond this is a printer jam, not a useful document.
    max_labels = 400

    def get_required_permission(self):
        """Read-only view."""
        return VIEW_INVENTORY

    def get(self, request):
        """Render the picker, and the sheet for whatever it selected."""
        form = forms.BinLabelPickerForm(request.GET or None)
        picked = bool(request.GET)

        queryset = SparePartInventory.objects.none()
        copies = 1
        if picked and form.is_valid():
            queryset = form.selected_records()
            copies = form.copy_count()
        elif picked:
            # Fall back to the list view's own filters, so a query copied off
            # the stock list still works even if it does not match the picker.
            queryset = filters.SparePartInventoryFilterSet(request.GET, queryset=SparePartInventory.objects.all()).qs

        queryset = (
            queryset.restrict(request.user, "view")
            .select_related("spare_part_type", "spare_part_type__manufacturer", "location")
            .order_by("location__name", "spare_part_type__name")
        )

        total = queryset.count()
        labels = []
        for record in queryset[: self.max_labels]:
            url = request.build_absolute_uri(
                reverse("plugins:nautobot_spare_parts:sparepartinventory_checkout", args=[record.pk])
            )
            entry = {"record": record, "url": url, "qr": _qr_svg(url)}
            labels.extend([entry] * copies)

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "labels": labels,
                "count": len(labels),
                "records": total,
                "copies": copies,
                "truncated": total > self.max_labels,
                "max_labels": self.max_labels,
                "picked": picked,
                "qr_available": _qr_svg("x") is not None,
            },
        )


class LowStockDashboardView(ObjectPermissionRequiredMixin, GenericView):
    """Everything at or below its reorder threshold."""

    queryset = SparePartInventory.objects.all()
    template_name = "nautobot_spare_parts/low_stock_dashboard.html"

    def get_required_permission(self):
        """Read-only view."""
        return VIEW_INVENTORY

    def get(self, request):
        """Render the low-stock table."""
        queryset = SparePartInventory.annotate_available(
            self.queryset.restrict(request.user, "view").select_related(
                "spare_part_type",
                "spare_part_type__manufacturer",
                "location",
            )
        ).filter(filters.SparePartInventoryFilterSet.low_stock_q())

        table = tables.LowStockTable(queryset)
        RequestConfig(
            request,
            {
                "paginator_class": EnhancedPaginator,
                "per_page": get_paginate_count(request),
            },
        ).configure(table)

        return render(
            request,
            self.template_name,
            {
                "table": table,
                "low_stock_count": queryset.count(),
                "reorder_count": queryset.filter(reorder_quantity__gt=0).count(),
            },
        )


class InventoryOverviewView(ObjectPermissionRequiredMixin, GenericView):
    """Landing page: the four numbers worth knowing, plus what just happened."""

    queryset = SparePartInventory.objects.all()
    template_name = "nautobot_spare_parts/inventory_overview.html"

    def get_required_permission(self):
        """Read-only view."""
        return VIEW_INVENTORY

    def get(self, request):
        """Render the overview."""
        inventory = self.queryset.restrict(request.user, "view")
        low_stock = SparePartInventory.annotate_available(
            inventory.select_related("spare_part_type", "location")
        ).filter(filters.SparePartInventoryFilterSet.low_stock_q())

        totals = inventory.aggregate(
            total_units=Coalesce(Sum("quantity_on_hand"), Value(0)),
            total_reserved=Coalesce(Sum("quantity_reserved"), Value(0)),
        )
        total_value = inventory.aggregate(
            value=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("quantity_on_hand") * F("spare_part_type__unit_cost"),
                        output_field=DecimalField(max_digits=16, decimal_places=2),
                    )
                ),
                Value(0, output_field=DecimalField(max_digits=16, decimal_places=2)),
            )
        )["value"]

        return render(
            request,
            self.template_name,
            {
                "total_skus": SparePartType.objects.count(),
                "total_units": totals["total_units"],
                "total_reserved": totals["total_reserved"],
                "total_value": total_value,
                "low_stock_count": low_stock.count(),
                "low_stock_items": low_stock.order_by("available")[:10],
                "recent_transactions": SparePartTransaction.objects.select_related(
                    "spare_part_inventory__spare_part_type",
                    "spare_part_inventory__location",
                    "user",
                )[:10],
                "locations_with_stock": inventory.filter(quantity_on_hand__gt=0).values("location").distinct().count(),
            },
        )


class InventoryCSVExportView(ObjectPermissionRequiredMixin, GenericView):
    """Flat CSV of current stock -- the format people actually paste into sheets."""

    queryset = SparePartInventory.objects.all()

    def get_required_permission(self):
        """Read-only view."""
        return VIEW_INVENTORY

    def get(self, request):
        """Stream the inventory as CSV."""
        queryset = SparePartInventory.annotate_available(
            self.queryset.restrict(request.user, "view").select_related(
                "spare_part_type",
                "spare_part_type__manufacturer",
                "location",
            )
        )
        queryset = filters.SparePartInventoryFilterSet(request.GET, queryset=queryset).qs

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="spare-parts-inventory.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "manufacturer",
                "part_name",
                "part_number",
                "category",
                "location",
                "storage_detail",
                "on_hand",
                "reserved",
                "available",
                "minimum",
                "reorder_quantity",
                "low_stock",
                "unit_cost",
            ]
        )
        for record in queryset.iterator():
            part = record.spare_part_type
            writer.writerow(
                [
                    part.manufacturer.name if part.manufacturer else "",
                    part.name,
                    part.part_number,
                    part.get_category_display(),
                    record.location.name,
                    record.storage_location_detail,
                    record.quantity_on_hand,
                    record.quantity_reserved,
                    record.quantity_available,
                    record.minimum_quantity,
                    record.reorder_quantity,
                    "yes" if record.is_low_stock else "no",
                    part.unit_cost if part.unit_cost is not None else "",
                ]
            )
        return response


class JiraTicketPartsView(ObjectPermissionRequiredMixin, GenericView):
    """Every part movement booked against one Jira ticket.

    Answers the question that actually comes up in a ticket review: "what
    hardware did this job consume?"
    """

    queryset = SparePartTransaction.objects.all()
    template_name = "nautobot_spare_parts/jira_ticket_parts.html"

    def get_required_permission(self):
        """Read-only view."""
        return "nautobot_spare_parts.view_spareparttransaction"

    def get(self, request, ticket):
        """Render the movements for one ticket."""
        ticket = ticket.upper()
        transactions = (
            self.queryset.restrict(request.user, "view")
            .filter(jira_ticket__iexact=ticket)
            .select_related(
                "spare_part_inventory__spare_part_type",
                "spare_part_inventory__spare_part_type__manufacturer",
                "spare_part_inventory__location",
                "user",
                "related_device",
            )
        )
        table = tables.SparePartTransactionTable(transactions)
        RequestConfig(
            request,
            {"paginator_class": EnhancedPaginator, "per_page": get_paginate_count(request)},
        ).configure(table)

        consumed = (
            transactions.filter(quantity__lt=0)
            .values("spare_part_inventory__spare_part_type__name")
            .annotate(units=Sum("quantity"), movements=Count("pk"))
            .order_by("spare_part_inventory__spare_part_type__name")
        )

        return render(
            request,
            self.template_name,
            {
                "ticket": ticket,
                "table": table,
                "transaction_count": transactions.count(),
                "consumed": [
                    {"part": row["spare_part_inventory__spare_part_type__name"], "units": -row["units"]}
                    for row in consumed
                ],
                "devices": [
                    device
                    for device in transactions.filter(related_device__isnull=False)
                    .values_list("related_device__name", flat=True)
                    .distinct()
                ],
                # Net units still reserved against this ticket: allocations are
                # positive, deallocations negative, so the sum is what is left.
                "reserved_still_open": transactions.filter(
                    Q(transaction_type="allocation") | Q(transaction_type="deallocation")
                ).aggregate(net=Coalesce(Sum("reserved_delta"), Value(0)))["net"],
            },
        )
