import { theme } from 'antd';
import type { ThemeConfig } from 'antd';

// Design tokens matching our design system documentation
export const colors = {
  // Backgrounds
  backgrounds: {
    primary: '#0a0e27',
    secondary: '#111827',
    tertiary: '#1f2937',
    hover: '#374151',
    border: '#374151',
    disabled: '#4b5563',
  },
  
  // Text
  text: {
    primary: '#f9fafb',
    secondary: '#d1d5db',
    tertiary: '#9ca3af',
    disabled: '#6b7280',
    inverse: '#111827',
  },
  
  // Semantic (Trading)
  semantic: {
    profit: '#52c41a',      // Green - gains, buy, long
    loss: '#f5222d',        // Red - losses, sell, short
    neutral: '#8c8c8c',     // Gray - flat, no change
    info: '#1890ff',        // Blue - informational
    warning: '#faad14',     // Orange - warnings
    error: '#f5222d',       // Red - errors
    success: '#52c41a',     // Green - success
    critical: '#ff4d4f',    // Bright red - critical alerts
    active: '#52c41a',      // Green - running/active
    pending: '#faad14',     // Orange - pending
    stopped: '#8c8c8c',     // Gray - stopped/inactive
    failed: '#f5222d',      // Red - failed/error
  },
  
  // Brand
  brand: {
    primary: '#1890ff',
    primaryHover: '#40a9ff',
    primaryActive: '#096dd9',
    secondary: '#722ed1',
    accent: '#13c2c2',
  },
};

// Typography
export const fonts = {
  sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  mono: '"Roboto Mono", "SF Mono", Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
  heading: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
};

// Font sizes
export const fontSizes = {
  xs: 11,
  sm: 12,
  base: 14,
  lg: 16,
  xl: 18,
  '2xl': 24,
  '3xl': 30,
  numberSm: 13,
  numberBase: 15,
  numberLg: 18,
  numberXl: 24,
};

// Ant Design Dark Theme Configuration
export const darkTheme: ThemeConfig = {
  token: {
    // Base colors
    colorPrimary: colors.brand.primary,
    colorSuccess: colors.semantic.success,
    colorWarning: colors.semantic.warning,
    colorError: colors.semantic.error,
    colorInfo: colors.semantic.info,
    
    // Text
    colorTextBase: colors.text.primary,
    colorText: colors.text.primary,
    colorTextSecondary: colors.text.secondary,
    colorTextTertiary: colors.text.tertiary,
    colorTextQuaternary: colors.text.disabled,
    
    // Background
    colorBgBase: colors.backgrounds.primary,
    colorBgContainer: colors.backgrounds.secondary,
    colorBgElevated: colors.backgrounds.tertiary,
    colorBgLayout: colors.backgrounds.primary,
    colorBorder: colors.backgrounds.border,
    colorBorderSecondary: colors.backgrounds.border,
    
    // Typography
    fontSize: fontSizes.base,
    fontFamily: fonts.sans,
    fontSizeHeading1: fontSizes['3xl'],
    fontSizeHeading2: fontSizes['2xl'],
    fontSizeHeading3: fontSizes.xl,
    fontSizeHeading4: fontSizes.lg,
    fontSizeHeading5: fontSizes.base,
    
    // Spacing
    marginXS: 8,
    marginSM: 12,
    margin: 16,
    marginMD: 20,
    marginLG: 24,
    marginXL: 32,
    marginXXL: 48,
    
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
    lineWidth: 1,
    
    // Control heights
    controlHeight: 32,
    controlHeightLG: 40,
    controlHeightSM: 24,
    
    // Shadows
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
    boxShadowSecondary: '0 4px 16px rgba(0, 0, 0, 0.08)',
  },
  
  components: {
    // Button
    Button: {
      controlHeight: 32,
      fontWeight: 500,
      primaryColor: '#ffffff',
      dangerColor: '#ffffff',
      colorPrimary: colors.brand.primary,
    },
    
    // Input
    Input: {
      controlHeight: 32,
      colorBgContainer: colors.backgrounds.secondary,
      colorBorder: colors.backgrounds.border,
      colorTextPlaceholder: colors.text.disabled,
      activeBorderColor: colors.brand.primary,
      hoverBorderColor: colors.brand.primaryHover,
    },
    
    // Select
    Select: {
      controlHeight: 32,
      colorBgContainer: colors.backgrounds.secondary,
      colorBorder: colors.backgrounds.border,
    },
    
    // Table
    Table: {
      headerBg: colors.backgrounds.tertiary,
      headerColor: colors.text.primary,
      rowHoverBg: colors.backgrounds.hover,
      borderColor: colors.backgrounds.border,
      fontSize: fontSizes.sm,
      cellPaddingBlock: 12,
      cellPaddingInline: 16,
    },
    
    // Card
    Card: {
      colorBgContainer: colors.backgrounds.secondary,
      padding: 20,
      paddingLG: 24,
      borderRadiusLG: 6,
    },
    
    // Modal
    Modal: {
      contentBg: colors.backgrounds.secondary,
      headerBg: colors.backgrounds.secondary,
      titleColor: colors.text.primary,
      borderRadiusLG: 6,
    },
    
    // Menu
    Menu: {
      itemBg: colors.backgrounds.secondary,
      itemSelectedBg: colors.backgrounds.tertiary,
      itemHoverBg: colors.backgrounds.hover,
      itemColor: colors.text.secondary,
      itemSelectedColor: colors.text.primary,
      darkItemBg: colors.backgrounds.secondary,
      darkItemSelectedBg: colors.backgrounds.tertiary,
      darkItemHoverBg: colors.backgrounds.hover,
      darkItemColor: colors.text.secondary,
      darkItemSelectedColor: colors.text.primary,
    },
    
    // Layout
    Layout: {
      headerBg: colors.backgrounds.secondary,
      siderBg: colors.backgrounds.secondary,
      bodyBg: colors.backgrounds.primary,
      footerBg: colors.backgrounds.secondary,
      headerHeight: 64,
      headerPadding: '0 24px',
    },
    
    // Tabs
    Tabs: {
      itemColor: colors.text.secondary,
      itemSelectedColor: colors.text.primary,
      itemHoverColor: colors.text.primary,
      inkBarColor: colors.brand.primary,
    },
    
    // Badge
    Badge: {
      dotSize: 6,
      textFontSize: fontSizes.xs,
    },
    
    // Tag
    Tag: {
      defaultBg: colors.backgrounds.tertiary,
      defaultColor: colors.text.primary,
    },
    
    // Tooltip
    Tooltip: {
      colorBgSpotlight: colors.backgrounds.tertiary,
    },
    
    // Notification
    Notification: {
      colorBgElevated: colors.backgrounds.tertiary,
    },
    
    // Message
    Message: {
      contentBg: colors.backgrounds.tertiary,
    },
  },
  
  algorithm: theme.darkAlgorithm, // Use Ant Design's dark algorithm
};

// Light theme (optional, for future use)
export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: colors.brand.primary,
    colorSuccess: colors.semantic.success,
    colorWarning: colors.semantic.warning,
    colorError: colors.semantic.error,
    colorInfo: colors.semantic.info,
    fontSize: fontSizes.base,
    fontFamily: fonts.sans,
  },
  // Light theme would have inverted backgrounds/text
  // Not implementing fully now as dark is default
};
