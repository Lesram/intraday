import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { Result, Button, Typography, Space, Card } from 'antd';
import { WarningOutlined, ReloadOutlined, HomeOutlined } from '@ant-design/icons';

const { Paragraph, Text } = Typography;

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * Error Boundary Component
 * Catches JavaScript errors anywhere in child component tree
 * Logs errors and displays fallback UI
 */
class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    // Update state so the next render will show the fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error to console in development
    console.error('Error Boundary caught an error:', error, errorInfo);
    
    // Log to error tracking service in production
    if (process.env.NODE_ENV === 'production') {
      // TODO: Send to error tracking service (Sentry, LogRocket, etc.)
      // logErrorToService(error, errorInfo);
    }

    this.setState({
      error,
      errorInfo,
    });
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });

    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      // Custom fallback UI if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <div style={{ padding: '50px 20px', maxWidth: '800px', margin: '0 auto' }}>
          <Result
            status="error"
            title="Something Went Wrong"
            subTitle="We're sorry, but something unexpected happened. Please try again."
            icon={<WarningOutlined style={{ color: '#ff4d4f' }} />}
            extra={[
              <Button
                key="reset"
                type="primary"
                icon={<ReloadOutlined />}
                onClick={this.handleReset}
              >
                Try Again
              </Button>,
              <Button
                key="home"
                icon={<HomeOutlined />}
                onClick={this.handleGoHome}
              >
                Go to Home
              </Button>,
            ]}
          >
            {process.env.NODE_ENV === 'development' && this.state.error && (
              <Card
                title="Error Details (Development Only)"
                style={{ marginTop: 24, textAlign: 'left' }}
                size="small"
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div>
                    <Text strong>Error Message:</Text>
                    <Paragraph
                      code
                      copyable
                      style={{
                        marginTop: 8,
                        padding: 12,
                        backgroundColor: '#f5f5f5',
                        borderRadius: 4,
                      }}
                    >
                      {this.state.error.message}
                    </Paragraph>
                  </div>

                  {this.state.error.stack && (
                    <div>
                      <Text strong>Stack Trace:</Text>
                      <Paragraph
                        code
                        copyable
                        style={{
                          marginTop: 8,
                          padding: 12,
                          backgroundColor: '#f5f5f5',
                          borderRadius: 4,
                          maxHeight: 300,
                          overflow: 'auto',
                          fontSize: 12,
                        }}
                      >
                        {this.state.error.stack}
                      </Paragraph>
                    </div>
                  )}

                  {this.state.errorInfo && (
                    <div>
                      <Text strong>Component Stack:</Text>
                      <Paragraph
                        code
                        style={{
                          marginTop: 8,
                          padding: 12,
                          backgroundColor: '#f5f5f5',
                          borderRadius: 4,
                          maxHeight: 200,
                          overflow: 'auto',
                          fontSize: 12,
                        }}
                      >
                        {this.state.errorInfo.componentStack}
                      </Paragraph>
                    </div>
                  )}
                </Space>
              </Card>
            )}
          </Result>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
