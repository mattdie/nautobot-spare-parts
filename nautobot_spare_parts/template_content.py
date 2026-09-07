"""Template extensions for the Spare Parts Inventory app.

The inventory detail page's action buttons are *not* here -- they are declared
as UI framework ``Button``/``DropdownButton`` components on the ViewSet, which
renders them with the same markup, sizing and permission handling as core
Nautobot's own buttons.

What is left is the join that the UI framework cannot express: a panel on
somebody else's model.
"""

from django.urls import reverse
from django.utils.html import format_html, format_html_join

from nautobot.apps.ui import TemplateExtension

CHANGE_INVENTORY = "nautobot_spare_parts.change_sparepartinventory"


class DeviceTakePartButton(TemplateExtension):
    """Put "Take a part" on the device page.

    The journey that matters starts here -- "ca099 needs a drive" -- not at a
    shelf, so the device page is where the action belongs.
    """

    model = "dcim.device"

    def buttons(self):
        """Render the button, if the user may move stock."""
        device = self.context["object"]
        if not self.context["request"].user.has_perm(CHANGE_INVENTORY):
            return ""
        url = reverse("plugins:nautobot_spare_parts:device_checkout", args=[device.pk])
        return format_html(
            '<a href="{}" class="btn btn-warning"><span class="mdi mdi-wrench"></span> Take a part</a>',
            url,
        )


class DeviceSparePartHistory(TemplateExtension):
    """Show which spare parts have been fitted to a device.

    This is the join most people actually want: standing on a device page and
    asking "what have we already replaced in this box?"
    """

    model = "dcim.device"

    def right_page(self):
        """Render the device's spare part history panel."""
        device = self.context["object"]
        transactions = device.spare_part_transactions.select_related(
            "spare_part_inventory__spare_part_type",
            "spare_part_inventory__location",
            "user",
        ).order_by("-timestamp")[:10]
        if not transactions:
            return ""

        rows = format_html_join(
            "\n",
            '<tr><td>{}</td><td>{}</td><td><span class="font-monospace">{}</span></td><td>{}</td><td>{}</td></tr>',
            (
                (
                    txn.timestamp.strftime("%Y-%m-%d"),
                    str(txn.spare_part_inventory.spare_part_type),
                    # Pre-formatted: format_html escapes arguments to
                    # SafeString, which "+d" cannot format.
                    f"{txn.quantity:+d}",
                    txn.jira_ticket or "—",
                    str(txn.user) if txn.user else "—",
                )
                for txn in transactions
            ),
        )
        return format_html(
            """
            <div class="panel panel-default">
              <div class="panel-heading"><strong>Spare Parts Used</strong></div>
              <table class="table table-hover panel-body">
                <thead><tr><th>Date</th><th>Part</th><th>Qty</th><th>Jira</th><th>By</th></tr></thead>
                <tbody>{}</tbody>
              </table>
            </div>
            """,
            rows,
        )


template_extensions = [DeviceTakePartButton, DeviceSparePartHistory]
