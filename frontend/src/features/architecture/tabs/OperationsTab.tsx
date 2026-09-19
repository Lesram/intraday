import { Typography, Tag, Card } from 'antd';
import MermaidDiagram from '../components/MermaidDiagram';
import CollapsibleSection from '../components/CollapsibleSection';
import ThresholdTable from '../components/ThresholdTable';
import { engineStartup } from '../data/mermaidDefinitions';
import { thresholds, engineConfig } from '../data/thresholds';
import type { EngineConfig } from '../data/thresholds';
import { apiRoutes, otherRouteGroups } from '../data/apiRoutes';
import { dbTables, startupSteps } from '../data/dbSchema';
import { colors } from '@styles/theme';

const { Title, Text } = Typography;

const middlewareStack = [
  { order: '1', middleware: 'CORS (CORSMiddleware)', detail: 'Credentials, 14 local origins (localhost + 127.0.0.1, ports 3000/3001/5173/5174)' },
  { order: '2', middleware: 'GZip', detail: 'Minimum 500 bytes' },
  { order: '3', middleware: 'Request Deduplication', detail: 'TTL=300s, max_cache=10000' },
  { order: '4', middleware: 'Rate Limiting', detail: 'Exempt: health/metrics/docs' },
  { order: '5', middleware: 'HTTP Metrics', detail: 'Counter + histogram' },
];

const diagnosticCategories = [
  { category: 'ML_MODEL', desc: 'Model health, staleness, prediction quality' },
  { category: 'TRADING_HEALTH', desc: 'Win rate, drawdown, position count' },
  { category: 'STATE_PERSISTENCE', desc: 'Brain save/load, exit levels, evolved params' },
  { category: 'ORDER_FLOW', desc: 'Stuck orders, zombie orders, DLQ depth, outbox' },
  { category: 'DATA_PIPELINE', desc: 'Bar freshness, NaN rates, feature completeness' },
  { category: 'STREAMING', desc: 'WebSocket health, staleness, reconnection' },
  { category: 'GOVERNANCE', desc: 'Drawdown proximity, halt state, change budget' },
  { category: 'BROKER_SYNC', desc: 'Broker vs DB sync, orphaned positions, fill reconciliation' },
];

const alertCategories = [
  { category: 'RISK_VIOLATION', examples: 'Drawdown kill, position limit, notional cap' },
  { category: 'ORDER_FAILURE', examples: 'Broker reject, timeout, DLQ' },
  { category: 'SYSTEM_ERROR', examples: 'DB down, Redis down, unhandled exception' },
  { category: 'CONNECTIVITY', examples: 'WebSocket disconnect, API timeout' },
  { category: 'PERFORMANCE', examples: 'Tick latency, queue overflow' },
  { category: 'SECURITY', examples: 'Auth failure, rate limit, suspicious activity' },
];

const methodColor: Record<string, string> = {
  GET: 'green', POST: 'blue', PUT: 'orange', PATCH: 'orange',
  DELETE: 'red', WS: 'purple',
};

const OperationsTab = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <Title level={4} style={{ margin: 0 }}>Operations & Reference</Title>

    <CollapsibleSection title="Engine Startup Sequence" subtitle="14-step boot order" defaultOpen>
      <MermaidDiagram definition={engineStartup} />
      <ThresholdTable
        data={startupSteps}
        columns={[
          { title: '#', dataIndex: 'step', key: 'step', width: 40 },
          { title: 'Component', dataIndex: 'component', key: 'component' },
          { title: 'Behavior', dataIndex: 'behavior', key: 'behavior' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="API Route Reference" subtitle={`${apiRoutes.length}+ detailed + ${otherRouteGroups.reduce((s, g) => s + g.endpoints, 0)} summarized endpoints`}>
      <ThresholdTable
        data={apiRoutes}
        searchField="endpoint"
        columns={[
          { title: 'Method', dataIndex: 'method', key: 'method', width: 80,
            render: (v: string) => <Tag color={methodColor[v] || 'default'}>{v}</Tag> },
          { title: 'Endpoint', dataIndex: 'endpoint', key: 'endpoint',
            render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code> },
          { title: 'Purpose', dataIndex: 'purpose', key: 'purpose' },
          { title: 'Group', dataIndex: 'group', key: 'group',
            filters: [...new Set(apiRoutes.map((r) => r.group))].map((g) => ({ text: g, value: g })),
            onFilter: (value, record) => record.group === value },
        ]}
        pageSize={15}
      />
      <div style={{ marginTop: 16 }}>
        <Text strong style={{ color: colors.text.primary }}>Other Route Groups (summarized)</Text>
        <ThresholdTable
          data={otherRouteGroups}
          columns={[
            { title: 'Route File', dataIndex: 'routeFile', key: 'routeFile',
              render: (v: string) => <code>{v}</code> },
            { title: 'Endpoints', dataIndex: 'endpoints', key: 'endpoints', width: 80 },
            { title: 'Key Operations', dataIndex: 'keyOps', key: 'keyOps' },
          ]}
        />
      </div>
    </CollapsibleSection>

    <CollapsibleSection title="Database Schema" subtitle="24 ORM tables in PostgreSQL">
      <ThresholdTable
        data={dbTables}
        searchField="table"
        columns={[
          { title: 'Table', dataIndex: 'table', key: 'table',
            render: (v: string) => <code style={{ color: colors.brand.primary }}>{v}</code> },
          { title: 'Key Columns', dataIndex: 'keyColumns', key: 'keyColumns',
            render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text> },
          { title: 'Purpose', dataIndex: 'purpose', key: 'purpose' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Engine Configuration" subtitle="Environment variables (.env / docker-compose.yml)">
      {/* V13 W98 (Lens 7): explicit generic type so TS infers
          searchField as keyof EngineConfig (string union of all keys),
          not the literal type of one entry. */}
      <ThresholdTable<EngineConfig>
        data={engineConfig}
        searchField="variable"
        columns={[
          { title: 'Variable', dataIndex: 'variable', key: 'variable',
            render: (v: string) => <code style={{ fontSize: 11 }}>{v}</code> },
          { title: 'Default', dataIndex: 'default', key: 'default' },
          { title: 'Production', dataIndex: 'production', key: 'production',
            render: (v: string, row: { default: string }) => (
              <Text style={{ color: v !== row.default ? colors.semantic.warning : colors.text.secondary, fontWeight: v !== row.default ? 600 : 400 }}>
                {v}
              </Text>
            ) },
          { title: 'Effect', dataIndex: 'effect', key: 'effect' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Middleware Stack" subtitle="Request processing order (middleware_setup.py)">
      <ThresholdTable
        data={middlewareStack}
        columns={[
          { title: '#', dataIndex: 'order', key: 'order', width: 40 },
          { title: 'Middleware', dataIndex: 'middleware', key: 'middleware', render: (v: string) => <Text strong>{v}</Text> },
          { title: 'Configuration', dataIndex: 'detail', key: 'detail' },
        ]}
      />
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginTop: 12 }}>
        <Text style={{ color: colors.semantic.warning, fontSize: 13 }}>
          NOTE: SecurityHeadersMiddleware class exists in infra/security_hardening.py but is NOT installed in the middleware chain.
        </Text>
      </Card>
    </CollapsibleSection>

    <CollapsibleSection title="Diagnostic System" subtitle="36 checks across 8 categories, scheduled pre-open/post-close">
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginBottom: 12 }}>
        <Text strong style={{ color: colors.text.primary }}>Schedule</Text>
        <div style={{ marginTop: 8, fontSize: 13, color: colors.text.secondary }}>
          <div>Pre-open: 9:25 AM ET | Post-close: 4:05 PM ET</div>
          <div>Skips weekends and holidays, date-idempotent (won't re-run same day/trigger)</div>
          <div>Persisted to: organism_brain/diagnostics/history.json</div>
        </div>
      </Card>
      <ThresholdTable
        data={diagnosticCategories}
        columns={[
          { title: 'Category', dataIndex: 'category', key: 'category', render: (v: string) => <code>{v}</code> },
          { title: 'Checks', dataIndex: 'desc', key: 'desc' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Alert System" subtitle="Slack + PagerDuty, dedup, rate limiting, market hours suppression">
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginBottom: 12 }}>
        <Text strong style={{ color: colors.text.primary }}>Alert Architecture (global singleton)</Text>
        <div style={{ marginTop: 8, fontSize: 13, color: colors.text.secondary }}>
          <div><strong>Channels:</strong> Slack (all severities) + PagerDuty (ERROR/CRITICAL always, WARNING in prod)</div>
          <div><strong>Dedup:</strong> SHA-256 content hash, 300s window, async lock</div>
          <div><strong>Rate limit:</strong> 30 alerts/min sliding window</div>
          <div><strong>Market hours:</strong> INFO/WARNING suppressed outside 4:00 AM - 8:00 PM ET; ERROR/CRITICAL always delivered</div>
        </div>
      </Card>
      <ThresholdTable
        data={alertCategories}
        columns={[
          { title: 'Category', dataIndex: 'category', key: 'category', render: (v: string) => <code>{v}</code> },
          { title: 'Examples', dataIndex: 'examples', key: 'examples' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Key Thresholds Summary" subtitle="All critical limits and gates">
      <ThresholdTable
        data={thresholds}
        searchField="threshold"
        columns={[
          { title: 'Threshold', dataIndex: 'threshold', key: 'threshold' },
          { title: 'Value', dataIndex: 'value', key: 'value',
            render: (v: string) => <Tag>{v}</Tag> },
          { title: 'Location', dataIndex: 'location', key: 'location',
            render: (v: string) => <code>{v}</code> },
          { title: 'Purpose', dataIndex: 'purpose', key: 'purpose' },
        ]}
      />
    </CollapsibleSection>
  </div>
);

export default OperationsTab;
