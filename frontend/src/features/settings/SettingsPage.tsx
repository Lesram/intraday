import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Collapse,
  InputNumber,
  Row,
  Select,
  Slider,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ReloadOutlined,
  SaveOutlined,
  SettingOutlined,
  UndoOutlined,
  PoweroffOutlined,
} from '@ant-design/icons';
import {
  settingsApi,
  type OrganismSettings,
  type TradingSettings,
  type MLSettings,
} from '@/services/settingsApi';

const { Title, Text } = Typography;

// ── Defaults ────────────────────────────────────────────────────

const DEFAULT_ORGANISM: OrganismSettings = {
  tick_interval_seconds: 60,
  timeframe: '1Day',
  lookback: 500,
  max_positions: 8,
  retrain_interval: 60,
  use_streaming: false,
  universe: [],
  min_bars: 200,
};

const DEFAULT_TRADING: TradingSettings = {
  max_position_pct: 0.08,
  vol_target: 0.15,
  min_position_usd: 500,
  long_only: true,
  atr_multiplier: 1.0,
  profit_r_multiple: 3.0,
  trailing_distance_atr: 1.5,
  max_bars_held: 120,
  partial_tp_pct: 0.4,
};

const DEFAULT_ML: MLSettings = {
  n_estimators: 200,
  max_depth: 5,
  learning_rate: 0.05,
  direction_threshold: 0.52,
  retrain_interval: 60,
};

// ── Section Components ──────────────────────────────────────────

interface SectionProps<T> {
  title: string;
  data: T;
  defaults: T;
  onChange: (partial: Partial<T>) => void;
  onSave: () => void;
  onReset: () => void;
  saving: boolean;
  children: React.ReactNode;
}

function SettingsSection<T>({ title, onSave, onReset, saving, children }: SectionProps<T>) {
  return (
    <Card
      title={title}
      extra={
        <Space>
          <Button
            icon={<UndoOutlined />}
            size="small"
            onClick={onReset}
          >
            Reset to Defaults
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            size="small"
            loading={saving}
            onClick={onSave}
          >
            Save
          </Button>
        </Space>
      }
      style={{ marginBottom: 16 }}
    >
      {children}
    </Card>
  );
}

// ── Universe Tag Input ──────────────────────────────────────────

function UniverseEditor({
  symbols,
  onChange,
}: {
  symbols: string[];
  onChange: (symbols: string[]) => void;
}) {
  const [inputValue, setInputValue] = useState('');

  const handleAdd = () => {
    const sym = inputValue.trim().toUpperCase();
    if (sym && !symbols.includes(sym)) {
      onChange([...symbols, sym]);
    }
    setInputValue('');
  };

  const handleRemove = (sym: string) => {
    onChange(symbols.filter((s) => s !== sym));
  };

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <Space>
          <InputNumber
            style={{ width: 120 }}
            placeholder="SYMBOL"
            value={inputValue as unknown as number}
            onChange={(v) => setInputValue(String(v ?? ''))}
            onPressEnter={handleAdd}
            controls={false}
          />
          <Button size="small" onClick={handleAdd}>
            Add
          </Button>
        </Space>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {symbols.map((sym) => (
          <Tag key={sym} closable onClose={() => handleRemove(sym)}>
            {sym}
          </Tag>
        ))}
        {symbols.length === 0 && (
          <Text type="secondary">No symbols configured</Text>
        )}
      </div>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────

const SettingsPage = () => {
  const [organism, setOrganism] = useState<OrganismSettings>(DEFAULT_ORGANISM);
  const [trading, setTrading] = useState<TradingSettings>(DEFAULT_TRADING);
  const [ml, setMl] = useState<MLSettings>(DEFAULT_ML);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [org, trd, mlRes] = await Promise.allSettled([
        settingsApi.getOrganismSettings(),
        settingsApi.getTradingSettings(),
        settingsApi.getMLSettings(),
      ]);
      if (org.status === 'fulfilled') setOrganism(org.value);
      if (trd.status === 'fulfilled') setTrading(trd.value);
      if (mlRes.status === 'fulfilled') setMl(mlRes.value);
    } catch {
      message.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleSave = async (
    category: 'organism' | 'trading' | 'ml',
    data: OrganismSettings | TradingSettings | MLSettings,
  ) => {
    setSaving(category);
    try {
      if (category === 'organism') {
        await settingsApi.updateOrganismSettings(data as OrganismSettings);
      } else if (category === 'trading') {
        await settingsApi.updateTradingSettings(data as TradingSettings);
      } else {
        await settingsApi.updateMLSettings(data as MLSettings);
      }
      message.success(`${category.charAt(0).toUpperCase() + category.slice(1)} settings saved`);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || `Failed to save ${category} settings`);
    } finally {
      setSaving(null);
    }
  };

  const handleRestart = async () => {
    setRestarting(true);
    try {
      await settingsApi.restartEngine();
      message.success('Engine restarted successfully');
      setTimeout(fetchAll, 2000);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || 'Engine restart failed');
    } finally {
      setRestarting(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <SettingOutlined /> Settings
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchAll}>
            Refresh
          </Button>
          <Button
            danger
            icon={<PoweroffOutlined />}
            loading={restarting}
            onClick={handleRestart}
          >
            Restart Engine
          </Button>
        </Space>
      </div>

      <Collapse
        defaultActiveKey={['engine', 'trading', 'exit', 'ml', 'universe']}
        items={[
          {
            key: 'engine',
            label: 'Engine Configuration',
            children: (
              <SettingsSection
                title="Engine Configuration"
                data={organism}
                defaults={DEFAULT_ORGANISM}
                onChange={(p) => setOrganism((prev) => ({ ...prev, ...p }))}
                onSave={() => handleSave('organism', organism)}
                onReset={() => setOrganism(DEFAULT_ORGANISM)}
                saving={saving === 'organism'}
              >
                <Row gutter={[24, 16]}>
                  <Col xs={24} md={12}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Tick Interval (seconds)</Text>
                      <Slider
                        min={1}
                        max={300}
                        value={organism.tick_interval_seconds}
                        onChange={(v) => setOrganism((p) => ({ ...p, tick_interval_seconds: v }))}
                        marks={{ 1: '1s', 10: '10s', 60: '60s', 300: '5m' }}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={12}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Timeframe</Text>
                      <Select
                        style={{ width: '100%', marginTop: 4 }}
                        value={organism.timeframe}
                        onChange={(v) => setOrganism((p) => ({ ...p, timeframe: v }))}
                        options={[
                          { value: '1Min', label: '1 Minute' },
                          { value: '5Min', label: '5 Minutes' },
                          { value: '15Min', label: '15 Minutes' },
                          { value: '1Hour', label: '1 Hour' },
                          { value: '1Day', label: '1 Day' },
                        ]}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Lookback</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={50}
                        max={2000}
                        value={organism.lookback}
                        onChange={(v) => setOrganism((p) => ({ ...p, lookback: v ?? 500 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Min Bars</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={10}
                        max={1000}
                        value={organism.min_bars}
                        onChange={(v) => setOrganism((p) => ({ ...p, min_bars: v ?? 200 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Streaming Data</Text>
                      <div style={{ marginTop: 8 }}>
                        <Switch
                          checked={organism.use_streaming}
                          onChange={(v) => setOrganism((p) => ({ ...p, use_streaming: v }))}
                          checkedChildren="ON"
                          unCheckedChildren="OFF"
                        />
                      </div>
                    </div>
                  </Col>
                </Row>
              </SettingsSection>
            ),
          },
          {
            key: 'trading',
            label: 'Trading Parameters',
            children: (
              <SettingsSection
                title="Trading Parameters"
                data={trading}
                defaults={DEFAULT_TRADING}
                onChange={(p) => setTrading((prev) => ({ ...prev, ...p }))}
                onSave={() => handleSave('trading', trading)}
                onReset={() => setTrading(DEFAULT_TRADING)}
                saving={saving === 'trading'}
              >
                <Row gutter={[24, 16]}>
                  <Col xs={24} md={12}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Max Positions</Text>
                      <Slider
                        min={1}
                        max={50}
                        value={organism.max_positions}
                        onChange={(v) => setOrganism((p) => ({ ...p, max_positions: v }))}
                        marks={{ 1: '1', 8: '8', 20: '20', 50: '50' }}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={12}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Max Position %</Text>
                      <Slider
                        min={1}
                        max={50}
                        value={Math.round(trading.max_position_pct * 100)}
                        onChange={(v) => setTrading((p) => ({ ...p, max_position_pct: v / 100 }))}
                        marks={{ 1: '1%', 8: '8%', 25: '25%', 50: '50%' }}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Vol Target</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={0.01}
                        max={1.0}
                        step={0.01}
                        value={trading.vol_target}
                        onChange={(v) => setTrading((p) => ({ ...p, vol_target: v ?? 0.15 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Min Position USD</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={0}
                        max={100000}
                        step={100}
                        value={trading.min_position_usd}
                        onChange={(v) => setTrading((p) => ({ ...p, min_position_usd: v ?? 500 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Long Only</Text>
                      <div style={{ marginTop: 8 }}>
                        <Switch
                          checked={trading.long_only}
                          onChange={(v) => setTrading((p) => ({ ...p, long_only: v }))}
                          checkedChildren="LONG"
                          unCheckedChildren="BOTH"
                        />
                      </div>
                    </div>
                  </Col>
                </Row>
              </SettingsSection>
            ),
          },
          {
            key: 'exit',
            label: 'Exit Strategy',
            children: (
              <SettingsSection
                title="Exit Strategy"
                data={trading}
                defaults={DEFAULT_TRADING}
                onChange={(p) => setTrading((prev) => ({ ...prev, ...p }))}
                onSave={() => handleSave('trading', trading)}
                onReset={() => setTrading(DEFAULT_TRADING)}
                saving={saving === 'trading'}
              >
                <Row gutter={[24, 16]}>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>ATR Multiplier</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={0.1}
                        max={10}
                        step={0.1}
                        value={trading.atr_multiplier}
                        onChange={(v) => setTrading((p) => ({ ...p, atr_multiplier: v ?? 1.0 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Profit R Multiple</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={0.5}
                        max={20}
                        step={0.5}
                        value={trading.profit_r_multiple}
                        onChange={(v) => setTrading((p) => ({ ...p, profit_r_multiple: v ?? 3.0 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Trailing Distance (ATR)</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={0.1}
                        max={10}
                        step={0.1}
                        value={trading.trailing_distance_atr}
                        onChange={(v) => setTrading((p) => ({ ...p, trailing_distance_atr: v ?? 1.5 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Max Bars Held</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={1}
                        max={10000}
                        value={trading.max_bars_held}
                        onChange={(v) => setTrading((p) => ({ ...p, max_bars_held: v ?? 120 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Partial TP %</Text>
                      <Slider
                        min={0}
                        max={100}
                        value={Math.round(trading.partial_tp_pct * 100)}
                        onChange={(v) => setTrading((p) => ({ ...p, partial_tp_pct: v / 100 }))}
                        marks={{ 0: '0%', 40: '40%', 100: '100%' }}
                      />
                    </div>
                  </Col>
                </Row>
              </SettingsSection>
            ),
          },
          {
            key: 'ml',
            label: 'ML Model',
            children: (
              <SettingsSection
                title="ML Model"
                data={ml}
                defaults={DEFAULT_ML}
                onChange={(p) => setMl((prev) => ({ ...prev, ...p }))}
                onSave={() => handleSave('ml', ml)}
                onReset={() => setMl(DEFAULT_ML)}
                saving={saving === 'ml'}
              >
                <Row gutter={[24, 16]}>
                  <Col xs={24} md={12}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>N Estimators</Text>
                      <Slider
                        min={50}
                        max={500}
                        step={10}
                        value={ml.n_estimators}
                        onChange={(v) => setMl((p) => ({ ...p, n_estimators: v }))}
                        marks={{ 50: '50', 200: '200', 500: '500' }}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={12}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Max Depth</Text>
                      <Slider
                        min={3}
                        max={15}
                        value={ml.max_depth}
                        onChange={(v) => setMl((p) => ({ ...p, max_depth: v }))}
                        marks={{ 3: '3', 5: '5', 10: '10', 15: '15' }}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Learning Rate</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={0.01}
                        max={0.5}
                        step={0.01}
                        value={ml.learning_rate}
                        onChange={(v) => setMl((p) => ({ ...p, learning_rate: v ?? 0.05 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Direction Threshold</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={0.5}
                        max={0.7}
                        step={0.01}
                        value={ml.direction_threshold}
                        onChange={(v) => setMl((p) => ({ ...p, direction_threshold: v ?? 0.52 }))}
                      />
                    </div>
                  </Col>
                  <Col xs={24} md={8}>
                    <div style={{ marginBottom: 16 }}>
                      <Text strong>Retrain Interval</Text>
                      <InputNumber
                        style={{ width: '100%', marginTop: 4 }}
                        min={10}
                        max={1000}
                        value={ml.retrain_interval}
                        onChange={(v) => setMl((p) => ({ ...p, retrain_interval: v ?? 60 }))}
                      />
                    </div>
                  </Col>
                </Row>
              </SettingsSection>
            ),
          },
          {
            key: 'universe',
            label: 'Universe',
            children: (
              <SettingsSection
                title="Universe"
                data={organism}
                defaults={DEFAULT_ORGANISM}
                onChange={(p) => setOrganism((prev) => ({ ...prev, ...p }))}
                onSave={() => handleSave('organism', organism)}
                onReset={() => setOrganism((p) => ({ ...p, universe: DEFAULT_ORGANISM.universe }))}
                saving={saving === 'organism'}
              >
                <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                  Manage the symbol universe for the organism engine. Symbols from the dynamic scanner will be shown separately.
                </Text>
                <UniverseEditor
                  symbols={organism.universe}
                  onChange={(symbols) => setOrganism((p) => ({ ...p, universe: symbols }))}
                />
              </SettingsSection>
            ),
          },
        ]}
      />
    </div>
  );
};

export default SettingsPage;
