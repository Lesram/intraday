import { Card, Typography } from 'antd';
import { RocketOutlined } from '@ant-design/icons';
import { colors } from '../../styles/theme';

const { Title, Paragraph } = Typography;

interface ComingSoonProps {
  title: string;
}

const ComingSoon = ({ title }: ComingSoonProps) => {
  return (
    <div style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      minHeight: '60vh' 
    }}>
      <Card
        style={{
          background: colors.backgrounds.secondary,
          textAlign: 'center',
          maxWidth: '500px',
          width: '100%',
        }}
      >
        <RocketOutlined style={{ fontSize: '64px', color: colors.brand.primary, marginBottom: '24px' }} />
        <Title level={2} style={{ color: colors.text.primary }}>
          {title}
        </Title>
        <Paragraph style={{ color: colors.text.secondary, fontSize: '16px' }}>
          This feature is currently under development and will be available soon.
        </Paragraph>
        <Paragraph style={{ color: colors.text.tertiary }}>
          We're working hard to bring you the best trading experience.
        </Paragraph>
      </Card>
    </div>
  );
};

export default ComingSoon;
