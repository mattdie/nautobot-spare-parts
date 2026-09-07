"""Navigation menu for the Spare Parts Inventory app."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

VIEW_INVENTORY = "nautobot_spare_parts.view_sparepartinventory"
CHANGE_INVENTORY = "nautobot_spare_parts.change_sparepartinventory"

menu_items = (
    NavMenuTab(
        name="Spare Parts",
        weight=600,
        groups=(
            NavMenuGroup(
                name="Inventory",
                weight=100,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:overview",
                        name="Overview",
                        permissions=[VIEW_INVENTORY],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:sparepartinventory_list",
                        name="Stock",
                        permissions=[VIEW_INVENTORY],
                        buttons=(
                            NavMenuAddButton(
                                link="plugins:nautobot_spare_parts:sparepartinventory_add",
                                permissions=["nautobot_spare_parts.add_sparepartinventory"],
                            ),
                        ),
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:spareparttype_list",
                        name="Part Types",
                        permissions=["nautobot_spare_parts.view_spareparttype"],
                        buttons=(
                            NavMenuAddButton(
                                link="plugins:nautobot_spare_parts:spareparttype_add",
                                permissions=["nautobot_spare_parts.add_spareparttype"],
                            ),
                        ),
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:low_stock_dashboard",
                        name="Low Stock",
                        permissions=[VIEW_INVENTORY],
                    ),
                ),
            ),
            NavMenuGroup(
                name="Movements",
                weight=200,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:sparepartinventory_bulk_receive",
                        name="Bulk Receive",
                        permissions=[CHANGE_INVENTORY],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:spareparttransaction_list",
                        name="Transaction Log",
                        permissions=["nautobot_spare_parts.view_spareparttransaction"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:bin_labels",
                        name="Print Bin Labels",
                        permissions=[VIEW_INVENTORY],
                    ),
                ),
            ),
        ),
    ),
)
