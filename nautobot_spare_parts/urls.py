"""URL patterns for the Spare Parts Inventory app."""

from django.urls import path

from nautobot.apps.urls import NautobotUIViewSetRouter

from nautobot_spare_parts import views

app_name = "nautobot_spare_parts"

router = NautobotUIViewSetRouter()
router.register("spare-part-types", views.SparePartTypeUIViewSet)
router.register("spare-part-inventory", views.SparePartInventoryUIViewSet)
router.register("spare-part-transactions", views.SparePartTransactionUIViewSet)

# Fixed paths first so none of them can be swallowed by a router pattern.
urlpatterns = [
    path("", views.InventoryOverviewView.as_view(), name="overview"),
    path("low-stock/", views.LowStockDashboardView.as_view(), name="low_stock_dashboard"),
    path("export/inventory.csv", views.InventoryCSVExportView.as_view(), name="inventory_csv_export"),
    path("jira/<str:ticket>/", views.JiraTicketPartsView.as_view(), name="jira_ticket_parts"),
    path("labels/", views.BinLabelsView.as_view(), name="bin_labels"),
    path(
        "device/<uuid:device_pk>/take-part/",
        views.DeviceCheckOutView.as_view(),
        name="device_checkout",
    ),
    path(
        "spare-part-inventory/bulk-receive/",
        views.BulkReceiveView.as_view(),
        name="sparepartinventory_bulk_receive",
    ),
    path(
        "spare-part-inventory/<uuid:pk>/check-in/",
        views.CheckInView.as_view(),
        name="sparepartinventory_checkin",
    ),
    path(
        "spare-part-inventory/<uuid:pk>/check-out/",
        views.CheckOutView.as_view(),
        name="sparepartinventory_checkout",
    ),
    path(
        "spare-part-inventory/<uuid:pk>/allocate/",
        views.AllocationView.as_view(),
        name="sparepartinventory_allocate",
    ),
    path(
        "spare-part-inventory/<uuid:pk>/deallocate/",
        views.DeallocationView.as_view(),
        name="sparepartinventory_deallocate",
    ),
    path(
        "spare-part-inventory/<uuid:pk>/adjust/",
        views.AdjustmentView.as_view(),
        name="sparepartinventory_adjust",
    ),
    path(
        "spare-part-inventory/<uuid:pk>/transfer/",
        views.TransferView.as_view(),
        name="sparepartinventory_transfer",
    ),
]

urlpatterns += router.urls
