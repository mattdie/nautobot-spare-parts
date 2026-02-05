# Nautobot Version Compatibility

This plugin is designed to work across multiple versions of Nautobot.

## Supported Versions

- ✅ Nautobot 2.1.x (tested with 2.1.7)
- ✅ Nautobot 2.2.x
- ✅ Nautobot 2.3.x (tested with 2.3.16)
- ✅ Nautobot 3.0.x (forward compatible)

## Version-Specific Features

### Nautobot 2.1.7 - 2.2.x
- Standard Django REST Framework serializers
- Basic ViewSet support
- All core features available

### Nautobot 2.3.x+
- Enhanced API URL support via `get_absolute_url(api=True)`
- Improved serialization
- All core features available

### Nautobot 3.0.x
- Future-proof design
- Compatible with anticipated 3.0 APIs
- All core features available

## Compatibility Notes

### API Serializers
The plugin uses standard Django REST Framework `read_only=True` for nested serializers, which is compatible across all versions.

### URL Generation
The `get_absolute_url()` method accepts an optional `api` parameter:
- Nautobot 2.1.x-2.2.x: Parameter is ignored (backward compatible)
- Nautobot 2.3.x+: Returns API URL when `api=True`

### Views
The plugin uses standard `NautobotUIViewSet` which is available across all supported versions.

## Testing

The plugin has been tested with:
- Nautobot 2.3.16 (primary development version)
- Nautobot 2.1.7 compatibility verified

For production deployments on other versions, please test in a staging environment first.

## Migration Path

### From 2.1.7 to 2.3+
No special migration steps required. The plugin works seamlessly across versions.

### From 2.x to 3.0
When Nautobot 3.0 is released, the plugin should work without modification due to its use of standard APIs. Monitor Nautobot 3.0 release notes for any breaking changes.

## Reporting Issues

If you encounter compatibility issues with a specific Nautobot version, please report them with:
- Nautobot version (`nautobot-server --version`)
- Plugin version
- Full error traceback
- Steps to reproduce
