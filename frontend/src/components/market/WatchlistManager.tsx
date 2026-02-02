/**
 * Watchlist Manager Component
 * Manages multiple watchlists with drag-drop reordering and real-time quotes
 */

import React, { useState } from 'react';
import {
  Button,
  Card,
  Dropdown,
  Input,
  Modal,
  Space,
  Spin,
  Tabs,
  Typography,
  Empty,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  MoreOutlined,
  StarOutlined,
  StarFilled,
} from '@ant-design/icons';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import {
  useWatchlists,
  useCreateWatchlist,
  useUpdateWatchlist,
  useDeleteWatchlist,
  useAddSymbol,
  useReorderSymbols,
} from '../../hooks/useWatchlists';
import WatchlistSymbolCard from './WatchlistSymbolCard';
import type { Watchlist, WatchlistSymbol } from '../../services/watchlistApi';

const { Text } = Typography;

interface WatchlistManagerProps {
  onSymbolClick?: (symbol: string) => void;
  compact?: boolean;
}

const WatchlistManager: React.FC<WatchlistManagerProps> = ({
  onSymbolClick,
  compact = false,
}) => {
  const [selectedWatchlistId, setSelectedWatchlistId] = useState<number | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [newSymbol, setNewSymbol] = useState('');
  const [editingWatchlist, setEditingWatchlist] = useState<Watchlist | null>(null);

  // Form states
  const [watchlistName, setWatchlistName] = useState('');
  const [watchlistDescription, setWatchlistDescription] = useState('');
  const [isDefault, setIsDefault] = useState(false);

  // React Query hooks
  const { data: watchlists, isLoading } = useWatchlists();
  const createWatchlist = useCreateWatchlist();
  const updateWatchlist = useUpdateWatchlist();
  const deleteWatchlist = useDeleteWatchlist();
  const addSymbol = useAddSymbol();
  const reorderSymbols = useReorderSymbols();

  // Drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Get current watchlist
  const currentWatchlist = watchlists?.find((w) => w.id === selectedWatchlistId);

  // Auto-select first watchlist or default
  React.useEffect(() => {
    if (watchlists && watchlists.length > 0 && !selectedWatchlistId) {
      const defaultWatchlist = watchlists.find((w) => w.is_default);
      setSelectedWatchlistId(defaultWatchlist?.id || watchlists[0].id);
    }
  }, [watchlists, selectedWatchlistId]);

  const handleCreateWatchlist = () => {
    if (!watchlistName.trim()) return;

    createWatchlist.mutate(
      {
        name: watchlistName,
        description: watchlistDescription || undefined,
        is_default: isDefault,
      },
      {
        onSuccess: () => {
          setIsCreateModalOpen(false);
          setWatchlistName('');
          setWatchlistDescription('');
          setIsDefault(false);
        },
      }
    );
  };

  const handleEditWatchlist = () => {
    if (!editingWatchlist) return;

    updateWatchlist.mutate(
      {
        id: editingWatchlist.id,
        data: {
          name: watchlistName,
          description: watchlistDescription || undefined,
          is_default: isDefault,
        },
      },
      {
        onSuccess: () => {
          setIsEditModalOpen(false);
          setEditingWatchlist(null);
          setWatchlistName('');
          setWatchlistDescription('');
          setIsDefault(false);
        },
      }
    );
  };

  const handleDeleteWatchlist = (id: number) => {
    Modal.confirm({
      title: 'Delete Watchlist',
      content: 'Are you sure you want to delete this watchlist?',
      okText: 'Delete',
      okType: 'danger',
      onOk: () => {
        deleteWatchlist.mutate(id, {
          onSuccess: () => {
            if (selectedWatchlistId === id) {
              setSelectedWatchlistId(null);
            }
          },
        });
      },
    });
  };

  const handleAddSymbol = () => {
    if (!currentWatchlist || !newSymbol.trim()) return;

    addSymbol.mutate(
      {
        id: currentWatchlist.id,
        data: { symbol: newSymbol.toUpperCase() },
      },
      {
        onSuccess: () => {
          setNewSymbol('');
        },
      }
    );
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (!currentWatchlist || !over || active.id === over.id) return;

    const oldIndex = currentWatchlist.symbols.findIndex((s) => s.symbol === active.id);
    const newIndex = currentWatchlist.symbols.findIndex((s) => s.symbol === over.id);

    if (oldIndex === -1 || newIndex === -1) return;

    const newOrder = arrayMove(currentWatchlist.symbols, oldIndex, newIndex);

    reorderSymbols.mutate({
      id: currentWatchlist.id,
      data: {
        symbol_orders: newOrder.map((s: WatchlistSymbol, idx: number) => ({ 
          symbol: s.symbol, 
          order: idx 
        })),
      },
    });
  };

  const openEditModal = (watchlist: Watchlist) => {
    setEditingWatchlist(watchlist);
    setWatchlistName(watchlist.name);
    setWatchlistDescription(watchlist.description || '');
    setIsDefault(watchlist.is_default);
    setIsEditModalOpen(true);
  };

  if (isLoading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin size="large" />
        </div>
      </Card>
    );
  }

  if (!watchlists || watchlists.length === 0) {
    return (
      <Card>
        <Empty
          description="No watchlists yet"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        >
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
          >
            Create Your First Watchlist
          </Button>
        </Empty>

        {/* Create Modal */}
        <Modal
          title="Create Watchlist"
          open={isCreateModalOpen}
          onOk={handleCreateWatchlist}
          onCancel={() => setIsCreateModalOpen(false)}
          confirmLoading={createWatchlist.isPending}
        >
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text>Name *</Text>
              <Input
                value={watchlistName}
                onChange={(e) => setWatchlistName(e.target.value)}
                placeholder="e.g., Tech Stocks, Day Trading"
                maxLength={50}
              />
            </div>
            <div>
              <Text>Description</Text>
              <Input.TextArea
                value={watchlistDescription}
                onChange={(e) => setWatchlistDescription(e.target.value)}
                placeholder="Optional description"
                rows={3}
                maxLength={200}
              />
            </div>
          </Space>
        </Modal>
      </Card>
    );
  }

  // Create tabs for each watchlist
  const tabItems = watchlists.map((watchlist) => ({
    key: watchlist.id.toString(),
    label: (
      <Space>
        {watchlist.is_default ? <StarFilled /> : null}
        {watchlist.name}
        <Text type="secondary">({watchlist.symbols?.length || 0})</Text>
      </Space>
    ),
    children: (
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          {/* Add Symbol Input */}
          <Input.Search
            placeholder="Add symbol (e.g., AAPL)"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            onSearch={handleAddSymbol}
            enterButton="Add"
            loading={addSymbol.isPending}
          />

          {/* Symbol List */}
          {currentWatchlist && currentWatchlist.symbols?.length > 0 ? (
            <SortableContext
              items={currentWatchlist.symbols.map((s) => s.symbol)}
              strategy={verticalListSortingStrategy}
            >
              {currentWatchlist.symbols.map((symbol) => (
                <WatchlistSymbolCard
                  key={symbol.symbol}
                  symbol={symbol}
                  watchlistId={currentWatchlist.id}
                  onSymbolClick={onSymbolClick}
                  compact={compact}
                />
              ))}
            </SortableContext>
          ) : (
            <Empty
              description="No symbols in this watchlist"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </Space>
      </DndContext>
    ),
  }));

  return (
    <>
      <Card
        title="Watchlists"
        extra={
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setIsCreateModalOpen(true)}
              size="small"
            >
              New
            </Button>
            {currentWatchlist && (
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'edit',
                      icon: <EditOutlined />,
                      label: 'Edit',
                      onClick: () => openEditModal(currentWatchlist),
                    },
                    {
                      key: 'setDefault',
                      icon: <StarOutlined />,
                      label: currentWatchlist.is_default
                        ? 'Unset as Default'
                        : 'Set as Default',
                      onClick: () =>
                        updateWatchlist.mutate({
                          id: currentWatchlist.id,
                          data: { is_default: !currentWatchlist.is_default },
                        }),
                    },
                    { type: 'divider' },
                    {
                      key: 'delete',
                      icon: <DeleteOutlined />,
                      label: 'Delete',
                      danger: true,
                      onClick: () => handleDeleteWatchlist(currentWatchlist.id),
                    },
                  ],
                }}
              >
                <Button size="small" icon={<MoreOutlined />} />
              </Dropdown>
            )}
          </Space>
        }
        styles={{ body: { padding: compact ? '8px' : '16px' } }}
      >
        <Tabs
          activeKey={selectedWatchlistId?.toString()}
          onChange={(key) => setSelectedWatchlistId(Number(key))}
          items={tabItems}
          size="small"
        />
      </Card>

      {/* Create Modal */}
      <Modal
        title="Create Watchlist"
        open={isCreateModalOpen}
        onOk={handleCreateWatchlist}
        onCancel={() => {
          setIsCreateModalOpen(false);
          setWatchlistName('');
          setWatchlistDescription('');
          setIsDefault(false);
        }}
        confirmLoading={createWatchlist.isPending}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text>Name *</Text>
            <Input
              value={watchlistName}
              onChange={(e) => setWatchlistName(e.target.value)}
              placeholder="e.g., Tech Stocks, Day Trading"
              maxLength={50}
            />
          </div>
          <div>
            <Text>Description</Text>
            <Input.TextArea
              value={watchlistDescription}
              onChange={(e) => setWatchlistDescription(e.target.value)}
              placeholder="Optional description"
              rows={3}
              maxLength={200}
            />
          </div>
        </Space>
      </Modal>

      {/* Edit Modal */}
      <Modal
        title="Edit Watchlist"
        open={isEditModalOpen}
        onOk={handleEditWatchlist}
        onCancel={() => {
          setIsEditModalOpen(false);
          setEditingWatchlist(null);
          setWatchlistName('');
          setWatchlistDescription('');
          setIsDefault(false);
        }}
        confirmLoading={updateWatchlist.isPending}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text>Name *</Text>
            <Input
              value={watchlistName}
              onChange={(e) => setWatchlistName(e.target.value)}
              placeholder="e.g., Tech Stocks, Day Trading"
              maxLength={50}
            />
          </div>
          <div>
            <Text>Description</Text>
            <Input.TextArea
              value={watchlistDescription}
              onChange={(e) => setWatchlistDescription(e.target.value)}
              placeholder="Optional description"
              rows={3}
              maxLength={200}
            />
          </div>
        </Space>
      </Modal>
    </>
  );
};

export default WatchlistManager;
