import { Card, Col, Progress, Row, Statistic, Tag } from 'antd';
import { SafetyOutlined, WarningOutlined } from '@ant-design/icons';
import type { DecisionSnapshot } from '../organismApi';

const GovernanceStatusBar = ({ snapshot }: { snapshot: DecisionSnapshot | null }) => {
  if (!snapshot) {
    return <Card title="Governance" size="small"><span>No governance data</span></Card>;
  }

  const { equity, peak_equity, drawdown_pct, is_halted, is_frozen } = snapshot.governance;
  const ddPct = drawdown_pct * 100;
  const ddStatus = ddPct > 5 ? 'exception' : ddPct > 2 ? 'active' : 'success';

  return (
    <Card
      title={<><SafetyOutlined /> Governance</>}
      size="small"
      extra={
        <>
          {is_halted && <Tag color="error" icon={<WarningOutlined />}>HALTED</Tag>}
          {is_frozen && <Tag color="warning">FROZEN</Tag>}
          {!is_halted && !is_frozen && <Tag color="success">ACTIVE</Tag>}
        </>
      }
    >
      <Row gutter={[12, 12]}>
        <Col span={6}>
          <Statistic title="Equity" value={equity} precision={0} prefix="$" valueStyle={{ fontSize: 16 }} />
        </Col>
        <Col span={6}>
          <Statistic title="Peak Equity" value={peak_equity} precision={0} prefix="$" valueStyle={{ fontSize: 16 }} />
        </Col>
        <Col span={6}>
          <Statistic title="Generation" value={snapshot.evolution.generation} valueStyle={{ fontSize: 16 }} />
        </Col>
        <Col span={6}>
          <div>
            <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>Drawdown</div>
            <Progress
              percent={Math.min(ddPct / 8 * 100, 100)}
              size="small"
              status={ddStatus}
              format={() => `${ddPct.toFixed(2)}%`}
            />
          </div>
        </Col>
      </Row>
    </Card>
  );
};

export default GovernanceStatusBar;
