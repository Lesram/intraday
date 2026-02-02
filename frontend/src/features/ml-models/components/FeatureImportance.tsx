/**
 * Feature Importance Component
 * Visualizes feature importance for ML models
 * Phase 6 Day 5 Implementation
 */

import React from 'react';
import {
  Card,
  Select,
  Space,
  Typography,
  Button,
  Table,
  Empty,
  Alert,
  Slider,
  Row,
  Col,
  Statistic,
  Spin,
} from 'antd';
import {
  BarChartOutlined,
  DownloadOutlined,
  SortAscendingOutlined,
  SortDescendingOutlined,
  FilterOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import type { TooltipItem } from 'chart.js';
import { mlApi, mlQueryKeys, mlQueryOptions } from '@/services/mlApi';
import { colors } from '@/styles/theme';
import type { ModelInfo, FeatureImportance as FeatureImportanceType } from '@/types/ml';

// Register Chart.js components
ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

const { Text } = Typography;
const { Option } = Select;

interface FeatureImportanceProps {
  preselectedModelId?: string;
}

export const FeatureImportance: React.FC<FeatureImportanceProps> = ({
  preselectedModelId,
}) => {
  const [selectedModelId, setSelectedModelId] = React.useState<string | undefined>(
    preselectedModelId
  );
  const [sortBy, setSortBy] = React.useState<'importance' | 'name'>('importance');
  const [sortOrder, setSortOrder] = React.useState<'asc' | 'desc'>('desc');
  const [importanceThreshold, setImportanceThreshold] = React.useState<number>(0);
  const [topN, setTopN] = React.useState<number>(10);

  // Fetch all models for selection
  const { data: modelsData } = useQuery({
    queryKey: mlQueryKeys.lists(),
    queryFn: () => mlApi.listModels(),
    ...mlQueryOptions.models,
  });

  // Fetch feature importance data
  const {
    data: featureData,
    isLoading,
    error,
  } = useQuery({
    queryKey: mlQueryKeys.features(selectedModelId || ''),
    queryFn: () => mlApi.getFeatureImportance(selectedModelId!),
    enabled: !!selectedModelId,
  });

  // Export feature importance data
  const handleExport = () => {
    if (!featureData) return;

    const csv = generateCSV(featureData.features);
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `feature-importance-${featureData.model_name}-${new Date().toISOString()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Generate CSV from feature data
  const generateCSV = (features: FeatureImportanceType[]): string => {
    const headers = ['Rank', 'Feature', 'Importance'];
    const rows = [
      headers.join(','),
      ...features.map((f) => `${f.rank},"${f.feature_name}",${f.importance}`),
    ];
    return rows.join('\n');
  };

  // Filter and sort features
  const processedFeatures = React.useMemo(() => {
    if (!featureData?.features) return [];

    const filtered = featureData.features.filter(
      (f) => f.importance >= importanceThreshold
    );

    // Sort
    filtered.sort((a, b) => {
      if (sortBy === 'importance') {
        return sortOrder === 'desc'
          ? b.importance - a.importance
          : a.importance - b.importance;
      } else {
        return sortOrder === 'desc'
          ? b.feature_name.localeCompare(a.feature_name)
          : a.feature_name.localeCompare(b.feature_name);
      }
    });

    // Limit to top N
    return filtered.slice(0, topN);
  }, [featureData, importanceThreshold, sortBy, sortOrder, topN]);

  // Prepare chart data
  const chartData = React.useMemo(() => {
    if (!processedFeatures.length) return null;

    return {
      labels: processedFeatures.map((f) => f.feature_name),
      datasets: [
        {
          label: 'Feature Importance',
          data: processedFeatures.map((f) => f.importance),
          backgroundColor: processedFeatures.map((f) =>
            f.importance > 0.5
              ? `${colors.semantic.success}99`
              : f.importance > 0.25
              ? `${colors.semantic.info}99`
              : `${colors.semantic.warning}99`
          ),
          borderColor: processedFeatures.map((f) =>
            f.importance > 0.5
              ? colors.semantic.success
              : f.importance > 0.25
              ? colors.semantic.info
              : colors.semantic.warning
          ),
          borderWidth: 2,
        },
      ],
    };
  }, [processedFeatures]);

  // Chart options
  const chartOptions = {
    indexAxis: 'y' as const,
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        beginAtZero: true,
        max: 1,
        ticks: { color: colors.text.secondary },
        grid: { color: colors.backgrounds.border },
        title: {
          display: true,
          text: 'Importance Score',
          color: colors.text.primary,
        },
      },
      y: {
        ticks: { color: colors.text.secondary },
        grid: { display: false },
      },
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        callbacks: {
          label: (context: TooltipItem<'bar'>) => {
            const value = context.parsed?.x ?? 0;
            return `Importance: ${(value * 100).toFixed(2)}%`;
          },
        },
      },
    },
  };

  // Table columns
  const tableColumns = [
    {
      title: 'Rank',
      dataIndex: 'rank',
      key: 'rank',
      width: 80,
      render: (rank: number) => (
        <Text strong style={{ fontSize: 16 }}>
          #{rank}
        </Text>
      ),
    },
    {
      title: 'Feature Name',
      dataIndex: 'feature_name',
      key: 'feature_name',
      render: (name: string) => <Text code>{name}</Text>,
    },
    {
      title: 'Importance',
      dataIndex: 'importance',
      key: 'importance',
      width: 150,
      render: (importance: number) => (
        <Space direction="vertical" size={0} style={{ width: '100%' }}>
          <Text>{(importance * 100).toFixed(2)}%</Text>
          <div
            style={{
              width: '100%',
              height: 4,
              backgroundColor: colors.backgrounds.border,
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${importance * 100}%`,
                height: '100%',
                backgroundColor:
                  importance > 0.5
                    ? colors.semantic.success
                    : importance > 0.25
                    ? colors.semantic.info
                    : colors.semantic.warning,
              }}
            />
          </div>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Model Selection & Controls */}
      <Card>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Row gutter={16} align="middle">
            <Col flex="auto">
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text type="secondary">Select Model</Text>
                <Select
                  style={{ width: '100%' }}
                  placeholder="Select a model to view feature importance"
                  value={selectedModelId}
                  onChange={setSelectedModelId}
                >
                  {modelsData?.models?.map((model: ModelInfo) => (
                    <Option key={model.id} value={model.id}>
                      {model.name} (v{model.version})
                    </Option>
                  ))}
                </Select>
              </Space>
            </Col>
            <Col>
              <Button
                icon={<DownloadOutlined />}
                onClick={handleExport}
                disabled={!featureData}
              >
                Export CSV
              </Button>
            </Col>
          </Row>

          {/* Filters */}
          {selectedModelId && (
            <Row gutter={16}>
              <Col xs={24} sm={12} md={6}>
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <Text type="secondary">
                    <FilterOutlined /> Top N Features
                  </Text>
                  <Select
                    style={{ width: '100%' }}
                    value={topN}
                    onChange={setTopN}
                  >
                    <Option value={5}>Top 5</Option>
                    <Option value={10}>Top 10</Option>
                    <Option value={20}>Top 20</Option>
                    <Option value={50}>Top 50</Option>
                    <Option value={100}>All</Option>
                  </Select>
                </Space>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <Text type="secondary">Sort By</Text>
                  <Select style={{ width: '100%' }} value={sortBy} onChange={setSortBy}>
                    <Option value="importance">Importance</Option>
                    <Option value="name">Feature Name</Option>
                  </Select>
                </Space>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <Text type="secondary">Sort Order</Text>
                  <Select
                    style={{ width: '100%' }}
                    value={sortOrder}
                    onChange={setSortOrder}
                  >
                    <Option value="desc">
                      <SortDescendingOutlined /> Descending
                    </Option>
                    <Option value="asc">
                      <SortAscendingOutlined /> Ascending
                    </Option>
                  </Select>
                </Space>
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <Text type="secondary">Min Importance: {importanceThreshold}%</Text>
                  <Slider
                    min={0}
                    max={100}
                    value={importanceThreshold}
                    onChange={setImportanceThreshold}
                    tooltip={{ formatter: (value) => `${value}%` }}
                  />
                </Space>
              </Col>
            </Row>
          )}
        </Space>
      </Card>

      {/* Results */}
      {!selectedModelId ? (
        <Card>
          <Empty
            description="Select a model to view feature importance"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      ) : error ? (
        <Card>
          <Alert
            message="Error Loading Feature Importance"
            description={(error as Error).message}
            type="error"
            showIcon
          />
        </Card>
      ) : isLoading ? (
        <Card>
          <Spin tip="Loading feature importance..." />
        </Card>
      ) : (
        <>
          {/* Summary Statistics */}
          {featureData && (
            <Card>
              <Row gutter={16}>
                <Col xs={24} sm={8}>
                  <Statistic
                    title="Total Features"
                    value={featureData.features.length}
                    prefix={<BarChartOutlined />}
                  />
                </Col>
                <Col xs={24} sm={8}>
                  <Statistic
                    title="Filtered Features"
                    value={processedFeatures.length}
                  />
                </Col>
                <Col xs={24} sm={8}>
                  <Statistic
                    title="Model"
                    value={featureData.model_name}
                    valueStyle={{ fontSize: 16 }}
                  />
                </Col>
              </Row>
            </Card>
          )}

          {/* Chart Visualization */}
          {chartData && (
            <Card title="Feature Importance Chart">
              <div style={{ height: Math.max(400, processedFeatures.length * 40) }}>
                <Bar data={chartData} options={chartOptions} />
              </div>
            </Card>
          )}

          {/* Detailed Table */}
          <Card title="Detailed Feature Importance">
            <Table
              columns={tableColumns}
              dataSource={processedFeatures.map((f) => ({ ...f, key: f.feature_name }))}
              pagination={{
                pageSize: 20,
                showSizeChanger: true,
                showTotal: (total) => `Total ${total} features`,
              }}
              bordered
            />
          </Card>
        </>
      )}
    </Space>
  );
};
