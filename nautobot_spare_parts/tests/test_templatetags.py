"""Tests for the app's own template filters."""

from decimal import Decimal

from django.test import SimpleTestCase

from nautobot_spare_parts.templatetags.spare_parts_helpers import get_item, usd


class UsdFilterTestCase(SimpleTestCase):
    """Every cost figure in this app is USD -- this filter is where that's spelled out."""

    def test_formats_with_dollar_sign_and_thousands_separator(self):
        self.assertEqual(usd(Decimal("12345.6")), "$12,345.60")

    def test_formats_a_plain_int(self):
        self.assertEqual(usd(0), "$0.00")

    def test_negative_value_keeps_the_sign_before_the_dollar_sign(self):
        self.assertEqual(usd(Decimal("-5.5")), "-$5.50")

    def test_none_renders_as_an_em_dash(self):
        self.assertEqual(usd(None), "—")

    def test_garbage_input_renders_as_an_em_dash_instead_of_raising(self):
        self.assertEqual(usd("not a number"), "—")


class GetItemFilterTestCase(SimpleTestCase):
    """Dict lookup by a template variable key, for the category-label mapping."""

    def test_known_key(self):
        self.assertEqual(get_item({"psu": "PSU"}, "psu"), "PSU")

    def test_unknown_key_falls_back_to_the_raw_value(self):
        self.assertEqual(get_item({"psu": "PSU"}, "mystery"), "mystery")

    def test_non_dict_input_falls_back_to_the_raw_value(self):
        self.assertEqual(get_item(None, "psu"), "psu")
