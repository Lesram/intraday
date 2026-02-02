/**
 * Login Page
 * User authentication with email and password
 */

import { Form, Input, Button, Card, Typography, Space } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { useLogin } from '@/hooks/useAuth';
import { colors } from '@/styles/theme';

const { Title, Text } = Typography;

const LoginPage = () => {
  const { mutate: login, isPending } = useLogin();

  const onFinish = (values: { email: string; password: string }) => {
    // Backend expects 'username' field, but we collect 'email'
    login({
      username: values.email,
      password: values.password,
    });
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: colors.backgrounds.primary,
        padding: '20px',
      }}
    >
      <Card
        style={{
          width: '100%',
          maxWidth: '420px',
          background: colors.backgrounds.secondary,
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3)',
        }}
      >
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* Header */}
          <div style={{ textAlign: 'center' }}>
            <Title level={2} style={{ color: colors.brand.primary, marginBottom: '8px' }}>
              AlgoTrading Platform
            </Title>
            <Text style={{ color: colors.text.secondary, fontSize: '16px' }}>
              Sign in to your account
            </Text>
          </div>

          {/* Login Form */}
          <Form
            name="login"
            onFinish={onFinish}
            layout="vertical"
            autoComplete="off"
            size="large"
          >
            <Form.Item
              name="email"
              rules={[
                { required: true, message: 'Please enter your email!' },
                { type: 'email', message: 'Please enter a valid email address!' },
              ]}
            >
              <Input
                prefix={<UserOutlined style={{ color: colors.text.tertiary }} />}
                placeholder="Email"
                autoComplete="email"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: 'Please enter your password!' },
                { min: 6, message: 'Password must be at least 6 characters!' },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: colors.text.tertiary }} />}
                placeholder="Password"
                autoComplete="current-password"
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Link
                  to="/forgot-password"
                  style={{ color: colors.brand.primary, fontSize: '14px' }}
                >
                  Forgot password?
                </Link>
              </div>
            </Form.Item>

            <Form.Item style={{ marginBottom: '16px' }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={isPending}
                size="large"
              >
                {isPending ? 'Signing in...' : 'Sign In'}
              </Button>
            </Form.Item>

            {/* Register Link */}
            <div style={{ textAlign: 'center' }}>
              <Text style={{ color: colors.text.secondary }}>
                Don't have an account?{' '}
                <Link to="/register" style={{ color: colors.brand.primary, fontWeight: 500 }}>
                  Sign up
                </Link>
              </Text>
            </div>
          </Form>
        </Space>
      </Card>
    </div>
  );
};

export default LoginPage;
