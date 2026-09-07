"""Tests for the places this app hooks into the rest of Nautobot.

These are the things that make it read as part of the platform rather than a
bolted-on plugin: the home page panel, global search, the Device table column,
the Device detail panel, and the registered Jobs. Each one is a separate
registration point that can silently stop working after an upgrade.
"""

from django.apps import apps

from nautobot.core.testing import TestCase
from nautobot.extras.models import Job

from nautobot_spare_parts.tests.fixtures import build_dcim, make_inventory, make_part_type


class NativeIntegrationTestCase(TestCase):
    """Every integration point answers and shows the app's data."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type(
            name="Integration DIMM",
            category="dimm",
            manufacturer=cls.dcim["manufacturer"],
            part_number="INT-DIMM-1",
        )

    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()
        self.inventory = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10, minimum=4)
        self.inventory.check_out(
            quantity=2,
            reason="fitted during integration test",
            related_device=self.dcim["device"],
            jira_ticket="INFRA2-9001",
        )

    def test_home_page_shows_the_app_panel(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Spare Parts")
        self.assertContains(response, "The spare parts catalogue")

    def test_global_search_finds_a_part_by_part_number(self):
        """The Cmd-K box should find a part number, like it finds a device."""
        response = self.client.get("/search/", {"q": "INT-DIMM-1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Integration DIMM")

    def test_global_search_can_be_scoped_to_the_app_models(self):
        for obj_type in ("spareparttype", "sparepartinventory"):
            with self.subTest(obj_type=obj_type):
                response = self.client.get("/search/", {"q": "Integration", "obj_type": obj_type})
                self.assertEqual(response.status_code, 200)

    def test_app_models_are_registered_as_searchable(self):
        app = apps.get_app_config("nautobot_spare_parts")
        self.assertIn("spareparttype", app.searchable_models)
        self.assertIn("sparepartinventory", app.searchable_models)

    def test_device_table_offers_the_spares_column(self):
        response = self.client.get("/dcim/devices/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Spares Used")

    def test_device_table_can_be_sorted_by_the_spares_column(self):
        """The column is annotated in the database, so ordering must work."""
        response = self.client.get("/dcim/devices/", {"sort": "nautobot_spare_parts_spares_used"})
        self.assertEqual(response.status_code, 200)

    def test_device_detail_lists_the_spares_it_consumed(self):
        response = self.client.get(self.dcim["device"].get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Spare Parts Used")
        self.assertContains(response, "INFRA2-9001")

    def test_device_detail_has_no_panel_when_nothing_was_used(self):
        response = self.client.get(self.dcim["other_device"].get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Spare Parts Used")

    def test_jobs_are_registered(self):
        names = set(Job.objects.filter(module_name="nautobot_spare_parts.jobs").values_list("name", flat=True))
        self.assertIn("Low Stock Report", names)
        self.assertIn("Stale Reservations Report", names)

    def test_detail_pages_use_the_ui_component_framework(self):
        """The panels come from the ViewSet, not a hand-written template.

        ObjectDetailContent turns its `panels` argument into tabs, so the tabs
        are what to assert on.
        """
        import pathlib

        from nautobot_spare_parts.views import (
            SparePartInventoryUIViewSet,
            SparePartTransactionUIViewSet,
            SparePartTypeUIViewSet,
        )

        for viewset in (
            SparePartTypeUIViewSet,
            SparePartInventoryUIViewSet,
            SparePartTransactionUIViewSet,
        ):
            with self.subTest(viewset=viewset.__name__):
                self.assertIsNotNone(viewset.object_detail_content)
                self.assertTrue(viewset.object_detail_content.tabs)

        templates = pathlib.Path(__file__).resolve().parent.parent / "templates" / "nautobot_spare_parts"
        for model in ("spareparttype", "sparepartinventory", "spareparttransaction"):
            with self.subTest(model=model):
                self.assertFalse(
                    (templates / f"{model}_retrieve.html").exists(),
                    f"{model}_retrieve.html is back -- the UI framework should be building this page",
                )

    def test_inventory_detail_offers_every_stock_action(self):
        response = self.client.get(self.inventory.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        for label in ("Check In", "Check Out", "Allocate", "Deallocate", "Transfer", "Adjust"):
            with self.subTest(label=label):
                self.assertContains(response, label)


class JobTestCase(TestCase):
    """The reporting Jobs run and say something useful."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type(name="Job DIMM", category="dimm")

    def test_low_stock_report(self):
        from nautobot_spare_parts.jobs import LowStockReport

        make_inventory(self.part_type, self.dcim["location_a"], on_hand=1, minimum=5, reorder=10)
        job = LowStockReport()
        job.logger = _CapturingLogger()
        result = job.run(location=None, only_with_reorder_quantity=False)
        self.assertIn("1 part(s)", result)
        self.assertTrue(any("short by 4" in message for message in job.logger.messages))

    def test_low_stock_report_with_nothing_low(self):
        from nautobot_spare_parts.jobs import LowStockReport

        make_inventory(self.part_type, self.dcim["location_b"], on_hand=50, minimum=5)
        job = LowStockReport()
        job.logger = _CapturingLogger()
        self.assertEqual(job.run(location=None, only_with_reorder_quantity=False), "0 parts below minimum.")

    def test_stale_reservations_report(self):
        from nautobot_spare_parts.jobs import StaleReservationsReport

        record = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10)
        record.allocate(quantity=3, reason="reserved and forgotten", jira_ticket="INFRA2-9002")

        job = StaleReservationsReport()
        job.logger = _CapturingLogger()
        result = job.run()
        self.assertIn("1 record(s)", result)
        self.assertTrue(any("INFRA2-9002" in message for message in job.logger.messages))


class _CapturingLogger:
    """Minimal stand-in for a Job's logger, so run() can be called directly."""

    def __init__(self):
        self.messages = []

    def _record(self, message, *args, **kwargs):
        self.messages.append(message % args if args else message)

    info = warning = error = debug = success = _record
