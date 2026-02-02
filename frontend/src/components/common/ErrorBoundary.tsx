/**
 * Error Boundary Component
 * Catches React errors and displays             )}
          >
            {import.meta.env.DEV && this.state.errorInfo && (
              <divback UI
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Result, Button } from 'antd';
import { colors } from '@/styles/theme';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
  errorInfo?: ErrorInfo;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100vh',
            background: colors.backgrounds.primary,
            padding: '24px',
          }}
        >
          <Result
            status="error"
            title="Something went wrong"
            subTitle={
              this.state.error?.message || 'An unexpected error occurred'
            }
            extra={[
              <Button key="reset" type="primary" onClick={this.handleReset}>
                Try Again
              </Button>,
              <Button key="reload" onClick={this.handleReload}>
                Reload Page
              </Button>,
            ]}
            style={{
              maxWidth: 600,
            }}
          >
            {import.meta.env.DEV && this.state.errorInfo && (
              <div
                style={{
                  textAlign: 'left',
                  marginTop: 24,
                  padding: 16,
                  background: colors.backgrounds.secondary,
                  borderRadius: 8,
                  overflow: 'auto',
                }}
              >
                <h3 style={{ color: colors.text.primary }}>Stack Trace:</h3>
                <pre
                  style={{
                    fontSize: 12,
                    color: colors.text.secondary,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {this.state.errorInfo.componentStack}
                </pre>
              </div>
            )}
          </Result>
        </div>
      );
    }

    return this.props.children;
  }
}
