"""Navigation menu items for Spare Parts Inventory plugin."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab


menu_items = (
    NavMenuTab(
        name="Spare Parts",
        weight=600,
        groups=(
            NavMenuGroup(
                name="Spare Parts Inventory",
                weight=100,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:spareparttype_list",
                        name="Spare Part Types",
                        permissions=["nautobot_spare_parts.view_spareparttype"],
                        buttons=(
                            NavMenuAddButton(
                                link="plugins:nautobot_spare_parts:spareparttype_add",
                                permissions=["nautobot_spare_parts.add_spareparttype"],
                            ),
                        ),
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:sparepartinventory_list",
                        name="Inventory",
                        permissions=["nautobot_spare_parts.view_sparepartinventory"],
                        buttons=(
                            NavMenuAddButton(
                                link="plugins:nautobot_spare_parts:sparepartinventory_add",
                                permissions=["nautobot_spare_parts.add_sparepartinventory"],
                            ),
                        ),
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:spareparttransaction_list",
                        name="Transactions",
                        permissions=["nautobot_spare_parts.view_spareparttransaction"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_spare_parts:low_stock_dashboard",
                        name="Low Stock Alert",
                        permissions=["nautobot_spare_parts.view_sparepartinventory"],
                    ),
                ),
            ),
        ),
    ),
)
