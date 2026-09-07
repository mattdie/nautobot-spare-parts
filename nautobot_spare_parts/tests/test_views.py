"""Tests for the UI: every page loads, and every action form behaves."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from nautobot.core.testing import TestCase
from nautobot.users.models import ObjectPermission

from nautobot_spare_parts.models import SparePartInventory
from nautobot_spare_parts.tests.fixtures import build_dcim, make_inventory, make_part_type

User = get_user_model()


class ViewTestCaseBase(TestCase):
    """Shared setup: a superuser client and one inventory record."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def setUp(self):
        super().setUp()
        self.inventory = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10, minimum=4, reorder=10)
        self.user.is_superuser = True
        self.user.save()

    def url(self, name, *args):
        """Reverse a plugin URL."""
        return reverse(f"plugins:nautobot_spare_parts:{name}", args=args)


class PageLoadTestCase(ViewTestCaseBase):
    """Every page returns 200 for a user who is allowed to see it."""

    def test_pages_load(self):
        pages = [
            ("overview",),
            ("low_stock_dashboard",),
            ("inventory_csv_export",),
            ("spareparttype_list",),
            ("sparepartinventory_list",),
            ("spareparttransaction_list",),
            ("sparepartinventory_bulk_receive",),
        ]
        for name, *args in pages:
            with self.subTest(page=name):
                response = self.client.get(self.url(name, *args))
                self.assertEqual(response.status_code, 200, name)

    def test_record_pages_load(self):
        for name in (
            "sparepartinventory",
            "sparepartinventory_checkin",
            "sparepartinventory_checkout",
            "sparepartinventory_allocate",
            "sparepartinventory_deallocate",
            "sparepartinventory_adjust",
            "sparepartinventory_transfer",
        ):
            with self.subTest(page=name):
                response = self.client.get(self.url(name, self.inventory.pk))
                self.assertEqual(response.status_code, 200, name)

    def test_search_does_not_error(self):
        """Regression: the search filters used a non-existent django_filters.Q,
        so every list view with ?q= returned a 500."""
        for name in ("spareparttype_list", "sparepartinventory_list", "spareparttransaction_list"):
            with self.subTest(page=name):
                response = self.client.get(self.url(name), {"q": "test"})
                self.assertEqual(response.status_code, 200, name)

    def test_low_stock_dashboard_renders_its_table(self):
        """Regression: the dashboard called table.configure(), which does not
        exist on Nautobot's BaseTable, so the page always 500'd."""
        self.inventory.check_out(quantity=8, reason="drop below the minimum of 4")
        response = self.client.get(self.url("low_stock_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.part_type))

    def test_low_stock_dashboard_excludes_unmanaged_records(self):
        """A record with no minimum is not stock-managed and must not appear."""
        unmanaged_type = make_part_type(name="Unmanaged cable", category="cable")
        make_inventory(unmanaged_type, self.dcim["location_b"], on_hand=0, minimum=0)
        response = self.client.get(self.url("low_stock_dashboard"))
        self.assertNotContains(response, "Unmanaged cable")

    def test_csv_export_has_a_row_per_record(self):
        response = self.client.get(self.url("inventory_csv_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        lines = response.content.decode().strip().splitlines()
        self.assertEqual(len(lines), SparePartInventory.objects.count() + 1)

    def test_jira_view_lists_the_movements_for_a_ticket(self):
        self.inventory.check_out(quantity=2, reason="used", jira_ticket="INFRA2-1234")
        response = self.client.get(self.url("jira_ticket_parts", "INFRA2-1234"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INFRA2-1234")

    def test_jira_view_handles_an_unknown_ticket(self):
        response = self.client.get(self.url("jira_ticket_parts", "INFRA2-0000"))
        self.assertEqual(response.status_code, 200)


class ActionViewTestCase(ViewTestCaseBase):
    """POSTing the action forms."""

    def test_check_in(self):
        response = self.client.post(
            self.url("sparepartinventory_checkin", self.inventory.pk),
            {"quantity": 5, "reason": "delivery"},
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 15)

    def test_check_out(self):
        response = self.client.post(
            self.url("sparepartinventory_checkout", self.inventory.pk),
            {"quantity": 3, "reason": "fitted", "jira_ticket": "INFRA2-1234"},
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 7)
        self.assertEqual(self.inventory.transactions.first().jira_ticket, "INFRA2-1234")

    def test_check_out_over_available_shows_a_form_error(self):
        response = self.client.post(
            self.url("sparepartinventory_checkout", self.inventory.pk),
            {"quantity": 99, "reason": "too many"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only 10 unit(s) available")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_check_out_explains_the_reservation(self):
        self.inventory.allocate(quantity=10, reason="all reserved")
        response = self.client.post(
            self.url("sparepartinventory_checkout", self.inventory.pk),
            {"quantity": 2, "reason": "taking reserved stock without saying so"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "reserved")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_check_out_fulfilling_a_reservation(self):
        self.inventory.allocate(quantity=10, reason="all reserved")
        response = self.client.post(
            self.url("sparepartinventory_checkout", self.inventory.pk),
            {"quantity": 2, "reason": "fitted the reserved units", "fulfil_reservation": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 8)
        self.assertEqual(self.inventory.quantity_reserved, 8)

    def test_check_out_warns_about_an_incompatible_device(self):
        self.part_type.compatible_device_types.add(self.dcim["device_type"])
        response = self.client.post(
            self.url("sparepartinventory_checkout", self.inventory.pk),
            {
                "quantity": 1,
                "reason": "wrong hardware",
                "related_device": str(self.dcim["other_device"].pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not listed as compatible")

    def test_check_out_accepts_a_compatible_device(self):
        self.part_type.compatible_device_types.add(self.dcim["device_type"])
        response = self.client.post(
            self.url("sparepartinventory_checkout", self.inventory.pk),
            {"quantity": 1, "reason": "right hardware", "related_device": str(self.dcim["device"].pk)},
        )
        self.assertEqual(response.status_code, 302)

    def test_allocate_and_deallocate(self):
        self.client.post(
            self.url("sparepartinventory_allocate", self.inventory.pk),
            {"quantity": 4, "reason": "planned work"},
        )
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_reserved, 4)

        self.client.post(
            self.url("sparepartinventory_deallocate", self.inventory.pk),
            {"quantity": 1, "reason": "cancelled"},
        )
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_reserved, 3)

    def test_over_allocation_shows_a_form_error(self):
        response = self.client.post(
            self.url("sparepartinventory_allocate", self.inventory.pk),
            {"quantity": 99, "reason": "too many"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "available to reserve")

    def test_adjust_rejects_zero(self):
        response = self.client.post(
            self.url("sparepartinventory_adjust", self.inventory.pk),
            {"quantity": 0, "reason": "no-op"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "changes nothing")

    def test_blank_reason_is_rejected(self):
        response = self.client.post(
            self.url("sparepartinventory_checkin", self.inventory.pk),
            {"quantity": 1, "reason": "    "},
        )
        self.assertEqual(response.status_code, 200)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_transfer(self):
        response = self.client.post(
            self.url("sparepartinventory_transfer", self.inventory.pk),
            {
                "quantity": 4,
                "destination_location": str(self.dcim["location_b"].pk),
                "reason": "rebalancing",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 6)
        self.assertEqual(
            SparePartInventory.objects.get(
                spare_part_type=self.part_type, location=self.dcim["location_b"]
            ).quantity_on_hand,
            4,
        )

    def test_transfer_to_the_same_location_is_rejected(self):
        response = self.client.post(
            self.url("sparepartinventory_transfer", self.inventory.pk),
            {
                "quantity": 1,
                "destination_location": str(self.dcim["location_a"].pk),
                "reason": "pointless",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_double_submitting_a_form_only_applies_once(self):
        """The hidden request_id is what makes a double-clicked button safe."""
        form = self.client.get(self.url("sparepartinventory_checkin", self.inventory.pk)).context["form"]
        request_id = str(form["request_id"].value())
        payload = {"quantity": 5, "reason": "delivery", "request_id": request_id}

        self.client.post(self.url("sparepartinventory_checkin", self.inventory.pk), payload)
        self.client.post(self.url("sparepartinventory_checkin", self.inventory.pk), payload)

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 15)
        self.assertEqual(self.inventory.transactions.count(), 1)


class EditFormTestCase(ViewTestCaseBase):
    """The edit form must not be a back door into the counters."""

    def test_edit_form_freezes_the_quantities(self):
        response = self.client.get(self.url("sparepartinventory_edit", self.inventory.pk))
        form = response.context["form"]
        for name in ("spare_part_type", "location", "quantity_on_hand", "quantity_reserved"):
            with self.subTest(field=name):
                self.assertTrue(form.fields[name].disabled, name)

    def test_posting_a_new_quantity_to_the_edit_form_is_ignored(self):
        response = self.client.post(
            self.url("sparepartinventory_edit", self.inventory.pk),
            {
                "spare_part_type": str(self.part_type.pk),
                "location": str(self.dcim["location_a"].pk),
                "quantity_on_hand": 999,
                "quantity_reserved": 0,
                "minimum_quantity": 4,
                "reorder_quantity": 10,
                "storage_location_detail": "Shelf 1",
            },
        )
        self.assertIn(response.status_code, (200, 302))
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)
        self.assertEqual(self.inventory.storage_location_detail, "Shelf 1")


class BulkReceiveTestCase(ViewTestCaseBase):
    """Bulk receive is all-or-nothing."""

    def setUp(self):
        super().setUp()
        self.second_type = make_part_type(name="Test SSD", category="ssd")
        self.second = make_inventory(self.second_type, self.dcim["location_a"], on_hand=2)

    def payload(self, lines, **extra):
        """Build formset POST data."""
        data = {
            "reason": "Shipment 1234",
            "form-TOTAL_FORMS": str(len(lines)),
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
        }
        for index, (inventory, quantity) in enumerate(lines):
            data[f"form-{index}-inventory"] = str(inventory.pk) if inventory else ""
            data[f"form-{index}-quantity"] = str(quantity) if quantity is not None else ""
        data.update(extra)
        return data

    def test_receives_every_line(self):
        response = self.client.post(
            self.url("sparepartinventory_bulk_receive"),
            self.payload([(self.inventory, 5), (self.second, 3)]),
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 15)
        self.assertEqual(self.second.quantity_on_hand, 5)

    def test_the_same_record_twice_is_rejected(self):
        response = self.client.post(
            self.url("sparepartinventory_bulk_receive"),
            self.payload([(self.inventory, 5), (self.inventory, 3)]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "one line")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_an_empty_submission_is_rejected(self):
        response = self.client.post(self.url("sparepartinventory_bulk_receive"), self.payload([(None, None)]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at least one line")

    def test_a_line_without_a_quantity_is_rejected(self):
        response = self.client.post(
            self.url("sparepartinventory_bulk_receive"),
            self.payload([(self.inventory, None)]),
        )
        self.assertEqual(response.status_code, 200)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)


class DeviceCheckOutTestCase(ViewTestCaseBase):
    """Taking a part starting from the device page."""

    def url_for(self, device):
        """The device-side take-a-part URL."""
        return self.url("device_checkout", device.pk)

    def test_page_loads_and_prefills_the_reason(self):
        response = self.client.get(self.url_for(self.dcim["device"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["reason"].value(),
            f"Replaced part in {self.dcim['device'].name}",
        )

    def test_part_picker_is_scoped_to_the_device_type(self):
        response = self.client.get(self.url_for(self.dcim["device"]))
        params = response.context["form"].fields["spare_part_type"].query_params
        self.assertEqual(params["fits_device_type"], str(self.dcim["device"].device_type_id))
        self.assertTrue(params["has_stock"])

    def test_taking_a_part_writes_the_movement_against_the_device(self):
        response = self.client.post(
            self.url_for(self.dcim["device"]),
            {
                "spare_part_type": str(self.part_type.pk),
                "inventory": str(self.inventory.pk),
                "quantity": 2,
                "reason": "Two drives failing SMART",
                "jira_ticket": "INFRA2-5130",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 8)

        txn = self.inventory.transactions.first()
        self.assertEqual(txn.related_device, self.dcim["device"])
        self.assertEqual(txn.jira_ticket, "INFRA2-5130")
        self.assertEqual(txn.transaction_type, "check_out")

    def test_over_taking_shows_a_form_error_and_changes_nothing(self):
        response = self.client.post(
            self.url_for(self.dcim["device"]),
            {
                "spare_part_type": str(self.part_type.pk),
                "inventory": str(self.inventory.pk),
                "quantity": 99,
                "reason": "too many",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only 10 unit(s) available")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_can_fulfil_a_reservation_from_the_device_page(self):
        self.inventory.allocate(quantity=10, reason="all reserved")
        response = self.client.post(
            self.url_for(self.dcim["device"]),
            {
                "spare_part_type": str(self.part_type.pk),
                "inventory": str(self.inventory.pk),
                "quantity": 2,
                "reason": "fitted the reserved units",
                "fulfil_reservation": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 8)
        self.assertEqual(self.inventory.quantity_reserved, 8)

    def test_device_page_offers_the_button(self):
        response = self.client.get(self.dcim["device"].get_absolute_url())
        self.assertContains(response, "Take a part")
        self.assertContains(response, self.url_for(self.dcim["device"]))

    def test_picker_only_offers_stock_in_the_devices_datacenter(self):
        """You do not carry a drive between datacenters to fix a node."""
        response = self.client.get(self.url_for(self.dcim["device"]))
        params = response.context["form"].fields["inventory"].query_params

        # The dropdown is scoped server-side by this filter; the API test below
        # proves the filter itself only returns same-datacenter stock.
        self.assertEqual(params["for_device"], str(self.dcim["device"].pk))
        self.assertFalse(params["out_of_stock"])
        self.assertContains(response, f"Only stock at {self.dcim['location_a']}")

    def test_the_for_device_filter_excludes_other_datacenters(self):
        from nautobot_spare_parts.filters import SparePartInventoryFilterSet

        remote = make_inventory(self.part_type, self.dcim["location_b"], on_hand=50)
        offered = SparePartInventoryFilterSet(
            {"for_device": str(self.dcim["device"].pk)}, queryset=SparePartInventory.objects.all()
        ).qs

        self.assertIn(self.inventory, offered)
        self.assertNotIn(remote, offered)

    def test_taking_from_another_datacenter_is_refused(self):
        """The queryset scope is a convenience; this is the actual guard."""
        remote = make_inventory(self.part_type, self.dcim["location_b"], on_hand=50)
        response = self.client.post(
            self.url_for(self.dcim["device"]),
            {
                "spare_part_type": str(self.part_type.pk),
                "inventory": str(remote.pk),
                "quantity": 1,
                "reason": "wrong datacenter",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not in the same datacenter")
        remote.refresh_from_db()
        self.assertEqual(remote.quantity_on_hand, 50)

    def test_a_part_stocked_only_elsewhere_says_where_it_is(self):
        """An empty dropdown with no explanation reads as a broken form."""
        remote_only = make_part_type(name="Remote only NIC", category="nic")
        make_inventory(remote_only, self.dcim["location_b"], on_hand=7)

        response = self.client.post(
            self.url_for(self.dcim["device"]),
            {
                "spare_part_type": str(remote_only.pk),
                "quantity": 1,
                "reason": "none here",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "None here. It is stocked at")
        self.assertContains(response, str(self.dcim["location_b"]))

    def test_an_empty_take_from_is_still_required(self):
        """When there IS local stock, not picking a source must be an error."""
        response = self.client.post(
            self.url_for(self.dcim["device"]),
            {"spare_part_type": str(self.part_type.pk), "quantity": 1, "reason": "forgot the source"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose where to take it from")

    def test_a_part_stocked_nowhere_says_so(self):
        nowhere = make_part_type(name="Never stocked GPU", category="gpu")
        response = self.client.post(
            self.url_for(self.dcim["device"]),
            {"spare_part_type": str(nowhere.pk), "quantity": 1, "reason": "none anywhere"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "None in stock anywhere")

    def test_stock_in_a_room_under_the_site_still_counts(self):
        """Stock recorded against a cage below the site is the same datacenter."""
        from nautobot.dcim.models import Location, LocationType

        room_type, _ = LocationType.objects.get_or_create(
            name="Test Room", defaults={"parent": self.dcim["location_a"].location_type}
        )
        cage = Location.objects.create(
            name="Test Cage",
            location_type=room_type,
            parent=self.dcim["location_a"],
            status=self.dcim["location_a"].status,
        )
        in_cage = make_inventory(make_part_type(name="Caged PSU", category="psu"), cage, on_hand=3)

        response = self.client.get(self.url_for(self.dcim["device"]))
        self.assertIn(in_cage, response.context["form"].fields["inventory"].queryset)


class BinLabelTestCase(ViewTestCaseBase):
    """The printable shelf labels."""

    def test_page_loads_with_no_selection(self):
        response = self.client.get(self.url("bin_labels"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["count"], 0)
        self.assertContains(response, "Pick some bins")

    def test_specific_records(self):
        response = self.client.get(self.url("bin_labels"), {"inventory": str(self.inventory.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["count"], 1)

    def test_whole_location(self):
        second = make_inventory(make_part_type(name="Label SSD", category="ssd"), self.dcim["location_a"], on_hand=4)
        response = self.client.get(self.url("bin_labels"), {"location": str(self.dcim["location_a"].pk)})
        self.assertEqual(response.context["count"], 2)
        self.assertContains(response, str(second.spare_part_type.name))

    def test_copies_multiply_the_sheet_but_not_the_records(self):
        response = self.client.get(self.url("bin_labels"), {"inventory": str(self.inventory.pk), "copies": 3})
        self.assertEqual(response.context["records"], 1)
        self.assertEqual(response.context["count"], 3)

    def test_low_stock_only(self):
        healthy = make_inventory(
            make_part_type(name="Label NIC", category="nic"), self.dcim["location_b"], on_hand=50, minimum=2
        )
        self.inventory.check_out(quantity=8, reason="drop below the minimum of 4")
        response = self.client.get(self.url("bin_labels"), {"low_stock": "on"})
        labelled = {entry["record"].pk for entry in response.context["labels"]}
        self.assertIn(self.inventory.pk, labelled)
        self.assertNotIn(healthy.pk, labelled)

    def test_the_qr_encodes_that_record_check_out_url(self):
        """Scanning must land on the check-out form, not the record page."""
        response = self.client.get(self.url("bin_labels"), {"inventory": str(self.inventory.pk)})
        entry = response.context["labels"][0]
        self.assertTrue(entry["url"].endswith(self.url("sparepartinventory_checkout", self.inventory.pk)))
        self.assertIn("/check-out/", entry["url"])

    def test_labels_render_a_qr_when_the_library_is_available(self):
        response = self.client.get(self.url("bin_labels"), {"inventory": str(self.inventory.pk)})
        if response.context["qr_available"]:
            self.assertIsNotNone(response.context["labels"][0]["qr"])
            self.assertContains(response, "<svg")
        else:
            self.skipTest("segno is not installed in this environment")

    def test_a_viewer_can_print_labels(self):
        """Printing is a read-only act, so view permission is enough."""
        self.user.is_superuser = False
        self.user.save()
        permission = ObjectPermission.objects.create(name="View spare parts", actions=["view"])
        permission.object_types.set(
            ContentType.objects.filter(app_label="nautobot_spare_parts", model="sparepartinventory")
        )
        permission.users.add(self.user)

        response = self.client.get(self.url("bin_labels"), {"inventory": str(self.inventory.pk)})
        self.assertEqual(response.status_code, 200)


class PermissionTestCase(TestCase):
    """A read-only user must not be able to move stock."""

    @classmethod
    def setUpTestData(cls):
        cls.dcim = build_dcim()
        cls.part_type = make_part_type()

    def setUp(self):
        super().setUp()
        self.inventory = make_inventory(self.part_type, self.dcim["location_a"], on_hand=10)

        self.viewer = User.objects.create_user(username="viewer", password="viewer")
        # Nautobot authorises through its own ObjectPermission model, not
        # Django's user_permissions -- granting the Django permission alone
        # would leave the user with no access at all.
        permission = ObjectPermission.objects.create(name="View spare parts", actions=["view"])
        permission.object_types.set(
            ContentType.objects.filter(
                app_label="nautobot_spare_parts",
                model__in=["sparepartinventory", "spareparttransaction", "spareparttype"],
            )
        )
        permission.users.add(self.viewer)
        self.viewer_client = Client()
        self.viewer_client.force_login(self.viewer)

    def url(self, name, *args):
        """Reverse a plugin URL."""
        return reverse(f"plugins:nautobot_spare_parts:{name}", args=args)

    def test_a_viewer_can_read(self):
        for name in ("overview", "low_stock_dashboard", "sparepartinventory_list"):
            with self.subTest(page=name):
                self.assertEqual(self.viewer_client.get(self.url(name)).status_code, 200)

    def test_a_viewer_cannot_open_an_action_page(self):
        for name in (
            "sparepartinventory_checkin",
            "sparepartinventory_checkout",
            "sparepartinventory_allocate",
            "sparepartinventory_transfer",
        ):
            with self.subTest(page=name):
                response = self.viewer_client.get(self.url(name, self.inventory.pk))
                self.assertIn(response.status_code, (302, 403), name)

    def test_a_viewer_cannot_post_a_movement(self):
        response = self.viewer_client.post(
            self.url("sparepartinventory_checkin", self.inventory.pk),
            {"quantity": 5, "reason": "should not work"},
        )
        self.assertIn(response.status_code, (302, 403))
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_on_hand, 10)

    def test_an_anonymous_user_is_sent_to_the_login_page(self):
        response = Client().get(self.url("sparepartinventory_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
