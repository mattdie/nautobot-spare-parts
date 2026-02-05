# Nautobot Spare Parts Inventory Plugin

## Overview

This plugin adds spare parts inventory management to Nautobot. It was built to solve a common problem in datacenter operations: keeping track of spare hardware across multiple locations. Whether you need to know how many Cat6 cables are in LON1 or if you have enough NVMe drives in stock for the next server refresh, this plugin handles it.

The plugin works with Nautobot v2.1.7 and later versions, including v3.0. It integrates with your existing Nautobot setup, using the same location hierarchy, device types, and manufacturers you already have configured.

## Why We Built This

Running a datacenter means having spare parts on hand. When a drive fails or you need to cable up a new rack, you need to know what's available and where it is. Before this plugin, teams were tracking this in spreadsheets or separate systems, which meant:
- No integration with Nautobot's existing infrastructure data
- No audit trail of who took what and why
- Manual tracking of stock levels
- No connection to the actual devices being maintained

This plugin brings spare parts management directly into Nautobot, where it belongs alongside your other infrastructure data.

## What It Does

### Managing Spare Part Types

You start by defining the types of spare parts you stock. Each spare part type includes basic information like the manufacturer, part number, category (Network, Storage, Memory, etc.), and unit cost. You can link parts to specific device types they're compatible with, add tags for organization, and use custom fields if you need additional attributes.

### Tracking Inventory by Location

The actual inventory lives at specific locations in your Nautobot setup. For each spare part type at each location, you track how many you have on hand, set a minimum quantity that triggers low-stock alerts, and define a reorder quantity. You can also record detailed storage information like which rack, shelf, or bin the parts are in.

The plugin calculates available quantity automatically by subtracting any reserved quantities from what's on hand. This is useful when you've allocated parts for upcoming maintenance but haven't physically used them yet.

### Check In and Check Out

This is the core workflow. When you need to use a spare part, you check it out. When you receive new parts or return unused ones, you check them in. There's also a manual adjustment option for fixing inventory count errors.

Every transaction requires a reason. This isn't just bureaucracy - it creates an audit trail. When someone asks "where did those five NVMe drives go?" you can see exactly who took them, when, and why. You can optionally associate transactions with specific devices, which is especially useful for tracking which parts went into which servers.

### Transaction History

All check-ins and check-outs are logged permanently. Each transaction record includes the quantity moved, the before and after inventory levels, who did it, when they did it, and why. This creates a complete audit trail that survives far longer than anyone's memory of moving parts around three months ago.

### Low Stock Monitoring

The low stock dashboard shows everything that's below minimum quantity. It also indicates which items need reordering based on your configured reorder quantities. This saves you from manually checking stock levels or discovering you're out of parts when you need them.

### Integration with Nautobot

The plugin uses Nautobot's existing data structures wherever possible. It uses your Location hierarchy, so you can track parts at whatever granularity makes sense for your organization. It links to Manufacturers and Device Types you've already defined. Transactions can reference specific Devices. Everything is exposed through the REST API and works with GraphQL.

---

## Installation

You'll need Nautobot 2.1.7 or later. The plugin works with Python 3.8 and up, and supports both PostgreSQL and MySQL.

Install the plugin:

```bash
pip install /path/to/nautobot-spare-parts
```

Add it to your Nautobot configuration in `nautobot_config.py`:

```python
PLUGINS = [
    "nautobot_spare_parts",
]

PLUGINS_CONFIG = {
    "nautobot_spare_parts": {
        # Configuration options go here if needed
    }
}
```

Run the database migrations:

```bash
nautobot-server migrate
```

Restart Nautobot:

```bash
# For systemd deployments
sudo systemctl restart nautobot nautobot-worker

# For Docker deployments
docker compose restart nautobot celery_worker
```

After restarting, you'll see "Spare Parts" in the Nautobot navigation menu.

---

## How to Use It

### Setting Up Your First Spare Parts

Start by creating spare part types. Go to Spare Parts > Spare Part Types and add the parts you stock. For example, if you keep Samsung NVMe drives on hand:

- Name: Samsung 980 PRO 1TB
- Manufacturer: Samsung
- Category: Storage
- Part Number: MZ-V8P1T0BW
- Unit Cost: $129.99
- Compatible Device Types: Select the server models that use these drives

Or for something simpler like network cables:

- Name: Cat6 Ethernet Cable - 3ft Blue
- Manufacturer: Monoprice
- Category: Network
- Part Number: CAT6-3FT-BL
- Unit Cost: $2.99

Once you have spare part types defined, add inventory to your locations. Go to Spare Parts > Inventory and click Add. For each location where you stock parts:

- Spare Part Type: Samsung 980 PRO 1TB
- Location: LON1
- Quantity on Hand: 10
- Minimum Quantity: 3
- Reorder Quantity: 5
- Storage Location Detail: Rack A12, Shelf 3, Bin 7

The storage location detail is optional but useful. Six months from now when you need one of these drives, you'll be glad you wrote down where they are.

### Checking Out Parts

When you need to use a spare part, go to Spare Parts > Inventory and click on the item. You'll see Check In and Check Out buttons at the top of the page. Click Check Out (the yellow one) and fill in the form:

- Quantity: How many you're taking
- Reason: Why you're taking them (be specific - "Replacing failed drive in LON1-WEB-01" not just "needed it")
- Related Device: Optional but recommended - select the device you're working on
- Notes: Any additional context

When you submit, the inventory count drops automatically and a transaction record is created with your username and timestamp.

### Checking In Parts

Checking in works the same way but in reverse. Click the green Check In button when you receive new parts or return unused ones. Fill in the quantity and reason ("Received shipment - PO #12345" or "Returned unused part from maintenance window").

### Watching Stock Levels

The Low Stock Dashboard (Spare Parts > Low Stock Dashboard) shows everything below minimum quantity. Check this regularly to know what needs reordering before you run out.

---

## Real-World Examples

### Emergency Drive Replacement

It's 2 AM and a drive failed in LON1-DB-03. You grab a spare Samsung 980 PRO from the storage rack, pop it in, and start the rebuild. In the morning, you log into Nautobot:

1. Find the Samsung 980 PRO 1TB inventory for LON1
2. Click Check Out
3. Enter quantity 1, reason "Emergency replacement for failed drive in LON1-DB-03", select LON1-DB-03 as the related device
4. Submit

Now the inventory shows 9 drives instead of 10, there's a transaction record with your name on it showing exactly which device got the new drive, and if this drops you below your minimum stock level of 3, it'll show up on the low stock dashboard.

### Receiving a Shipment

A box of Cat6 cables arrives. You sign for it, put them in the storage area, and update Nautobot:

1. Go to Cat6 Ethernet Cable - 3ft inventory for AUS1
2. Click Check In
3. Enter quantity 50, reason "Received shipment - PO #12345"
4. Add notes with vendor and invoice info for reference
5. Submit

The stock level updates and you have a record of when the shipment came in, tied to the purchase order number.

### Inventory Audit

You're doing a physical count and find 8 cables on the shelf, but Nautobot says there should be 12. Rather than just updating the number, you create a transaction:

1. Go to the inventory item
2. Check out 4 units (even though you're not physically taking them - you're just correcting the count)
3. Reason: "Inventory adjustment - physical count discrepancy"
4. Submit

Now the count matches reality and there's a record of when and why it was adjusted. This helps spot patterns - if you're constantly adjusting the same items, maybe they're being used without being logged.

---

## Technical Details

### Database Models

**SparePartType**
- Defines the type of spare part
- Links to Manufacturer
- Specifies category and specifications
- Supports tags and custom fields

**SparePartInventory**
- Tracks quantity at specific locations
- Calculated fields: quantity_available, is_low_stock
- Relationships: spare_part_type, location

**SparePartTransaction**
- Audit log of all inventory movements
- Types: check_in, check_out, manual_adjust
- Records: quantity, before/after values, user, timestamp, reason
- Optional device association

### REST API

All models are exposed via REST API:

```bash
# List inventory
GET /api/plugins/spare-parts/spare-part-inventory/

# Get specific inventory item
GET /api/plugins/spare-parts/spare-part-inventory/{uuid}/

# Create spare part type
POST /api/plugins/spare-parts/spare-part-types/
Content-Type: application/json
{
  "name": "Dell PowerEdge R740 PSU",
  "manufacturer": "<manufacturer-uuid>",
  "category": "power",
  "part_number": "450-AEIE"
}

# Check out parts (custom endpoint)
POST /api/plugins/spare-parts/spare-part-inventory/{uuid}/check-out/
Content-Type: application/json
{
  "quantity": 1,
  "reason": "Replacement for failed PSU",
  "related_device": "<device-uuid>"
}
```

### Permissions

The plugin respects Nautobot's object-level permissions:
- `nautobot_spare_parts.view_spareparttype`
- `nautobot_spare_parts.add_sparepartinventory`
- `nautobot_spare_parts.change_sparepartinventory`
- `nautobot_spare_parts.delete_sparepartinventory`
- etc.

### Version Compatibility

| Nautobot Version | Support Status | Notes |
|-----------------|----------------|-------|
| 2.1.7 - 2.1.x   | Fully supported | Tested and working |
| 2.2.x           | Fully supported | Compatible |
| 2.3.x           | Fully supported | Tested and working |
| 3.0.x           | Forward compatible | Ready when you upgrade |

The plugin uses version detection internally to handle API differences between Nautobot versions.

---

## Configuration

Right now the plugin works with default settings. No configuration is required in PLUGINS_CONFIG. Future versions might add options like:

```python
PLUGINS_CONFIG = {
    "nautobot_spare_parts": {
        # Possible future options
        "enable_automatic_reordering": False,
        "low_stock_notification_email": "inventory@example.com",
        "require_device_association": False,
    }
}
```

---

## User Interface

The inventory list shows all your parts. Click any spare part type name to see details for that inventory item. The tables are clean - no primary key columns cluttering up the view.

On the inventory detail page, you'll see Check In (green) and Check Out (yellow) buttons at the top. They're hard to miss. Below the main details, there's a list of recent transactions showing the last 20 movements for that inventory item.

Low stock items get visual indicators. The Low Stock Dashboard gives you a dedicated view of everything that needs attention, with "Needs Reorder" badges for items below their reorder threshold.

---

## Best Practices

### Naming Parts

Use clear, descriptive names that include the manufacturer and key specs. "Samsung 980 PRO 1TB" is much better than "SSD1" or "NVMe drive." Six months from now, you won't remember what "SSD1" refers to, but "Samsung 980 PRO 1TB" is unambiguous. Keep part numbers consistent with your procurement system.

### Setting Stock Levels

For minimum quantity, think about your typical monthly usage and multiply by 2-3. That gives you enough buffer to reorder without running out. For reorder quantity, consider your vendor's lead time. If it takes two weeks to get parts and you use 10 per month, ordering 10 at a time might leave you short. Review these numbers quarterly and adjust based on actual usage patterns.

### Writing Good Transaction Reasons

Be specific in your transaction reasons. "Replaced failed drive in LON1-WEB-01" tells the story. "Needed drive" doesn't help anyone. Include device names when applicable and reference ticket numbers or work orders if you have them. This makes auditing and troubleshooting much easier later.

### Organizing Storage Locations

Use a consistent format for storage locations. "Rack A12, Shelf 3, Bin 7" works well. Keep frequently-used items in easily accessible spots. Document the storage location in the inventory record because you won't remember where you put things three months from now.

### Regular Audits

Do physical counts quarterly. When you find discrepancies, don't just silently fix the numbers - use the manual adjustment transaction type and document why there's a difference. Review the transaction history to spot patterns. If the same items keep getting adjusted, maybe people are using them without logging it.

---

## Troubleshooting

### Can't see inventory items in the list

Check your permissions. You need the `view_sparepartinventory` permission to see inventory items.

### Check In and Check Out buttons aren't showing up

Make sure you have the `change_sparepartinventory` permission. Also verify you're on the detail page for an inventory item, not the list page. Click on a spare part type name in the inventory list to get to the detail page where the buttons are.

### Low stock dashboard is empty

The dashboard only shows items where the quantity on hand is below the minimum quantity. If it's empty, either nothing is low or you haven't set minimum quantities on your inventory items yet.

### Transactions aren't being created

Check that you filled in all required fields, particularly quantity and reason. If everything looks right but it's still not working, check the Nautobot logs for error messages.

---

## Development

### Local Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd nautobot-spare-parts

# Install in development mode
pip install -e .

# Or with poetry
poetry install

# Run tests
poetry run pytest

# Check code quality
poetry run black .
poetry run pylint nautobot_spare_parts
```

### Docker Development Environment

```bash
# Navigate to development environment
cd ~/projects/nautobot-local-dev

# Start services
docker compose up -d

# Access Nautobot
# URL: http://localhost:8000
# Username: admin
# Password: admin

# View logs
docker compose logs -f nautobot

# Restart after changes
docker compose restart nautobot celery_worker
```

---

## Future Plans

There are a few features we're considering for future versions:

- Email notifications when stock drops below minimum levels
- Automatic generation of reorder requests or purchase requisitions
- Barcode or QR code scanning for faster check-in/check-out
- Better mobile interface for warehouse use
- Bulk operations for checking in or out multiple items at once
- Integration with procurement or ticketing systems
- More detailed reporting and analytics
- Multi-currency support for international deployments

These aren't promises, just ideas based on how people are using the plugin.

---

## Support

### Getting Help
- Check the documentation first
- Review transaction history for audit trails
- Check Nautobot logs for errors: `docker compose logs nautobot`

### Reporting Issues
When reporting issues, include:
- Nautobot version
- Plugin version
- Steps to reproduce
- Error messages or logs
- Expected vs actual behavior

---

## About This Plugin

This plugin was developed to solve real datacenter inventory management problems. It's compatible with Nautobot 2.1.7 through 3.0 and later versions. Licensed under Apache 2.0.

Current feature set includes:
- Spare part type management with categories and specifications
- Location-based inventory tracking with min/max levels
- Check in and check out workflows with audit trails
- Complete transaction history with user attribution
- Low stock monitoring and alerts
- Full REST API and GraphQL support
- Multi-version Nautobot compatibility
- Clean user interface with clickable inventory items

---

## Quick Reference

To navigate the plugin:
- Add a spare part type: Spare Parts > Spare Part Types > Add
- Add inventory: Spare Parts > Inventory > Add
- Check out parts: Spare Parts > Inventory > click the item > Check Out button
- View transactions: Spare Parts > Transactions
- See low stock: Spare Parts > Low Stock Dashboard

Tips for daily use:
- Write clear reasons for every check-in and check-out
- Link transactions to specific devices whenever possible
- Set minimum quantities based on actual usage patterns
- Document storage locations so you can find parts later
- Review the low stock dashboard regularly

---

## Example Inventory Setup

### Network Equipment Spare Parts
```
Location: LON1 (London)

1. Cat6 Ethernet Cable - 1ft (Qty: 50, Min: 20)
2. Cat6 Ethernet Cable - 3ft (Qty: 100, Min: 30)
3. Cat6 Ethernet Cable - 6ft (Qty: 75, Min: 25)
4. SFP+ 10G Transceiver (Qty: 20, Min: 5)
5. QSFP+ 40G Transceiver (Qty: 10, Min: 3)
```

### Server Components
```
Location: AUS1 (Austin)

1. Samsung 980 PRO 1TB NVMe (Qty: 15, Min: 5)
2. Micron 32GB DDR4 RAM (Qty: 40, Min: 10)
3. Intel Xeon Gold 6248R CPU (Qty: 4, Min: 2)
4. NVIDIA A100 GPU (Qty: 2, Min: 1)
```

### Power & Cooling
```
Location: NYC1 (New York)

1. Dell R740 PSU 750W (Qty: 8, Min: 3)
2. APC UPS Battery (Qty: 6, Min: 2)
3. Server Fan 80mm (Qty: 25, Min: 10)
```

---

**End of Documentation**

For the latest updates and version information, see the project repository.
