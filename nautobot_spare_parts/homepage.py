"""Nautobot home page panel.

Puts spare parts on the Nautobot landing page next to Organization, DCIM and
IPAM, so it reads as part of the platform rather than something hidden behind
the Apps menu.
"""

from nautobot.apps.ui import HomePageItem, HomePagePanel

from nautobot_spare_parts.models import SparePartInventory, SparePartType

VIEW_INVENTORY = "nautobot_spare_parts.view_sparepartinventory"


layout = (
    HomePagePanel(
        name="Spare Parts",
        weight=650,
        items=(
            HomePageItem(
                name="Stock Records",
                link="plugins:nautobot_spare_parts:sparepartinventory_list",
                model=SparePartInventory,
                description="Spare parts held at each location",
                permissions=[VIEW_INVENTORY],
                weight=100,
            ),
            HomePageItem(
                name="Part Types",
                link="plugins:nautobot_spare_parts:spareparttype_list",
                model=SparePartType,
                description="The spare parts catalogue",
                permissions=["nautobot_spare_parts.view_spareparttype"],
                weight=200,
            ),
            HomePageItem(
                name="Low Stock",
                link="plugins:nautobot_spare_parts:low_stock_dashboard",
                description="Parts at or below their reorder threshold",
                permissions=[VIEW_INVENTORY],
                weight=300,
            ),
        ),
    ),
)
