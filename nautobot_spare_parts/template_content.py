"""Template content extensions for Spare Parts Inventory plugin."""

from django.urls import reverse
from nautobot.apps.ui import TemplateExtension


class SparePartInventoryButtons(TemplateExtension):
    """Add check-in/check-out buttons to SparePartInventory detail view."""

    model = "nautobot_spare_parts.sparepartinventory"

    def buttons(self):
        """Add custom action buttons."""
        obj = self.context["object"]
        check_in_url = reverse("plugins:nautobot_spare_parts:sparepartinventory_checkin", args=[obj.pk])
        check_out_url = reverse("plugins:nautobot_spare_parts:sparepartinventory_checkout", args=[obj.pk])

        return f"""
        <a href="{check_in_url}" class="btn btn-success">
            <i class="mdi mdi-plus"></i> Check In
        </a>
        <a href="{check_out_url}" class="btn btn-warning">
            <i class="mdi mdi-minus"></i> Check Out
        </a>
        """


template_extensions = [SparePartInventoryButtons]
