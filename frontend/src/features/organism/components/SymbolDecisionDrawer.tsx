import { Col, Descriptions, Drawer, Row, Tag, Typography } from 'antd';
import type { AlphaFactorScore, BreakoutFactorScore, ExitProximity, KellySizingStage } from '../organismApi';
import AlphaFactorRadar from './AlphaFactorRadar';
import BreakoutFactorRadar from './BreakoutFactorRadar';
import KellyPipelineWaterfall from './KellyPipelineWaterfall';
import ExitProximityGauges from './ExitProximityGauges';

const { Text } = Typography;

interface SymbolDecisionDrawerProps {
  open: boolean;
  symbol: string | null;
  alpha: AlphaFactorScore | null;
  breakout: BreakoutFactorScore | null;
  exit: ExitProximity | null;
  kelly: KellySizingStage | null;
  onClose: () => void;
}

const SymbolDecisionDrawer = ({
  open,
  symbol,
  alpha,
  breakout,
  exit,
  kelly,
  onClose,
}: SymbolDecisionDrawerProps) => {
  return (
    <Drawer
      title={`Decision Detail: ${symbol ?? ''}`}
      open={open}
      onClose={onClose}
      width={720}
    >
      {symbol ? (
        <Row gutter={[16, 16]}>
          {/* Summary */}
          <Col span={24}>
            <Descriptions size="small" column={3} bordered>
              <Descriptions.Item label="Symbol">
                <Text strong>{symbol}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Alpha">
                {alpha ? (
                  <Tag color={alpha.passed_threshold ? 'success' : 'default'}>
                    {alpha.composite_score.toFixed(3)}
                  </Tag>
                ) : (
                  <Text type="secondary">N/A</Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="Breakout">
                {breakout ? (
                  <Tag color={breakout.passed_threshold ? 'success' : 'default'}>
                    {breakout.composite_score.toFixed(3)}
                  </Tag>
                ) : (
                  <Text type="secondary">N/A</Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="Direction">
                {alpha ? (
                  <Tag color={alpha.direction > 0 ? 'green' : alpha.direction < 0 ? 'red' : 'default'}>
                    {alpha.direction > 0 ? 'LONG' : alpha.direction < 0 ? 'SHORT' : 'HOLD'}
                  </Tag>
                ) : (
                  '-'
                )}
              </Descriptions.Item>
              <Descriptions.Item label="Fitness">
                {alpha ? (
                  <Tag color={alpha.passed_fitness ? 'green' : 'red'}>
                    {alpha.symbol_fitness.toFixed(2)}
                  </Tag>
                ) : (
                  '-'
                )}
              </Descriptions.Item>
              <Descriptions.Item label="Kelly Weight">
                {kelly ? `${(kelly.pipeline.final_weight * 100).toFixed(2)}%` : '-'}
              </Descriptions.Item>
            </Descriptions>
          </Col>

          {/* Radar charts */}
          <Col span={12}>
            <AlphaFactorRadar data={alpha} threshold={alpha?.threshold} />
          </Col>
          <Col span={12}>
            <BreakoutFactorRadar data={breakout} threshold={breakout?.threshold} />
          </Col>

          {/* Kelly pipeline */}
          <Col span={24}>
            <KellyPipelineWaterfall data={kelly} />
          </Col>

          {/* Exit proximity */}
          {exit && (
            <Col span={24}>
              <ExitProximityGauges data={exit} />
            </Col>
          )}
        </Row>
      ) : (
        <Text type="secondary">No symbol selected</Text>
      )}
    </Drawer>
  );
};

export default SymbolDecisionDrawer;
