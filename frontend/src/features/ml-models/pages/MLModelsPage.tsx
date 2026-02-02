/**
 * ML Models Page
 * Main container for ML model management with tabs
 * Phase 6 Implementation
 */

import React, { useState } from 'react';
import { Card, Tabs, Typography, Space, Row, Col, Statistic, Button, App } from 'antd';
import {
  AppstoreOutlined,
  RocketOutlined,
  LineChartOutlined,
  SettingOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mlApi, mlQueryKeys, mlQueryOptions } from '@/services/mlApi';
import { PageSkeleton } from '@/components/common/LoadingComponents';
import { colors } from '@/styles/theme';
import { ModelRegistry } from '../components/ModelRegistry';
import { ModelCard } from '../components/ModelCard';
import { TrainingForm } from '../components/TrainingForm';
import { TrainingProgressMonitor } from '../components/TrainingProgressMonitor';
import {
  ModelComparisonLazyWrapped as ModelComparison,
  FeatureImportanceLazyWrapped as FeatureImportance,
  PerformanceChartsLazyWrapped as PerformanceCharts,
} from '../components/AnalyticsLazy';
import { LifecycleDashboard } from '../components/LifecycleDashboard';
import ErrorBoundary from '@/components/ErrorBoundary';

const { Title, Text } = Typography;

/**
 * ML Models Page Component
 */
export const MLModelsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('overview');

  // Fetch model statistics
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery({
    queryKey: mlQueryKeys.stats(),
    queryFn: () => mlApi.getModelStats(),
    ...mlQueryOptions.stats,
  });

  // Loading state
  if (statsLoading) {
    return <PageSkeleton />;
  }

  return (
    <div style={{ padding: 24, background: colors.backgrounds.primary }}>
      {/* Page Header */}
      <div style={{ marginBottom: 24 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space direction="vertical" size={4}>
              <Title level={2} style={{ margin: 0, color: colors.text.primary }}>
                ML Models
              </Title>
              <Text style={{ color: colors.text.secondary }}>
                Manage machine learning models, training, and predictions
              </Text>
            </Space>
          </Col>
          <Col>
            <Space>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => refetchStats()}
              >
                Refresh
              </Button>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setActiveTab('training')}
              >
                Train New Model
              </Button>
            </Space>
          </Col>
        </Row>
      </div>

      {/* Statistics Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Total Models"
              value={stats?.total_models || 0}
              prefix={<AppstoreOutlined />}
              valueStyle={{ color: colors.brand.primary }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Active Models"
              value={stats?.active_models || 0}
              prefix={<RocketOutlined />}
              valueStyle={{ color: colors.semantic.success }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Training Jobs"
              value={stats?.training_jobs || 0}
              prefix={<SettingOutlined spin={!!stats?.training_jobs} />}
              valueStyle={{ color: colors.semantic.warning }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Avg Accuracy"
              value={stats?.avg_accuracy ? (stats.avg_accuracy * 100).toFixed(2) : 0}
              suffix="%"
              prefix={<LineChartOutlined />}
              valueStyle={{ color: colors.semantic.info }}
            />
          </Card>
        </Col>
      </Row>

      {/* Main Content with Tabs */}
      <Card
        style={{
          background: colors.backgrounds.secondary,
          borderColor: colors.backgrounds.border,
        }}
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'overview',
              label: (
                <span>
                  <AppstoreOutlined />
                  Overview
                </span>
              ),
              children: <OverviewTab />,
            },
            {
              key: 'registry',
              label: (
                <span>
                  <AppstoreOutlined />
                  Model Registry
                </span>
              ),
              children: <ModelRegistryTab />,
            },
            {
              key: 'training',
              label: (
                <span>
                  <RocketOutlined />
                  Training
                </span>
              ),
              children: <TrainingTab />,
            },
            {
              key: 'analytics',
              label: (
                <span>
                  <LineChartOutlined />
                  Analytics
                </span>
              ),
              children: <AnalyticsTab />,
            },
          ]}
        />
      </Card>
    </div>
  );
};

/**
 * Overview Tab - Dashboard view with recent models and activity
 */
const OverviewTab: React.FC = () => {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  // Fetch recent models (active models, limited to 6)
  const { data: modelsData, isLoading } = useQuery({
    queryKey: mlQueryKeys.list({ active_only: true, page_size: 6 }),
    queryFn: () => mlApi.listModels({ active_only: true, page_size: 6 }),
    ...mlQueryOptions.models,
  });

  // Activate/deactivate mutation
  const activateMutation = useMutation({
    mutationFn: ({ modelId, active }: { modelId: string; active: boolean }) =>
      mlApi.activateModel(modelId, { active: !active }),
    onSuccess: (_, variables) => {
      message.success(
        !variables.active ? 'Model activated successfully' : 'Model deactivated successfully'
      );
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.stats() });
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || 'Failed to update model status');
    },
  });

  const handleActivate = (modelId: string, currentActive: boolean) => {
    activateMutation.mutate({ modelId, active: currentActive });
  };

  if (isLoading) {
    return (
      <div style={{ padding: 16, textAlign: 'center' }}>
        <Text type="secondary">Loading models...</Text>
      </div>
    );
  }

  const models = modelsData?.models || [];

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={4}>Active Models</Title>
          <Text type="secondary">
            Your currently active and recently deployed models
          </Text>
        </div>
        
        {models.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Text type="secondary">
              No active models found. Train a new model to get started.
            </Text>
          </div>
        ) : (
          <Row gutter={[16, 16]}>
            {models.map((model) => (
              <Col key={model.id} xs={24} sm={24} md={12} lg={8} xl={8}>
                <ModelCard
                  model={model}
                  onActivate={handleActivate}
                  loading={activateMutation.isPending}
                />
              </Col>
            ))}
          </Row>
        )}
      </Space>
    </div>
  );
};

/**
 * Model Registry Tab - Full table view of all models
 */
const ModelRegistryTab: React.FC = () => {
  return (
    <div style={{ padding: 16 }}>
      <ModelRegistry />
    </div>
  );
};

/**
 * Training Tab - Train new models and monitor training progress
 */
const TrainingTab: React.FC = () => {
  const [currentTrainingId, setCurrentTrainingId] = React.useState<string | undefined>();

  const handleTrainingStarted = (trainingId: string) => {
    setCurrentTrainingId(trainingId);
  };

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Training Form */}
        <TrainingForm onTrainingStarted={handleTrainingStarted} />
        
        {/* Training Progress Monitor */}
        {currentTrainingId && (
          <TrainingProgressMonitor trainingId={currentTrainingId} />
        )}
      </Space>
    </div>
  );
};

/**
 * Analytics Tab - Model performance analytics and comparisons
 */
const AnalyticsTab: React.FC = () => {
  const [analyticsView, setAnalyticsView] = useState<'comparison' | 'importance' | 'performance' | 'lifecycle'>('comparison');

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Row justify="space-between" align="middle">
            <Col>
              <Space direction="vertical" size={4}>
                <Title level={4} style={{ margin: 0 }}>Model Analytics</Title>
                <Text type="secondary">
                  Compare models, analyze feature importance, and track performance trends
                </Text>
              </Space>
            </Col>
            <Col>
              <Space>
                <Button
                  type={analyticsView === 'comparison' ? 'primary' : 'default'}
                  onClick={() => setAnalyticsView('comparison')}
                >
                  Model Comparison
                </Button>
                <Button
                  type={analyticsView === 'importance' ? 'primary' : 'default'}
                  onClick={() => setAnalyticsView('importance')}
                >
                  Feature Importance
                </Button>
                <Button
                  type={analyticsView === 'performance' ? 'primary' : 'default'}
                  onClick={() => setAnalyticsView('performance')}
                >
                  Performance Trends
                </Button>
                <Button
                  type={analyticsView === 'lifecycle' ? 'primary' : 'default'}
                  onClick={() => setAnalyticsView('lifecycle')}
                >
                  Lifecycle Dashboard
                </Button>
              </Space>
            </Col>
          </Row>
        </div>
        
        {/* Analytics Content - Wrap each in ErrorBoundary */}
        {analyticsView === 'comparison' && (
          <ErrorBoundary>
            <ModelComparison />
          </ErrorBoundary>
        )}
        {analyticsView === 'importance' && (
          <ErrorBoundary>
            <FeatureImportance />
          </ErrorBoundary>
        )}
        {analyticsView === 'performance' && (
          <ErrorBoundary>
            <PerformanceCharts />
          </ErrorBoundary>
        )}
        {analyticsView === 'lifecycle' && (
          <ErrorBoundary>
            <LifecycleDashboard />
          </ErrorBoundary>
        )}
      </Space>
    </div>
  );
};

export default MLModelsPage;
