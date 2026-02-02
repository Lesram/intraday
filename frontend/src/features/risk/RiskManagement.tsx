/**
 * Risk Management Main Page
 * Complete risk management interface with dashboard, configuration, and controls
 */

import React, { useState } from 'react';
import { Layout, Tabs, Card, Typography, Space } from 'antd';
import {
  DashboardOutlined,
  SettingOutlined,

  FireOutlined,
} from '@ant-design/icons';
import RiskDashboard from './RiskDashboard';
import RiskLimitsConfig from './RiskLimitsConfig';
import KillSwitchButton from './KillSwitchButton';

const { Content } = Layout;
const { Title } = Typography;

type TabKey = 'dashboard' | 'limits' | 'history';

const RiskManagement: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard');

  const tabItems = [
    {
      key: 'dashboard' as TabKey,
      label: (
        <Space>
          <DashboardOutlined />
          Dashboard
        </Space>
      ),
      children: (
        <RiskDashboard 
          showKillSwitch={false} // We'll show it in the header instead
          autoRefresh={true}
        />
      ),
    },
    {
      key: 'limits' as TabKey,
      label: (
        <Space>
          <SettingOutlined />
          Risk Limits
        </Space>
      ),
      children: (
        <RiskLimitsConfig editable={true} />
      ),
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh', background: '#f0f2f5' }}>
      <Content style={{ padding: '24px' }}>
        {/* Page Header */}
        <Card style={{ marginBottom: 24 }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '16px'
          }}>
            <div>
              <Title level={2} style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                <FireOutlined style={{ color: '#ff4d4f' }} />
                Risk Management
              </Title>
              <Typography.Text type="secondary" style={{ fontSize: '16px' }}>
                Monitor risk metrics, configure limits, and manage emergency controls
              </Typography.Text>
            </div>
            <div>
              <KillSwitchButton size="large" />
            </div>
          </div>
        </Card>

        {/* Main Content Tabs */}
        <Card style={{ minHeight: 'calc(100vh - 200px)' }}>
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as TabKey)}
            items={tabItems}
            size="large"
            style={{ height: '100%' }}
            tabBarStyle={{ 
              marginBottom: 24,
              borderBottom: '1px solid #f0f0f0'
            }}
          />
        </Card>
      </Content>
    </Layout>
  );
};

export default RiskManagement;