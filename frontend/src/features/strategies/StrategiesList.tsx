/**
 * Strategies List
 * Main table/grid view for all strategies with filtering and actions
 */

import React, { useState, useMemo } from 'react';
import {
  Table,
  Space,
  Button,
  Input,
  Select,
  Row,
  Col,
  App,
  Popconfirm,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  PlusOutlined,
  SearchOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useStrategiesStore } from '@/store/strategiesStore';
import { strategiesService } from '@/services/strategiesService';
import type { Strategy, StrategyStatus, StrategyType } from '@/types/strategy';
import type { StrategyUpdateMessage } from '@/types/websocket';
import { useWebSocket } from '@/hooks/useWebSocket';
import { StrategyStatusBadge } from '@/components/strategies/StrategyStatusBadge';
import { StrategyCard } from '@/components/strategies/StrategyCard';
import { colors, fontSizes } from '@/styles/theme';
import { formatCurrency, formatPercent } from '@/utils/formatters';
import { getStrategyTypeConfig } from '@/utils/strategyTypeConfig';

const { Search } = Input;
const { Text } = Typography;

type ViewMode = 'table' | 'grid';

export const StrategiesList: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const strategies = useStrategiesStore((state) => state.strategies);
  const updateStrategy = useStrategiesStore((state) => state.updateStrategy);
  const removeStrategy = useStrategiesStore((state) => state.removeStrategy);

  const [viewMode, setViewMode] = useState<ViewMode>('table');
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<StrategyStatus | 'all'>('all');
  const [typeFilter, setTypeFilter] = useState<StrategyType | 'all'>('all');
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());

  // WebSocket handler for real-time strategy updates
  const handleStrategyUpdate = React.useCallback((wsMessage: StrategyUpdateMessage) => {
    // Handle delete action
    if (wsMessage.data.action === 'deleted') {
      removeStrategy(wsMessage.data.strategyId);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      message.info(`Strategy deleted`);
      return;
    }
    
    // Handle update action (status changes, etc.)
    if (wsMessage.data.action === 'updated' && wsMessage.data.strategy) {
      const strategy = wsMessage.data.strategy;
      updateStrategy(strategy.strategyId, strategy);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      
      // Show notification for status changes
      if (strategy.status === 'active') {
        message.success(`Strategy "${strategy.name}" started`);
      } else if (strategy.status === 'paused') {
        message.info(`Strategy "${strategy.name}" paused`);
      } else if (strategy.status === 'stopped') {
        message.info(`Strategy "${strategy.name}" stopped`);
      } else if (strategy.status === 'error') {
        message.error(`Strategy "${strategy.name}" encountered an error`);
      }
      return;
    }
    
    // Direct strategy data format (current backend format)
    if (wsMessage.data.strategyId) {
      updateStrategy(wsMessage.data.strategyId, wsMessage.data);
      // Don't show duplicate notifications if they were already shown by the mutation
    }
  }, [updateStrategy, removeStrategy, queryClient]);

  // Subscribe to strategy updates via WebSocket
  useWebSocket('strategies', handleStrategyUpdate);

  // Start strategy mutation
  const startMutation = useMutation({
    mutationFn: (strategyId: string) => strategiesService.startStrategy(strategyId),
    onSuccess: (updatedStrategy) => {
      message.success(`Strategy "${updatedStrategy.name}" started successfully`);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(updatedStrategy.strategyId);
        return next;
      });
    },
    onError: (error: unknown, strategyId: string) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to start strategy');
      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(strategyId);
        return next;
      });
    },
  });

  // Pause strategy mutation
  const pauseMutation = useMutation({
    mutationFn: (strategyId: string) => strategiesService.pauseStrategy(strategyId),
    onSuccess: (updatedStrategy) => {
      message.success(`Strategy "${updatedStrategy.name}" paused successfully`);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(updatedStrategy.strategyId);
        return next;
      });
    },
    onError: (error: unknown, strategyId: string) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to pause strategy');
      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(strategyId);
        return next;
      });
    },
  });

  // Stop strategy mutation
  const stopMutation = useMutation({
    mutationFn: (strategyId: string) => strategiesService.stopStrategy(strategyId),
    onSuccess: (updatedStrategy) => {
      message.success(`Strategy "${updatedStrategy.name}" stopped successfully`);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(updatedStrategy.strategyId);
        return next;
      });
    },
    onError: (error: unknown, strategyId: string) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to stop strategy');
      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(strategyId);
        return next;
      });
    },
  });

  // Delete strategy mutation
  const deleteMutation = useMutation({
    mutationFn: (strategyId: string) => strategiesService.deleteStrategy(strategyId),
    onSuccess: (_, strategyId) => {
      message.success('Strategy deleted successfully');
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(strategyId);
        return next;
      });
    },
    onError: (error: unknown, strategyId: string) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to delete strategy');
      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(strategyId);
        return next;
      });
    },
  });

  // Action handlers
  const handleStart = (strategyId: string) => {
    setLoadingIds((prev) => new Set(prev).add(strategyId));
    startMutation.mutate(strategyId);
  };

  const handlePause = (strategyId: string) => {
    setLoadingIds((prev) => new Set(prev).add(strategyId));
    pauseMutation.mutate(strategyId);
  };

  const handleStop = (strategyId: string) => {
    setLoadingIds((prev) => new Set(prev).add(strategyId));
    stopMutation.mutate(strategyId);
  };

  const handleEdit = (strategyId: string) => {
    navigate(`/strategies/${strategyId}/edit`);
  };

  const handleDelete = (strategyId: string) => {
    setLoadingIds((prev) => new Set(prev).add(strategyId));
    deleteMutation.mutate(strategyId);
  };

  const handleView = (strategyId: string) => {
    navigate(`/strategies/${strategyId}`);
  };

  // Filtered strategies
  const filteredStrategies = useMemo(() => {
    return strategies.filter((strategy) => {
      // Search filter
      if (searchText) {
        const searchLower = searchText.toLowerCase();
        const matchesName = strategy.name.toLowerCase().includes(searchLower);
        const matchesDescription = strategy.description
          .toLowerCase()
          .includes(searchLower);
        if (!matchesName && !matchesDescription) {
          return false;
        }
      }

      // Status filter
      if (statusFilter !== 'all' && strategy.status !== statusFilter) {
        return false;
      }

      // Type filter
      if (typeFilter !== 'all' && strategy.strategyType !== typeFilter) {
        return false;
      }

      return true;
    });
  }, [strategies, searchText, statusFilter, typeFilter]);

  // Table columns
  const columns: ColumnsType<Strategy> = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      fixed: 'left',
      render: (name: string, record: Strategy) => {
        const typeConfig = getStrategyTypeConfig(record.strategyType);
        return (
          <Space direction="vertical" size={0}>
            <Button
              type="link"
              onClick={() => handleView(record.strategyId)}
              style={{ padding: 0, height: 'auto', fontSize: fontSizes.base }}
            >
              <Space>
                <span style={{ fontSize: '16px' }}>{typeConfig.icon}</span>
                {name}
              </Space>
            </Button>
            <Text type="secondary" style={{ fontSize: fontSizes.xs, color: typeConfig.color }}>
              {typeConfig.label}
            </Text>
          </Space>
        );
      },
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      filters: [
        { text: 'Active', value: 'active' },
        { text: 'Paused', value: 'paused' },
        { text: 'Stopped', value: 'stopped' },
        { text: 'Error', value: 'error' },
      ],
      onFilter: (value, record) => record.status === value,
      render: (status: StrategyStatus) => <StrategyStatusBadge status={status} />,
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (description: string) => (
        <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
          {description}
        </Text>
      ),
    },
    {
      title: 'Total P&L',
      key: 'totalPnL',
      width: 140,
      sorter: (a, b) =>
        (a.performance?.totalPnL ?? 0) - (b.performance?.totalPnL ?? 0),
      render: (_, record: Strategy) => {
        if (!record.performance) return <Text type="secondary">N/A</Text>;
        const pnl = record.performance.totalPnL;
        return (
          <Text
            strong
            style={{
              color: pnl >= 0 ? colors.semantic.profit : colors.semantic.loss,
            }}
          >
            {formatCurrency(pnl)}
          </Text>
        );
      },
    },
    {
      title: 'Win Rate',
      key: 'winRate',
      width: 120,
      sorter: (a, b) =>
        (a.performance?.winRate ?? 0) - (b.performance?.winRate ?? 0),
      render: (_, record: Strategy) => {
        if (!record.performance) return <Text type="secondary">N/A</Text>;
        return (
          <Text strong>{formatPercent(record.performance.winRate)}</Text>
        );
      },
    },
    {
      title: 'Total Trades',
      key: 'totalTrades',
      width: 120,
      sorter: (a, b) =>
        (a.performance?.totalTrades ?? 0) - (b.performance?.totalTrades ?? 0),
      render: (_, record: Strategy) => {
        if (!record.performance) return <Text type="secondary">N/A</Text>;
        return <Text>{record.performance.totalTrades}</Text>;
      },
    },
    {
      title: 'Sharpe Ratio',
      key: 'sharpeRatio',
      width: 130,
      sorter: (a, b) =>
        (a.performance?.sharpeRatio ?? 0) - (b.performance?.sharpeRatio ?? 0),
      render: (_, record: Strategy) => {
        if (!record.performance) return <Text type="secondary">N/A</Text>;
        const sharpe = record.performance.sharpeRatio;
        return (
          <Text
            style={{
              color: sharpe >= 1 ? colors.semantic.success : colors.text.secondary,
            }}
          >
            {sharpe.toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_, record: Strategy) => {
        const isLoading = loadingIds.has(record.strategyId);
        const canStart = record.status === 'stopped' || record.status === 'paused';
        const canPause = record.status === 'active';
        const canStop = record.status === 'active' || record.status === 'paused';

        return (
          <Space size="small">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => handleView(record.strategyId)}
            />
            {canStart && (
              <Button
                type="text"
                size="small"
                icon={<PlayCircleOutlined />}
                onClick={() => handleStart(record.strategyId)}
                loading={isLoading}
                style={{ color: colors.semantic.success }}
              />
            )}
            {canPause && (
              <Button
                type="text"
                size="small"
                icon={<PauseCircleOutlined />}
                onClick={() => handlePause(record.strategyId)}
                loading={isLoading}
                style={{ color: colors.semantic.warning }}
              />
            )}
            {canStop && (
              <Button
                type="text"
                size="small"
                icon={<StopOutlined />}
                onClick={() => handleStop(record.strategyId)}
                loading={isLoading}
                style={{ color: colors.semantic.stopped }}
              />
            )}
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record.strategyId)}
            />
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => {
                const strategy = strategies.find(s => s.strategyId === record.strategyId);
                if (strategy) {
                  navigate('/strategies/builder', { state: { cloneFrom: strategy } });
                }
              }}
              title="Clone this strategy"
            />
            <Popconfirm
              title="Delete Strategy"
              description="Are you sure you want to delete this strategy? This action cannot be undone."
              onConfirm={() => handleDelete(record.strategyId)}
              okText="Delete"
              cancelText="Cancel"
              okButtonProps={{ danger: true }}
            >
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={isLoading}
              />
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      {/* Filters and Actions */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={8}>
          <Search
            placeholder="Search strategies..."
            allowClear
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: '100%' }}
          />
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: '100%' }}
            options={[
              { label: 'All Status', value: 'all' },
              { label: 'Active', value: 'active' },
              { label: 'Paused', value: 'paused' },
              { label: 'Stopped', value: 'stopped' },
              { label: 'Error', value: 'error' },
            ]}
          />
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Select
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: '100%' }}
            options={[
              { label: 'All Types', value: 'all' },
              // Implementation Types
              { label: 'Momentum', value: 'momentum' },
              { label: 'Mean Reversion', value: 'mean_reversion' },
              { label: 'Ensemble', value: 'ensemble' },
              { label: 'Statistical Arbitrage', value: 'stat_arb' },
              // Classification Types
              { label: 'Technical Analysis', value: 'technical' },
              { label: 'Fundamental Analysis', value: 'fundamental' },
              { label: 'Quantitative', value: 'quantitative' },
              { label: 'Hybrid Strategy', value: 'hybrid' },
            ]}
          />
        </Col>
        <Col xs={24} sm={12} md={8} style={{ textAlign: 'right' }}>
          <Space>
            <Button
              type={viewMode === 'table' ? 'primary' : 'default'}
              icon={<UnorderedListOutlined />}
              onClick={() => setViewMode('table')}
            >
              Table
            </Button>
            <Button
              type={viewMode === 'grid' ? 'primary' : 'default'}
              icon={<AppstoreOutlined />}
              onClick={() => setViewMode('grid')}
            >
              Grid
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => navigate('/strategies/builder')}
            >
              Create with Wizard
            </Button>
            <Button
              icon={<PlusOutlined />}
              onClick={() => navigate('/strategies/new')}
            >
              Quick Create
            </Button>
          </Space>
        </Col>
      </Row>

      {/* Table View */}
      {viewMode === 'table' && (
        <Table
          columns={columns}
          dataSource={filteredStrategies}
          rowKey="strategyId"
          scroll={{ x: 1200 }}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} strategies`,
          }}
        />
      )}

      {/* Grid View */}
      {viewMode === 'grid' && (
        <Row gutter={[16, 16]}>
          {filteredStrategies.map((strategy) => (
            <Col key={strategy.strategyId} xs={24} sm={12} lg={8} xl={6}>
              <StrategyCard
                strategy={strategy}
                onStart={handleStart}
                onPause={handlePause}
                onStop={handleStop}
                onEdit={handleEdit}
                onDelete={handleDelete}
                loading={loadingIds.has(strategy.strategyId)}
              />
            </Col>
          ))}
        </Row>
      )}

      {/* Empty State */}
      {filteredStrategies.length === 0 && (
        <div
          style={{
            textAlign: 'center',
            padding: 48,
            background: colors.backgrounds.secondary,
            borderRadius: 8,
          }}
        >
          <Text type="secondary" style={{ fontSize: fontSizes.lg }}>
            {searchText || statusFilter !== 'all' || typeFilter !== 'all'
              ? 'No strategies match your filters'
              : 'No strategies yet. Create your first strategy to get started!'}
          </Text>
        </div>
      )}
    </div>
  );
};
