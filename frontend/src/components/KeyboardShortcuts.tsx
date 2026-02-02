/**
 * Keyboard Shortcuts Component
 * Global keyboard shortcuts for the application
 */
import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Modal, Typography, Space, Divider } from 'antd';
import { useKeyboardShortcut } from '@/hooks/useAccessibility';

const { Title, Text } = Typography;

export const KeyboardShortcuts: React.FC = () => {
  const navigate = useNavigate();
  const [helpVisible, setHelpVisible] = React.useState(false);

  // Navigation shortcuts
  useKeyboardShortcut('h', () => navigate('/'), { alt: true }); // Alt+H = Home
  useKeyboardShortcut('d', () => navigate('/dashboard'), { alt: true }); // Alt+D = Dashboard
  useKeyboardShortcut('m', () => navigate('/ml-models'), { alt: true }); // Alt+M = ML Models
  useKeyboardShortcut('s', () => navigate('/strategies'), { alt: true }); // Alt+S = Strategies
  useKeyboardShortcut('p', () => navigate('/portfolio'), { alt: true }); // Alt+P = Portfolio
  
  // Utility shortcuts
  useKeyboardShortcut('/', () => {
    // Focus search if it exists
    const searchInput = document.querySelector('input[aria-label*="Search"]') as HTMLInputElement;
    if (searchInput) {
      searchInput.focus();
    }
  }); // / = Focus search

  useKeyboardShortcut('?', () => setHelpVisible(true)); // ? = Show help
  useKeyboardShortcut('Escape', () => setHelpVisible(false)); // ESC = Close help

  // Add keyboard navigation class to body
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Tab') {
        document.body.classList.add('keyboard-navigation-active');
      }
    };

    const handleMouseDown = () => {
      document.body.classList.remove('keyboard-navigation-active');
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('mousedown', handleMouseDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('mousedown', handleMouseDown);
    };
  }, []);

  return (
    <Modal
      title="Keyboard Shortcuts"
      open={helpVisible}
      onCancel={() => setHelpVisible(false)}
      footer={null}
      width={600}
    >
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={5}>Navigation</Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Go to Home</Text>
              <Text keyboard className="keyboard-shortcut">Alt + H</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Go to Dashboard</Text>
              <Text keyboard className="keyboard-shortcut">Alt + D</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Go to ML Models</Text>
              <Text keyboard className="keyboard-shortcut">Alt + M</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Go to Strategies</Text>
              <Text keyboard className="keyboard-shortcut">Alt + S</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Go to Portfolio</Text>
              <Text keyboard className="keyboard-shortcut">Alt + P</Text>
            </div>
          </Space>
        </div>

        <Divider />

        <div>
          <Title level={5}>Search & Actions</Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Focus Search</Text>
              <Text keyboard className="keyboard-shortcut">/</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Show Keyboard Shortcuts</Text>
              <Text keyboard className="keyboard-shortcut">?</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Close Modal/Dialog</Text>
              <Text keyboard className="keyboard-shortcut">Esc</Text>
            </div>
          </Space>
        </div>

        <Divider />

        <div>
          <Title level={5}>Table Navigation</Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Next Item</Text>
              <Text keyboard className="keyboard-shortcut">↓</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Previous Item</Text>
              <Text keyboard className="keyboard-shortcut">↑</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>First Item</Text>
              <Text keyboard className="keyboard-shortcut">Home</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Last Item</Text>
              <Text keyboard className="keyboard-shortcut">End</Text>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Navigate Controls</Text>
              <Text keyboard className="keyboard-shortcut">Tab</Text>
            </div>
          </Space>
        </div>

        <Divider />

        <div>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            <strong>Tip:</strong> Press Tab to navigate between interactive elements. 
            Most buttons and links can be activated with Space or Enter.
          </Text>
        </div>
      </Space>
    </Modal>
  );
};
