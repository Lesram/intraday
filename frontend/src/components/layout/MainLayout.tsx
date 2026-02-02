import { Layout } from 'antd';
import { Outlet } from 'react-router-dom';
import AppHeader from './AppHeader';
import AppSidebar from './AppSidebar';
import { colors } from '../../styles/theme';
import { useWebSocketConnection } from '@/hooks/useWebSocket';
import { SkipLinks } from '../SkipLinks';

const { Content } = Layout;

const MainLayout = () => {
  // Initialize WebSocket connection when user is authenticated
  useWebSocketConnection();
  
  return (
    <Layout style={{ minHeight: '100vh', background: colors.backgrounds.primary }}>
      {/* Skip Links for Keyboard Navigation */}
      <SkipLinks />
      
      {/* Top Navigation Bar */}
      <AppHeader />
      
      <Layout>
        {/* Side Navigation */}
        <AppSidebar />
        
        {/* Main Content Area */}
        <Content
          id="main-content"
          tabIndex={-1}
          style={{
            padding: '24px',
            background: colors.backgrounds.primary,
            minHeight: 'calc(100vh - 64px)',
          }}
          role="main"
          aria-label="Main content"
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
