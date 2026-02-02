/**
 * Loading Components
 * Reusable loading indicators and skeleton screens
 */

import { Spin, Skeleton, Card } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { colors } from '@/styles/theme';

// ============= Loading Spinner =============

interface LoadingSpinnerProps {
  tip?: string;
  size?: 'small' | 'default' | 'large';
  fullscreen?: boolean;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  tip,
  size = 'large',
  fullscreen = false,
}) => {
  const icon = <LoadingOutlined style={{ fontSize: 48 }} spin />;

  const spinner = (
    <Spin
      indicator={icon}
      size={size}
      tip={tip}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: fullscreen ? '100vh' : '400px',
      }}
    />
  );

  if (fullscreen) {
    return (
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.7)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {spinner}
      </div>
    );
  }

  return spinner;
};

// ============= Page Skeleton =============

export const PageSkeleton: React.FC = () => {
  return (
    <div style={{ padding: '24px' }}>
      {/* Header skeleton */}
      <Skeleton.Input
        active
        style={{ width: 300, marginBottom: 24, height: 40 }}
      />

      {/* Stats cards skeleton */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} style={{ background: colors.backgrounds.secondary }}>
            <Skeleton active paragraph={{ rows: 1 }} />
          </Card>
        ))}
      </div>

      {/* Table skeleton */}
      <Card style={{ background: colors.backgrounds.secondary }}>
        <Skeleton active paragraph={{ rows: 8 }} />
      </Card>
    </div>
  );
};

// ============= Table Skeleton =============

interface TableSkeletonProps {
  rows?: number;
  columns?: number;
}

export const TableSkeleton: React.FC<TableSkeletonProps> = ({
  rows = 5,
  columns = 4,
}) => {
  return (
    <div>
      {/* Table header */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${columns}, 1fr)`,
          gap: 16,
          marginBottom: 16,
          padding: '12px 16px',
          background: colors.backgrounds.tertiary,
          borderRadius: 8,
        }}
      >
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton.Input key={i} active style={{ width: '100%', height: 20 }} />
        ))}
      </div>

      {/* Table rows */}
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div
          key={rowIndex}
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${columns}, 1fr)`,
            gap: 16,
            marginBottom: 12,
            padding: '12px 16px',
            background: colors.backgrounds.secondary,
            borderRadius: 8,
          }}
        >
          {Array.from({ length: columns }).map((_, colIndex) => (
            <Skeleton.Input
              key={colIndex}
              active
              style={{ width: '100%', height: 20 }}
            />
          ))}
        </div>
      ))}
    </div>
  );
};

// ============= Card Skeleton =============

export const CardSkeleton: React.FC = () => {
  return (
    <Card style={{ background: colors.backgrounds.secondary }}>
      <Skeleton active paragraph={{ rows: 3 }} />
    </Card>
  );
};

// ============= Chart Skeleton =============

export const ChartSkeleton: React.FC<{ height?: number }> = ({
  height = 400,
}) => {
  return (
    <Card style={{ background: colors.backgrounds.secondary }}>
      <Skeleton.Node
        active
        style={{
          width: '100%',
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <LoadingOutlined style={{ fontSize: 48, color: colors.text.secondary }} />
      </Skeleton.Node>
    </Card>
  );
};
