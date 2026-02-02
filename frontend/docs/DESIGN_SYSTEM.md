# Design System Specification
**Created**: October 5, 2025  
**Version**: 1.0  
**Purpose**: Define visual design language and component library for institutional trading platform  
**Status**: 🟢 Ready for Implementation

---

## Design Philosophy

### Institutional Trading Platform Principles

1. **Density Over Minimalism** - Traders need information at a glance
2. **Precision Over Polish** - Numbers must be clear, aligned, and easy to scan
3. **Function Over Form** - Beauty through clarity, not decoration
4. **Consistency Above All** - Predictable behavior reduces cognitive load
5. **Speed Matters** - Every interaction should feel instant

### Target Aesthetic
**Bloomberg Terminal meets Modern Web** - Professional, data-dense, dark-first, with clean typography and purposeful color.

---

## Color System

### Theme: Dark Mode (Default)

#### Background Colors
```typescript
const backgrounds = {
  primary: '#0a0e27',      // Main app background (deep navy)
  secondary: '#111827',    // Card/panel background (dark gray)
  tertiary: '#1f2937',     // Elevated surface (medium gray)
  hover: '#374151',        // Hover state
  border: '#374151',       // Border color
  disabled: '#4b5563',     // Disabled backgrounds
};
```

#### Text Colors
```typescript
const text = {
  primary: '#f9fafb',      // Main text (near white)
  secondary: '#d1d5db',    // Secondary text (light gray)
  tertiary: '#9ca3af',     // Tertiary text (medium gray)
  disabled: '#6b7280',     // Disabled text
  inverse: '#111827',      // Text on light backgrounds
};
```

#### Semantic Colors
```typescript
const semantic = {
  // Trading Colors
  profit: '#52c41a',       // Green - gains, buy, long
  loss: '#f5222d',         // Red - losses, sell, short
  neutral: '#8c8c8c',      // Gray - flat, no change
  
  // Alert Colors
  info: '#1890ff',         // Blue - informational
  warning: '#faad14',      // Orange - warnings
  error: '#f5222d',        // Red - errors
  success: '#52c41a',      // Green - success
  critical: '#ff4d4f',     // Bright red - critical alerts
  
  // Status Colors
  active: '#52c41a',       // Green - running/active
  pending: '#faad14',      // Orange - pending
  stopped: '#8c8c8c',      // Gray - stopped/inactive
  failed: '#f5222d',       // Red - failed/error
};
```

#### Brand Colors
```typescript
const brand = {
  primary: '#1890ff',      // Primary brand color (blue)
  primaryHover: '#40a9ff',
  primaryActive: '#096dd9',
  secondary: '#722ed1',    // Secondary brand (purple)
  accent: '#13c2c2',       // Accent (cyan)
};
```

### Light Mode (Optional, Desktop Only)
For users who prefer light theme during daytime trading:
```typescript
const lightTheme = {
  backgrounds: {
    primary: '#ffffff',
    secondary: '#f5f5f5',
    tertiary: '#e8e8e8',
  },
  text: {
    primary: '#262626',
    secondary: '#595959',
    tertiary: '#8c8c8c',
  },
  // Semantic colors remain the same (profit/loss must be consistent)
};
```

---

## Typography

### Font Families

```typescript
const fonts = {
  // UI Text (labels, buttons, paragraphs)
  sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  
  // Numbers & Financial Data (CRITICAL)
  mono: '"Roboto Mono", "SF Mono", Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
  
  // Headings (optional, can use sans)
  heading: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
};
```

**Why Monospace for Numbers?**
- **Alignment**: All digits same width → perfect column alignment
- **Scanning**: Easy to compare values vertically
- **Precision**: No ambiguity (1 vs l, 0 vs O)
- **Professional**: Standard in financial terminals

### Font Sizes
```typescript
const fontSizes = {
  // Text
  xs: '11px',    // Labels, captions
  sm: '12px',    // Secondary text
  base: '14px',  // Default body text
  lg: '16px',    // Prominent text
  xl: '18px',    // Subheadings
  '2xl': '24px', // Section headers
  '3xl': '30px', // Page titles
  
  // Numbers (often larger than surrounding text)
  numberSm: '13px',
  numberBase: '15px',
  numberLg: '18px',
  numberXl: '24px',
};
```

### Font Weights
```typescript
const fontWeights = {
  light: 300,
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
};
```

### Line Heights
```typescript
const lineHeights = {
  tight: 1.2,    // Headings
  normal: 1.5,   // Body text
  relaxed: 1.75, // Long-form content
};
```

### Usage Examples
```tsx
// Price Display
<span style={{
  fontFamily: fonts.mono,
  fontSize: fontSizes.numberLg,
  fontWeight: fontWeights.semibold,
  color: profit > 0 ? semantic.profit : semantic.loss
}}>
  $178.45
</span>

// Label
<span style={{
  fontFamily: fonts.sans,
  fontSize: fontSizes.sm,
  color: text.secondary
}}>
  Unrealized P&L
</span>
```

---

## Spacing System

### 8-Point Grid
All spacing uses multiples of 8px for consistency.

```typescript
const spacing = {
  0: '0',
  1: '4px',    // 0.5 × 8
  2: '8px',    // 1 × 8
  3: '12px',   // 1.5 × 8
  4: '16px',   // 2 × 8
  5: '20px',   // 2.5 × 8
  6: '24px',   // 3 × 8
  8: '32px',   // 4 × 8
  10: '40px',  // 5 × 8
  12: '48px',  // 6 × 8
  16: '64px',  // 8 × 8
  20: '80px',  // 10 × 8
  24: '96px',  // 12 × 8
};
```

### Common Patterns
```typescript
const commonSpacing = {
  componentPadding: spacing[4],     // 16px inside cards/panels
  sectionGap: spacing[6],           // 24px between sections
  gridGap: spacing[4],              // 16px between grid items
  formFieldGap: spacing[4],         // 16px between form fields
  buttonPadding: `${spacing[2]} ${spacing[4]}`, // 8px top/bottom, 16px left/right
  modalPadding: spacing[6],         // 24px inside modals
};
```

---

## Component Library (Ant Design Customization)

### Button Variants

```tsx
import { Button } from 'antd';

// Primary (main actions)
<Button type="primary">Submit Order</Button>

// Secondary (less prominent)
<Button>Cancel</Button>

// Danger (destructive actions)
<Button danger>Close Position</Button>

// Ghost (on dark backgrounds)
<Button ghost>View Details</Button>

// Link (inline actions)
<Button type="link">Edit</Button>

// Trading-Specific
<Button type="primary" style={{ backgroundColor: semantic.profit }}>
  Buy
</Button>
<Button danger>Sell</Button>
```

### Trading-Specific Components

#### Price Display
```tsx
interface PriceDisplayProps {
  value: number;
  change?: number;
  changePercent?: number;
  size?: 'sm' | 'md' | 'lg';
  showCurrency?: boolean;
}

// Usage
<PriceDisplay 
  value={178.45} 
  change={2.34} 
  changePercent={1.33}
  size="lg"
/>
```

#### P&L Display
```tsx
interface PnLDisplayProps {
  value: number;
  percent?: number;
  size?: 'sm' | 'md' | 'lg';
}

// Usage
<PnLDisplay value={347.50} percent={0.33} />
// Renders: +$347.50 (+0.33%) in green
```

#### Order Status Badge
```tsx
interface OrderStatusBadgeProps {
  status: 'pending' | 'open' | 'filled' | 'cancelled' | 'rejected';
}

const statusColors = {
  pending: semantic.warning,
  open: semantic.info,
  filled: semantic.success,
  cancelled: semantic.neutral,
  rejected: semantic.error,
};

// Usage
<Badge color={statusColors[status]} text={status} />
```

#### Position Card
```tsx
interface PositionCardProps {
  symbol: string;
  quantity: number;
  averagePrice: number;
  currentPrice: number;
  unrealizedPL: number;
  unrealizedPLPercent: number;
}

// Compact card showing position summary
```

### Data Tables

#### Configuration
```tsx
import { Table } from 'antd';

const tableTheme = {
  headerBg: backgrounds.tertiary,
  headerColor: text.primary,
  rowHoverBg: backgrounds.hover,
  borderColor: backgrounds.border,
  fontSize: fontSizes.sm,
};

// Number Column (right-aligned, monospace)
const numberColumn = {
  align: 'right' as const,
  render: (value: number) => (
    <span style={{ fontFamily: fonts.mono, fontSize: fontSizes.numberBase }}>
      {formatNumber(value)}
    </span>
  ),
};

// P&L Column (colored)
const plColumn = {
  align: 'right' as const,
  render: (value: number) => (
    <span style={{ 
      fontFamily: fonts.mono, 
      color: value >= 0 ? semantic.profit : semantic.loss,
      fontWeight: fontWeights.semibold
    }}>
      {value >= 0 ? '+' : ''}{formatCurrency(value)}
    </span>
  ),
};
```

### Forms

#### Form Layout
```tsx
import { Form, Input, Select } from 'antd';

const formTheme = {
  labelColor: text.secondary,
  inputBg: backgrounds.secondary,
  inputBorder: backgrounds.border,
  inputHoverBorder: brand.primary,
  inputFocusBorder: brand.primary,
  errorColor: semantic.error,
};

// Trading Order Form
<Form layout="vertical">
  <Form.Item label="Symbol" required>
    <Input placeholder="AAPL" />
  </Form.Item>
  
  <Form.Item label="Quantity" required>
    <Input type="number" style={{ fontFamily: fonts.mono }} />
  </Form.Item>
  
  <Form.Item label="Order Type">
    <Select>
      <Select.Option value="market">Market</Select.Option>
      <Select.Option value="limit">Limit</Select.Option>
    </Select>
  </Form.Item>
</Form>
```

### Modals & Dialogs

```tsx
import { Modal } from 'antd';

// Order Confirmation Modal
<Modal
  title="Confirm Order"
  open={visible}
  onOk={handleSubmit}
  onCancel={handleCancel}
  okText="Submit Order"
  okButtonProps={{ danger: side === 'sell' }}
  width={600}
>
  <div style={{ padding: spacing[4] }}>
    {/* Order summary */}
  </div>
</Modal>

// Critical Action (Delete, Kill Switch)
<Modal
  title="Emergency Stop"
  open={visible}
  onOk={handleEmergencyStop}
  onCancel={handleCancel}
  okText="STOP ALL"
  okButtonProps={{ danger: true }}
  cancelText="Cancel"
  width={500}
  centered
>
  <Alert
    message="This will stop all active strategies and cancel all open orders."
    type="error"
    showIcon
  />
</Modal>
```

---

## Charts & Visualizations

### TradingView Lightweight Charts Theme

```typescript
const chartTheme = {
  layout: {
    background: { color: backgrounds.primary },
    textColor: text.secondary,
  },
  grid: {
    vertLines: { color: backgrounds.border },
    horzLines: { color: backgrounds.border },
  },
  crosshair: {
    mode: 1, // Normal
    vertLine: {
      color: text.tertiary,
      width: 1,
      style: 0, // Solid
      visible: true,
    },
    horzLine: {
      color: text.tertiary,
      width: 1,
      style: 0,
      visible: true,
    },
  },
  priceScale: {
    borderColor: backgrounds.border,
  },
  timeScale: {
    borderColor: backgrounds.border,
    timeVisible: true,
    secondsVisible: false,
  },
};

// Candlestick colors
const candlestickColors = {
  upColor: semantic.profit,
  downColor: semantic.loss,
  borderUpColor: semantic.profit,
  borderDownColor: semantic.loss,
  wickUpColor: semantic.profit,
  wickDownColor: semantic.loss,
};
```

---

## Layout Components

### Main Layout Structure

```tsx
// App Shell
<Layout style={{ minHeight: '100vh', background: backgrounds.primary }}>
  {/* Top Navigation */}
  <Header style={{ 
    background: backgrounds.secondary, 
    padding: `0 ${spacing[6]}`,
    borderBottom: `1px solid ${backgrounds.border}`
  }}>
    <AppHeader />
  </Header>
  
  <Layout>
    {/* Side Navigation */}
    <Sider 
      width={240} 
      style={{ background: backgrounds.secondary }}
      collapsible
    >
      <SideNav />
    </Sider>
    
    {/* Main Content */}
    <Content style={{ 
      padding: spacing[6], 
      background: backgrounds.primary 
    }}>
      {children}
    </Content>
  </Layout>
</Layout>
```

### Dashboard Grid
```tsx
// Responsive grid for dashboard widgets
<Row gutter={[16, 16]}>
  <Col xs={24} sm={12} lg={8}>
    <PortfolioSummaryCard />
  </Col>
  <Col xs={24} sm={12} lg={8}>
    <OpenPositionsCard />
  </Col>
  <Col xs={24} sm={24} lg={8}>
    <RecentOrdersCard />
  </Col>
</Row>
```

---

## Ant Design Theme Configuration

### theme.ts
```typescript
import type { ThemeConfig } from 'antd';

export const darkTheme: ThemeConfig = {
  token: {
    // Colors
    colorPrimary: '#1890ff',          // Primary brand
    colorSuccess: '#52c41a',          // Profit/success
    colorWarning: '#faad14',          // Warning
    colorError: '#f5222d',            // Loss/error
    colorInfo: '#1890ff',             // Info
    colorTextBase: '#f9fafb',         // Text
    colorBgBase: '#0a0e27',           // Background
    
    // Typography
    fontSize: 14,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    fontSizeHeading1: 30,
    fontSizeHeading2: 24,
    fontSizeHeading3: 18,
    fontSizeHeading4: 16,
    fontSizeHeading5: 14,
    
    // Spacing
    marginXS: 8,
    marginSM: 12,
    margin: 16,
    marginMD: 20,
    marginLG: 24,
    marginXL: 32,
    
    paddingXS: 8,
    paddingSM: 12,
    padding: 16,
    paddingMD: 20,
    paddingLG: 24,
    paddingXL: 32,
    
    // Border
    borderRadius: 4,
    borderRadiusLG: 6,
    borderRadiusSM: 2,
    
    // Other
    lineWidth: 1,
    controlHeight: 32,
    controlHeightLG: 40,
    controlHeightSM: 24,
  },
  
  components: {
    Button: {
      controlHeight: 32,
      fontWeight: 500,
      primaryColor: '#ffffff',
      dangerColor: '#ffffff',
    },
    
    Input: {
      controlHeight: 32,
      colorBgContainer: '#111827',
      colorBorder: '#374151',
      colorTextPlaceholder: '#6b7280',
    },
    
    Select: {
      controlHeight: 32,
      colorBgContainer: '#111827',
      colorBorder: '#374151',
    },
    
    Table: {
      headerBg: '#1f2937',
      headerColor: '#f9fafb',
      rowHoverBg: '#374151',
      borderColor: '#374151',
      fontSize: 13,
    },
    
    Card: {
      colorBgContainer: '#111827',
      padding: 20,
      paddingLG: 24,
    },
    
    Modal: {
      contentBg: '#111827',
      headerBg: '#111827',
      titleColor: '#f9fafb',
    },
    
    Menu: {
      darkItemBg: '#111827',
      darkItemSelectedBg: '#1f2937',
      darkItemHoverBg: '#374151',
    },
  },
};

// Usage in App.tsx
import { ConfigProvider } from 'antd';
import { darkTheme } from './theme';

function App() {
  return (
    <ConfigProvider theme={darkTheme}>
      {/* Your app */}
    </ConfigProvider>
  );
}
```

---

## Icons

### Icon Library: Ant Design Icons
```bash
npm install @ant-design/icons
```

### Common Icons
```tsx
import {
  DashboardOutlined,
  LineChartOutlined,
  WalletOutlined,
  ThunderboltOutlined,
  RobotOutlined,
  WarningOutlined,
  StockOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';

// Usage
<LineChartOutlined style={{ fontSize: 18, color: brand.primary }} />
```

---

## Responsive Design

### Breakpoints (Ant Design defaults)
```typescript
const breakpoints = {
  xs: 480,   // Mobile
  sm: 576,   // Small tablet
  md: 768,   // Tablet
  lg: 992,   // Desktop
  xl: 1200,  // Large desktop
  xxl: 1600, // Extra large
};
```

### Desktop-First Approach
Platform is optimized for desktop trading workstations (1920×1080 or higher). Mobile responsiveness is secondary:

- **Desktop (≥1200px)**: Full UI, multi-column layouts, all features
- **Tablet (768-1199px)**: Simplified layout, essential features only
- **Mobile (≤767px)**: Read-only view, portfolio monitoring only (no trading)

---

## Accessibility

### Color Contrast
All text meets WCAG AA standards:
- **Normal text** (14px): 4.5:1 contrast ratio
- **Large text** (18px+): 3:1 contrast ratio
- **Profit/Loss colors** tested against dark background

### Keyboard Navigation
- All interactive elements focusable
- Logical tab order
- Keyboard shortcuts for common actions:
  - `Cmd/Ctrl + K`: Global search
  - `Cmd/Ctrl + O`: New order
  - `Cmd/Ctrl + P`: Portfolio view
  - `Esc`: Close modals

### Screen Readers
- Semantic HTML
- ARIA labels on all interactive elements
- Live regions for dynamic updates (order fills, alerts)

---

## Animation & Motion

### Principles
- **Fast**: All animations ≤200ms (traders need speed)
- **Purposeful**: Only animate to communicate state change
- **Subtle**: Don't distract from data

### Common Animations
```typescript
const animations = {
  // Fade in/out
  fade: {
    duration: 150,
    easing: 'ease-in-out',
  },
  
  // Slide (drawers, modals)
  slide: {
    duration: 200,
    easing: 'ease-out',
  },
  
  // Scale (buttons, cards)
  scale: {
    duration: 100,
    easing: 'ease-out',
  },
};

// CSS
.fade-in {
  animation: fadeIn 150ms ease-in-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

### Micro-interactions
- **Button hover**: Scale 1.02, duration 100ms
- **Card hover**: Lift (box-shadow), duration 150ms
- **Data update**: Flash highlight (fade yellow → transparent), duration 500ms

---

## Number Formatting

### Utilities
```typescript
// Currency
export const formatCurrency = (value: number, decimals = 2): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
};

// Percent
export const formatPercent = (value: number, decimals = 2): string => {
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`;
};

// Large numbers
export const formatNumber = (value: number): string => {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`;
  }
  return value.toFixed(2);
};

// Price (variable decimals based on value)
export const formatPrice = (value: number): string => {
  if (value < 1) return value.toFixed(4);      // Penny stocks
  if (value < 10) return value.toFixed(3);
  return value.toFixed(2);
};
```

---

## Best Practices Summary

✅ **DO**:
- Use monospace font for all numbers
- Right-align numeric columns
- Show + prefix for positive P&L
- Use color consistently (green = profit, red = loss)
- Batch rapid updates (throttle WebSocket price updates)
- Show loading states (skeletons, spinners)
- Provide keyboard shortcuts for power users

❌ **DON'T**:
- Animate data tables (causes motion sickness)
- Use tiny fonts (<11px for critical data)
- Change color meanings (red ≠ buy!)
- Hide important information in tooltips
- Make users wait for animations
- Use complex layouts on mobile

---

**Last Updated**: October 5, 2025  
**Maintainer**: Frontend Team Lead  
**Review Schedule**: Monthly or when adding new components
