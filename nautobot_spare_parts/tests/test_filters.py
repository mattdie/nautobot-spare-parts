"""Tests for the filtersets.

The important one is the parity check: the low-stock SQL and the low-stock
Python property must always agree, or the dashboard and the record page tell
different stories.
"""

from nautobot.core.testing import TestCase

from nautobot_spare_parts.filters import (
    SparePartInventoryFilterSet,
    SparePartTransactionFilterSet,
    SparePartTypeFilterSet,
)
from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType
from nautobot_spare_parts.tests.fixtures import build_dcim, make_inventory, make_part_type


class SparePartTypeFilterTestCase(TestCase):
    """Filters on the catalogue."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.ram = make_part_type(
            name="Filter RAM", category="ram", manufacturer=cls.dcim["manufacturer"], part_number="RAM-1"
        )
        cls.psu = make_part_type(name="Filter PSU", category="psu")
        make_inventory(cls.ram, cls.dcim["location_a"], on_hand=5)
        make_inventory(cls.psu, cls.dcim["location_a"], on_hand=0)

    def filter(self, params):
        """Run the filterset."""
        return SparePartTypeFilterSet(params, queryset=SparePartType.objects.all()).qs

    def test_search_matches_name_part_number_and_manufacturer(self):
        for term in ("Filter RAM", "RAM-1", self.dcim["manufacturer"].name):
            with self.subTest(term=term):
                self.assertIn(self.ram, self.filter({"q": term}))

    def test_search_ignores_whitespace(self):
        self.assertEqual(self.filter({"q": "   "}).count(), SparePartType.objects.count())

    def test_category_filter(self):
        results = self.filter({"category": ["psu"]})
        self.assertIn(self.psu, results)
        self.assertNotIn(self.ram, results)

    def test_has_stock_filter(self):
        with_stock = self.filter({"has_stock": True})
        self.assertIn(self.ram, with_stock)
        self.assertNotIn(self.psu, with_stock)

        without_stock = self.filter({"has_stock": False})
        self.assertIn(self.psu, without_stock)
        self.assertNotIn(self.ram, without_stock)


class SparePartInventoryFilterTestCase(TestCase):
    """Filters on stock records."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type(name="Filter DIMM", category="dimm")

    def filter(self, params):
        """Run the filterset."""
        return SparePartInventoryFilterSet(params, queryset=SparePartInventory.objects.all()).qs

    def test_low_stock_filter_agrees_with_the_property(self):
        """Parity check across every interesting combination of counters."""
        cases = [
            # (on_hand, reserved, minimum)
            (0, 0, 0),
            (0, 0, 5),
            (10, 0, 0),
            (10, 0, 5),
            (5, 0, 5),
            (4, 0, 5),
            (10, 6, 5),
            (10, 5, 5),
            (10, 4, 5),
            (1, 1, 1),
        ]
        records = []
        for index, (on_hand, reserved, minimum) in enumerate(cases):
            location = self.dcim["location_a"] if index % 2 else self.dcim["location_b"]
            part_type = make_part_type(name=f"Parity part {index}", category="dimm")
            records.append(
                (
                    make_inventory(part_type, location, on_hand=on_hand, reserved=reserved, minimum=minimum),
                    (on_hand, reserved, minimum),
                )
            )

        matched = set(self.filter({"low_stock": True}).values_list("pk", flat=True))
        for record, params in records:
            with self.subTest(on_hand=params[0], reserved=params[1], minimum=params[2]):
                self.assertEqual(
                    record.pk in matched,
                    record.is_low_stock,
                    f"SQL and property disagree for {params}",
                )

    def test_out_of_stock_filter(self):
        empty = make_inventory(self.part_type, self.dcim["location_a"], on_hand=0)
        stocked = make_inventory(make_part_type(name="Stocked", category="ssd"), self.dcim["location_a"], on_hand=3)

        results = self.filter({"out_of_stock": True})
        self.assertIn(empty, results)
        self.assertNotIn(stocked, results)

    def test_fully_reserved_counts_as_out_of_stock(self):
        record = make_inventory(self.part_type, self.dcim["location_a"], on_hand=4, reserved=4)
        self.assertIn(record, self.filter({"out_of_stock": True}))

    def test_has_reservations_filter(self):
        reserved = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10, reserved=2)
        free = make_inventory(make_part_type(name="Free", category="ssd"), self.dcim["location_a"], on_hand=5)

        results = self.filter({"has_reservations": True})
        self.assertIn(reserved, results)
        self.assertNotIn(free, results)

    def test_search_matches_storage_detail(self):
        record = make_inventory(self.part_type, self.dcim["location_a"], on_hand=1)
        record.storage_location_detail = "Cage B, shelf 7"
        record.save()
        self.assertIn(record, self.filter({"q": "shelf 7"}))

    def test_category_and_manufacturer_traverse_the_part_type(self):
        part = make_part_type(name="Traversed", category="nic", manufacturer=self.dcim["manufacturer"])
        record = make_inventory(part, self.dcim["location_a"], on_hand=1)

        self.assertIn(record, self.filter({"category": ["nic"]}))
        self.assertIn(record, self.filter({"manufacturer": [str(self.dcim["manufacturer"].pk)]}))


class SparePartTransactionFilterTestCase(TestCase):
    """Filters on the audit trail."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type(name="Filter SSD", category="ssd")

    def setUp(self):
        super().setUp()
        self.inventory = make_inventory(self.part_type, self.dcim["location_a"], on_hand=20)
        self.inventory.check_in(quantity=5, reason="delivery from vendor")
        self.inventory.check_out(
            quantity=2, reason="fitted to a node", jira_ticket="INFRA2-7777", related_device=self.dcim["device"]
        )
        self.inventory.allocate(quantity=3, reason="reserved for maintenance")

    def filter(self, params):
        """Run the filterset."""
        return SparePartTransactionFilterSet(params, queryset=SparePartTransaction.objects.all()).qs

    def test_transaction_type_filter(self):
        self.assertEqual(self.filter({"transaction_type": ["check_out"]}).count(), 1)
        self.assertEqual(self.filter({"transaction_type": ["check_in", "allocation"]}).count(), 2)

    def test_jira_ticket_filter_is_case_insensitive(self):
        self.assertEqual(self.filter({"jira_ticket": "infra2-7777"}).count(), 1)

    def test_related_device_filter(self):
        self.assertEqual(self.filter({"related_device": [str(self.dcim["device"].pk)]}).count(), 1)

    def test_location_filter_traverses_the_inventory_record(self):
        self.assertEqual(self.filter({"location": [str(self.dcim["location_a"].pk)]}).count(), 3)

    def test_search_matches_reason_and_ticket(self):
        self.assertEqual(self.filter({"q": "delivery"}).count(), 1)
        self.assertEqual(self.filter({"q": "INFRA2-7777"}).count(), 1)
