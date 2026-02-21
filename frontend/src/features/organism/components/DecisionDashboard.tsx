import { useCallback, useEffect, useState } from 'react';
import { Card, Col, Row, Spin, Typography } from 'antd';
import { organismApi } from '../organismApi';
import type {
  AlphaFactorScore,
  BreakoutFactorScore,
  DecisionSnapshot,
  EvolutionSnapshot,
  ExitProximity,
  KellySizingStage,
} from '../organismApi';
import DecisionHeader from './DecisionHeader';
import GovernanceStatusBar from './GovernanceStatusBar';
import FilteringFunnel from './FilteringFunnel';
import RegimeProbabilityPanel from './RegimeProbabilityPanel';
import AlphaScoreTable from './AlphaScoreTable';
import ExitProximityTable from './ExitProximityTable';
import EvolutionTimeline from './EvolutionTimeline';
import SymbolDecisionDrawer from './SymbolDecisionDrawer';

const { Text } = Typography;

const DecisionDashboard = () => {
  const [snapshot, setSnapshot] = useState<DecisionSnapshot | null>(null);
  const [evolutionData, setEvolutionData] = useState<EvolutionSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  const fetchData = useCallback(async (withSpinner = false) => {
    if (withSpinner) setLoading(true);
    try {
      const [decResult, evoResult] = await Promise.allSettled([
        organismApi.getDecisions(),
        organismApi.getEvolutionHistory(60),
      ]);
      if (decResult.status === 'fulfilled' && decResult.value.snapshot) {
        setSnapshot(decResult.value.snapshot);
      }
      if (evoResult.status === 'fulfilled') {
        setEvolutionData(evoResult.value.history);
      }
    } catch {
      // Silently handle — data will be stale
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(true);
    const interval = setInterval(() => fetchData(false), 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleSymbolClick = useCallback((symbol: string) => {
    setSelectedSymbol(symbol);
    setDrawerOpen(true);
  }, []);

  // Find data for selected symbol
  const selectedAlpha: AlphaFactorScore | null =
    snapshot?.alpha_scores.find((a) => a.symbol === selectedSymbol) ?? null;
  const selectedBreakout: BreakoutFactorScore | null =
    snapshot?.breakout_scores.find((b) => b.symbol === selectedSymbol) ?? null;
  const selectedExit: ExitProximity | null =
    snapshot?.exit_proximity.find((e) => e.symbol === selectedSymbol) ?? null;
  const selectedKelly: KellySizingStage | null =
    snapshot?.kelly_sizing.find((k) => k.symbol === selectedSymbol) ?? null;

  if (loading && !snapshot) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!snapshot) {
    return (
      <Card>
        <Text type="secondary">
          No decision data available yet. The engine needs to complete at least one tick.
        </Text>
      </Card>
    );
  }

  return (
    <>
      <Row gutter={[16, 16]}>
        {/* Header + Governance */}
        <Col span={24}>
          <DecisionHeader snapshot={snapshot} />
        </Col>
        <Col span={24}>
          <GovernanceStatusBar snapshot={snapshot} />
        </Col>

        {/* Regime + Filtering */}
        <Col xs={24} lg={8}>
          <RegimeProbabilityPanel regime={snapshot.regime} />
        </Col>
        <Col xs={24} lg={16}>
          <FilteringFunnel data={snapshot.filtering} />
        </Col>

        {/* Alpha Score Table */}
        <Col span={24}>
          <Card title={`Alpha Scores (${snapshot.alpha_scores.length} symbols)`} size="small">
            <AlphaScoreTable data={snapshot.alpha_scores} onRowClick={handleSymbolClick} />
          </Card>
        </Col>

        {/* Exit Proximity Table */}
        {snapshot.exit_proximity.length > 0 && (
          <Col span={24}>
            <Card title={`Exit Proximity (${snapshot.exit_proximity.length} positions)`} size="small">
              <ExitProximityTable data={snapshot.exit_proximity} onRowClick={handleSymbolClick} />
            </Card>
          </Col>
        )}

        {/* Evolution Timeline */}
        <Col span={24}>
          <EvolutionTimeline data={evolutionData} />
        </Col>
      </Row>

      <SymbolDecisionDrawer
        open={drawerOpen}
        symbol={selectedSymbol}
        alpha={selectedAlpha}
        breakout={selectedBreakout}
        exit={selectedExit}
        kelly={selectedKelly}
        onClose={() => setDrawerOpen(false)}
      />
    </>
  );
};

export default DecisionDashboard;
