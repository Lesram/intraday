import { Collapse, Typography } from 'antd';
import type { ReactNode } from 'react';
import { colors } from '@styles/theme';

const { Text } = Typography;

interface CollapsibleSectionProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}

const CollapsibleSection = ({ title, subtitle, children, defaultOpen = false }: CollapsibleSectionProps) => (
  <Collapse
    defaultActiveKey={defaultOpen ? ['1'] : []}
    style={{ background: colors.backgrounds.secondary, marginBottom: 12 }}
    items={[{
      key: '1',
      label: (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Text strong style={{ color: colors.text.primary, fontSize: 15 }}>{title}</Text>
          {subtitle && <Text style={{ color: colors.text.tertiary, fontSize: 12 }}>{subtitle}</Text>}
        </div>
      ),
      children,
    }]}
  />
);

export default CollapsibleSection;
