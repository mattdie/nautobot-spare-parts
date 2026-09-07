"""Tests for the stock movement logic.

These are the tests that matter: every one of them is a way the counters could
end up disagreeing with the transaction log.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from nautobot.core.testing import TestCase

from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType
from nautobot_spare_parts.tests.fixtures import build_dcim, make_inventory, make_part_type


class MovementTestCase(TestCase):
    """check_in / check_out / adjust / allocate / deallocate."""

    @classmethod
    def setUpTestData(cls):
        """Build the DCIM objects and a part type once."""
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def setUp(self):
        """Fresh inventory record per test."""
        super().setUp()
        self.inventory = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10)

    # --- happy paths ---------------------------------------------------------

    def test_check_in_adds_stock_and_writes_a_transaction(self):
        txn = self.inventory.check_in(quantity=3, reason="delivery")

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 13)
        self.assertEqual((txn.quantity_before, txn.quantity, txn.quantity_after), (10, 3, 13))
        self.assertEqual((txn.reserved_before, txn.reserved_delta, txn.reserved_after), (0, 0, 0))

    def test_check_out_removes_stock(self):
        txn = self.inventory.check_out(quantity=4, reason="fitted to a node")

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 6)
        self.assertEqual(txn.quantity, -4)

    def test_adjust_accepts_both_directions(self):
        self.inventory.adjust(quantity=-2, reason="stock take")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 8)

        self.inventory.adjust(quantity=5, reason="found a box")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 13)

    def test_allocate_reserves_without_moving_stock(self):
        txn = self.inventory.allocate(quantity=4, reason="planned work")

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)
        self.assertEqual(self.inventory.quantity_reserved, 4)
        self.assertEqual(self.inventory.quantity_available, 6)
        self.assertEqual(txn.quantity, 0)
        self.assertEqual(txn.reserved_delta, 4)

    def test_deallocate_releases_the_reservation(self):
        self.inventory.allocate(quantity=6, reason="planned work")
        self.inventory.deallocate(quantity=4, reason="cancelled")

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_reserved, 2)
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_check_out_can_fulfil_a_reservation(self):
        """The workflow the previous version had no answer for.

        With everything reserved, a plain check-out is correctly refused; a
        check-out that fulfils the reservation drops both counters together.
        """
        self.inventory.allocate(quantity=10, reason="all reserved")

        with self.assertRaises(ValidationError):
            self.inventory.check_out(quantity=2, reason="ignoring the reservation")

        self.inventory.check_out(quantity=2, reason="fitted the reserved units", fulfil_reservation=True)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 8)
        self.assertEqual(self.inventory.quantity_reserved, 8)
        self.assertEqual(self.inventory.quantity_available, 0)

    # --- refusals ------------------------------------------------------------

    def test_check_out_cannot_go_negative(self):
        with self.assertRaises(ValidationError):
            self.inventory.check_out(quantity=11, reason="too many")

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)
        self.assertEqual(self.inventory.transactions.count(), 0)

    def test_check_out_cannot_eat_into_reserved_stock(self):
        self.inventory.allocate(quantity=8, reason="reserved")

        with self.assertRaises(ValidationError) as ctx:
            self.inventory.check_out(quantity=5, reason="too many")
        self.assertIn("reserved", str(ctx.exception).lower())

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_allocate_cannot_exceed_available(self):
        self.inventory.allocate(quantity=8, reason="reserved")
        with self.assertRaises(ValidationError):
            self.inventory.allocate(quantity=3, reason="over-reserve")

    def test_deallocate_cannot_exceed_reserved(self):
        self.inventory.allocate(quantity=2, reason="reserved")
        with self.assertRaises(ValidationError):
            self.inventory.deallocate(quantity=5, reason="over-release")

    def test_zero_and_negative_quantities_are_refused(self):
        for quantity in (0, -1):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError):
                    self.inventory.check_in(quantity=quantity, reason="nope")
                with self.assertRaises(ValidationError):
                    self.inventory.check_out(quantity=quantity, reason="nope")
                with self.assertRaises(ValidationError):
                    self.inventory.allocate(quantity=quantity, reason="nope")

    def test_zero_adjustment_is_refused(self):
        with self.assertRaises(ValidationError):
            self.inventory.adjust(quantity=0, reason="no-op")

    def test_a_reason_is_required(self):
        for reason in ("", "   "):
            with self.subTest(reason=repr(reason)):
                with self.assertRaises(ValidationError):
                    self.inventory.check_in(quantity=1, reason=reason)

    def test_check_in_cannot_be_used_to_remove_stock(self):
        """The types mean what they say, so reports can trust them."""
        with self.assertRaises(ValidationError):
            self.inventory.record_movement(transaction_type="check_in", quantity=-1, reason="sneaky")

    def test_allocation_cannot_move_stock_on_hand(self):
        with self.assertRaises(ValidationError):
            self.inventory.record_movement(transaction_type="allocation", quantity=5, reserved_delta=1, reason="sneaky")

    def test_unknown_transaction_type_is_refused(self):
        with self.assertRaises(ValidationError):
            self.inventory.record_movement(transaction_type="teleport", quantity=1, reason="nope")

    def test_malformed_jira_ticket_is_refused(self):
        with self.assertRaises(ValidationError):
            self.inventory.check_out(quantity=1, reason="use", jira_ticket="not a ticket")

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_well_formed_jira_ticket_is_kept(self):
        txn = self.inventory.check_out(quantity=1, reason="use", jira_ticket="INFRA2-1234")
        self.assertEqual(txn.jira_ticket, "INFRA2-1234")


class IdempotencyTestCase(TestCase):
    """A repeated request_id must not apply a movement twice."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def setUp(self):
        super().setUp()
        self.inventory = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10)

    def test_repeating_a_request_id_is_a_no_op(self):
        request_id = uuid.uuid4()
        first = self.inventory.check_in(quantity=5, reason="delivery", request_id=request_id)
        second = self.inventory.check_in(quantity=5, reason="delivery", request_id=request_id)

        self.assertEqual(first.pk, second.pk)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 15)
        self.assertEqual(self.inventory.transactions.count(), 1)

    def test_different_request_ids_both_apply(self):
        self.inventory.check_in(quantity=5, reason="delivery", request_id=uuid.uuid4())
        self.inventory.check_in(quantity=5, reason="delivery", request_id=uuid.uuid4())

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 20)

    def test_no_request_id_means_no_deduplication(self):
        self.inventory.check_in(quantity=5, reason="delivery")
        self.inventory.check_in(quantity=5, reason="delivery")

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 20)


class TransferTestCase(TestCase):
    """Both legs of a transfer, or neither."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def setUp(self):
        super().setUp()
        self.source = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10)

    def test_transfer_moves_stock_and_links_both_legs(self):
        out_txn, in_txn = self.source.transfer_to(
            destination_location=self.dcim["location_b"], quantity=4, reason="rebalancing"
        )

        self.source.refresh_from_db()
        destination = SparePartInventory.objects.get(spare_part_type=self.part_type, location=self.dcim["location_b"])

        self.assertEqual(self.source.quantity_on_hand, 6)
        self.assertEqual(destination.quantity_on_hand, 4)
        self.assertEqual(out_txn.quantity, -4)
        self.assertEqual(in_txn.quantity, 4)

        out_txn.refresh_from_db()
        in_txn.refresh_from_db()
        self.assertIsNotNone(out_txn.transfer_group)
        self.assertEqual(out_txn.transfer_group, in_txn.transfer_group)
        self.assertEqual(out_txn.other_transfer_leg, in_txn)
        self.assertEqual(in_txn.other_transfer_leg, out_txn)

    def test_transfer_creates_the_destination_record_if_needed(self):
        self.assertFalse(
            SparePartInventory.objects.filter(spare_part_type=self.part_type, location=self.dcim["location_b"]).exists()
        )
        self.source.transfer_to(destination_location=self.dcim["location_b"], quantity=1, reason="seed")
        self.assertTrue(
            SparePartInventory.objects.filter(spare_part_type=self.part_type, location=self.dcim["location_b"]).exists()
        )

    def test_transfer_to_the_same_location_is_refused(self):
        with self.assertRaises(ValidationError):
            self.source.transfer_to(destination_location=self.dcim["location_a"], quantity=1, reason="pointless")

    def test_a_refused_transfer_leaves_nothing_behind(self):
        """The destination record must not be created if the source cannot pay."""
        with self.assertRaises(ValidationError):
            self.source.transfer_to(destination_location=self.dcim["location_b"], quantity=99, reason="too many")

        self.source.refresh_from_db()
        self.assertEqual(self.source.quantity_on_hand, 10)
        self.assertFalse(
            SparePartInventory.objects.filter(spare_part_type=self.part_type, location=self.dcim["location_b"]).exists()
        )

    def test_reserved_stock_cannot_be_transferred_away(self):
        self.source.allocate(quantity=8, reason="reserved here")
        with self.assertRaises(ValidationError):
            self.source.transfer_to(
                destination_location=self.dcim["location_b"], quantity=5, reason="moving reserved stock"
            )


class AuditTrailTestCase(TestCase):
    """The transaction log is append-only and always adds up."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def setUp(self):
        super().setUp()
        self.inventory = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10)

    def test_transactions_cannot_be_edited(self):
        txn = self.inventory.check_in(quantity=1, reason="delivery")
        txn.quantity = 999
        with self.assertRaises(ValidationError):
            txn.save()

    def test_transactions_cannot_be_deleted(self):
        txn = self.inventory.check_in(quantity=1, reason="delivery")
        with self.assertRaises(ValidationError):
            txn.delete()

    def test_notes_can_still_be_corrected(self):
        txn = self.inventory.check_in(quantity=1, reason="delivery")
        txn.set_notes("box was dented")
        txn.refresh_from_db()
        self.assertEqual(txn.notes, "box was dented")

    def test_quantities_cannot_be_edited_directly(self):
        """The hole that made the audit trail optional before."""
        self.inventory.quantity_on_hand = 500
        with self.assertRaises(ValidationError):
            self.inventory.save()

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_other_fields_can_still_be_edited(self):
        self.inventory.storage_location_detail = "Shelf 9"
        self.inventory.minimum_quantity = 5
        self.inventory.save()

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.storage_location_detail, "Shelf 9")
        self.assertEqual(self.inventory.minimum_quantity, 5)

    def test_transaction_log_adds_up_to_the_counters(self):
        self.inventory.check_in(quantity=5, reason="in")
        self.inventory.check_out(quantity=3, reason="out")
        self.inventory.adjust(quantity=-1, reason="stock take")
        self.inventory.allocate(quantity=4, reason="reserved")
        self.inventory.deallocate(quantity=1, reason="released")
        self.inventory.check_out(quantity=2, reason="fulfilled", fulfil_reservation=True)

        self.inventory.refresh_from_db()
        totals = self.inventory.transactions.all()
        self.assertEqual(sum(txn.quantity for txn in totals) + 10, self.inventory.quantity_on_hand)
        self.assertEqual(sum(txn.reserved_delta for txn in totals), self.inventory.quantity_reserved)

    def test_every_transaction_is_internally_consistent(self):
        self.inventory.check_in(quantity=5, reason="in")
        self.inventory.allocate(quantity=2, reason="reserved")

        for txn in self.inventory.transactions.all():
            with self.subTest(txn=str(txn)):
                self.assertEqual(txn.quantity_before + txn.quantity, txn.quantity_after)
                self.assertEqual(txn.reserved_before + txn.reserved_delta, txn.reserved_after)

    def test_opening_balance_is_recorded_on_creation(self):
        record = SparePartInventory.objects.create(
            spare_part_type=self.part_type,
            location=self.dcim["location_b"],
            quantity_on_hand=7,
        )
        transactions = record.transactions.all()
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].quantity, 7)
        self.assertEqual(transactions[0].quantity_before, 0)


class DerivedStateTestCase(TestCase):
    """quantity_available, is_low_stock, is_out_of_stock, needs_reorder."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def test_available_excludes_reserved(self):
        record = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10, reserved=4)
        self.assertEqual(record.quantity_available, 6)

    def test_low_stock_needs_a_minimum_to_be_set(self):
        """A part with no minimum is not stock-managed and must not alert.

        Previously every record with 0 available was flagged forever, including
        the ones nobody had asked to track, which is how a low-stock dashboard
        becomes something people stop reading.
        """
        unmanaged = make_inventory(self.part_type, self.dcim["location_a"], on_hand=0, minimum=0)
        self.assertFalse(unmanaged.is_low_stock)
        self.assertTrue(unmanaged.is_out_of_stock)

    def test_low_stock_at_and_below_the_minimum(self):
        record = make_inventory(self.part_type, self.dcim["location_b"], on_hand=5, minimum=5)
        self.assertTrue(record.is_low_stock)
        self.assertFalse(record.needs_reorder)

        record.reorder_quantity = 10
        record.save()
        self.assertTrue(record.needs_reorder)

    def test_reservations_count_towards_low_stock(self):
        record = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10, reserved=8, minimum=4)
        self.assertTrue(record.is_low_stock)

    def test_annotated_available_matches_the_property(self):
        make_inventory(self.part_type, self.dcim["location_a"], on_hand=10, reserved=3)
        annotated = SparePartInventory.annotate_available(SparePartInventory.objects.all()).first()
        self.assertEqual(annotated.available, annotated.quantity_available)


class ConstraintTestCase(TestCase):
    """Database-level guards, for the paths Python never sees."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def test_database_refuses_reserved_above_on_hand(self):
        record = make_inventory(self.part_type, self.dcim["location_a"], on_hand=5)
        with self.assertRaises(IntegrityError):
            # .update() bypasses the model layer entirely -- exactly what the
            # check constraint is there for.
            SparePartInventory.objects.filter(pk=record.pk).update(quantity_reserved=9)

    def test_one_record_per_part_and_location(self):
        make_inventory(self.part_type, self.dcim["location_a"], on_hand=1)
        with self.assertRaises(Exception):
            SparePartInventory.objects.create(spare_part_type=self.part_type, location=self.dcim["location_a"])

    def test_part_number_is_unique_per_manufacturer(self):
        SparePartType.objects.create(
            name="First", manufacturer=self.dcim["manufacturer"], part_number="PN-1", category="psu"
        )
        clash = SparePartType(name="Second", manufacturer=self.dcim["manufacturer"], part_number="PN-1", category="psu")
        with self.assertRaises(ValidationError):
            clash.full_clean()

    def test_several_part_types_may_have_no_part_number(self):
        """The old unique_together made the second one impossible."""
        SparePartType.objects.create(name="A", manufacturer=self.dcim["manufacturer"], category="fan")
        SparePartType.objects.create(name="B", manufacturer=self.dcim["manufacturer"], category="fan")
        self.assertEqual(
            SparePartType.objects.filter(manufacturer=self.dcim["manufacturer"], part_number="").count(), 2
        )

    def test_part_number_requires_a_manufacturer(self):
        part = SparePartType(name="Orphan", part_number="PN-9", category="psu")
        with self.assertRaises(ValidationError):
            part.full_clean()

    def test_negative_unit_cost_is_refused(self):
        part = SparePartType(name="Cheap", category="psu", unit_cost=-1)
        with self.assertRaises(ValidationError):
            part.full_clean()


class TransactionQueryTestCase(TestCase):
    """The reporting joins the app exists to answer."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def test_transactions_are_reachable_from_the_device(self):
        record = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10)
        record.check_out(
            quantity=2,
            reason="replaced a failed part",
            related_device=self.dcim["device"],
            jira_ticket="INFRA2-1111",
        )
        self.assertEqual(self.dcim["device"].spare_part_transactions.count(), 1)

    def test_transactions_are_reachable_from_the_jira_ticket(self):
        record = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10)
        record.check_out(quantity=1, reason="one", jira_ticket="INFRA2-2222")
        record.check_out(quantity=1, reason="two", jira_ticket="INFRA2-2222")
        record.check_out(quantity=1, reason="other", jira_ticket="INFRA2-3333")

        self.assertEqual(SparePartTransaction.objects.filter(jira_ticket="INFRA2-2222").count(), 2)
