/**
 * Lazy Loading Wrapper for Analytics Components
 * Delays Chart.js loading until analytics tab is opened
 */

import React, { Suspense, lazy } from 'react';
import { Skeleton, Card } from 'antd';

// Lazy load analytics components (includes Chart.js bundle)
const ModelComparisonLazy = lazy(() =>
  import('./ModelComparison').then(module => ({ default: module.ModelComparison }))
);

const FeatureImportanceLazy = lazy(() =>
  import('./FeatureImportance').then(module => ({ default: module.FeatureImportance }))
);

const PerformanceChartsLazy = lazy(() =>
  import('./PerformanceCharts').then(module => ({ default: module.PerformanceCharts }))
);

// Loading fallback component
const AnalyticsLoading: React.FC = () => (
  <Card>
    <Skeleton active paragraph={{ rows: 8 }} />
  </Card>
);

// Wrapped components with Suspense
export const ModelComparisonLazyWrapped: React.FC<Record<string, unknown>> = (props) => (
  <Suspense fallback={<AnalyticsLoading />}>
    <ModelComparisonLazy {...props} />
  </Suspense>
);

export const FeatureImportanceLazyWrapped: React.FC<Record<string, unknown>> = (props) => (
  <Suspense fallback={<AnalyticsLoading />}>
    <FeatureImportanceLazy {...props} />
  </Suspense>
);

export const PerformanceChartsLazyWrapped: React.FC<Record<string, unknown>> = (props) => (
  <Suspense fallback={<AnalyticsLoading />}>
    <PerformanceChartsLazy {...props} />
  </Suspense>
);

// Bundle size savings: ~150KB by lazy loading Chart.js
