/**
 * Virtualized Data Grid Component
 * Uses AG Grid for high-performance rendering of large datasets
 * 
 * Features:
 * - Row virtualization (only renders visible rows)
 * - Column virtualization for wide tables
 * - Built-in sorting and filtering
 * - Real-time data updates
 * - Dark theme styling
 */

import React, { useMemo, useCallback, useRef } from 'react';
import { AgGridReact } from 'ag-grid-react';
import type { 
  ColDef, 
  GridApi, 
  GridReadyEvent,
  RowClassParams,
  GetRowIdParams,
} from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';
import { colors } from '@/styles/theme';

// AG Grid license for enterprise features
import { LicenseManager } from 'ag-grid-enterprise';
// For development/demo - in production, use real license key
if (import.meta.env.VITE_AG_GRID_LICENSE_KEY) {
  LicenseManager.setLicenseKey(import.meta.env.VITE_AG_GRID_LICENSE_KEY);
}

export interface VirtualizedGridProps<T> {
  /** Data array to display */
  rowData: T[];
  /** Column definitions */
  columnDefs: ColDef<T>[];
  /** Unique ID field for each row */
  getRowId: (params: GetRowIdParams<T>) => string;
  /** Height of each row in pixels */
  rowHeight?: number;
  /** Container height */
  height?: number | string;
  /** Enable row selection */
  rowSelection?: 'single' | 'multiple' | false;
  /** Callback when selection changes */
  onSelectionChanged?: (selectedRows: T[]) => void;
  /** Callback when row is clicked */
  onRowClicked?: (row: T) => void;
  /** Custom row styling based on data */
  getRowClass?: (params: RowClassParams<T>) => string | undefined;
  /** Loading state */
  loading?: boolean;
  /** Enable server-side row model for very large datasets */
  serverSide?: boolean;
  /** Suppress pagination (use for infinite scroll) */
  suppressPagination?: boolean;
  /** Additional class name */
  className?: string;
}

// Custom dark theme CSS variables
const darkThemeStyles = `
  .ag-theme-alpine-dark-custom {
    --ag-background-color: ${colors.backgrounds.primary};
    --ag-header-background-color: ${colors.backgrounds.tertiary};
    --ag-odd-row-background-color: ${colors.backgrounds.secondary};
    --ag-row-hover-color: rgba(255, 255, 255, 0.08);
    --ag-selected-row-background-color: rgba(24, 144, 255, 0.2);
    --ag-border-color: ${colors.backgrounds.border};
    --ag-header-foreground-color: ${colors.text.secondary};
    --ag-foreground-color: ${colors.text.primary};
    --ag-row-border-color: ${colors.backgrounds.border};
    --ag-cell-horizontal-padding: 12px;
  }
  
  .ag-theme-alpine-dark-custom .ag-header-cell {
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  
  .ag-theme-alpine-dark-custom .ag-cell {
    font-size: 13px;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  }
  
  .ag-theme-alpine-dark-custom .highlight-row {
    animation: rowHighlight 1s ease-out;
  }
  
  @keyframes rowHighlight {
    0% { background-color: rgba(82, 196, 26, 0.3); }
    100% { background-color: transparent; }
  }
`;

export function VirtualizedGrid<T>({
  rowData,
  columnDefs,
  getRowId,
  rowHeight = 40,
  height = 600,
  rowSelection = false,
  onSelectionChanged,
  onRowClicked,
  getRowClass,
  loading = false,
  suppressPagination = true,
  className = '',
}: VirtualizedGridProps<T>) {
  const gridRef = useRef<AgGridReact<T>>(null);
  const gridApiRef = useRef<GridApi<T> | null>(null);

  // Default column properties
  const defaultColDef = useMemo<ColDef<T>>(() => ({
    sortable: true,
    resizable: true,
    filter: true,
    minWidth: 80,
    flex: 1,
  }), []);

  // Grid ready handler
  const onGridReady = useCallback((params: GridReadyEvent<T>) => {
    gridApiRef.current = params.api;
    // Auto-size columns on initial load
    params.api.sizeColumnsToFit();
  }, []);

  // Selection change handler
  const handleSelectionChanged = useCallback(() => {
    if (onSelectionChanged && gridApiRef.current) {
      const selectedRows = gridApiRef.current.getSelectedRows();
      onSelectionChanged(selectedRows);
    }
  }, [onSelectionChanged]);

  // Row click handler
  const handleRowClicked = useCallback((event: { data: T | undefined }) => {
    if (onRowClicked && event.data) {
      onRowClicked(event.data);
    }
  }, [onRowClicked]);

  // Inject custom styles
  React.useEffect(() => {
    const styleId = 'virtualized-grid-styles';
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style');
      style.id = styleId;
      style.textContent = darkThemeStyles;
      document.head.appendChild(style);
    }
  }, []);

  return (
    <div 
      className={`ag-theme-alpine-dark-custom ${className}`}
      style={{ height, width: '100%' }}
    >
      <AgGridReact<T>
        ref={gridRef}
        rowData={rowData}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        getRowId={getRowId}
        rowHeight={rowHeight}
        headerHeight={44}
        rowSelection={rowSelection || undefined}
        onGridReady={onGridReady}
        onSelectionChanged={handleSelectionChanged}
        onRowClicked={handleRowClicked}
        getRowClass={getRowClass}
        animateRows={true}
        suppressRowClickSelection={!rowSelection}
        suppressCellFocus={true}
        pagination={!suppressPagination}
        paginationPageSize={100}
        paginationPageSizeSelector={[50, 100, 200, 500]}
        loading={loading}
        loadingOverlayComponent={() => (
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            height: '100%'
          }}>
            Loading...
          </div>
        )}
        noRowsOverlayComponent={() => (
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            height: '100%',
            color: colors.text.secondary
          }}>
            No data available
          </div>
        )}
        // Performance optimizations
        suppressPropertyNamesCheck={true}
        debounceVerticalScrollbar={true}
        rowBuffer={10}
        // Enable cell virtualization for wide tables
        suppressColumnVirtualisation={false}
      />
    </div>
  );
}

export default VirtualizedGrid;
