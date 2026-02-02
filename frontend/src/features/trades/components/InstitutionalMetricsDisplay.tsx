/**
 * Institutional Metrics Display Component
 * Shows professional-grade performance metrics in the Trade Detail Modal
 */

import React from 'react';
import { Card, Descriptions, Row, Col, Statistic, Tag, Tooltip, Progress, Table } from 'antd';
import {
  ThunderboltOutlined,
  FireOutlined,
  TrophyOutlined,
  WarningOutlined,
  InfoCircleOutlined
} from '@ant-design/icons';
import type { InstitutionalMetrics } from '@/types/trades';

interface InstitutionalMetricsDisplayProps {
  metrics: InstitutionalMetrics;
}

export const InstitutionalMetricsDisplay: React.FC<InstitutionalMetricsDisplayProps> = ({ metrics }) => {
  
  // Helper to get color based on Sharpe Ratio
  const getSharpeColor = (sharpe: number) => {
    if (sharpe < 0) return '#cf1322';
    if (sharpe < 1) return '#faad14';
    if (sharpe < 2) return '#52c41a';
    return '#1890ff';
  };

  // Helper to get color for Profit Factor
  const getProfitFactorColor = (pf: number) => {
    if (pf < 1) return '#cf1322';
    if (pf < 1.5) return '#faad14';
    if (pf < 2) return '#52c41a';
    return '#1890ff';
  };

  // Helper to get rating tag
  const getRatingTag = (value: number, thresholds: [number, number, number]) => {
    const [poor, good, excellent] = thresholds;
    if (value < poor) return <Tag color="error">Poor</Tag>;
    if (value < good) return <Tag color="warning">Fair</Tag>;
    if (value < excellent) return <Tag color="success">Good</Tag>;
    return <Tag color="blue">Excellent</Tag>;
  };

  // Monthly returns table columns
  const monthlyColumns = [
    {
      title: 'Month',
      dataIndex: 'month',
      key: 'month',
      render: (month: string) => month
    },
    {
      title: 'P&L',
      dataIndex: 'pnl',
      key: 'pnl',
      align: 'right' as const,
      render: (pnl: number) => (
        <span style={{ color: pnl >= 0 ? '#3f8600' : '#cf1322' }}>
          ${pnl.toFixed(2)}
        </span>
      )
    },
    {
      title: 'Trades',
      dataIndex: 'trades',
      key: 'trades',
      align: 'right' as const
    },
    {
      title: 'Win Rate',
      dataIndex: 'winRate',
      key: 'winRate',
      align: 'right' as const,
      render: (rate: number) => `${rate.toFixed(1)}%`
    }
  ];

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title={
          <span>
            <TrophyOutlined style={{ marginRight: 8 }} />
            Institutional Performance Metrics
          </span>
        }
        size="small"
      >
        {/* Risk-Adjusted Returns */}
        <Card type="inner" title="Risk-Adjusted Returns" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 350 }}>
                    <strong>Sharpe Ratio</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Measures risk-adjusted returns. Shows how much excess return you receive for the volatility you endure.
                    </p>
                    <div style={{ fontSize: '11px', fontFamily: 'monospace', background: 'rgba(255,255,255,0.1)', padding: '4px', borderRadius: '4px', margin: '8px 0' }}>
                      (Return - Risk Free Rate) / Std Dev<br/>
                      Annualized: × √252 trading days
                    </div>
                    <div style={{ fontSize: '11px' }}>
                      <div>• &lt; 1.0: Poor</div>
                      <div>• 1.0-2.0: Good</div>
                      <div>• &gt; 2.0: Excellent</div>
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 400 } }}
              >
                <Statistic
                  title={
                    <span>
                      Sharpe Ratio <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.sharpeRatio}
                  precision={2}
                  valueStyle={{ color: getSharpeColor(metrics.sharpeRatio) }}
                  suffix={getRatingTag(metrics.sharpeRatio, [0, 1, 2])}
                />
              </Tooltip>
            </Col>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 350 }}>
                    <strong>Sortino Ratio</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Like Sharpe but only penalizes downside volatility. Better for strategies with asymmetric returns.
                    </p>
                    <div style={{ fontSize: '11px', fontFamily: 'monospace', background: 'rgba(255,255,255,0.1)', padding: '4px', borderRadius: '4px', margin: '8px 0' }}>
                      (Return - Risk Free Rate) / Downside Dev<br/>
                      Only uses negative returns in denominator
                    </div>
                    <div style={{ fontSize: '11px' }}>
                      <div>• Higher than Sharpe = good asymmetry</div>
                      <div>• &gt; 2.0: Strong downside protection</div>
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 400 } }}
              >
                <Statistic
                  title={
                    <span>
                      Sortino Ratio <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.sortinoRatio}
                  precision={2}
                  valueStyle={{ color: getSharpeColor(metrics.sortinoRatio) }}
                />
              </Tooltip>
            </Col>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 350 }}>
                    <strong>Calmar Ratio</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Annual return divided by maximum drawdown. Shows return per unit of worst-case risk.
                    </p>
                    <div style={{ fontSize: '11px', fontFamily: 'monospace', background: 'rgba(255,255,255,0.1)', padding: '4px', borderRadius: '4px', margin: '8px 0' }}>
                      Annualized Return / Max Drawdown %
                    </div>
                    <div style={{ fontSize: '11px' }}>
                      <div>• &lt; 1.0: Returns don't justify risk</div>
                      <div>• 1.0-3.0: Good risk management</div>
                      <div>• &gt; 3.0: Excellent</div>
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 400 } }}
              >
                <Statistic
                  title={
                    <span>
                      Calmar Ratio <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.calmarRatio}
                  precision={2}
                  valueStyle={{ color: metrics.calmarRatio > 1 ? '#3f8600' : '#cf1322' }}
                />
              </Tooltip>
            </Col>
          </Row>
        </Card>

        {/* Drawdown Analysis */}
        <Card type="inner" title="Drawdown Analysis" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 350 }}>
                    <strong>Maximum Drawdown</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Largest peak-to-trough decline. Shows worst-case scenario loss from any high point.
                    </p>
                    <div style={{ fontSize: '11px', fontFamily: 'monospace', background: 'rgba(255,255,255,0.1)', padding: '4px', borderRadius: '4px', margin: '8px 0' }}>
                      (Peak Value - Trough Value) / Peak Value
                    </div>
                    <div style={{ fontSize: '11px' }}>
                      <div>• &lt; 10%: Excellent control</div>
                      <div>• 10-20%: Typical for equity strategies</div>
                      <div>• 20-30%: Requires strong conviction</div>
                      <div>• &gt; 30%: High - difficult to stomach</div>
                    </div>
                    <div style={{ fontSize: '11px', marginTop: '8px', fontStyle: 'italic' }}>
                      Most investors abandon strategies after 20-25% drawdowns.
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 400 } }}
              >
                <Statistic
                  title={
                    <span>
                      Max Drawdown <WarningOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.maxDrawdown}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: metrics.maxDrawdown < 10 ? '#3f8600' : metrics.maxDrawdown < 20 ? '#faad14' : '#cf1322' }}
                />
                <Progress
                  percent={Math.min(metrics.maxDrawdown, 50)}
                  showInfo={false}
                  strokeColor={metrics.maxDrawdown < 10 ? '#52c41a' : metrics.maxDrawdown < 20 ? '#faad14' : '#ff4d4f'}
                  style={{ marginTop: 8 }}
                />
              </Tooltip>
            </Col>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 300 }}>
                    <strong>Max Drawdown (Dollars)</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Dollar amount of maximum drawdown. The actual money lost from peak to trough.
                    </p>
                  </div>
                }
              >
                <Statistic
                  title={
                    <span>
                      Max DD (Dollars) <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.maxDrawdownDollars}
                  precision={2}
                  prefix="$"
                  valueStyle={{ color: '#cf1322' }}
                />
              </Tooltip>
            </Col>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 300 }}>
                    <strong>Drawdown Duration</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Number of days from peak to trough. Longer durations are psychologically harder to endure.
                    </p>
                    <div style={{ fontSize: '11px' }}>
                      A 20% drawdown lasting 1 week is very different from one lasting 6 months.
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 350 } }}
              >
                <Statistic
                  title={
                    <span>
                      DD Duration <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.maxDrawdownDuration}
                  suffix="days"
                />
              </Tooltip>
            </Col>
          </Row>
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={12}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 350 }}>
                    <strong>Recovery Factor</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Net profit relative to maximum drawdown. Shows how well the system recovers from losses.
                    </p>
                    <div style={{ fontSize: '11px', fontFamily: 'monospace', background: 'rgba(255,255,255,0.1)', padding: '4px', borderRadius: '4px', margin: '8px 0' }}>
                      Net Profit / Max Drawdown ($)
                    </div>
                    <div style={{ fontSize: '11px' }}>
                      <div>• &lt; 1.0: Haven't recovered yet</div>
                      <div>• 1.0-3.0: Slow recovery</div>
                      <div>• 3.0-10.0: Good recovery ability</div>
                      <div>• &gt; 10.0: Excellent recovery</div>
                    </div>
                    <div style={{ fontSize: '11px', marginTop: '8px', fontStyle: 'italic' }}>
                      Example: Value of 5 means you make $5 for every $1 of max loss.
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 400 } }}
              >
                <Statistic
                  title={
                    <span>
                      Recovery Factor <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.recoveryFactor}
                  precision={2}
                  valueStyle={{ color: metrics.recoveryFactor > 2 ? '#3f8600' : '#faad14' }}
                />
              </Tooltip>
            </Col>
          </Row>
        </Card>

        {/* Profitability Metrics */}
        <Card type="inner" title="Profitability Metrics" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 350 }}>
                    <strong>Profit Factor</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Ratio of gross profits to gross losses. Simple but powerful metric of system profitability.
                    </p>
                    <div style={{ fontSize: '11px', fontFamily: 'monospace', background: 'rgba(255,255,255,0.1)', padding: '4px', borderRadius: '4px', margin: '8px 0' }}>
                      Sum(Winning Trades) / |Sum(Losing Trades)|
                    </div>
                    <div style={{ fontSize: '11px' }}>
                      <div>• &lt; 1.0: Losing system</div>
                      <div>• 1.0-1.5: Barely profitable</div>
                      <div>• 1.5-2.0: Decent profitability</div>
                      <div>• 2.0-3.0: Good system</div>
                      <div>• &gt; 3.0: Excellent (verify sample size!)</div>
                    </div>
                    <div style={{ fontSize: '11px', marginTop: '8px', fontStyle: 'italic' }}>
                      Must be &gt; 1.0 to be profitable. Values &gt; 2.0 indicate solid edge.
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 400 } }}
              >
                <Statistic
                  title={
                    <span>
                      Profit Factor <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.profitFactor}
                  precision={2}
                  valueStyle={{ color: getProfitFactorColor(metrics.profitFactor) }}
                  suffix={getRatingTag(metrics.profitFactor, [1, 1.5, 2])}
                />
              </Tooltip>
            </Col>
            <Col span={12}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 350 }}>
                    <strong>Expectancy</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Expected dollar profit per trade. The "average" outcome if you took this trade 1000 times.
                    </p>
                    <div style={{ fontSize: '11px', fontFamily: 'monospace', background: 'rgba(255,255,255,0.1)', padding: '4px', borderRadius: '4px', margin: '8px 0' }}>
                      (Win Rate × Avg Win) + (Loss Rate × Avg Loss)
                    </div>
                    <div style={{ fontSize: '11px' }}>
                      <div>• &lt; $0: Losing system - stop trading!</div>
                      <div>• $0-$50: Barely profitable</div>
                      <div>• $50-$200: Decent</div>
                      <div>• &gt; $200: Excellent per trade</div>
                    </div>
                    <div style={{ fontSize: '11px', marginTop: '8px', fontStyle: 'italic' }}>
                      Example: $80 expectancy × 100 trades = $8,000 expected annual profit.
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 400 } }}
              >
                <Statistic
                  title={
                    <span>
                      Expectancy <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.expectancy >= 0 ? metrics.expectancy : Math.abs(metrics.expectancy)}
                  precision={2}
                  prefix={metrics.expectancy >= 0 ? '$' : '-$'}
                  valueStyle={{ color: metrics.expectancy >= 0 ? '#3f8600' : '#cf1322' }}
                />
              </Tooltip>
            </Col>
          </Row>
        </Card>

        {/* Streak Analysis */}
        <Card type="inner" title="Streak Analysis" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 320 }}>
                    <strong>Max Win Streak</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Maximum number of consecutive winning trades. Shows best momentum period.
                    </p>
                    <div style={{ fontSize: '11px', marginTop: '8px' }}>
                      Important for confidence building and psychological resilience.
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 350 } }}
              >
                <Statistic
                  title={
                    <span>
                      <FireOutlined style={{ color: '#52c41a', marginRight: 4 }} />
                      Max Win Streak <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.maxWinStreak}
                  valueStyle={{ color: '#3f8600' }}
                />
              </Tooltip>
            </Col>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 350 }}>
                    <strong>Max Loss Streak</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Maximum number of consecutive losing trades. You must be psychologically prepared to endure this.
                    </p>
                    <div style={{ fontSize: '11px', marginTop: '8px' }}>
                      <strong>Critical:</strong> Most traders abandon strategies during long loss streaks. Know this number before trading.
                    </div>
                    <div style={{ fontSize: '11px', marginTop: '8px', fontStyle: 'italic' }}>
                      Expected max loss streak ≈ log(N) / log(1/loss_rate) for N trades.
                    </div>
                  </div>
                }
                styles={{ root: { maxWidth: 380 } }}
              >
                <Statistic
                  title={
                    <span>
                      <ThunderboltOutlined style={{ color: '#ff4d4f', marginRight: 4 }} />
                      Max Loss Streak <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.maxLossStreak}
                  valueStyle={{ color: '#cf1322' }}
                />
              </Tooltip>
            </Col>
            <Col span={8}>
              <Tooltip 
                title={
                  <div style={{ maxWidth: 300 }}>
                    <strong>Current Streak</strong>
                    <p style={{ margin: '8px 0', fontSize: '12px' }}>
                      Your current consecutive win or loss streak. Shows current momentum.
                    </p>
                    <div style={{ fontSize: '11px' }}>
                      Type: <strong>{metrics.currentStreakType}</strong>
                    </div>
                  </div>
                }
              >
                <Statistic
                  title={
                    <span>
                      Current Streak <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                    </span>
                  }
                  value={metrics.currentStreak}
                  suffix={
                    <Tag color={metrics.currentStreakType === 'win' ? 'success' : metrics.currentStreakType === 'loss' ? 'error' : 'default'}>
                      {metrics.currentStreakType}
                    </Tag>
                  }
                />
              </Tooltip>
            </Col>
          </Row>
        </Card>

        {/* R-Multiple Distribution */}
        <Card type="inner" title="R-Multiple Distribution" size="small" style={{ marginBottom: 16 }}>
          <Tooltip 
            title={
              <div style={{ maxWidth: 350 }}>
                <strong>R-Multiple Distribution</strong>
                <p style={{ margin: '8px 0', fontSize: '12px' }}>
                  Shows the distribution of returns normalized by risk. Helps understand your risk/reward profile.
                </p>
                <div style={{ fontSize: '11px' }}>
                  <strong>Ideal Distribution:</strong>
                  <div>• 30-40% losses (R &lt; 0%)</div>
                  <div>• 20-30% small wins (0-1%)</div>
                  <div>• 30-50% solid wins (&gt; 1%)</div>
                </div>
                <div style={{ fontSize: '11px', marginTop: '8px', fontStyle: 'italic' }}>
                  Key: Wins must be bigger than losses on average.
                </div>
              </div>
            }
            styles={{ root: { maxWidth: 400 } }}
          >
            <div style={{ cursor: 'help' }}>
              <InfoCircleOutlined style={{ fontSize: 14, color: '#999', marginRight: 8 }} />
              <span style={{ fontSize: '13px', color: '#999' }}>Hover for details</span>
            </div>
          </Tooltip>
          <Descriptions size="small" column={2} bordered style={{ marginTop: 8 }}>
            <Descriptions.Item label="Avg R-Multiple">{metrics.rMultiples.avgRMultiple.toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="Median R-Multiple">{metrics.rMultiples.medianRMultiple.toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="Trades > 1R" span={2}>
              <Tag color="success">{metrics.rMultiples.countAbove1R} trades</Tag>
            </Descriptions.Item>
          </Descriptions>
          <div style={{ marginTop: 12 }}>
            <strong>Distribution:</strong>
            <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
              {Object.entries(metrics.rMultiples.distribution).map(([range, count]) => (
                <Col span={24} key={range}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 100 }}>{range}:</span>
                    <Progress
                      percent={(count / metrics.totalTrades) * 100}
                      format={() => `${count} trades`}
                      style={{ flex: 1 }}
                    />
                  </div>
                </Col>
              ))}
            </Row>
          </div>
        </Card>

        {/* Time Metrics */}
        <Card type="inner" title="Time Metrics" size="small" style={{ marginBottom: 16 }}>
          <Tooltip 
            title={
              <div style={{ maxWidth: 350 }}>
                <strong>Average Trade Duration</strong>
                <p style={{ margin: '8px 0', fontSize: '12px' }}>
                  How long positions are held on average. Helps classify strategy style.
                </p>
                <div style={{ fontSize: '11px' }}>
                  <div>• &lt; 1 hour: Scalping</div>
                  <div>• 1-8 hours: Day trading</div>
                  <div>• 8-24 hours: Swing trading</div>
                  <div>• &gt; 24 hours: Position trading</div>
                </div>
                <div style={{ fontSize: '11px', marginTop: '8px', fontStyle: 'italic' }}>
                  Affects commission costs and overnight risk exposure.
                </div>
              </div>
            }
            styles={{ root: { maxWidth: 400 } }}
          >
            <Statistic
              title={
                <span>
                  Average Trade Duration <InfoCircleOutlined style={{ fontSize: 12, color: '#999' }} />
                </span>
              }
              value={metrics.avgTradeDurationHours}
              precision={1}
              suffix="hours"
            />
          </Tooltip>
        </Card>

        {/* Monthly Returns */}
        {metrics.monthlyReturns.length > 0 && (
          <Card type="inner" title="Monthly Returns Breakdown" size="small">
            <Tooltip 
              title={
                <div style={{ maxWidth: 350 }}>
                  <strong>Monthly Returns</strong>
                  <p style={{ margin: '8px 0', fontSize: '12px' }}>
                    Aggregated performance by month. Shows consistency and identifies seasonal patterns.
                  </p>
                  <div style={{ fontSize: '11px' }}>
                    <strong>Red Flags:</strong>
                    <div>• More losing months than winning</div>
                    <div>• Wild swings (±50% per month)</div>
                    <div>• 3+ consecutive losing months</div>
                  </div>
                </div>
              }
              styles={{ root: { maxWidth: 400 } }}
            >
              <div style={{ marginBottom: 12, cursor: 'help' }}>
                <InfoCircleOutlined style={{ fontSize: 14, color: '#999', marginRight: 8 }} />
                <span style={{ fontSize: '13px', color: '#999' }}>Hover for details</span>
              </div>
            </Tooltip>
            <Table
              dataSource={metrics.monthlyReturns}
              columns={monthlyColumns}
              size="small"
              pagination={false}
              rowKey="month"
            />
          </Card>
        )}
      </Card>
    </div>
  );
};
