"""Tests for the REST API.

The API is the surface scripts use, so it gets the same coverage as the UI:
create, read, every movement action, every refusal, and the guarantees the
audit trail depends on.
"""

import uuid

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from nautobot.core.testing import APITestCase
from nautobot.users.models import ObjectPermission

from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction, SparePartType
from nautobot_spare_parts.tests.fixtures import build_dcim, make_inventory, make_part_type


class SparePartAPITestCase(APITestCase):
    """Base class with a superuser token and one stocked record."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()
        self.inventory = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10, minimum=4, reorder=10)

    def list_url(self, model):
        """Reverse an API list URL."""
        return reverse(f"plugins-api:nautobot_spare_parts-api:{model}-list")

    def detail_url(self, model, pk):
        """Reverse an API detail URL."""
        return reverse(f"plugins-api:nautobot_spare_parts-api:{model}-detail", kwargs={"pk": pk})

    def action_url(self, action, pk=None):
        """URL of one of the inventory movement actions."""
        return f"{self.detail_url('sparepartinventory', pk or self.inventory.pk)}{action}/"


class ReadTestCase(SparePartAPITestCase):
    """Every read endpoint answers."""

    def test_list_endpoints(self):
        for model in ("spareparttype", "sparepartinventory", "spareparttransaction"):
            with self.subTest(model=model):
                response = self.client.get(self.list_url(model), **self.header)
                self.assertHttpStatus(response, 200)

    def test_transaction_list_serialises(self):
        """Regression: the transaction serializer declared a `url` field on a
        plain ModelSerializer, so listing transactions returned a 500."""
        self.inventory.check_in(quantity=1, reason="delivery")
        response = self.client.get(self.list_url("spareparttransaction"), **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertIn("url", response.data["results"][0])

    def test_transaction_detail_serialises(self):
        txn = self.inventory.check_in(quantity=1, reason="delivery")
        response = self.client.get(self.detail_url("spareparttransaction", txn.pk), **self.header)
        self.assertHttpStatus(response, 200)

    def test_inventory_exposes_the_derived_fields(self):
        response = self.client.get(self.detail_url("sparepartinventory", self.inventory.pk), **self.header)
        self.assertHttpStatus(response, 200)
        for field in ("quantity_available", "is_low_stock", "is_out_of_stock", "needs_reorder"):
            self.assertIn(field, response.data, field)

    def test_search_filter(self):
        """Regression: `?q=` raised AttributeError on django_filters.Q."""
        response = self.client.get(f"{self.list_url('spareparttype')}?q=test", **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["count"], 1)

    def test_low_stock_filter_matches_the_property(self):
        response = self.client.get(f"{self.list_url('sparepartinventory')}?low_stock=true", **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["count"], 0)

        self.inventory.check_out(quantity=8, reason="drop below minimum")
        response = self.client.get(f"{self.list_url('sparepartinventory')}?low_stock=true", **self.header)
        self.assertEqual(response.data["count"], 1)

    def test_jira_ticket_filter(self):
        self.inventory.check_out(quantity=1, reason="used", jira_ticket="INFRA2-4242")
        response = self.client.get(f"{self.list_url('spareparttransaction')}?jira_ticket=INFRA2-4242", **self.header)
        self.assertEqual(response.data["count"], 1)


class WriteTestCase(SparePartAPITestCase):
    """Creating objects through the API.

    Regression for both models: the nested related serializers were declared
    read-only, which made related fields unsettable and POST impossible.
    """

    def test_create_part_type(self):
        response = self.client.post(
            self.list_url("spareparttype"),
            {
                "name": "API part",
                "part_number": "API-1",
                "category": "psu",
                "manufacturer": str(self.dcim["manufacturer"].pk),
            },
            format="json",
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        created = SparePartType.objects.get(pk=response.data["id"])
        self.assertEqual(created.manufacturer, self.dcim["manufacturer"])

    def test_create_part_type_without_a_part_number(self):
        """A part number must stay optional -- the old unique_together made
        DRF mark it required."""
        response = self.client.post(
            self.list_url("spareparttype"),
            {"name": "Nameless part", "category": "fan"},
            format="json",
            **self.header,
        )
        self.assertHttpStatus(response, 201)

    def test_create_inventory_record(self):
        response = self.client.post(
            self.list_url("sparepartinventory"),
            {
                "spare_part_type": str(self.part_type.pk),
                "location": str(self.dcim["location_b"].pk),
                "quantity_on_hand": 5,
                "minimum_quantity": 2,
            },
            format="json",
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        record = SparePartInventory.objects.get(pk=response.data["id"])
        self.assertEqual(record.quantity_on_hand, 5)
        self.assertEqual(record.transactions.count(), 1, "opening balance should be recorded")

    def test_patch_cannot_move_stock(self):
        self.client.patch(
            self.detail_url("sparepartinventory", self.inventory.pk),
            {"quantity_on_hand": 500},
            format="json",
            **self.header,
        )
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_patch_can_still_change_planning_fields(self):
        response = self.client.patch(
            self.detail_url("sparepartinventory", self.inventory.pk),
            {"minimum_quantity": 7, "storage_location_detail": "Shelf 3"},
            format="json",
            **self.header,
        )
        self.assertHttpStatus(response, 200)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.minimum_quantity, 7)
        self.assertEqual(self.inventory.storage_location_detail, "Shelf 3")

    def test_transactions_are_read_only(self):
        txn = self.inventory.check_in(quantity=1, reason="delivery")
        for method, payload in (("patch", {"reason": "rewritten"}), ("put", {"reason": "rewritten"})):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    self.detail_url("spareparttransaction", txn.pk), payload, format="json", **self.header
                )
                self.assertIn(response.status_code, (403, 405))

        response = self.client.delete(self.detail_url("spareparttransaction", txn.pk), **self.header)
        self.assertIn(response.status_code, (403, 405))
        self.assertTrue(SparePartTransaction.objects.filter(pk=txn.pk).exists())


class ActionTestCase(SparePartAPITestCase):
    """The six movement actions."""

    def post_action(self, action, payload, pk=None):
        """POST to a movement action."""
        return self.client.post(self.action_url(action, pk), payload, format="json", **self.header)

    def test_check_in(self):
        response = self.post_action("check-in", {"quantity": 5, "reason": "delivery"})
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["inventory"]["quantity_on_hand"], 15)
        self.assertEqual(response.data["transaction"]["quantity"], 5)

    def test_urls_use_dashes(self):
        """Nautobot's own API uses dashes; underscores would be the odd one out."""
        self.assertHttpStatus(self.post_action("check-in", {"quantity": 1, "reason": "x"}), 200)
        response = self.client.post(
            self.action_url("check_in"), {"quantity": 1, "reason": "x"}, format="json", **self.header
        )
        self.assertHttpStatus(response, 404)

    def test_check_out(self):
        response = self.post_action(
            "check-out",
            {
                "quantity": 3,
                "reason": "fitted",
                "related_device": str(self.dcim["device"].pk),
                "jira_ticket": "INFRA2-1234",
            },
        )
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["inventory"]["quantity_on_hand"], 7)
        self.assertEqual(response.data["transaction"]["jira_ticket"], "INFRA2-1234")

    def test_check_out_with_an_unknown_device(self):
        response = self.post_action("check-out", {"quantity": 1, "reason": "x", "related_device": str(uuid.uuid4())})
        self.assertHttpStatus(response, 400)

    def test_allocate_and_deallocate(self):
        response = self.post_action("allocate", {"quantity": 4, "reason": "planned work"})
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["inventory"]["quantity_reserved"], 4)
        self.assertEqual(response.data["inventory"]["quantity_on_hand"], 10)

        response = self.post_action("deallocate", {"quantity": 1, "reason": "cancelled"})
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["inventory"]["quantity_reserved"], 3)

    def test_check_out_fulfilling_a_reservation(self):
        self.post_action("allocate", {"quantity": 10, "reason": "all reserved"})
        response = self.post_action(
            "check-out", {"quantity": 2, "reason": "fitted reserved units", "fulfil_reservation": True}
        )
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["inventory"]["quantity_on_hand"], 8)
        self.assertEqual(response.data["inventory"]["quantity_reserved"], 8)

    def test_adjust(self):
        response = self.post_action("adjust", {"quantity": -2, "reason": "stock take"})
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["inventory"]["quantity_on_hand"], 8)

    def test_transfer(self):
        response = self.post_action(
            "transfer",
            {
                "quantity": 4,
                "destination_location": str(self.dcim["location_b"].pk),
                "reason": "rebalancing",
            },
        )
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data["inventory"]["quantity_on_hand"], 6)
        self.assertEqual(
            SparePartInventory.objects.get(
                spare_part_type=self.part_type, location=self.dcim["location_b"]
            ).quantity_on_hand,
            4,
        )

    def test_transfer_to_an_unknown_location(self):
        response = self.post_action(
            "transfer", {"quantity": 1, "destination_location": str(uuid.uuid4()), "reason": "x"}
        )
        self.assertHttpStatus(response, 400)

    def test_idempotency(self):
        request_id = str(uuid.uuid4())
        payload = {"quantity": 5, "reason": "delivery", "request_id": request_id}
        first = self.post_action("check-in", payload)
        second = self.post_action("check-in", payload)

        self.assertHttpStatus(first, 200)
        self.assertHttpStatus(second, 200)
        self.assertEqual(second.data["inventory"]["quantity_on_hand"], 15)
        self.assertEqual(first.data["transaction"]["id"], second.data["transaction"]["id"])


class RefusalTestCase(SparePartAPITestCase):
    """Bad requests must be 400 with a reason, and change nothing."""

    def post_action(self, action, payload):
        """POST to a movement action."""
        return self.client.post(self.action_url(action), payload, format="json", **self.header)

    def test_refusals(self):
        cases = [
            ("check-out", {"quantity": 999, "reason": "too many"}),
            ("check-in", {"quantity": 0, "reason": "zero"}),
            ("check-in", {"quantity": -5, "reason": "negative"}),
            ("check-in", {"quantity": 1, "reason": "   "}),
            ("check-in", {"quantity": 1}),
            ("adjust", {"quantity": 0, "reason": "no-op"}),
            ("allocate", {"quantity": 500, "reason": "over-reserve"}),
            ("deallocate", {"quantity": 1, "reason": "nothing reserved"}),
            ("check-in", {"quantity": 1, "reason": "bad ticket", "jira_ticket": "nope"}),
            ("transfer", {"quantity": 1, "reason": "no destination"}),
        ]
        for action, payload in cases:
            with self.subTest(action=action, payload=payload):
                response = self.post_action(action, payload)
                self.assertHttpStatus(response, 400)

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)
        self.assertEqual(self.inventory.transactions.count(), 0)


class APIPermissionTestCase(SparePartAPITestCase):
    """A read-only token must not be able to move stock."""

    def setUp(self):
        super().setUp()
        self.user.is_superuser = False
        self.user.save()
        permission = ObjectPermission.objects.create(name="View spare parts", actions=["view"])
        permission.object_types.set(
            ContentType.objects.filter(
                app_label="nautobot_spare_parts",
                model__in=["sparepartinventory", "spareparttransaction", "spareparttype"],
            )
        )
        permission.users.add(self.user)

    def test_read_is_allowed(self):
        response = self.client.get(self.list_url("sparepartinventory"), **self.header)
        self.assertHttpStatus(response, 200)

    def test_movements_are_refused(self):
        for action in ("check-in", "check-out", "allocate", "deallocate", "adjust", "transfer"):
            with self.subTest(action=action):
                response = self.client.post(
                    self.action_url(action), {"quantity": 1, "reason": "x"}, format="json", **self.header
                )
                self.assertIn(response.status_code, (403, 400))

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)
