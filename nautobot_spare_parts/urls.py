"""URL patterns for Spare Parts Inventory plugin."""

from django.urls import path

from nautobot.apps.urls import NautobotUIViewSetRouter

from nautobot_spare_parts import views

app_name = "nautobot_spare_parts"

router = NautobotUIViewSetRouter()
router.register("spare-part-types", views.SparePartTypeUIViewSet)
router.register("spare-part-inventory", views.SparePartInventoryUIViewSet)
router.register("spare-part-transactions", views.SparePartTransactionUIViewSet)

urlpatterns = [
    # Custom action URLs
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
        "low-stock/",
        views.LowStockDashboardView.as_view(),
        name="low_stock_dashboard",
    ),
]

urlpatterns += router.urls
