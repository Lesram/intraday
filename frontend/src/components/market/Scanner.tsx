/**
 * Market Scanner Component
 * 
 * Scans and filters stocks based on technical criteria.
 * 
 * Features:
 * - Multiple filter types (price, volume, RSI, MACD, moving averages)
 * - Predefined scan presets
 * - Results table with sorting
 * - Click to load symbol on chart
 * - Real-time scanning via WebSocket
 * - Auto-refresh toggle
 * 
 * Phase 7 - Market Data & Charting
 * Enhanced: October 16, 2025
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  Form,
  InputNumber,
  Select,
  Button,
  Table,
  Space,
  Tag,
  Switch,
  Divider,
  Typography,
  Row,
  Col,
  Statistic,
  message,
  Tooltip,
  Badge,
} from 'antd';
import {
  SearchOutlined,
  RiseOutlined,
  FallOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
  StarOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  WifiOutlined,
  DisconnectOutlined,
  DownloadOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useScannerWebSocket } from '../../hooks/useScannerWebSocket';
import { apiClient } from '../../services/api';

const { Title, Text } = Typography;
const { Option } = Select;

// ============================================================================
// TYPES
// ============================================================================

interface ScanFilters {
  price_min?: number;
  price_max?: number;
  volume_min?: number;
  volume_spike?: number;
  rsi_min?: number;
  rsi_max?: number;
  macd_signal?: 'any' | 'bullish' | 'bearish';
  ma_crossover?: 'none' | 'golden_cross' | 'death_cross';
  above_sma_50?: boolean;
  above_sma_200?: boolean;
  gap_up?: boolean;
  gap_down?: boolean;
  gap_percentage?: number;
  atr_multiplier?: number;
  limit?: number;
}

interface ScanResult {
  symbol: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  avg_volume?: number;
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  sma_50?: number;
  sma_200?: number;
  atr?: number;
  score: number;
  signals: string[];
}

interface ScanPreset {
  name: string;
  description: string;
  filters: ScanFilters;
}

// ============================================================================
// API CLIENT
// ============================================================================

class ScannerAPI {
  async scan(filters: ScanFilters): Promise<{ results: ScanResult[]; total: number; scan_time: number; filters_applied: number }> {
    const response = await apiClient.post('/scanner/scan', filters);
    return response.data;
  }

  async getPresets(): Promise<ScanPreset[]> {
    const response = await apiClient.get('/scanner/presets');
    return response.data;
  }
}

// ============================================================================
// COMPONENT
// ============================================================================

interface ScannerProps {
  onSymbolSelect?: (symbol: string) => void;
}

export const Scanner: React.FC<ScannerProps> = ({ onSymbolSelect }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [scanStats, setScanStats] = useState<{ total: number; scan_time: number; filters_applied: number } | null>(null);
  const [presets, setPresets] = useState<ScanPreset[]>([]);
  const [presetsLoaded, setPresetsLoaded] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(10); // seconds

  const api = new ScannerAPI();
  
  // WebSocket hook for real-time scanning
  const {
    connectionStatus,
    isScanning,
    lastResults,
    isConnected,
    connect,
    disconnect,
    startScanning,
    stopScanning,
    updateFilters,
  } = useScannerWebSocket(false); // Don't auto-connect

  // Load presets on mount
  useEffect(() => {
    loadPresets();
  }, []);
  
  // Update results from WebSocket
  useEffect(() => {
    if (lastResults) {
      setResults(lastResults.results);
      setScanStats({
        total: lastResults.total,
        scan_time: lastResults.scan_time,
        filters_applied: lastResults.filters_applied,
      });
    }
  }, [lastResults]);
  
  // Handle auto-refresh toggle
  useEffect(() => {
    if (autoRefresh) {
      // Connect and start scanning
      if (!isConnected) {
        connect();
      }
      
      // Wait for connection then start scanning
      if (isConnected) {
        const currentFilters = form.getFieldsValue();
        startScanning(currentFilters, refreshInterval);
      }
    } else {
      // Stop scanning and disconnect
      if (isScanning) {
        stopScanning();
      }
      if (isConnected) {
        disconnect();
      }
    }
  }, [autoRefresh, isConnected]);

  const loadPresets = async () => {
    try {
      const loadedPresets = await api.getPresets();
      setPresets(loadedPresets);
      setPresetsLoaded(true);
    } catch (error) {
      console.error('Failed to load presets:', error);
      message.error('Failed to load scan presets');
    }
  };

  // Handle scan
  const handleScan = async (values: ScanFilters) => {
    setLoading(true);

    try {
      const response = await api.scan(values);
      setResults(response.results);
      setScanStats({
        total: response.total,
        scan_time: response.scan_time,
        filters_applied: response.filters_applied,
      });
      message.success(`Found ${response.total} matching stocks in ${response.scan_time.toFixed(2)}s`);
    } catch (error) {
      console.error('Scan failed:', error);
      message.error(error instanceof Error ? error.message : 'Scan failed');
    } finally {
      setLoading(false);
    }
  };

  // Apply preset
  const applyPreset = (preset: ScanPreset) => {
    form.setFieldsValue(preset.filters);
    message.info(`Applied ${preset.name} preset`);
  };

  // Reset form
  const handleReset = () => {
    form.resetFields();
    setResults([]);
    setScanStats(null);
  };
  
  // Export functions
  const handleExportCSV = async () => {
    if (results.length === 0) {
      message.warning('No results to export');
      return;
    }
    
    try {
      const currentFilters = form.getFieldsValue();
      const response = await apiClient.post('/scanner/export/csv', currentFilters, {
        responseType: 'blob',
      });
      
      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `scan_results_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      message.success('Results exported to CSV');
    } catch (error) {
      console.error('CSV export failed:', error);
      message.error('Failed to export CSV');
    }
  };
  
  const handleExportJSON = async () => {
    if (results.length === 0) {
      message.warning('No results to export');
      return;
    }
    
    try {
      const currentFilters = form.getFieldsValue();
      const response = await apiClient.post('/scanner/export/json', currentFilters, {
        responseType: 'blob',
      });
      
      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `scan_results_${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      message.success('Results exported to JSON');
    } catch (error) {
      console.error('JSON export failed:', error);
      message.error('Failed to export JSON');
    }
  };

  // Table columns
  const columns: ColumnsType<ScanResult> = [
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      fixed: 'left',
      width: 100,
      render: (symbol: string) => (
        <Button
          type="link"
          onClick={() => onSymbolSelect?.(symbol)}
          style={{ fontWeight: 'bold' }}
        >
          {symbol}
        </Button>
      ),
    },
    {
      title: 'Price',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      sorter: (a, b) => a.price - b.price,
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: 'Change',
      dataIndex: 'change_percent',
      key: 'change_percent',
      width: 100,
      sorter: (a, b) => a.change_percent - b.change_percent,
      render: (change_percent: number) => {
        const isPositive = change_percent >= 0;
        return (
          <Space>
            {isPositive ? <RiseOutlined style={{ color: '#52c41a' }} /> : <FallOutlined style={{ color: '#ff4d4f' }} />}
            <Text style={{ color: isPositive ? '#52c41a' : '#ff4d4f' }}>
              {isPositive ? '+' : ''}{change_percent.toFixed(2)}%
            </Text>
          </Space>
        );
      },
    },
    {
      title: 'Volume',
      dataIndex: 'volume',
      key: 'volume',
      width: 120,
      sorter: (a, b) => a.volume - b.volume,
      render: (volume: number) => volume.toLocaleString(),
    },
    {
      title: 'RSI',
      dataIndex: 'rsi',
      key: 'rsi',
      width: 80,
      sorter: (a, b) => (a.rsi || 0) - (b.rsi || 0),
      render: (rsi?: number) => {
        if (!rsi) return '-';
        const color = rsi > 70 ? '#ff4d4f' : rsi < 30 ? '#52c41a' : '#1890ff';
        return <Text style={{ color }}>{rsi.toFixed(1)}</Text>;
      },
    },
    {
      title: 'Score',
      dataIndex: 'score',
      key: 'score',
      width: 100,
      sorter: (a, b) => a.score - b.score,
      defaultSortOrder: 'descend',
      render: (score: number) => (
        <Tag color={score >= 80 ? 'green' : score >= 60 ? 'blue' : 'default'}>
          {score.toFixed(0)}%
        </Tag>
      ),
    },
    {
      title: 'Signals',
      dataIndex: 'signals',
      key: 'signals',
      render: (signals: string[]) => (
        <Space wrap size="small">
          {signals.slice(0, 3).map((signal, idx) => (
            <Tag key={idx} color="blue" style={{ fontSize: 11 }}>
              {signal}
            </Tag>
          ))}
          {signals.length > 3 && (
            <Tooltip title={signals.slice(3).join(', ')}>
              <Tag color="default" style={{ fontSize: 11 }}>
                +{signals.length - 3}
              </Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <SearchOutlined />
          <span>Market Scanner</span>
          {isConnected && (
            <Badge status="success" text="Live" />
          )}
        </Space>
      }
      extra={
        <Space>
          {/* Auto-Refresh Toggle */}
          <Tooltip title={autoRefresh ? 'Stop auto-refresh' : 'Enable auto-refresh'}>
            <Space>
              {autoRefresh ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              <Switch
                checked={autoRefresh}
                onChange={(checked) => setAutoRefresh(checked)}
                checkedChildren="Live"
                unCheckedChildren="Manual"
              />
            </Space>
          </Tooltip>
          
          {/* Refresh Interval */}
          {autoRefresh && (
            <InputNumber
              min={5}
              max={60}
              value={refreshInterval}
              onChange={(value) => {
                if (value) {
                  setRefreshInterval(value);
                  if (isScanning) {
                    const currentFilters = form.getFieldsValue();
                    updateFilters(currentFilters, value);
                  }
                }
              }}
              addonAfter="sec"
              style={{ width: 100 }}
            />
          )}
          
          {/* Connection Status */}
          {autoRefresh && (
            <Tooltip title={`WebSocket: ${connectionStatus}`}>
              {isConnected ? (
                <WifiOutlined style={{ color: 'green', fontSize: 18 }} />
              ) : (
                <DisconnectOutlined style={{ color: 'red', fontSize: 18 }} />
              )}
            </Tooltip>
          )}
          
          {/* Manual Scan Button */}
          {!autoRefresh && (
            <Button
              icon={<ReloadOutlined />}
              onClick={() => form.submit()}
              loading={loading}
            >
              Scan
            </Button>
          )}
          
          <Button onClick={handleReset}>
            Reset
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        {/* Presets */}
        {presetsLoaded && presets.length > 0 && (
          <div>
            <Text strong>Quick Presets:</Text>
            <div style={{ marginTop: 8 }}>
              <Space wrap>
                {presets.map((preset, idx) => (
                  <Tooltip key={idx} title={preset.description}>
                    <Button
                      size="small"
                      icon={<StarOutlined />}
                      onClick={() => applyPreset(preset)}
                    >
                      {preset.name}
                    </Button>
                  </Tooltip>
                ))}
              </Space>
            </div>
          </div>
        )}

        <Divider />

        {/* Filters Form */}
        <Form
          form={form}
          layout="vertical"
          onFinish={handleScan}
          initialValues={{
            limit: 50,
            macd_signal: 'any',
            ma_crossover: 'none',
          }}
        >
          <Row gutter={16}>
            {/* Price Filters */}
            <Col span={12}>
              <Form.Item label="Price Range" style={{ marginBottom: 8 }}>
                <Space.Compact style={{ width: '100%' }}>
                  <Form.Item name="price_min" noStyle>
                    <InputNumber placeholder="Min $" style={{ width: '50%' }} min={0} />
                  </Form.Item>
                  <Form.Item name="price_max" noStyle>
                    <InputNumber placeholder="Max $" style={{ width: '50%' }} min={0} />
                  </Form.Item>
                </Space.Compact>
              </Form.Item>
            </Col>

            {/* Volume */}
            <Col span={12}>
              <Form.Item label="Min Volume" name="volume_min">
                <InputNumber
                  placeholder="e.g., 1000000"
                  style={{ width: '100%' }}
                  min={0}
                  formatter={(value) => `${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                />
              </Form.Item>
            </Col>

            {/* RSI Range */}
            <Col span={24}>
              <Form.Item label="RSI Range">
                <Row gutter={8}>
                  <Col span={12}>
                    <Form.Item name="rsi_min" noStyle>
                      <InputNumber placeholder="Min (e.g., 30)" style={{ width: '100%' }} min={0} max={100} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="rsi_max" noStyle>
                      <InputNumber placeholder="Max (e.g., 70)" style={{ width: '100%' }} min={0} max={100} />
                    </Form.Item>
                  </Col>
                </Row>
              </Form.Item>
            </Col>

            {/* MACD Signal */}
            <Col span={12}>
              <Form.Item label="MACD Signal" name="macd_signal">
                <Select>
                  <Option value="any">Any</Option>
                  <Option value="bullish">Bullish</Option>
                  <Option value="bearish">Bearish</Option>
                </Select>
              </Form.Item>
            </Col>

            {/* MA Crossover */}
            <Col span={12}>
              <Form.Item label="MA Crossover" name="ma_crossover">
                <Select>
                  <Option value="none">None</Option>
                  <Option value="golden_cross">Golden Cross</Option>
                  <Option value="death_cross">Death Cross</Option>
                </Select>
              </Form.Item>
            </Col>

            {/* Moving Average Filters */}
            <Col span={12}>
              <Form.Item label="Above SMA 50" name="above_sma_50" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item label="Above SMA 200" name="above_sma_200" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>

            {/* Gap Filters */}
            <Col span={12}>
              <Form.Item label="Gap Up" name="gap_up" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item label="Gap Down" name="gap_down" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>

            {/* Advanced Filters */}
            <Col span={12}>
              <Form.Item label="Volume Spike (x avg)" name="volume_spike">
                <InputNumber placeholder="e.g., 2.0" style={{ width: '100%' }} min={1} step={0.1} />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item label="Max Results" name="limit">
                <InputNumber style={{ width: '100%' }} min={1} max={100} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              icon={<SearchOutlined />}
              loading={loading}
              block
              size="large"
            >
              Scan Market
            </Button>
          </Form.Item>
        </Form>

        {/* Scan Statistics */}
        {scanStats && (
          <>
            <Divider />
            <Row gutter={16}>
              <Col span={8}>
                <Statistic title="Results Found" value={scanStats.total} prefix={<ThunderboltOutlined />} />
              </Col>
              <Col span={8}>
                <Statistic title="Scan Time" value={scanStats.scan_time.toFixed(2)} suffix="s" />
              </Col>
              <Col span={8}>
                <Statistic title="Filters Applied" value={scanStats.filters_applied} />
              </Col>
            </Row>
          </>
        )}

        {/* Results Table */}
        {results.length > 0 && (
          <>
            <Divider />
            
            {/* Export Buttons */}
            <Row justify="space-between" align="middle">
              <Col>
                <Text strong>Scan Results ({results.length} stocks)</Text>
              </Col>
              <Col>
                <Space>
                  <Button
                    size="small"
                    onClick={handleExportCSV}
                    icon={<FileTextOutlined />}
                  >
                    Export CSV
                  </Button>
                  <Button
                    size="small"
                    onClick={handleExportJSON}
                    icon={<DownloadOutlined />}
                  >
                    Export JSON
                  </Button>
                </Space>
              </Col>
            </Row>
            
            <Table
              columns={columns}
              dataSource={results}
              rowKey="symbol"
              loading={loading}
              pagination={{
                pageSize: 20,
                showSizeChanger: true,
                showTotal: (total) => `Total ${total} stocks`,
              }}
              scroll={{ x: 800 }}
              size="small"
            />
          </>
        )}

        {/* Empty State */}
        {!loading && results.length === 0 && scanStats === null && (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <SearchOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
            <Title level={5} style={{ marginTop: 16, color: '#999' }}>
              Configure filters and click Scan to find stocks
            </Title>
          </div>
        )}
      </Space>
    </Card>
  );
};

export default Scanner;
