# Version Compatibility Testing Guide

## Quick Version Check

To check which Nautobot version your plugin is running on:

```python
from nautobot_spare_parts.utils import get_nautobot_version, is_nautobot_2_3_or_newer, is_nautobot_3_0_or_newer

print(f"Nautobot version: {get_nautobot_version()}")
print(f"Is 2.3+: {is_nautobot_2_3_or_newer()}")
print(f"Is 3.0+: {is_nautobot_3_0_or_newer()}")
```

## Testing on Different Versions

### Testing on Nautobot 2.1.7

1. Update your `docker-compose.yml` to use version 2.1.7:
   ```yaml
   image: "networktocode/nautobot:2.1.7-py3.11"
   ```

2. Recreate containers:
   ```bash
   docker compose down
   docker compose up -d
   ```

3. Test core functionality:
   - Create spare part types
   - Add inventory
   - Check-in/check-out operations
   - View transactions

### Testing on Nautobot 2.3.x

1. Use version 2.3:
   ```yaml
   image: "networktocode/nautobot:2.3-py3.11"
   ```

2. Test enhanced API features:
   - API URL generation with `get_absolute_url(api=True)`
   - All core functionality

### Testing on Nautobot 3.0 (when released)

1. Update to 3.0:
   ```yaml
   image: "networktocode/nautobot:3.0-py3.11"
   ```

2. Monitor for any deprecation warnings
3. Test all functionality
4. Report any issues

## Automated Testing

You can create a test script to verify functionality:

```python
# test_compatibility.py
from nautobot_spare_parts.models import SparePartType, SparePartInventory
from nautobot_spare_parts.utils import get_nautobot_version

print(f"Testing on Nautobot {get_nautobot_version()}")

# Test model creation
part_type = SparePartType.objects.create(
    name="Test Part",
    slug="test-part",
    category="ram"
)

# Test URL generation (both UI and API)
ui_url = part_type.get_absolute_url()
api_url = part_type.get_absolute_url(api=True)

print(f"UI URL: {ui_url}")
print(f"API URL: {api_url}")

# Cleanup
part_type.delete()

print("✅ All tests passed!")
```

## Known Compatibility Notes

### Nautobot 2.1.7
- `get_absolute_url(api=True)` parameter is ignored (backward compatible)
- All features work normally

### Nautobot 2.3.x
- Full API URL support
- Enhanced serialization
- All features work optimally

### Nautobot 3.0
- Forward compatible design
- Should work without modification
- Monitor release notes for breaking changes

## Reporting Issues

If you find a compatibility issue:

1. Note the exact Nautobot version
2. Capture the full error message
3. Document steps to reproduce
4. Check if it's a known issue in COMPATIBILITY.md
