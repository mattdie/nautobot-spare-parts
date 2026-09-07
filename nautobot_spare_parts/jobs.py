"""Jobs shipped with the app.

Registering Jobs is what lets this run on a schedule through Nautobot's own
scheduler, with its own job result, log and approval machinery -- rather than a
cron job on somebody's laptop.
"""

from django.db.models import F, Q

from nautobot.apps.jobs import BooleanVar, Job, ObjectVar, register_jobs
from nautobot.dcim.models import Location

from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction

name = "Spare Parts"


class LowStockReport(Job):
    """Report every stock-managed part at or below its reorder threshold."""

    location = ObjectVar(
        model=Location,
        required=False,
        description="Limit the report to one location. Leave blank for all.",
    )
    only_with_reorder_quantity = BooleanVar(
        default=False,
        label="Only parts with a reorder quantity set",
        description="Useful when the output is going to feed a purchase order.",
    )

    class Meta:
        """Job metadata."""

        name = "Low Stock Report"
        description = "List spare parts at or below their minimum, with the shortfall and suggested reorder."
        read_only = True
        has_sensitive_variables = False

    def run(self, location=None, only_with_reorder_quantity=False):  # pylint: disable=arguments-differ
        """Log the low-stock lines, worst shortfall first."""
        queryset = SparePartInventory.objects.select_related(
            "spare_part_type", "spare_part_type__manufacturer", "location"
        ).filter(Q(minimum_quantity__gt=0) & Q(quantity_on_hand__lte=F("minimum_quantity") + F("quantity_reserved")))
        if location is not None:
            queryset = queryset.filter(location=location)
        if only_with_reorder_quantity:
            queryset = queryset.filter(reorder_quantity__gt=0)

        records = sorted(queryset, key=lambda record: record.quantity_available - record.minimum_quantity)

        if not records:
            self.logger.info("Nothing is below its minimum.")
            return "0 parts below minimum."

        for record in records:
            shortfall = record.minimum_quantity - record.quantity_available
            self.logger.warning(
                "%s short by %s (available %s, minimum %s, reorder %s)",
                record.spare_part_type,
                shortfall,
                record.quantity_available,
                record.minimum_quantity,
                record.reorder_quantity or "not set",
                extra={"object": record},
            )

        no_reorder = [record for record in records if not record.reorder_quantity]
        if no_reorder:
            self.logger.info(
                "%s of these have no reorder quantity set, so nobody knows how many to buy.",
                len(no_reorder),
            )

        return f"{len(records)} part(s) below minimum."


class StaleReservationsReport(Job):
    """Find reservations that were never consumed or released.

    Stock reserved for work that already happened is the main way the available
    counts drift away from reality, and nothing else in the app nags about it.
    """

    class Meta:
        """Job metadata."""

        name = "Stale Reservations Report"
        description = "List locations holding reserved stock, and the Jira tickets they were reserved for."
        read_only = True
        has_sensitive_variables = False

    def run(self):  # pylint: disable=arguments-differ
        """Log each record with stock reserved, plus the tickets involved."""
        records = SparePartInventory.objects.filter(quantity_reserved__gt=0).select_related(
            "spare_part_type", "location"
        )
        if not records:
            self.logger.info("No stock is reserved anywhere.")
            return "0 records with reservations."

        for record in records:
            tickets = (
                SparePartTransaction.objects.filter(
                    spare_part_inventory=record,
                    transaction_type="allocation",
                )
                .exclude(jira_ticket="")
                .values_list("jira_ticket", flat=True)
                .distinct()
            )
            self.logger.warning(
                "%s at %s: %s reserved%s",
                record.spare_part_type,
                record.location,
                record.quantity_reserved,
                f" (allocated against {', '.join(sorted(set(tickets)))})" if tickets else "",
                extra={"object": record},
            )

        return f"{len(records)} record(s) holding reserved stock."


jobs = [LowStockReport, StaleReservationsReport]
register_jobs(*jobs)
