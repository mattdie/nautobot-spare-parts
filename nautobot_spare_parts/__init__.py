"""Nautobot Spare Parts Inventory Plugin."""

from nautobot.apps import NautobotAppConfig


class NautobotSparePartsConfig(NautobotAppConfig):
    """Plugin configuration for nautobot_spare_parts."""

    name = "nautobot_spare_parts"
    verbose_name = "Spare Parts Inventory"
    version = "1.0.0"
    author = "Your Name"
    author_email = "your.email@example.com"
    description = "Track spare parts inventory across datacenter locations with quantity management and audit trails"
    base_url = "spare-parts"
    required_settings = []
    min_version = "2.0.0"
    max_version = "3.9999"
    default_settings = {}

    def ready(self):
        """Register signals when Django app is ready."""
        super().ready()
        import nautobot_spare_parts.signals  # noqa: F401


config = NautobotSparePartsConfig
