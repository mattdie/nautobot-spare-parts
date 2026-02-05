# Nautobot Spare Parts Inventory Plugin

A Nautobot plugin for tracking spare parts inventory across datacenter locations with quantity management, check-in/out history, device type compatibility, and low stock alerts.

## Features

- **Spare Parts Catalog**: Define spare part types with manufacturer, part number, category, and cost information
- **Location-Based Inventory**: Track quantities at each datacenter/site location
- **Stock Management**: Check-in and check-out workflows with reservation support
- **Audit Trail**: Complete transaction history for all stock movements
- **Low Stock Alerts**: Configurable minimum quantity thresholds with reorder notifications
- **Device Compatibility**: Link parts to compatible device types for easy reference
- **REST API**: Full API support for automation and integration

## Requirements

- Nautobot >= 2.0.0, < 4.0.0
- Python >= 3.8

### Version Compatibility

This plugin is compatible with:
- Nautobot 2.1.x (tested with 2.1.7)
- Nautobot 2.3.x (tested with 2.3.16)
- Nautobot 3.0.x (forward compatible)

See [COMPATIBILITY.md](COMPATIBILITY.md) for detailed version information.

## Installation

1. Install the plugin:
   ```bash
   pip install nautobot-spare-parts
   ```

2. Add to your `nautobot_config.py`:
   ```python
   PLUGINS = [
       "nautobot_spare_parts",
   ]
   ```

3. Run migrations:
   ```bash
   nautobot-server migrate
   ```

4. Restart Nautobot:
   ```bash
   systemctl restart nautobot
   ```

## Usage

### Creating Spare Part Types

1. Navigate to **Spare Parts > Spare Part Types**
2. Click **Add** to create a new part type
3. Fill in manufacturer, part number, category, and other details
4. Optionally link to compatible device types

### Managing Inventory

1. Navigate to **Spare Parts > Inventory**
2. Add inventory records for each location where parts are stored
3. Set minimum quantity thresholds for low stock alerts
4. Use **Check In** and **Check Out** actions to manage stock levels

### Viewing Transaction History

All stock movements are automatically logged in **Spare Parts > Transactions** with timestamp, user, and reason.

### API Usage

```python
import requests

# Get all spare part types
response = requests.get(
    'https://nautobot.example.com/api/plugins/spare-parts/spare-part-types/',
    headers={'Authorization': 'Token YOUR_TOKEN'}
)

# Check out inventory
response = requests.post(
    'https://nautobot.example.com/api/plugins/spare-parts/spare-part-inventory/1/check-out/',
    headers={'Authorization': 'Token YOUR_TOKEN'},
    json={'quantity': 5, 'reason': 'Replace failed component'}
)
```

## Data Models

### SparePartType
Template/definition for types of spare parts. Contains manufacturer info, part numbers, category, unit cost, and compatible device types.

### SparePartInventory
Location-specific inventory records tracking on-hand quantity, reserved quantity, minimum thresholds, and storage location details.

### SparePartTransaction
Audit trail for all stock movements including check-ins, check-outs, adjustments, allocations, and transfers.

## License

Apache License 2.0
