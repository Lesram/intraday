/**
 * Register Page
 * User registration form with validation
 */

import { Form, Input, Button, Card, Typography, Space } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { useRegister } from '@/hooks/useAuth';
import { colors } from '@/styles/theme';
import type { RegisterRequest } from '@/types/auth';

const { Title, Text } = Typography;

const RegisterPage = () => {
  const { mutate: register, isPending } = useRegister();

  const onFinish = (values: RegisterRequest & { confirmPassword: string }) => {
    const { confirmPassword: _confirmPassword, ...registerData } = values;
    register(registerData);
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
              Create Account
            </Title>
            <Text style={{ color: colors.text.secondary, fontSize: '16px' }}>
              Join AlgoTrading Platform
            </Text>
          </div>

          {/* Registration Form */}
          <Form
            name="register"
            onFinish={onFinish}
            layout="vertical"
            autoComplete="off"
            size="large"
          >
            <Form.Item
              name="name"
              rules={[
                { required: true, message: 'Please enter your full name!' },
                { min: 2, message: 'Name must be at least 2 characters!' },
              ]}
            >
              <Input
                prefix={<UserOutlined style={{ color: colors.text.tertiary }} />}
                placeholder="Full Name"
                autoComplete="name"
              />
            </Form.Item>

            <Form.Item
              name="email"
              rules={[
                { required: true, message: 'Please enter your email!' },
                { type: 'email', message: 'Please enter a valid email address!' },
              ]}
            >
              <Input
                prefix={<MailOutlined style={{ color: colors.text.tertiary }} />}
                placeholder="Email"
                autoComplete="email"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: 'Please enter your password!' },
                { min: 8, message: 'Password must be at least 8 characters!' },
                {
                  pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
                  message: 'Password must contain uppercase, lowercase, and number!',
                },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: colors.text.tertiary }} />}
                placeholder="Password"
                autoComplete="new-password"
              />
            </Form.Item>

            <Form.Item
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: 'Please confirm your password!' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('The passwords do not match!'));
                  },
                }),
              ]}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: colors.text.tertiary }} />}
                placeholder="Confirm Password"
                autoComplete="new-password"
              />
            </Form.Item>

            <Form.Item style={{ marginTop: '24px', marginBottom: '16px' }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={isPending}
                size="large"
              >
                {isPending ? 'Creating account...' : 'Sign Up'}
              </Button>
            </Form.Item>

            {/* Login Link */}
            <div style={{ textAlign: 'center' }}>
              <Text style={{ color: colors.text.secondary }}>
                Already have an account?{' '}
                <Link to="/login" style={{ color: colors.brand.primary, fontWeight: 500 }}>
                  Sign in
                </Link>
              </Text>
            </div>
          </Form>
        </Space>
      </Card>
    </div>
  );
};

export default RegisterPage;
