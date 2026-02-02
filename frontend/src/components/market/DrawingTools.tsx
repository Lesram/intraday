/**
 * Drawing Tools Component
 * 
 * Provides UI toolbar for chart drawing tools (trendlines, shapes, annotations).
 * 
 * Features:
 * - Trendline tool (2 points)
 * - Horizontal/Vertical line tools (1 point)
 * - Fibonacci retracement (2 points with levels)
 * - Rectangle and Ellipse tools (2 points)
 * - Text annotation tool (1 point with input)
 * - Save/load drawings from backend
 * - Delete individual or all drawings
 * 
 * Phase 7 - Market Data & Charting
 * Created: October 16, 2025
 */

import React, { useState } from 'react';
import {
  Space,
  Button,
  Tooltip,
  Dropdown,
  ColorPicker,
  InputNumber,
  Select,
  message,
  Popconfirm,
  Badge,
} from 'antd';
import {
  LineOutlined,
  MinusOutlined,
  ColumnHeightOutlined,
  FallOutlined,
  BorderOutlined,
  RadiusSettingOutlined,
  FontSizeOutlined,
  DeleteOutlined,
  SaveOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';

// ============================================================================
// TYPES
// ============================================================================

export type DrawingType =
  | 'trendline'
  | 'horizontal'
  | 'vertical'
  | 'fibonacci'
  | 'rectangle'
  | 'ellipse'
  | 'text';

export interface DrawingStyle {
  color: string;
  lineWidth: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
  fillColor?: string;
  fillOpacity: number;
  textSize: number;
}

export interface Point {
  time: number; // Unix timestamp in seconds
  price: number;
}

export interface Drawing {
  id: string;
  symbol: string;
  type: DrawingType;
  points: Point[];
  style: DrawingStyle;
  text?: string;
  timeframe: string;
}

// ============================================================================
// COMPONENT PROPS
// ============================================================================

interface DrawingToolsProps {
  /** Current drawing tool selected */
  selectedTool: DrawingType | null;
  
  /** Callback when tool is selected */
  onToolSelect: (tool: DrawingType | null) => void;
  
  /** Current drawing style */
  style: DrawingStyle;
  
  /** Callback when style changes */
  onStyleChange: (style: Partial<DrawingStyle>) => void;
  
  /** Active drawings count */
  drawingsCount: number;
  
  /** Callback to save all drawings */
  onSaveDrawings?: () => Promise<void>;
  
  /** Callback to clear all drawings */
  onClearDrawings?: () => void;
  
  /** Callback to undo last drawing */
  onUndo?: () => void;
  
  /** Loading state */
  loading?: boolean;
}

// ============================================================================
// DRAWING TOOLS COMPONENT
// ============================================================================

/**
 * Tool Button Component (memoized to prevent re-renders)
 */
interface ToolButtonProps {
  tool: DrawingType;
  icon: React.ReactNode;
  title: string;
  disabled?: boolean;
  selectedTool: DrawingType | null;
  onToolSelect: (tool: DrawingType | null) => void;
  loading?: boolean;
}

const ToolButton: React.FC<ToolButtonProps> = React.memo(({ 
  tool, 
  icon, 
  title, 
  disabled, 
  selectedTool, 
  onToolSelect, 
  loading 
}) => (
  <Tooltip title={title}>
    <Button
      type={selectedTool === tool ? 'primary' : 'default'}
      icon={icon}
      onClick={() => onToolSelect(selectedTool === tool ? null : tool)}
      disabled={disabled || loading}
    />
  </Tooltip>
));

ToolButton.displayName = 'ToolButton';

export const DrawingTools: React.FC<DrawingToolsProps> = ({
  selectedTool,
  onToolSelect,
  style,
  onStyleChange,
  drawingsCount,
  onSaveDrawings,
  onClearDrawings,
  onUndo,
  loading = false,
}) => {
  // State
  const [savingDrawings, setSavingDrawings] = useState(false);

  // Handle save drawings
  const handleSaveDrawings = async () => {
    if (!onSaveDrawings) return;

    setSavingDrawings(true);
    try {
      await onSaveDrawings();
      message.success('Drawings saved successfully');
    } catch (error) {
      message.error('Failed to save drawings');
      console.error('Save drawings error:', error);
    } finally {
      setSavingDrawings(false);
    }
  };

  // Handle clear drawings
  const handleClearDrawings = () => {
    if (onClearDrawings) {
      onClearDrawings();
      message.success('All drawings cleared');
    }
  };

  // Handle undo
  const handleUndo = () => {
    if (onUndo) {
      onUndo();
      message.info('Undid last drawing');
    }
  };

  // Style configuration dropdown
  const styleMenuItems: MenuProps['items'] = [
    {
      key: 'color',
      label: (
        <Space>
          <span>Color:</span>
          <ColorPicker
            value={style.color}
            onChange={(_, hex) => onStyleChange({ color: hex })}
            showText
          />
        </Space>
      ),
    },
    {
      key: 'lineWidth',
      label: (
        <Space>
          <span>Line Width:</span>
          <InputNumber
            min={1}
            max={10}
            value={style.lineWidth}
            onChange={(value) => value && onStyleChange({ lineWidth: value })}
            style={{ width: 80 }}
          />
        </Space>
      ),
    },
    {
      key: 'lineStyle',
      label: (
        <Space>
          <span>Line Style:</span>
          <Select
            value={style.lineStyle}
            onChange={(value) => onStyleChange({ lineStyle: value })}
            style={{ width: 100 }}
            options={[
              { label: 'Solid', value: 'solid' },
              { label: 'Dashed', value: 'dashed' },
              { label: 'Dotted', value: 'dotted' },
            ]}
          />
        </Space>
      ),
    },
    {
      type: 'divider',
    },
    {
      key: 'fillColor',
      label: (
        <Space>
          <span>Fill Color:</span>
          <ColorPicker
            value={style.fillColor || '#2962FF'}
            onChange={(_, hex) => onStyleChange({ fillColor: hex })}
            showText
          />
        </Space>
      ),
    },
    {
      key: 'fillOpacity',
      label: (
        <Space>
          <span>Fill Opacity:</span>
          <InputNumber
            min={0}
            max={1}
            step={0.1}
            value={style.fillOpacity}
            onChange={(value) => value !== null && onStyleChange({ fillOpacity: value })}
            style={{ width: 80 }}
          />
        </Space>
      ),
    },
    {
      type: 'divider',
    },
    {
      key: 'textSize',
      label: (
        <Space>
          <span>Text Size:</span>
          <InputNumber
            min={8}
            max={24}
            value={style.textSize}
            onChange={(value) => value && onStyleChange({ textSize: value })}
            style={{ width: 80 }}
          />
        </Space>
      ),
    },
  ];

  return (
    <Space size="small" wrap>
      {/* Line Tools */}
      <Space.Compact>
        <ToolButton
          tool="trendline"
          icon={<LineOutlined />}
          title="Trendline (2 points)"
          selectedTool={selectedTool}
          onToolSelect={onToolSelect}
          loading={loading}
        />
        <ToolButton
          tool="horizontal"
          icon={<MinusOutlined />}
          title="Horizontal Line"
          selectedTool={selectedTool}
          onToolSelect={onToolSelect}
          loading={loading}
        />
        <ToolButton
          tool="vertical"
          icon={<ColumnHeightOutlined />}
          title="Vertical Line"
          selectedTool={selectedTool}
          onToolSelect={onToolSelect}
          loading={loading}
        />
      </Space.Compact>

      {/* Advanced Tools */}
      <Space.Compact>
        <ToolButton
          tool="fibonacci"
          icon={<FallOutlined />}
          title="Fibonacci Retracement"
          selectedTool={selectedTool}
          onToolSelect={onToolSelect}
          loading={loading}
        />
        <ToolButton
          tool="rectangle"
          icon={<BorderOutlined />}
          title="Rectangle"
          selectedTool={selectedTool}
          onToolSelect={onToolSelect}
          loading={loading}
        />
        <ToolButton
          tool="ellipse"
          icon={<RadiusSettingOutlined />}
          title="Ellipse"
          selectedTool={selectedTool}
          onToolSelect={onToolSelect}
          loading={loading}
        />
      </Space.Compact>

      {/* Text Tool */}
      <ToolButton
        tool="text"
        icon={<FontSizeOutlined />}
        title="Text Annotation"
        selectedTool={selectedTool}
        onToolSelect={onToolSelect}
        loading={loading}
      />

      {/* Style Configuration */}
      <Dropdown
        menu={{ items: styleMenuItems }}
        trigger={['click']}
        placement="bottomLeft"
      >
        <Button>
          Style
          <div
            style={{
              width: 16,
              height: 16,
              backgroundColor: style.color,
              border: '1px solid #d9d9d9',
              borderRadius: 2,
              marginLeft: 8,
              display: 'inline-block',
            }}
          />
        </Button>
      </Dropdown>

      {/* Actions */}
      <Space.Compact>
        <Tooltip title="Undo last drawing">
          <Button
            icon={<UndoOutlined />}
            onClick={handleUndo}
            disabled={!onUndo || drawingsCount === 0 || loading}
          />
        </Tooltip>

        <Tooltip title="Save all drawings">
          <Badge count={drawingsCount} offset={[-5, 5]}>
            <Button
              icon={<SaveOutlined />}
              onClick={handleSaveDrawings}
              loading={savingDrawings}
              disabled={!onSaveDrawings || drawingsCount === 0 || loading}
            />
          </Badge>
        </Tooltip>

        <Tooltip title="Clear all drawings">
          <Popconfirm
            title="Clear all drawings?"
            description="This will remove all drawings from the chart."
            onConfirm={handleClearDrawings}
            okText="Clear"
            cancelText="Cancel"
            okButtonProps={{ danger: true }}
            disabled={!onClearDrawings || drawingsCount === 0 || loading}
          >
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={!onClearDrawings || drawingsCount === 0 || loading}
            />
          </Popconfirm>
        </Tooltip>
      </Space.Compact>

      {/* Active Tool Indicator */}
      {selectedTool && (
        <span style={{ color: '#1890ff', fontSize: 12, fontWeight: 500 }}>
          {selectedTool.charAt(0).toUpperCase() + selectedTool.slice(1)} Tool Active
        </span>
      )}
    </Space>
  );
};

export default DrawingTools;
