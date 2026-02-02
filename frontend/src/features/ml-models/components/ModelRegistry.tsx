/**
 * Model Registry Component
 * Table view of all ML models with filtering, search, and pagination
 * Phase 6 Implementation
 */

import React, { useState } from 'react';
import {
  Table,
  Space,
  Button,
  Input,
  Select,
  Tag,
  Tooltip,
  Popconfirm,
  App,
  Card,
  Row,
  Col,
  Alert,
  Result,
  Skeleton,
} from 'antd';
import {
  EyeOutlined,
  DeleteOutlined,
  RocketOutlined,
  StopOutlined,
  ReloadOutlined,
  SearchOutlined,
  FilterOutlined,
} from '@ant-design/icons';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { mlApi, mlQueryKeys, mlQueryOptions, getModelStatusColor, formatAccuracy } from '@/services/mlApi';
import type { ModelInfo, ModelStatus, ModelType as MLModelType } from '@/types/ml';
import { colors } from '@/styles/theme';
import { useErrorHandler } from '../hooks/useErrorHandler';
import { useIsMobile } from '@/hooks/useResponsive';
import { MobileModelCardGrid } from './ModelCard_Mobile';
import { useDebounce } from '@/hooks/usePerformance';
import { useAnnouncer, useAriaId } from '@/hooks/useAccessibility';

const { Search } = Input;
const { Option } = Select;

/**
 * Model Registry Table Component
 */
export const ModelRegistry: React.FC = () => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { handleError } = useErrorHandler();
  const isMobile = useIsMobile();
  const announce = useAnnouncer();
  const searchId = useAriaId('model-search');

  // State for filters and pagination
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<ModelStatus | 'all'>('all');
  const [typeFilter, setTypeFilter] = useState<MLModelType | 'all'>('all');
  const [activeOnly, setActiveOnly] = useState(false);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
  });

  // Debounce search to reduce API calls
  const debouncedSearch = useDebounce(search, 500);

  // Track which item is being acted upon
  const [activatingId, setActivatingId] = useState<string | undefined>();
  const [deletingId, setDeletingId] = useState<string | undefined>();

  // Fetch models with filters - with error handling
  const { data: modelsData, isLoading, isError, error, refetch } = useQuery({
    queryKey: mlQueryKeys.list({
      page: pagination.current,
      page_size: pagination.pageSize,
      active_only: activeOnly || undefined,
      model_type: typeFilter !== 'all' ? typeFilter : undefined,
    }),
    queryFn: () =>
      mlApi.listModels({
        page: pagination.current,
        page_size: pagination.pageSize,
        active_only: activeOnly || undefined,
        model_type: typeFilter !== 'all' ? typeFilter : undefined,
      }),
    retry: 2, // Automatic retry on failure
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    ...mlQueryOptions.models,
  });

  // Delete model mutation - with error handling
  const deleteMutation = useMutation({
    mutationFn: (modelId: string) => mlApi.deleteModel(modelId),
    onMutate: (modelId) => {
      setDeletingId(modelId);
    },
    onSuccess: () => {
      message.success('Model deleted successfully');
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.stats() });
      setDeletingId(undefined);
    },
    onError: (error: unknown) => {
      handleError(error);
      setDeletingId(undefined);
    },
  });

  // Activate/deactivate model mutation - with error handling
  const activateMutation = useMutation({
    mutationFn: ({ modelId, active }: { modelId: string; active: boolean }) =>
      mlApi.activateModel(modelId, { active }),
    onMutate: ({ modelId }) => {
      setActivatingId(modelId);
    },
    onSuccess: (_, variables) => {
      message.success(
        variables.active ? 'Model activated successfully' : 'Model deactivated successfully'
      );
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.stats() });
      setActivatingId(undefined);
    },
    onError: (error: unknown) => {
      handleError(error);
      setActivatingId(undefined);
    },
  });

  // Filter data by search - using debounced search for performance
  const filteredData = React.useMemo(() => {
    if (!modelsData?.models) return [];
    
    if (!debouncedSearch) return modelsData.models;
    
    const searchLower = debouncedSearch.toLowerCase();
    const filtered = modelsData.models.filter(
      (model: ModelInfo) =>
        model.name.toLowerCase().includes(searchLower) ||
        model.model_type.toLowerCase().includes(searchLower) ||
        model.version.toLowerCase().includes(searchLower)
    );
    
    // Announce search results to screen readers
    announce(`Found ${filtered.length} model${filtered.length !== 1 ? 's' : ''}`);
    
    return filtered;
  }, [modelsData?.models, debouncedSearch, announce]);

  // Handle pagination change
  const handleTableChange = (newPagination: TablePaginationConfig) => {
    setPagination({
      current: newPagination.current || 1,
      pageSize: newPagination.pageSize || 10,
    });
  };

  // Handle delete
  const handleDelete = (modelId: string) => {
    deleteMutation.mutate(modelId);
  };

  // Handle activate/deactivate
  const handleToggleActive = (modelId: string, currentActive: boolean) => {
    activateMutation.mutate({ modelId, active: !currentActive });
  };

  // Handle view details
  const handleViewDetails = (modelId: string) => {
    navigate(`/ml-models/${modelId}`);
  };

  // Table columns
  const columns: ColumnsType<ModelInfo> = [
    {
      title: 'Model Name',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      fixed: 'left',
      render: (name: string, record: ModelInfo) => (
        <Space direction="vertical" size={0}>
          <strong style={{ color: colors.text.primary }}>{name}</strong>
          <span style={{ fontSize: 12, color: colors.text.tertiary }}>v{record.version}</span>
        </Space>
      ),
      sorter: (a, b) => a.name.localeCompare(b.name),
    },
    {
      title: 'Type',
      dataIndex: 'model_type',
      key: 'model_type',
      width: 120,
      render: (type: string) => (
        <Tag color="blue">{type.replace('_', ' ').toUpperCase()}</Tag>
      ),
      filters: [
        { text: 'Ensemble', value: 'ensemble' },
        { text: 'LSTM', value: 'lstm' },
        { text: 'XGBoost', value: 'xgboost' },
        { text: 'Random Forest', value: 'random_forest' },
        { text: 'Regression', value: 'regression' },
        { text: 'Classification', value: 'classification' },
      ],
      onFilter: (value, record) => record.model_type === value,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={getModelStatusColor(status)}>{status.toUpperCase()}</Tag>
      ),
      filters: [
        { text: 'Training', value: 'training' },
        { text: 'Ready', value: 'ready' },
        { text: 'Failed', value: 'failed' },
        { text: 'Inactive', value: 'inactive' },
      ],
      onFilter: (value, record) => record.status === value,
    },
    {
      title: 'Active',
      dataIndex: 'active',
      key: 'active',
      width: 80,
      render: (active: boolean) => (
        <Tag color={active ? 'success' : 'default'}>
          {active ? 'Yes' : 'No'}
        </Tag>
      ),
      filters: [
        { text: 'Active', value: true },
        { text: 'Inactive', value: false },
      ],
      onFilter: (value, record) => record.active === value,
    },
    {
      title: 'Accuracy',
      dataIndex: 'metrics',
      key: 'accuracy',
      width: 100,
      render: (metrics: ModelInfo['metrics']) => {
        const accuracy = metrics?.accuracy;
        if (!accuracy) return <span style={{ color: colors.text.tertiary }}>N/A</span>;
        
        const color = accuracy >= 0.9 ? colors.semantic.success : 
                     accuracy >= 0.7 ? colors.semantic.warning : 
                     colors.semantic.error;
        
        return (
          <span style={{ color, fontWeight: 'bold' }}>
            {formatAccuracy(accuracy)}
          </span>
        );
      },
      sorter: (a, b) => (a.metrics?.accuracy || 0) - (b.metrics?.accuracy || 0),
    },
    {
      title: 'F1 Score',
      dataIndex: 'metrics',
      key: 'f1_score',
      width: 100,
      render: (metrics: ModelInfo['metrics']) => {
        const f1 = metrics?.f1_score;
        if (!f1) return <span style={{ color: colors.text.tertiary }}>N/A</span>;
        return formatAccuracy(f1);
      },
      sorter: (a, b) => (a.metrics?.f1_score || 0) - (b.metrics?.f1_score || 0),
    },
    {
      title: 'Training Time',
      dataIndex: 'metrics',
      key: 'training_time',
      width: 120,
      render: (metrics: ModelInfo['metrics']) => {
        const time = metrics?.training_time;
        if (!time) return <span style={{ color: colors.text.tertiary }}>N/A</span>;
        const minutes = Math.round(time / 60);
        return `${minutes}m`;
      },
      sorter: (a, b) => (a.metrics?.training_time || 0) - (b.metrics?.training_time || 0),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 110,
      render: (date: string) => dayjs(date).format('MMM DD, YYYY'),
      sorter: (a, b) => dayjs(a.created_at).unix() - dayjs(b.created_at).unix(),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      fixed: 'right',
      render: (_, record: ModelInfo) => (
        <Space size="small">
          <Tooltip title="View Details">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => handleViewDetails(record.id)}
              aria-label={`View details for ${record.name}`}
            />
          </Tooltip>
          
          <Tooltip title={record.active ? 'Deactivate' : 'Activate'}>
            <Button
              type="text"
              size="small"
              icon={record.active ? <StopOutlined /> : <RocketOutlined />}
              onClick={() => handleToggleActive(record.id, record.active)}
              loading={activateMutation.isPending}
              style={{ color: record.active ? colors.semantic.warning : colors.semantic.success }}
              aria-label={`${record.active ? 'Deactivate' : 'Activate'} model ${record.name}`}
            />
          </Tooltip>
          
          <Popconfirm
            title="Delete Model"
            description="Are you sure you want to delete this model? This action cannot be undone."
            onConfirm={() => handleDelete(record.id)}
            okText="Yes, delete"
            cancelText="Cancel"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="Delete">
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={deleteMutation.isPending}
                aria-label={`Delete model ${record.name}`}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Filters */}
      <Card size="small">
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={12} md={8}>
            <Search
              placeholder="Search by name, type, or version..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onSearch={(value) => setSearch(value)}
              prefix={<SearchOutlined />}
              allowClear
              aria-label="Search ML models by name, type, or version"
              aria-describedby={`${searchId}-description`}
              id={searchId}
            />
            <span id={`${searchId}-description`} className="sr-only">
              Type to filter models in real-time. Results update as you type.
            </span>
          </Col>
          
          <Col xs={12} sm={6} md={4}>
            <Select
              style={{ width: '100%' }}
              placeholder="Status"
              value={statusFilter}
              onChange={setStatusFilter}
              aria-label="Filter models by status"
            >
              <Option value="all">All Status</Option>
              <Option value="training">Training</Option>
              <Option value="ready">Ready</Option>
              <Option value="failed">Failed</Option>
              <Option value="inactive">Inactive</Option>
            </Select>
          </Col>
          
          <Col xs={12} sm={6} md={4}>
            <Select
              style={{ width: '100%' }}
              placeholder="Type"
              value={typeFilter}
              onChange={setTypeFilter}
              aria-label="Filter models by type"
            >
              <Option value="all">All Types</Option>
              <Option value="ensemble">Ensemble</Option>
              <Option value="lstm">LSTM</Option>
              <Option value="xgboost">XGBoost</Option>
              <Option value="random_forest">Random Forest</Option>
              <Option value="regression">Regression</Option>
              <Option value="classification">Classification</Option>
            </Select>
          </Col>
          
          <Col xs={12} sm={6} md={4}>
            <Select
              style={{ width: '100%' }}
              placeholder="Active Status"
              value={activeOnly ? 'active' : 'all'}
              onChange={(value) => setActiveOnly(value === 'active')}
              aria-label="Filter models by active status"
            >
              <Option value="all">All Models</Option>
              <Option value="active">Active Only</Option>
            </Select>
          </Col>
          
          <Col xs={12} sm={6} md={4}>
            <Space>
              <Tooltip title="Refresh">
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => refetch()}
                  loading={isLoading}
                  aria-label="Refresh models list"
                />
              </Tooltip>
              
              <Tooltip title="Reset Filters">
                <Button
                  icon={<FilterOutlined />}
                  onClick={() => {
                    setSearch('');
                    setStatusFilter('all');
                    setTypeFilter('all');
                    setActiveOnly(false);
                  }}
                  aria-label="Reset all filters"
                />
              </Tooltip>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Error State */}
      {isError && (
        <Card>
          <Result
            status="error"
            title="Failed to Load Models"
            subTitle="We encountered an error while loading your models. Please try again."
            extra={[
              <Button type="primary" key="retry" icon={<ReloadOutlined />} onClick={() => refetch()}>
                Retry
              </Button>,
              <Button key="reset" onClick={() => {
                setSearch('');
                setStatusFilter('all');
                setTypeFilter('all');
                setActiveOnly(false);
                setPagination({ current: 1, pageSize: 10 });
              }}>
                Reset Filters
              </Button>,
            ]}
          >
            {error && (
              <Alert
                message="Error Details"
                description={error instanceof Error ? error.message : 'Unknown error occurred'}
                type="error"
                showIcon
                style={{ marginTop: 16, textAlign: 'left' }}
              />
            )}
          </Result>
        </Card>
      )}

      {/* Empty State - No Results */}
      {!isError && !isLoading && filteredData.length === 0 && (
        <Card>
          <Result
            icon={<SearchOutlined style={{ color: colors.text.tertiary }} />}
            title="No Models Found"
            subTitle={
              search || statusFilter !== 'all' || typeFilter !== 'all' || activeOnly
                ? 'Try adjusting your filters or search criteria.'
                : 'No ML models have been trained yet. Start by training your first model!'
            }
            extra={
              search || statusFilter !== 'all' || typeFilter !== 'all' || activeOnly ? (
                <Button
                  type="primary"
                  onClick={() => {
                    setSearch('');
                    setStatusFilter('all');
                    setTypeFilter('all');
                    setActiveOnly(false);
                  }}
                >
                  Clear Filters
                </Button>
              ) : (
                <Button type="primary" onClick={() => navigate('/ml-models?tab=training')}>
                  Train New Model
                </Button>
              )
            }
          />
        </Card>
      )}

      {/* Table/Cards - Responsive */}
      {!isError && (isLoading || filteredData.length > 0) && (
        <>
          {isLoading && filteredData.length === 0 ? (
            <Skeleton active paragraph={{ rows: 8 }} />
          ) : isMobile ? (
            // Mobile: Card Grid
            <MobileModelCardGrid
              models={filteredData}
              onViewDetails={handleViewDetails}
              onToggleActive={handleToggleActive}
              onDelete={handleDelete}
              activatingId={activatingId}
              deletingId={deletingId}
            />
          ) : (
            // Desktop: Table
            <Card>
              <Table
                columns={columns}
                dataSource={filteredData}
                rowKey="id"
                loading={isLoading && filteredData.length > 0}
                pagination={{
                  current: pagination.current,
                  pageSize: pagination.pageSize,
                  total: modelsData?.total || 0,
                  showSizeChanger: true,
                  showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} models`,
                  pageSizeOptions: ['10', '20', '50', '100'],
                }}
                onChange={handleTableChange}
                scroll={{ x: 1200 }}
                size="middle"
                aria-label="ML Models table"
                aria-describedby="models-table-description"
              />
              <span id="models-table-description" className="sr-only">
                Table showing all ML models with their status, performance metrics, and actions. 
                Use arrow keys to navigate between rows, and Tab to navigate between interactive elements.
              </span>
            </Card>
          )}
        </>
      )}
    </Space>
  );
};

export default ModelRegistry;
