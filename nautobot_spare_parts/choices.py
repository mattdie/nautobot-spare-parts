"""Choice sets for the Spare Parts Inventory app.

Using Nautobot's ChoiceSet (rather than bare tuples on the model) is what makes
the values show up correctly in the REST API schema, GraphQL and dynamic
filter forms.
"""

from nautobot.apps.choices import ChoiceSet


class SparePartCategoryChoices(ChoiceSet):
    """Physical category of a spare part."""

    RAM = "ram"
    DIMM = "dimm"
    CABLE = "cable"
    CABLE_FIBER = "cable_fiber"
    CABLE_COPPER = "cable_copper"
    TRANSCEIVER = "transceiver"
    PSU = "psu"
    HDD = "hdd"
    SSD = "ssd"
    NVME = "nvme"
    NIC = "nic"
    FAN = "fan"
    MOTHERBOARD = "motherboard"
    CPU = "cpu"
    GPU = "gpu"
    RAID_CARD = "raid_card"
    RISER = "riser"
    OTHER = "other"

    CHOICES = (
        (RAM, "RAM"),
        (DIMM, "DIMM"),
        (CABLE, "Cable"),
        (CABLE_FIBER, "Cable (Fiber)"),
        (CABLE_COPPER, "Cable (Copper)"),
        (TRANSCEIVER, "Transceiver"),
        (PSU, "PSU"),
        (HDD, "HDD"),
        (SSD, "SSD"),
        (NVME, "NVMe"),
        (NIC, "NIC"),
        (FAN, "Fan"),
        (MOTHERBOARD, "Motherboard"),
        (CPU, "CPU"),
        (GPU, "GPU"),
        (RAID_CARD, "RAID Card"),
        (RISER, "Riser"),
        (OTHER, "Other"),
    )

    #: Categories that physically live inside a device, as opposed to
    #: interconnects (cables, transceivers) that are consumed but never show
    #: up as one of the device's own components. Checking one of these out
    #: against a device creates/replaces a matching Nautobot InventoryItem.
    DEVICE_COMPONENT_CATEGORIES = frozenset(
        {RAM, DIMM, PSU, HDD, SSD, NVME, NIC, FAN, MOTHERBOARD, CPU, GPU, RAID_CARD, RISER}
    )


class FailureReasonChoices(ChoiceSet):
    """Why the old part was consumed/removed, captured on check-out.

    Optional on every check-out, but cheap to ask for and the entire value of
    the vendor/model reliability analysis downstream depends on it being
    there -- a check-out with no failure reason is a data gap, not a feature.
    """

    DOA = "doa"
    WEAR = "wear"
    PHYSICAL_DAMAGE = "physical_damage"
    PROACTIVE = "proactive"
    UNKNOWN = "unknown"
    OTHER = "other"

    CHOICES = (
        (DOA, "Dead on arrival"),
        (WEAR, "Wear / age"),
        (PHYSICAL_DAMAGE, "Physical damage"),
        (PROACTIVE, "Proactive replacement (not a failure)"),
        (UNKNOWN, "Unknown"),
        (OTHER, "Other"),
    )


class SparePartTransactionTypeChoices(ChoiceSet):
    """Kind of stock movement recorded in the audit trail.

    Each type says exactly which counters it is allowed to move:

    ==============  ================  ==================
    type            quantity (hand)   reserved
    ==============  ================  ==================
    check_in        + only            unchanged
    check_out       - only            unchanged or - (when fulfilling)
    adjustment      + or - (not 0)    unchanged
    transfer        + or - (not 0)    unchanged
    allocation      unchanged         + only
    deallocation    unchanged         - only
    ==============  ================  ==================
    """

    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    ADJUSTMENT = "adjustment"
    ALLOCATION = "allocation"
    DEALLOCATION = "deallocation"
    TRANSFER = "transfer"

    CHOICES = (
        (CHECK_IN, "Check In"),
        (CHECK_OUT, "Check Out"),
        (ADJUSTMENT, "Adjustment"),
        (ALLOCATION, "Allocation"),
        (DEALLOCATION, "Deallocation"),
        (TRANSFER, "Transfer"),
    )

    #: Types that move quantity_on_hand.
    STOCK_TYPES = (CHECK_IN, CHECK_OUT, ADJUSTMENT, TRANSFER)
    #: Types that move quantity_reserved only.
    RESERVATION_TYPES = (ALLOCATION, DEALLOCATION)
