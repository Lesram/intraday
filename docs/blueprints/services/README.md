# Service Blueprints

This directory contains service module blueprints that have been moved from the runtime package.
These modules are primarily documentation/placeholder code and are not actively used in the runtime.

## Moved Files

The following files were moved from `backend/services/` to this directory:

- `analytics.py` - moved from runtime package to blueprint docs
- `audit.py` - moved from runtime package to blueprint docs
- `authentication.py` - moved from runtime package to blueprint docs
- `authorization.py` - moved from runtime package to blueprint docs
- `broker_service.py` - moved from runtime package to blueprint docs
- `compliance.py` - moved from runtime package to blueprint docs
- `configuration.py` - moved from runtime package to blueprint docs
- `data_synchronization.py` - moved from runtime package to blueprint docs
- `document.py` - moved from runtime package to blueprint docs
- `email.py` - moved from runtime package to blueprint docs
- `error_handling.py` - moved from runtime package to blueprint docs
- `feature_flag.py` - moved from runtime package to blueprint docs
- `integration.py` - moved from runtime package to blueprint docs
- `key_management.py` - moved from runtime package to blueprint docs
- `load_balancer.py` - moved from runtime package to blueprint docs
- `notification.py` - moved from runtime package to blueprint docs
- `order_fsm.py` - moved from runtime package to blueprint docs
- `order_integrity_service.py` - moved from runtime package to blueprint docs
- `positions_service.py` - moved from runtime package to blueprint docs
- `risk_manager.py` - moved from runtime package to blueprint docs
- `safety_modes.py` - moved from runtime package to blueprint docs

## Active Runtime Services

The following services remain in the runtime package (`backend/services/`):

- `order_service.py` - Core order management and execution service
- `signal_service.py` - Trading signal processing and management service
- `__init__.py` - Package initialization

## Usage

These blueprint files can be used as:
- Documentation of planned/potential services
- Templates for future service implementations  
- Reference architecture examples

To activate a service blueprint:
1. Move it back to `backend/services/`
2. Implement the actual functionality
3. Add proper imports and integration
4. Update tests and documentation
