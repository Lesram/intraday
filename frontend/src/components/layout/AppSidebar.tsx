import { useState, useMemo } from 'react';
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
  ApartmentOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { colors } from '../../styles/theme';
import { useAuthStore } from '@/store/authStore';

const { Sider } = Layout;

type MenuItem = Required<MenuProps>['items'][number];

const AppSidebar = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const userRole = user?.role ?? 'viewer';

  const menuItems: MenuItem[] = useMemo(() => {
    const items: MenuItem[] = [
      { key: '/', icon: <DashboardOutlined />, label: 'Dashboard' },
      { key: '/orders', icon: <ShoppingOutlined />, label: 'Orders' },
      { key: '/trades', icon: <HistoryOutlined />, label: 'Trade History' },
      { key: '/trading', icon: <LineChartOutlined />, label: 'Trading' },
      { key: '/portfolio', icon: <WalletOutlined />, label: 'Portfolio' },
      { key: '/strategies', icon: <ThunderboltOutlined />, label: 'Strategies' },
      { key: '/backtesting', icon: <ExperimentOutlined />, label: 'Backtesting' },
      { key: '/ml-models', icon: <RobotOutlined />, label: 'ML Models' },
      { key: '/risk', icon: <WarningOutlined />, label: 'Risk Management' },
      { key: '/market-data', icon: <SearchOutlined />, label: 'Market Scanner' },
      { key: '/organism', icon: <ApartmentOutlined />, label: 'Living Organism' },
      { type: 'divider' },
      { key: '/reports', icon: <FileTextOutlined />, label: 'Reports' },
    ];

    // Admin menu item — only visible to admin users
    if (userRole === 'admin') {
      items.push({ key: '/admin', icon: <TeamOutlined />, label: 'Admin' });
    }

    items.push({ key: '/settings', icon: <SettingOutlined />, label: 'Settings' });
    return items;
  }, [userRole]);

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
