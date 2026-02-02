/**
 * Grid utility functions for AG Grid
 * Separated from VirtualizedGrid for Fast Refresh compatibility
 */

import type { ValueFormatterParams } from 'ag-grid-community';
import { colors } from '@/styles/theme';

// Common value formatters for reuse
export const gridFormatters = {
  currency: (params: ValueFormatterParams): string => {
    if (params.value == null) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(params.value);
  },
  
  percent: (params: ValueFormatterParams): string => {
    if (params.value == null) return '-';
    return `${(params.value * 100).toFixed(2)}%`;
  },
  
  number: (decimals = 2) => (params: ValueFormatterParams): string => {
    if (params.value == null) return '-';
    return Number(params.value).toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  },
  
  dateTime: (params: ValueFormatterParams): string => {
    if (!params.value) return '-';
    const date = new Date(params.value);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  },
  
  date: (params: ValueFormatterParams): string => {
    if (!params.value) return '-';
    const date = new Date(params.value);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  },
};

// Common cell renderers
export const gridRenderers = {
  statusTag: (colorMap: Record<string, string>) => (params: { value: string }) => {
    const color = colorMap[params.value] || '#888';
    return `<span style="
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      background-color: ${color}22;
      color: ${color};
      border: 1px solid ${color}44;
    ">${params.value}</span>`;
  },
  
  sideIndicator: (params: { value: string }) => {
    const isBuy = params.value?.toLowerCase() === 'buy';
    const color = isBuy ? colors.semantic.success : colors.semantic.error;
    return `<span style="
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: ${color};
      font-weight: 600;
    ">
      <span style="
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background-color: ${color};
      "></span>
      ${params.value?.toUpperCase()}
    </span>`;
  },
};
