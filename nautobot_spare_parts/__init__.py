"""Nautobot Spare Parts Inventory app."""

from importlib import metadata

from nautobot.apps import NautobotAppConfig

try:
    __version__ = metadata.version("nautobot-spare-parts")
except metadata.PackageNotFoundError:  # running straight off a source checkout
    __version__ = "2.0.0"


class NautobotSparePartsConfig(NautobotAppConfig):
    """App configuration for nautobot_spare_parts."""

    name = "nautobot_spare_parts"
    verbose_name = "Spare Parts Inventory"
    version = __version__
    author = "Matthijs Diemel"
    description = (
        "Track spare parts stock across datacenter locations with reservations, transfers "
        "and a complete audit trail."
    )
    base_url = "spare-parts"
    required_settings = []
    # Verified against 3.0.11 (see COMPATIBILITY.md). The version range is
    # deliberately narrow: the UI templates target Nautobot 3's Bootstrap 5
    # markup, so claiming 2.x support would be claiming something untested.
    min_version = "3.0.0"
    max_version = "3.99"
    default_settings = {}
    # Puts these models in Nautobot's global search (the Cmd-K box), so looking
    # up a part number works the same way as looking up a device.
    searchable_models = ["spareparttype", "sparepartinventory"]

    def ready(self):
        """Register signal handlers once the app registry is populated."""
        super().ready()
        from nautobot_spare_parts import signals  # noqa: F401  (registers receivers)


config = NautobotSparePartsConfig
