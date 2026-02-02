/**
 * Watchlist Symbol Card Component
 * Displays a single symbol with real-time quote data and drag handle
 */

import React from 'react';
import { Card, Space, Typography, Button } from 'antd';
import { DeleteOutlined, HolderOutlined } from '@ant-design/icons';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useWatchlistQuotes, useRemoveSymbol } from '../../hooks/useWatchlists';
import type { WatchlistSymbol } from '../../services/watchlistApi';

const { Text } = Typography;

interface WatchlistSymbolCardProps {
  symbol: WatchlistSymbol;
  watchlistId: number;
  onSymbolClick?: (symbol: string) => void;
  compact?: boolean;
}

const WatchlistSymbolCard: React.FC<WatchlistSymbolCardProps> = ({
  symbol,
  watchlistId,
  onSymbolClick,
  compact = false,
}) => {
  const { data: quotes } = useWatchlistQuotes(watchlistId);
  const removeSymbol = useRemoveSymbol();

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: symbol.symbol });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    cursor: 'pointer',
  };

  const quote = quotes?.[symbol.symbol];

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    removeSymbol.mutate({
      id: watchlistId,
      symbol: symbol.symbol,
    });
  };

  const handleClick = () => {
    if (onSymbolClick) {
      onSymbolClick(symbol.symbol);
    }
  };

  return (
    <div ref={setNodeRef} style={style}>
      <Card
        size="small"
        hoverable
        onClick={handleClick}
        styles={{
          body: {
            padding: compact ? '8px' : '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          },
        }}
      >
        <Space style={{ flex: 1 }}>
          {/* Drag Handle */}
          <div {...attributes} {...listeners} style={{ cursor: 'grab' }}>
            <HolderOutlined style={{ fontSize: 16, color: '#999' }} />
          </div>

          {/* Symbol and Quote Data */}
          <div style={{ flex: 1 }}>
            <Space direction="vertical" size={0}>
              <Text strong style={{ fontSize: compact ? 14 : 16 }}>
                {symbol.symbol}
              </Text>
              {quote && (
                <Space size="small">
                  <Text style={{ fontSize: compact ? 12 : 14 }}>
                    ${quote.price.toFixed(2)}
                  </Text>
                  <Text
                    type={quote.change >= 0 ? 'success' : 'danger'}
                    style={{ fontSize: compact ? 11 : 13 }}
                  >
                    {quote.change >= 0 ? '+' : ''}
                    {quote.changePercent.toFixed(2)}%
                  </Text>
                </Space>
              )}
            </Space>
          </div>
        </Space>

        {/* Remove Button */}
        <Button
          type="text"
          danger
          size="small"
          icon={<DeleteOutlined />}
          onClick={handleRemove}
          loading={removeSymbol.isPending}
        />
      </Card>
    </div>
  );
};

export default WatchlistSymbolCard;
