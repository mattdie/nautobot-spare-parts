"""API URL patterns for the Spare Parts Inventory app."""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_spare_parts.api import views

router = OrderedDefaultRouter(view_name="Spare Parts")
router.register("spare-part-types", views.SparePartTypeViewSet)
router.register("spare-part-inventory", views.SparePartInventoryViewSet)
router.register("spare-part-transactions", views.SparePartTransactionViewSet)

app_name = "nautobot_spare_parts-api"
urlpatterns = router.urls
