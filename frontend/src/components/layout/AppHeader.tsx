import { Layout, Space, Badge, Dropdown, Avatar } from 'antd';
import {
  BellOutlined,
  UserOutlined,
  SettingOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { useLogout } from '@/hooks/useAuth';
import { colors } from '../../styles/theme';

const { Header } = Layout;

const AppHeader = () => {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const { mutate: logout } = useLogout();

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: 'Profile',
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: 'Settings',
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: 'Logout',
      danger: true,
    },
  ];

  const handleUserMenuClick: MenuProps['onClick'] = ({ key }) => {
    switch (key) {
      case 'profile':
        navigate('/settings');
        break;
      case 'settings':
        navigate('/settings');
        break;
      case 'logout':
        logout();
        break;
    }
  };

  return (
    <Header
      style={{
        background: colors.backgrounds.secondary,
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: `1px solid ${colors.backgrounds.border}`,
        height: '64px',
      }}
      role="banner"
      aria-label="Application header"
    >
      {/* Logo & Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div
          style={{
            fontSize: '20px',
            fontWeight: 600,
            color: colors.brand.primary,
          }}
          role="heading"
          aria-level={1}
        >
          AlgoTrading Platform
        </div>
      </div>

      {/* Right Side - Notifications & User */}
      <Space size="large">
        {/* Notifications */}
        <Badge count={5} offset={[-5, 5]}>
          <button
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '8px',
              display: 'flex',
              alignItems: 'center',
            }}
            aria-label="Notifications (5 unread)"
            onClick={() => navigate('/notifications')}
          >
            <BellOutlined
              style={{
                fontSize: '20px',
                color: colors.text.primary,
              }}
            />
          </button>
        </Badge>

        {/* User Menu */}
        <Dropdown
          menu={{ items: userMenuItems, onClick: handleUserMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <button
            style={{
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'none',
              border: 'none',
              padding: '8px',
            }}
            aria-label={`User menu for ${user?.name || 'User'}`}
            aria-haspopup="true"
          >
            <Avatar
              size="default"
              icon={<UserOutlined />}
              style={{ backgroundColor: colors.brand.primary }}
              alt={user?.name || 'User avatar'}
            />
            <span style={{ color: colors.text.primary }}>{user?.name || 'User'}</span>
          </button>
        </Dropdown>
      </Space>
    </Header>
  );
};

export default AppHeader;
