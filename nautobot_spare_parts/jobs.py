"""Jobs shipped with the app.

Registering Jobs is what lets this run on a schedule through Nautobot's own
scheduler, with its own job result, log and approval machinery -- rather than a
cron job on somebody's laptop.
"""

from datetime import timedelta

from django.db.models import Max, Q, Sum
from django.utils import timezone

from nautobot.apps.jobs import BooleanVar, IntegerVar, Job, ObjectVar, register_jobs
from nautobot.dcim.models import Location

from nautobot_spare_parts import zulip
from nautobot_spare_parts.filters import SparePartInventoryFilterSet
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
        ).filter(SparePartInventoryFilterSet.low_stock_q())
        if location is not None:
            queryset = queryset.filter(location=location)

        records = sorted(queryset, key=lambda record: record.quantity_available - record.minimum_quantity)

        if not records:
            self.logger.info("Nothing is below its minimum.")
            if notify_zulip:
                zulip.notify_job(self.logger, "Spare Parts Low Stock Report: nothing is below its minimum.")
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
                f"**Spare Parts Low Stock Report** — {len(records)} part(s) below minimum",
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
    A reservation counts as stale once nothing has touched the record's
    reserved pool for ``older_than_days``.
    """

    older_than_days = IntegerVar(
        default=14,
        min_value=0,
        label="Untouched for (days)",
        description="Only report reservations with no allocate/deallocate/fulfilling check-out in this many days.",
    )
    notify_zulip = NOTIFY_ZULIP_VAR

    class Meta:
        """Job metadata."""

        name = "Stale Reservations Report"
        description = "List reserved stock nobody has touched in a while, and the Jira tickets still holding it."
        read_only = True
        has_sensitive_variables = False

    def run(self, older_than_days=14, notify_zulip=False):  # pylint: disable=arguments-differ
        """Log each stale reservation, plus the tickets that still hold units of it."""
        cutoff = timezone.now() - timedelta(days=older_than_days)
        records = list(
            SparePartInventory.objects.filter(quantity_reserved__gt=0)
            .annotate(last_reserved_change=Max("transactions__timestamp", filter=~Q(transactions__reserved_delta=0)))
            .filter(Q(last_reserved_change__lte=cutoff) | Q(last_reserved_change__isnull=True))
            .select_related("spare_part_type", "location")
        )
        if not records:
            self.logger.info("No reservation has been left untouched for %s day(s).", older_than_days)
            if notify_zulip:
                zulip.notify_job(
                    self.logger,
                    f"Spare Parts Stale Reservations Report: nothing reserved for over {older_than_days} day(s).",
                )
            return "0 stale reservations."

        # Net units each ticket still holds per record: allocations add,
        # deallocations and fulfilling check-outs subtract. A ticket at 0 has
        # been dealt with and is not worth chasing.
        open_tickets = {}
        for row in (
            SparePartTransaction.objects.filter(spare_part_inventory__in=records)
            .exclude(jira_ticket="")
            .values("spare_part_inventory_id", "jira_ticket")
            .annotate(net=Sum("reserved_delta"))
            .filter(net__gt=0)
        ):
            open_tickets.setdefault(row["spare_part_inventory_id"], []).append(row["jira_ticket"])

        lines = [
            f"**Spare Parts Stale Reservations Report** — {len(records)} record(s) with reservations "
            f"untouched for over {older_than_days} day(s)",
            "",
        ]
        for record in records:
            tickets = sorted(open_tickets.get(record.pk, []))
            ticket_note = f" (still held by {', '.join(tickets)})" if tickets else ""
            age = (
                f"last changed {record.last_reserved_change:%Y-%m-%d}"
                if record.last_reserved_change
                else "no reservation history"
            )
            self.logger.warning(
                "%s at %s: %s reserved, %s%s",
                record.spare_part_type,
                record.location,
                record.quantity_reserved,
                age,
                ticket_note,
                extra={"object": record},
            )
            lines.append(
                f"- **{record.spare_part_type}** at {record.location}: {record.quantity_reserved} reserved, "
                f"{age}{ticket_note}"
            )

        if notify_zulip:
            zulip.notify_job(self.logger, "\n".join(lines))

        return f"{len(records)} stale reservation(s)."


jobs = [LowStockReport, StaleReservationsReport]
register_jobs(*jobs)
