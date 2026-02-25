import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Collapse, Select, Space, Spin, Tag, Tooltip, Typography } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  organismApi,
  type DiagnosticCheckResult,
  type DiagnosticHistoryEntry,
  type DiagnosticReport,
} from '../organismApi';

const { Text } = Typography;

const severityColor: Record<string, string> = {
  critical: 'red',
  warning: 'orange',
  info: 'blue',
};

const severityIcon: Record<string, React.ReactNode> = {
  critical: <CloseCircleOutlined />,
  warning: <ExclamationCircleOutlined />,
  info: <InfoCircleOutlined />,
};

const triggerLabel: Record<string, string> = {
  preflight: 'PF',
  pre_open: 'PRE',
  post_close: 'POST',
  continuous: 'CONT',
  manual: 'MAN',
};

const triggerColor: Record<string, string> = {
  preflight: '#722ed1',
  pre_open: '#1890ff',
  post_close: '#13c2c2',
  continuous: '#8c8c8c',
  manual: '#faad14',
};

const categoryLabel: Record<string, string> = {
  wiring: 'Wiring',
  state_persistence: 'State Persistence',
  order_flow: 'Order Flow',
  data_pipeline: 'Data Pipeline',
  streaming: 'Streaming',
  governance: 'Governance',
  broker_sync: 'Broker Sync',
  infrastructure: 'Infrastructure',
};

// ── Check Row ────────────────────────────────────────────────────

const CheckRow = ({ check }: { check: DiagnosticCheckResult }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '6px 0',
      borderLeft: `3px solid ${check.passed ? '#52c41a' : severityColor[check.severity] || '#999'}`,
      paddingLeft: 12,
    }}
  >
    {check.passed ? (
      <CheckCircleOutlined style={{ color: '#52c41a' }} />
    ) : (
      severityIcon[check.severity] ?? <CloseCircleOutlined style={{ color: 'red' }} />
    )}
    <Tag color={check.passed ? 'green' : severityColor[check.severity]}>
      {check.severity.toUpperCase()}
    </Tag>
    <Text code style={{ fontSize: 12 }}>
      {check.name}
    </Text>
    <Text type={check.passed ? 'secondary' : undefined} style={{ flex: 1 }}>
      {check.message}
    </Text>
    <Text type="secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
      {check.duration_ms.toFixed(1)}ms
    </Text>
  </div>
);

// ── Report Detail ────────────────────────────────────────────────

const ReportDetail = ({
  report,
  trigger,
  timestamp,
}: {
  report: DiagnosticReport;
  trigger?: string;
  timestamp?: string;
}) => {
  const { summary } = report;
  const alertType =
    summary.critical_failures > 0 ? 'error' : summary.warnings > 0 ? 'warning' : 'success';
  const alertMessage =
    summary.critical_failures > 0
      ? `${summary.critical_failures} critical failure${summary.critical_failures > 1 ? 's' : ''} detected`
      : summary.warnings > 0
        ? `All critical checks passed, ${summary.warnings} warning${summary.warnings > 1 ? 's' : ''}`
        : 'All checks passed';

  const byCategory: Record<string, DiagnosticCheckResult[]> = {};
  for (const r of report.results) {
    if (!byCategory[r.category]) byCategory[r.category] = [];
    byCategory[r.category].push(r);
  }

  const failedCategories = Object.entries(byCategory)
    .filter(([, checks]) => checks.some((c) => !c.passed))
    .map(([cat]) => cat);

  return (
    <div>
      <Alert
        type={alertType}
        showIcon
        message={alertMessage}
        description={
          <span>
            {summary.passed}/{summary.total} passed &middot; Mode: <Tag>{report.mode}</Tag>
            {trigger && (
              <>
                {' '}
                &middot; Trigger:{' '}
                <Tag color={triggerColor[trigger] || '#999'}>{trigger}</Tag>
              </>
            )}
            {' '}&middot; {report.duration_ms.toFixed(0)}ms &middot;{' '}
            <Text type="secondary" style={{ fontSize: 11 }}>
              {new Date(timestamp || report.timestamp).toLocaleString()}
            </Text>
          </span>
        }
        style={{ marginBottom: 12 }}
      />

      <Collapse defaultActiveKey={failedCategories}>
        {Object.entries(byCategory).map(([cat, checks]) => {
          const catFailed = checks.filter((c) => !c.passed).length;
          const catPassed = checks.filter((c) => c.passed).length;
          return (
            <Collapse.Panel
              key={cat}
              header={
                <span>
                  {categoryLabel[cat] || cat}{' '}
                  <Tag color={catFailed > 0 ? 'red' : 'green'}>
                    {catPassed}/{checks.length}
                  </Tag>
                </span>
              }
            >
              {checks.map((check) => (
                <CheckRow key={check.name} check={check} />
              ))}
            </Collapse.Panel>
          );
        })}
      </Collapse>
    </div>
  );
};

// ── History Timeline ─────────────────────────────────────────────

const HistoryDot = ({
  entry,
  isSelected,
  onClick,
}: {
  entry: DiagnosticHistoryEntry;
  isSelected: boolean;
  onClick: () => void;
}) => {
  const { report, trigger, timestamp } = entry;
  const summary = report.summary;
  const color =
    summary.critical_failures > 0 ? '#ff4d4f' : summary.warnings > 0 ? '#faad14' : '#52c41a';

  return (
    <Tooltip
      title={
        <div style={{ fontSize: 11 }}>
          <div>
            <strong>{trigger.toUpperCase()}</strong> &middot;{' '}
            {new Date(timestamp).toLocaleString()}
          </div>
          <div>
            {summary.passed}/{summary.total} passed
            {summary.critical_failures > 0 && ` | ${summary.critical_failures} critical`}
            {summary.warnings > 0 && ` | ${summary.warnings} warnings`}
          </div>
        </div>
      }
    >
      <div
        onClick={onClick}
        style={{
          display: 'inline-flex',
          flexDirection: 'column',
          alignItems: 'center',
          cursor: 'pointer',
          padding: '4px 3px',
          borderRadius: 4,
          background: isSelected ? '#e6f4ff' : 'transparent',
          border: isSelected ? '1px solid #91caff' : '1px solid transparent',
          minWidth: 28,
        }}
      >
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: '50%',
            background: color,
            border: isSelected ? '2px solid #1890ff' : '2px solid transparent',
          }}
        />
        <Text
          type="secondary"
          style={{
            fontSize: 9,
            lineHeight: 1,
            marginTop: 2,
            color: triggerColor[trigger] || '#8c8c8c',
          }}
        >
          {triggerLabel[trigger] || trigger.slice(0, 3).toUpperCase()}
        </Text>
      </div>
    </Tooltip>
  );
};

// ── Main Panel ───────────────────────────────────────────────────

const DiagnosticsPanel = () => {
  const [history, setHistory] = useState<DiagnosticHistoryEntry[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [triggerFilter, setTriggerFilter] = useState<string>('all');
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const fetchHistory = useCallback(async (filter?: string) => {
    setLoading(true);
    try {
      const resp = await organismApi.getDiagnosticsHistory(50, filter || 'all');
      setHistory(resp.reports || []);
      setSelectedIdx(0);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  const runDeep = useCallback(async () => {
    setRunning(true);
    try {
      await organismApi.runDiagnostics();
      // Refresh history after running
      await fetchHistory(triggerFilter);
    } catch {
      // ignore
    } finally {
      setRunning(false);
    }
  }, [fetchHistory, triggerFilter]);

  useEffect(() => {
    fetchHistory(triggerFilter);
  }, [fetchHistory, triggerFilter]);

  const selected = useMemo(
    () => (history.length > 0 ? history[selectedIdx] : null),
    [history, selectedIdx],
  );

  // Latest report summary for the top banner
  const latestReport = history.length > 0 ? history[0].report : null;

  if (loading && history.length === 0) {
    return <Spin tip="Loading diagnostics..." />;
  }

  if (!latestReport) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Text type="secondary">No diagnostic report available yet.</Text>
        <br />
        <br />
        <Button type="primary" icon={<ThunderboltOutlined />} onClick={runDeep} loading={running}>
          Run Deep Diagnostics
        </Button>
      </div>
    );
  }

  const { summary } = latestReport;
  const statusType =
    summary.critical_failures > 0 ? 'error' : summary.warnings > 0 ? 'warning' : 'success';
  const statusMsg =
    summary.critical_failures > 0
      ? `${summary.critical_failures} critical failure${summary.critical_failures > 1 ? 's' : ''}`
      : summary.warnings > 0
        ? `${summary.warnings} warning${summary.warnings > 1 ? 's' : ''}`
        : 'All systems healthy';

  return (
    <div>
      {/* A. Summary + Controls */}
      <Alert
        type={statusType}
        showIcon
        message={`Latest: ${statusMsg}`}
        description={
          <span>
            {summary.passed}/{summary.total} passed &middot;{' '}
            <Text type="secondary" style={{ fontSize: 11 }}>
              {new Date(history[0].timestamp).toLocaleString()}
            </Text>{' '}
            &middot;{' '}
            <Tag color={triggerColor[history[0].trigger]}>
              {history[0].trigger}
            </Tag>
          </span>
        }
        style={{ marginBottom: 12 }}
      />

      <Space style={{ marginBottom: 12 }} wrap>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => fetchHistory(triggerFilter)}
          loading={loading}
        >
          Refresh
        </Button>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={runDeep}
          loading={running}
        >
          Run Deep Diagnostics
        </Button>
        <Select
          value={triggerFilter}
          onChange={setTriggerFilter}
          style={{ width: 140 }}
          options={[
            { value: 'all', label: 'All Triggers' },
            { value: 'pre_open', label: 'Pre-Open' },
            { value: 'post_close', label: 'Post-Close' },
            { value: 'continuous', label: 'Continuous' },
            { value: 'manual', label: 'Manual' },
            { value: 'preflight', label: 'Preflight' },
          ]}
        />
        <Text type="secondary" style={{ fontSize: 11 }}>
          {history.length} report{history.length !== 1 ? 's' : ''}
        </Text>
      </Space>

      {/* B. History Timeline */}
      {history.length > 1 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 1,
            padding: '8px 4px',
            marginBottom: 12,
            background: '#fafafa',
            borderRadius: 6,
            border: '1px solid #f0f0f0',
            maxHeight: 80,
            overflowY: 'auto',
          }}
        >
          {history.map((entry, idx) => (
            <HistoryDot
              key={`${entry.timestamp}-${idx}`}
              entry={entry}
              isSelected={idx === selectedIdx}
              onClick={() => setSelectedIdx(idx)}
            />
          ))}
        </div>
      )}

      {/* C. Selected Report Detail */}
      {selected && (
        <ReportDetail
          report={selected.report}
          trigger={selected.trigger}
          timestamp={selected.timestamp}
        />
      )}
    </div>
  );
};

export default DiagnosticsPanel;
