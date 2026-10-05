"""Jobs shipped with the app.

Registering Jobs is what lets this run on a schedule through Nautobot's own
scheduler, with its own job result, log and approval machinery -- rather than a
cron job on somebody's laptop.
"""

from django.db.models import F, Q

from nautobot.apps.jobs import BooleanVar, Job, ObjectVar, register_jobs
from nautobot.dcim.models import Location

from nautobot_spare_parts import zulip
from nautobot_spare_parts.models import SparePartInventory, SparePartTransaction

NOTIFY_ZULIP_VAR = BooleanVar(
    default=False,
    label="Post to Zulip",
    description=(
        "Also post this report to Zulip. No-op if no webhook is configured. "
        "Off by default -- this is an explicit choice every run, not a standing subscription."
    ),
)

name = "Spare Parts"


class LowStockReport(Job):
    """Report every stock-managed part at or below its reorder threshold."""

    location = ObjectVar(
        model=Location,
        required=False,
        description="Limit the report to one location. Leave blank for all.",
    )
    notify_zulip = NOTIFY_ZULIP_VAR

    class Meta:
        """Job metadata."""

        name = "Low Stock Report"
        description = "List spare parts at or below their minimum, with the shortfall and suggested reorder."
        read_only = True
        has_sensitive_variables = False

    def run(self, location=None, notify_zulip=False):  # pylint: disable=arguments-differ
        """Log the low-stock lines, worst shortfall first."""
        queryset = SparePartInventory.objects.select_related(
            "spare_part_type", "spare_part_type__manufacturer", "location"
        ).filter(Q(minimum_quantity__gt=0) & Q(quantity_on_hand__lte=F("minimum_quantity") + F("quantity_reserved")))
        if location is not None:
            queryset = queryset.filter(location=location)

        records = sorted(queryset, key=lambda record: record.quantity_available - record.minimum_quantity)

        if not records:
            self.logger.info("Nothing is below its minimum.")
            if notify_zulip:
                zulip.notify_job(self.logger, "✅ Spare Parts Low Stock Report: nothing is below its minimum.")
            return "0 parts below minimum."

        for record in records:
            shortfall = record.minimum_quantity - record.quantity_available
            self.logger.warning(
                "%s short by %s (available %s, minimum %s)",
                record.spare_part_type,
                shortfall,
                record.quantity_available,
                record.minimum_quantity,
                extra={"object": record},
            )

        if notify_zulip:
            lines = [
                f"⚠️ **Spare Parts Low Stock Report** — {len(records)} part(s) below minimum",
                "",
            ]
            for record in records[:20]:
                shortfall = record.minimum_quantity - record.quantity_available
                lines.append(f"- **{record.spare_part_type}** at {record.location}: short by {shortfall}")
            if len(records) > 20:
                lines.append(f"- …and {len(records) - 20} more")
            zulip.notify_job(self.logger, "\n".join(lines))

        return f"{len(records)} part(s) below minimum."


class StaleReservationsReport(Job):
    """Find reservations that were never consumed or released.

    Stock reserved for work that already happened is the main way the available
    counts drift away from reality, and nothing else in the app nags about it.
    """

    notify_zulip = NOTIFY_ZULIP_VAR

    class Meta:
        """Job metadata."""

        name = "Stale Reservations Report"
        description = "List locations holding reserved stock, and the Jira tickets they were reserved for."
        read_only = True
        has_sensitive_variables = False

    def run(self, notify_zulip=False):  # pylint: disable=arguments-differ
        """Log each record with stock reserved, plus the tickets involved."""
        records = SparePartInventory.objects.filter(quantity_reserved__gt=0).select_related(
            "spare_part_type", "location"
        )
        if not records:
            self.logger.info("No stock is reserved anywhere.")
            if notify_zulip:
                zulip.notify_job(self.logger, "✅ Spare Parts Stale Reservations Report: nothing is reserved anywhere.")
            return "0 records with reservations."

        lines = [f"⚠️ **Spare Parts Stale Reservations Report** — {len(records)} record(s) holding reserved stock", ""]
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
            ticket_note = f" (allocated against {', '.join(sorted(set(tickets)))})" if tickets else ""
            self.logger.warning(
                "%s at %s: %s reserved%s",
                record.spare_part_type,
                record.location,
                record.quantity_reserved,
                ticket_note,
                extra={"object": record},
            )
            lines.append(
                f"- **{record.spare_part_type}** at {record.location}: {record.quantity_reserved} reserved{ticket_note}"
            )

        if notify_zulip:
            zulip.notify_job(self.logger, "\n".join(lines))

        return f"{len(records)} record(s) holding reserved stock."


jobs = [LowStockReport, StaleReservationsReport]
register_jobs(*jobs)
