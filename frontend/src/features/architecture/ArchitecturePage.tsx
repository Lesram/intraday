import { useState, useCallback } from 'react';
import { Typography, Tabs } from 'antd';
import {
  ClusterOutlined,
  SyncOutlined,
  ExperimentOutlined,
  CloudServerOutlined,
  RobotOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import SystemOverviewTab from './tabs/SystemOverviewTab';
import TickLifecycleTab from './tabs/TickLifecycleTab';
import AlgorithmEngineTab from './tabs/AlgorithmEngineTab';
import InfrastructureTab from './tabs/InfrastructureTab';
import MLPipelineTab from './tabs/MLPipelineTab';
import OperationsTab from './tabs/OperationsTab';
import { colors } from '@styles/theme';

const { Title, Text } = Typography;

const ArchitecturePage = () => {
  const [activeTab, setActiveTab] = useState('overview');

  const handleNavigateTab = useCallback((tab: string) => {
    setActiveTab(tab);
  }, []);

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>Architecture Map</Title>
        <Text style={{ color: colors.text.tertiary }}>
          Interactive visualization of the Intra trading platform — 9 layers, 62 sections, every threshold documented.
        </Text>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        size="large"
        items={[
          {
            key: 'overview',
            label: <span><ClusterOutlined /> System Overview</span>,
            children: <SystemOverviewTab onNavigateTab={handleNavigateTab} />,
          },
          {
            key: 'tick',
            label: <span><SyncOutlined /> Tick Lifecycle</span>,
            children: <TickLifecycleTab />,
          },
          {
            key: 'algorithm',
            label: <span><ExperimentOutlined /> Algorithm Engine</span>,
            children: <AlgorithmEngineTab />,
          },
          {
            key: 'infra',
            label: <span><CloudServerOutlined /> Infrastructure</span>,
            children: <InfrastructureTab />,
          },
          {
            key: 'ml',
            label: <span><RobotOutlined /> ML Pipeline</span>,
            children: <MLPipelineTab />,
          },
          {
            key: 'ops',
            label: <span><ToolOutlined /> Operations</span>,
            children: <OperationsTab />,
          },
        ]}
      />
    </div>
  );
};

export default ArchitecturePage;
