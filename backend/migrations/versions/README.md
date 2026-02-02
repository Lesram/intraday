# Database Migration Naming Convention

## Standard Naming Format

All migration files in this directory should follow this naming convention:

```
YYYYMMDD_description.py
```

### Format Components

- **YYYYMMDD**: The date the migration was created (e.g., `20251007`)
- **description**: A lowercase, underscore-separated description of what the migration does

### Examples

✅ **Correct naming:**
- `20251007_214733_add_strategies_table.py`
- `20251015_risk_management.py`
- `20260115_add_user_preferences.py`
- `20260120_add_portfolio_snapshots.py`

❌ **Incorrect naming (legacy):**
- `706e00fe1a28_initial_migration_users_orders_.py` (Alembic auto-generated hash)
- `add_user_id_to_orders.py` (missing date prefix)
- `phase7_watchlists_templates.py` (missing date prefix)

## Migration Guidelines

### Creating New Migrations

1. Use Alembic with custom naming:
   ```bash
   alembic revision --autogenerate -m "add_new_table"
   ```

2. Rename the generated file to follow the convention:
   ```bash
   # Before: abc123def456_add_new_table.py
   # After:  20260202_add_new_table.py
   ```

3. Update the `revision` variable inside the file if needed for consistency.

### Legacy Migrations

Existing migrations with non-standard names are kept for backward compatibility:
- `706e00fe1a28_initial_migration_users_orders_.py` - Initial schema
- `76f317122560_add_backtests_table.py` - Backtests table
- `83ec4ee73d7d_add_order_price_and_fill_fields.py` - Order fields
- `add_user_id_to_orders.py` - User ID for orders
- `d9dc79977b6d_add_position_lots_and_realized_trades.py` - Position lots
- `ec197100938a_add_idempotency_constraints_and_order_.py` - Idempotency
- `phase7_watchlists_templates.py` - Watchlists feature

**Do NOT rename legacy migrations** as this would break the Alembic migration chain.

### Best Practices

1. **One migration per feature**: Keep migrations focused on a single change
2. **Reversible**: Always implement `downgrade()` to enable rollbacks
3. **Idempotent**: Check if objects exist before creating them
4. **Data migrations**: Separate schema changes from data migrations
5. **Testing**: Test both `upgrade()` and `downgrade()` locally before committing

## Alembic Configuration

To enforce consistent naming, consider adding to `alembic.ini`:

```ini
# File template for new migrations
file_template = %%(year)d%%(month).2d%%(day).2d_%%(slug)s
```

Or use a custom revision template in `alembic/script.py.mako`.
