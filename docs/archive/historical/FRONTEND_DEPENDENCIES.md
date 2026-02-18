# Frontend Dependencies Documentation

This document explains the rationale behind major frontend dependency choices, particularly those with significant bundle size impact.

## AG-Grid Enterprise (~500KB gzipped)

### Why AG-Grid Enterprise?

The algorithmic trading platform uses **AG-Grid Enterprise** (`ag-grid-enterprise`) as an intentional architectural decision. While it adds approximately 500KB to the bundle size, this is justified by the following requirements:

#### Critical Features Used

1. **Server-Side Row Model**
   - Essential for displaying 100K+ order history records
   - Enables virtual scrolling with database-backed pagination
   - Prevents browser memory issues with large datasets

2. **Excel-Style Filtering**
   - Professional trading interfaces require complex filtering
   - Multi-condition filters (AND/OR) for order/trade analysis
   - Set filters for status, symbols, strategies

3. **Row Grouping & Aggregation**
   - Group trades by strategy, symbol, or time period
   - Real-time aggregated P&L calculations
   - Pivot table views for portfolio analysis

4. **Clipboard Operations**
   - Copy/paste functionality for trade data
   - Excel integration for compliance reports
   - Essential for operations team workflows

5. **Master/Detail Views**
   - Order → Executions drill-down
   - Strategy → Trades hierarchy
   - Position → Lots breakdown

6. **Range Selection**
   - Multi-cell selection for bulk operations
   - Chart creation from selected data
   - Export selected ranges

### Bundle Size Mitigation

To minimize the impact of AG-Grid's size:

1. **Tree Shaking**: Only import used modules
   ```typescript
   import { ModuleRegistry } from '@ag-grid-community/core';
   import { ServerSideRowModelModule } from '@ag-grid-enterprise/server-side-row-model';
   
   ModuleRegistry.registerModules([ServerSideRowModelModule]);
   ```

2. **Lazy Loading**: Grid components are code-split
   ```typescript
   const OrdersGrid = lazy(() => import('./components/OrdersGrid'));
   ```

3. **Preload on Hover**: Critical grids preload when navigation is likely

### Alternatives Considered

| Library | Bundle Size | Why Not Used |
|---------|-------------|--------------|
| TanStack Table | ~20KB | No server-side row model, limited aggregation |
| React-Table | ~15KB | Missing enterprise features needed |
| AG-Grid Community | ~200KB | No row grouping, no master/detail |
| Custom Implementation | Variable | Maintenance burden, edge cases |

### Cost-Benefit Analysis

- **Bundle Impact**: +500KB (one-time download, cached)
- **Development Time Saved**: ~3 months of custom grid development
- **Feature Completeness**: 100% of requirements met
- **Maintenance**: Vendor-supported, regular updates

**Conclusion**: The ~500KB bundle size increase is an acceptable trade-off for a production trading application where performance, reliability, and feature completeness are critical.

---

## Other Notable Dependencies

### Chart Libraries

| Library | Size | Usage |
|---------|------|-------|
| `lightweight-charts` | ~40KB | Real-time candlestick charts |
| `recharts` | ~100KB | Portfolio analytics charts |
| `chart.js` + `react-chartjs-2` | ~60KB | General purpose charts |

**Note**: Multiple chart libraries are used because:
- `lightweight-charts` is optimized for financial time-series (TradingView quality)
- `recharts` provides better React integration for static dashboards
- `chart.js` handles miscellaneous chart types

### UI Framework

- **Ant Design** (`antd`): ~500KB
  - Complete component library
  - Used with tree-shaking to reduce actual bundle impact
  - Provides consistent design system

### State Management

- **Zustand** (~2KB): Minimal footprint global state
- **React Query** (~12KB): Server state management with caching

---

## Bundle Analysis

To analyze the current bundle:

```bash
# Build with stats
npm run build -- --stats

# Or use the visualizer
npm run analyze
```

The `rollup-plugin-visualizer` generates an interactive treemap at `dist/stats.html`.

### Current Bundle Budget

| Category | Budget | Current |
|----------|--------|---------|
| Initial JS | <500KB | ~480KB |
| AG-Grid (lazy) | <600KB | ~520KB |
| Total (all routes) | <2MB | ~1.8MB |

---

## Future Considerations

1. **Module Federation**: Consider micro-frontend architecture for grid-heavy views
2. **Edge Caching**: Use CDN with aggressive caching for vendor bundles
3. **Partial Hydration**: Investigate React Server Components for static content
