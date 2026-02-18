import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  DashboardOutlined,
  ExperimentOutlined,
  GlobalOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useWebSocket } from '@/hooks/useWebSocket';
import { organismApi, type OrganismRun, type OrganismStatus, type ScannerStatus, type UniverseStatus } from './organismApi';
import ScannerPanel from './ScannerPanel';
import UniversePanel from './UniversePanel';

const { Title, Text } = Typography;

const safeNumber = (value: unknown, fallback = 0) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
};

const formatDateTime = (value?: string) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const OrganismDashboard = () => {
  const [status, setStatus] = useState<OrganismStatus | null>(null);
  const [runs, setRuns] = useState<OrganismRun[]>([]);
  const [policy, setPolicy] = useState<Record<string, number>>({});
  const [brain, setBrain] = useState<Record<string, unknown> | null>(null);
  const [attribution, setAttribution] = useState<Record<string, unknown> | null>(null);
  const [scannerData, setScannerData] = useState<ScannerStatus | null>(null);
  const [universeData, setUniverseData] = useState<UniverseStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchAll = useCallback(async (withSpinner = false) => {
    if (withSpinner) setLoading(true);
    try {
      const [statusResult, runsResult, policyResult, brainResult, attributionResult, scannerResult, universeResult] = await Promise.allSettled([
        organismApi.getStatus(),
        organismApi.getRuns(120),
        organismApi.getPolicy(),
        organismApi.getBrain(),
        organismApi.getAttribution(),
        organismApi.getScanner(),
        organismApi.getUniverse(),
      ]);

      if (statusResult.status === 'fulfilled') {
        if (statusResult.value?.enabled === false) {
          setError('Organism is not enabled in backend configuration.');
          setStatus(statusResult.value);
          setRuns([]);
          return;
        }
        setStatus(statusResult.value);
      }

      if (runsResult.status === 'fulfilled') {
        setRuns(Array.isArray(runsResult.value?.runs) ? runsResult.value.runs : []);
      }

      if (policyResult.status === 'fulfilled') {
        setPolicy(policyResult.value?.weights ?? {});
      }

      if (brainResult.status === 'fulfilled') {
        setBrain(brainResult.value);
      }

      if (attributionResult.status === 'fulfilled') {
        setAttribution((attributionResult.value?.attribution ?? null) as Record<string, unknown> | null);
      }

      if (scannerResult.status === 'fulfilled') {
        setScannerData(scannerResult.value);
      }

      if (universeResult.status === 'fulfilled') {
        setUniverseData(universeResult.value);
      }

      setError(null);
    } catch {
      setError('Failed to load organism data from backend.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll(true);
    const interval = setInterval(() => {
      fetchAll(false);
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleTickMessage = useCallback((wsPayload: unknown) => {
    const payload = wsPayload as Record<string, unknown>;
    const tickData = (payload?.data as OrganismRun | undefined) ?? (payload as OrganismRun);
    if (!tickData || typeof tickData !== 'object') return;

    setRuns((previous) => {
      const next = [tickData, ...previous];
      return next.slice(0, 200);
    });

    setStatus((previous) => {
      if (!previous) return previous;
      return {
        ...previous,
        live_engine: {
          ...(previous.live_engine ?? {}),
          last_tick: tickData,
        },
      };
    });

    // Refresh scanner & universe data when a scan just ran
    if (tickData.scanner_ran) {
      organismApi.getScanner().then(setScannerData).catch(() => {});
      organismApi.getUniverse().then(setUniverseData).catch(() => {});
    }
  }, []);

  useWebSocket('organism', handleTickMessage);

  const handleAction = useCallback(async (action: 'freeze' | 'unfreeze' | 'halt' | 'resume' | 'train' | 'tick') => {
    setActionLoading(action);
    try {
      await organismApi.action(action);
      message.success(`Organism ${action} completed`);
      await fetchAll(false);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || `Failed to ${action}`);
    } finally {
      setActionLoading(null);
    }
  }, [fetchAll]);

  const governance = status?.governance ?? {};
  const latestTick = useMemo(() => {
    if (status?.live_engine?.last_tick) return status.live_engine.last_tick;
    return runs[0] ?? null;
  }, [runs, status]);

  const runStats = useMemo(() => {
    const validRuns = runs.filter((run) => run?.timestamp);
    const total = validRuns.length;
    const recent = validRuns.slice(0, 10);
    const prev = validRuns.slice(10, 20);

    const avgDurationRecent = recent.length
      ? recent.reduce((acc, item) => acc + safeNumber(item.duration_s), 0) / recent.length
      : 0;
    const avgDurationPrev = prev.length
      ? prev.reduce((acc, item) => acc + safeNumber(item.duration_s), 0) / prev.length
      : 0;
    const durationImprovementPct = avgDurationPrev > 0
      ? ((avgDurationPrev - avgDurationRecent) / avgDurationPrev) * 100
      : 0;

    const errorFreeRecent = recent.filter((item) => (item.errors ?? []).length === 0).length;
    const errorFreeRate = recent.length > 0 ? (errorFreeRecent / recent.length) * 100 : 0;

    const avgSignalsRecent = recent.length
      ? recent.reduce((acc, item) => acc + safeNumber(item.signals_generated), 0) / recent.length
      : 0;

    return {
      total,
      avgDurationRecent,
      durationImprovementPct,
      errorFreeRate,
      avgSignalsRecent,
    };
  }, [runs]);

  const runColumns = [
    {
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (value: string) => formatDateTime(value),
    },
    {
      title: 'Regime',
      dataIndex: 'regime',
      key: 'regime',
      render: (value: string) => <Tag>{value || 'UNKNOWN'}</Tag>,
    },
    {
      title: 'Signals',
      dataIndex: 'signals_generated',
      key: 'signals_generated',
      render: (value: number) => safeNumber(value),
    },
    {
      title: 'Orders',
      dataIndex: 'orders_submitted',
      key: 'orders_submitted',
      render: (value: number) => safeNumber(value),
    },
    {
      title: 'Errors',
      dataIndex: 'errors',
      key: 'errors',
      render: (errors: string[] | undefined) => {
        const count = Array.isArray(errors) ? errors.length : 0;
        return <Tag color={count === 0 ? 'success' : 'error'}>{count}</Tag>;
      },
    },
    {
      title: 'Duration (s)',
      dataIndex: 'duration_s',
      key: 'duration_s',
      render: (value: number) => safeNumber(value).toFixed(3),
    },
  ];

  const policyRows = Object.entries(policy).map(([key, value]) => ({
    key,
    metric: key,
    value: safeNumber(value),
  }));

  const brainRows = Object.entries(brain ?? {}).map(([key, value]) => ({
    key,
    field: key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }));

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error) {
    const isNotEnabled = error.includes('not enabled');
    return (
      <div style={{ maxWidth: 640, margin: '48px auto' }}>
        <Alert
          message={isNotEnabled ? 'Living Organism — Not Activated' : 'Organism Unavailable'}
          description={
            isNotEnabled ? (
              <div>
                <p>The Living Organism subsystem is <strong>opt-in</strong> and currently disabled on the backend.</p>
                <p style={{ marginBottom: 4 }}>To activate it, add these to your <code>.env</code> and restart the server:</p>
                <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, fontSize: 13 }}>
{`ORGANISM_ENABLED=1
ENABLE_ORGANISM_SCHEDULER=1   # optional — starts the live tick loop`}
                </pre>
                <p style={{ marginTop: 8, marginBottom: 0, color: '#888' }}>
                  The backend also needs a running database session (<code>sessionmaker</code>) for governance &amp; promotion controllers.
                </p>
              </div>
            ) : (
              error
            )
          }
          type={isNotEnabled ? 'info' : 'warning'}
          showIcon
          action={<Button icon={<ReloadOutlined />} onClick={() => fetchAll(true)}>Retry</Button>}
        />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <ExperimentOutlined /> Living Organism
        </Title>
        <Button icon={<ReloadOutlined />} onClick={() => fetchAll(false)}>
          Refresh
        </Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic
              title="State"
              value={governance.halted ? 'HALTED' : governance.frozen ? 'FROZEN' : 'ACTIVE'}
              prefix={governance.halted ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="Policy Version" value={safeNumber(governance.policy_version)} prefix={<SafetyOutlined />} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="Tick Count" value={safeNumber(status?.tick_count)} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="Recorded Runs" value={runStats.total} prefix={<DashboardOutlined />} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="Universe" value={universeData?.universe_size ?? 0} prefix={<GlobalOutlined />} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="Scanner Candidates" value={scannerData?.candidate_count ?? 0} prefix={<RadarChartOutlined />} />
          </Card>
        </Col>
      </Row>

      <Card title="Controls" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button
            type={governance.frozen ? 'primary' : 'default'}
            onClick={() => handleAction(governance.frozen ? 'unfreeze' : 'freeze')}
            loading={actionLoading === 'freeze' || actionLoading === 'unfreeze'}
          >
            {governance.frozen ? 'Unfreeze Adaptation' : 'Freeze Adaptation'}
          </Button>
          <Button
            danger={!governance.halted}
            type={governance.halted ? 'primary' : 'default'}
            onClick={() => handleAction(governance.halted ? 'resume' : 'halt')}
            loading={actionLoading === 'halt' || actionLoading === 'resume'}
          >
            {governance.halted ? 'Resume Trading' : 'Halt Trading'}
          </Button>
          <Button onClick={() => handleAction('train')} loading={actionLoading === 'train'}>
            Trigger Training
          </Button>
          <Button onClick={() => handleAction('tick')} loading={actionLoading === 'tick'}>
            Trigger Live Tick
          </Button>
        </Space>
      </Card>

      <Tabs
        items={[
          {
            key: 'overview',
            label: 'Overview',
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card title="Latest Run">
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label="Timestamp">{formatDateTime(latestTick?.timestamp)}</Descriptions.Item>
                      <Descriptions.Item label="Regime">{latestTick?.regime || status?.regime?.last_regime || '-'}</Descriptions.Item>
                      <Descriptions.Item label="Signals">{safeNumber(latestTick?.signals_generated)}</Descriptions.Item>
                      <Descriptions.Item label="Orders">{safeNumber(latestTick?.orders_submitted)}</Descriptions.Item>
                      <Descriptions.Item label="Duration">{safeNumber(latestTick?.duration_s).toFixed(3)}s</Descriptions.Item>
                      <Descriptions.Item label="Errors">
                        <Tag color={(latestTick?.errors?.length ?? 0) === 0 ? 'success' : 'error'}>
                          {(latestTick?.errors?.length ?? 0) === 0 ? 'none' : latestTick?.errors?.length}
                        </Tag>
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="Improvement Indicators">
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label="Recent error-free rate">
                        <Progress percent={Math.round(runStats.errorFreeRate)} size="small" />
                      </Descriptions.Item>
                      <Descriptions.Item label="Avg signals (recent 10)">
                        {runStats.avgSignalsRecent.toFixed(2)}
                      </Descriptions.Item>
                      <Descriptions.Item label="Duration improvement vs previous window">
                        <Text type={runStats.durationImprovementPct >= 0 ? 'success' : 'danger'}>
                          {runStats.durationImprovementPct.toFixed(2)}%
                        </Text>
                      </Descriptions.Item>
                      <Descriptions.Item label="Avg duration (recent 10)">
                        {runStats.avgDurationRecent.toFixed(3)}s
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'runs',
            label: 'Runs History',
            children: (
              <Card title="Recent Organism Runs">
                <Table
                  dataSource={runs.map((run, index) => ({ key: `${run.timestamp ?? index}-${index}`, ...run }))}
                  columns={runColumns}
                  pagination={{ pageSize: 20 }}
                  size="small"
                />
              </Card>
            ),
          },
          {
            key: 'scanner',
            label: (
              <span>
                <RadarChartOutlined /> Scanner{' '}
                <Badge count={scannerData?.candidate_count ?? 0} overflowCount={999} style={{ backgroundColor: '#1890ff' }} />
              </span>
            ),
            children: <ScannerPanel scanner={scannerData} loading={loading} />,
          },
          {
            key: 'universe',
            label: (
              <span>
                <GlobalOutlined /> Universe{' '}
                <Badge count={universeData?.universe_size ?? 0} overflowCount={999} style={{ backgroundColor: '#52c41a' }} />
              </span>
            ),
            children: <UniversePanel universe={universeData} loading={loading} />,
          },
          {
            key: 'learned',
            label: 'Learned State',
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card title="Policy Weights">
                    <Table
                      dataSource={policyRows}
                      columns={[
                        { title: 'Metric', dataIndex: 'metric', key: 'metric' },
                        {
                          title: 'Weight',
                          dataIndex: 'value',
                          key: 'value',
                          render: (value: number) => value.toFixed(4),
                        },
                      ]}
                      pagination={false}
                      size="small"
                      locale={{ emptyText: 'No policy weights available from backend' }}
                    />
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="Brain Manifest">
                    <Table
                      dataSource={brainRows}
                      columns={[
                        { title: 'Field', dataIndex: 'field', key: 'field' },
                        { title: 'Value', dataIndex: 'value', key: 'value', ellipsis: true },
                      ]}
                      pagination={{ pageSize: 8 }}
                      size="small"
                      locale={{ emptyText: 'Brain details unavailable' }}
                    />
                  </Card>
                </Col>
                <Col xs={24}>
                  <Card title="Attribution Snapshot">
                    <Text type="secondary">
                      {attribution ? JSON.stringify(attribution).slice(0, 1500) : 'No attribution data available'}
                    </Text>
                  </Card>
                </Col>
              </Row>
            ),
          },
        ]}
      />
    </div>
  );
};

export default OrganismDashboard;
