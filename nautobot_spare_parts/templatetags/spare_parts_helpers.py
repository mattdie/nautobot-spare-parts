"""Template filters for the Spare Parts Inventory app.

Every cost figure in this app -- unit_cost, inventory value, consumption
spend -- is a plain DecimalField with no currency field next to it. That is a
deliberate simplification, not an oversight: this app has exactly one
currency, USD, and every number it shows is in USD. The ``usd`` filter is
the one place that fact is spelled out, so nobody reading a dashboard has to
guess what a bare number like ``12345.67`` means.
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def usd(value):
    """Render a number as a USD amount: ``$12,345.67``.

    ``None`` or anything that cannot be read as a number renders as an
    em-dash, matching how the rest of the app shows "nothing to show" rather
    than a confusing ``$0.00`` or a raw error.
    """
    if value is None:
        return "—"
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return "—"
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


@register.filter
def get_item(mapping, key):
    """Dict lookup by a variable key -- ``{{ labels|get_item:row.category }}``.

    Needed because the cost dashboard groups by the raw stored category
    value (``.values("spare_part_type__category")``), which has no model
    instance attached to call ``get_category_display()`` on.
    """
    try:
        return mapping.get(key, key)
    except AttributeError:
        return key
