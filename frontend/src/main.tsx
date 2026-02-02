import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import 'antd/dist/reset.css';
import App from './App.tsx';
import './index.css';

// Suppress browser extension errors that appear in console
// These are typically caused by browser extensions trying to communicate
// and don't affect app functionality
window.addEventListener('unhandledrejection', (event) => {
  // Filter out known extension-related errors
  if (
    event.reason?.message?.includes('message channel closed') ||
    event.reason?.message?.includes('Extension context invalidated')
  ) {
    event.preventDefault();
    // Optionally log to help with debugging
    console.debug('[Suppressed Extension Error]:', event.reason?.message);
  }
});

// Suppress Ant Design React 19 compatibility warning
// Ant Design v5 works fine with React 19, but shows a warning
// See: https://github.com/ant-design/ant-design/issues/43888
const originalConsoleWarn = console.warn;
console.warn = function (...args: unknown[]) {
  const message = args[0];
  // Suppress Ant Design React 19 compatibility warning
  if (
    typeof message === 'string' &&
    message.includes('antd v5 support React is 16 ~ 18')
  ) {
    console.debug('[Suppressed Ant Design Warning]:', message);
    return;
  }
  originalConsoleWarn.apply(console, args);
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
