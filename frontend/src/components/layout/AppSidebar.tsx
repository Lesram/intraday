import { useState } from 'react';
import { Layout, Menu } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  LineChartOutlined,
  WalletOutlined,
  ThunderboltOutlined,
  RobotOutlined,
  WarningOutlined,
  SearchOutlined,
  FileTextOutlined,
  SettingOutlined,
  TeamOutlined,
  ShoppingOutlined,
  HistoryOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { colors } from '../../styles/theme';

const { Sider } = Layout;

type MenuItem = Required<MenuProps>['items'][number];

const AppSidebar = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems: MenuItem[] = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: 'Dashboard',
    },
    {
      key: '/orders',
      icon: <ShoppingOutlined />,
      label: 'Orders',
    },
    {
      key: '/trades',
      icon: <HistoryOutlined />,
      label: 'Trade History',
    },
    {
      key: '/trading',
      icon: <LineChartOutlined />,
      label: 'Trading',
    },
    {
      key: '/portfolio',
      icon: <WalletOutlined />,
      label: 'Portfolio',
    },
    {
      key: '/strategies',
      icon: <ThunderboltOutlined />,
      label: 'Strategies',
    },
    {
      key: '/backtesting',
      icon: <ExperimentOutlined />,
      label: 'Backtesting',
    },
    {
      key: '/ml-models',
      icon: <RobotOutlined />,
      label: 'ML Models',
    },
    {
      key: '/risk',
      icon: <WarningOutlined />,
      label: 'Risk Management',
    },
    {
      key: '/market-data',
      icon: <SearchOutlined />,
      label: 'Market Scanner',
    },
    {
      type: 'divider',
    },
    {
      key: '/reports',
      icon: <FileTextOutlined />,
      label: 'Reports',
    },
    {
      key: '/admin',
      icon: <TeamOutlined />,
      label: 'Admin',
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: 'Settings',
    },
  ];

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key);
  };

  return (
    <Sider
      collapsible
      collapsed={collapsed}
      onCollapse={setCollapsed}
      width={240}
      style={{
        background: colors.backgrounds.secondary,
        borderRight: `1px solid ${colors.backgrounds.border}`,
      }}
      theme="dark"
      role="navigation"
      aria-label="Main navigation"
      id="main-navigation"
    >
      <Menu
        mode="inline"
        selectedKeys={[location.pathname]}
        onClick={handleMenuClick}
        items={menuItems}
        style={{
          background: colors.backgrounds.secondary,
          border: 'none',
          paddingTop: '16px',
        }}
        aria-label="Navigation menu"
      />
    </Sider>
  );
};

export default AppSidebar;
