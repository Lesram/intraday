import { Typography, Tag } from 'antd';
import MermaidDiagram from '../components/MermaidDiagram';
import CollapsibleSection from '../components/CollapsibleSection';
import ThresholdTable from '../components/ThresholdTable';
import { engineStartup } from '../data/mermaidDefinitions';
import { thresholds, engineConfig } from '../data/thresholds';
import { apiRoutes, otherRouteGroups } from '../data/apiRoutes';
import { dbTables, startupSteps } from '../data/dbSchema';
import { colors } from '@styles/theme';

const { Title, Text } = Typography;

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
      <ThresholdTable
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
