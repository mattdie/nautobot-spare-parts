"""Move legacy allocation/deallocation numbers into the reserved_* columns.

Before this release, allocation and deallocation rows stored the *reserved*
counts in ``quantity``, ``quantity_before`` and ``quantity_after`` -- the same
columns stock movements used for on-hand counts. That made the log ambiguous:
you could not tell from a row whether "before 4, after 6" meant stock or
reservations.

The two are now separate, so the historical rows are moved across. The on-hand
figures for those old rows are genuinely not recorded anywhere, so they are set
to the record's current on-hand count with a zero delta, which keeps the
"before + delta == after" invariant true without inventing a stock movement
that never happened.
"""

from django.db import migrations


def move_reservation_numbers(apps, schema_editor):
    """Rewrite historical allocation/deallocation rows."""
    SparePartTransaction = apps.get_model("nautobot_spare_parts", "SparePartTransaction")

    rows = SparePartTransaction.objects.filter(
        transaction_type__in=["allocation", "deallocation"]
    ).select_related("spare_part_inventory")

    for row in rows.iterator():
        on_hand = row.spare_part_inventory.quantity_on_hand
        row.reserved_delta = row.quantity
        row.reserved_before = row.quantity_before
        row.reserved_after = row.quantity_after
        row.quantity = 0
        row.quantity_before = on_hand
        row.quantity_after = on_hand
        row.save(
            update_fields=[
                "reserved_delta",
                "reserved_before",
                "reserved_after",
                "quantity",
                "quantity_before",
                "quantity_after",
            ]
        )


def undo(apps, schema_editor):
    """Put the reserved numbers back into the quantity columns."""
    SparePartTransaction = apps.get_model("nautobot_spare_parts", "SparePartTransaction")

    rows = SparePartTransaction.objects.filter(transaction_type__in=["allocation", "deallocation"])
    for row in rows.iterator():
        row.quantity = row.reserved_delta
        row.quantity_before = row.reserved_before
        row.quantity_after = row.reserved_after
        row.save(update_fields=["quantity", "quantity_before", "quantity_after"])


class Migration(migrations.Migration):
    """Data migration for the split of stock and reservation columns."""

    dependencies = [
        ("nautobot_spare_parts", "0004_audit_trail_and_constraints"),
    ]

    operations = [
        migrations.RunPython(move_reservation_numbers, undo),
    ]
