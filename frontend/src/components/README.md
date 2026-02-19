# Frontend Components Structure

This document explains the organization of React components in the trading platform frontend.

## Directory Structure

```
src/components/
├── KeyboardShortcuts.tsx     # Global keyboard shortcut handler
├── SkipLinks.tsx             # Skip navigation links (a11y)
│
├── atomic/                   # Atomic Design - smallest building blocks
│   ├── Button/
│   ├── Input/
│   ├── Badge/
│   └── ...
│
├── auth/                     # Authentication components
│   ├── LoginForm.tsx
│   ├── ProtectedRoute.tsx
│   └── ...
│
├── charts/                   # Charting components
│   ├── CandlestickChart.tsx
│   ├── LineChart.tsx
│   └── ...
│
├── common/                   # Shared/reusable components
│   ├── Modal.tsx
│   ├── Tabs.tsx
│   ├── Table.tsx
│   └── ...
│
├── data-display/             # Data visualization components
│   ├── DataTable.tsx
│   ├── StatCard.tsx
│   └── ...
│
├── financial/                # Finance-specific components
│   ├── PriceDisplay.tsx
│   ├── PnLIndicator.tsx
│   └── ...
│
├── layout/                   # Layout components
│   ├── Header.tsx
│   ├── Sidebar.tsx
│   ├── MainLayout.tsx
│   └── ...
│
├── market/                   # Market data components
│   ├── MarketOverview.tsx
│   ├── QuoteCard.tsx
│   ├── OrderBook.tsx
│   └── ...
│
├── portfolio/                # Portfolio management components
│   ├── PositionList.tsx
│   ├── PortfolioSummary.tsx
│   └── ...
│
└── strategies/               # Strategy management components
    ├── StrategyCard.tsx
    ├── StrategyForm.tsx
    └── ...
```

## Component Categories

### Atomic Components (`atomic/`)
Smallest, indivisible UI elements following Atomic Design principles:
- Buttons, inputs, badges, icons
- No business logic, purely presentational
- Highly reusable across the application

### Feature Components
Organized by domain/feature area:
- **`auth/`**: Login, logout, session management
- **`charts/`**: Financial charts (candlestick, line, area)
- **`financial/`**: Price displays, P&L indicators, currency formatting
- **`market/`**: Real-time market data, quotes, order books
- **`portfolio/`**: Position management, portfolio analytics
- **`strategies/`**: Strategy CRUD, performance metrics

### Infrastructure Components
Cross-cutting concerns:
- **`layout/`**: Page structure, navigation, responsive layouts
- **`common/`**: Shared utilities (modals, tabs, tables)
- **`data-display/`**: Generic data visualization

### Accessibility Components
WCAG 2.1 AA compliance:
- `SkipLinks.tsx`: Skip-to-content navigation
- `KeyboardShortcuts.tsx`: Application-wide hotkeys

## Naming Conventions

1. **PascalCase** for component files: `PositionList.tsx`
2. **camelCase** for utilities: `gridUtils.ts`
3. **kebab-case** for directories when needed
4. Suffix with `.tsx` for React components, `.ts` for plain TypeScript

## Component Guidelines

### Creating New Components

1. Place in the appropriate category directory
2. Export from directory's `index.ts` for clean imports
3. Include TypeScript types for all props
4. Add JSDoc comments for complex components

### Example Component Structure

```tsx
// src/components/portfolio/PositionCard.tsx

import { memo } from 'react';
import type { Position } from '@/types';

interface PositionCardProps {
  position: Position;
  onClose?: (symbol: string) => void;
}

/**
 * Displays a single portfolio position with P&L.
 */
export const PositionCard = memo(function PositionCard({
  position,
  onClose,
}: PositionCardProps) {
  // Component implementation
});
```

## Performance Optimizations

- **React.memo**: Applied to expensive pure components
- **AG-Grid Enterprise**: Required for advanced features (see FRONTEND_DEPENDENCIES.md)

## Related Documentation

- [FRONTEND_DEPENDENCIES.md](../../docs/FRONTEND_DEPENDENCIES.md) - Dependency choices
- [QUICK_START.md](../QUICK_START.md) - Development setup
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Common issues
