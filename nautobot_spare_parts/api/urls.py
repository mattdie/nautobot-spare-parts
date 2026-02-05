"""API URL patterns for Spare Parts Inventory plugin."""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_spare_parts.api import views

router = OrderedDefaultRouter()
router.register("spare-part-types", views.SparePartTypeViewSet)
router.register("spare-part-inventory", views.SparePartInventoryViewSet)
router.register("spare-part-transactions", views.SparePartTransactionViewSet)

app_name = "nautobot_spare_parts-api"
urlpatterns = router.urls
