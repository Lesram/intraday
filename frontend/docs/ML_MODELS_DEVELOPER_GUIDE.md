# ML Models Feature - Developer Documentation

**Version:** 1.0.0  
**Last Updated:** October 15, 2024  
**Status:** Production Ready ✅

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Component Structure](#component-structure)
3. [State Management](#state-management)
4. [API Integration](#api-integration)
5. [Testing Strategy](#testing-strategy)
6. [Accessibility Implementation](#accessibility-implementation)
7. [Performance Optimization](#performance-optimization)
8. [Extending the Feature](#extending-the-feature)
9. [Troubleshooting](#troubleshooting)
10. [Best Practices](#best-practices)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Frontend (React)                      │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Pages      │  │  Components  │  │    Hooks     │ │
│  │              │  │              │  │              │ │
│  │ - MLModels   │  │ - Registry   │  │ - useMLModels│ │
│  │ - Training   │  │ - TrainForm  │  │ - useSocket  │ │
│  │ - Analytics  │  │ - ModelCard  │  │ - useA11y    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ React Query  │  │   Zustand    │  │  WebSocket   │ │
│  │ (API Cache)  │  │  (UI State)  │  │ (Real-time)  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                          ↕ REST API + WebSocket
┌─────────────────────────────────────────────────────────┐
│                   Backend (FastAPI)                     │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Routers    │  │   Services   │  │   Models     │ │
│  │              │  │              │  │              │ │
│  │ - ML Routes  │  │ - Training   │  │ - Registry   │ │
│  │ - WebSocket  │  │ - Prediction │  │ - Metadata   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │            Model Storage (Disk + DB)             │  │
│  │  artifacts/{model_name}/{version}/model.pkl     │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Technology Stack

**Frontend**:
- **React 19**: UI framework
- **TypeScript**: Type safety
- **Ant Design**: Component library
- **React Query**: Server state management
- **Zustand**: Client state management
- **Chart.js / Recharts**: Data visualization
- **Socket.IO Client**: Real-time updates
- **Vitest**: Unit testing
- **React Testing Library**: Component testing

**Backend**:
- **FastAPI**: Web framework
- **SQLAlchemy**: ORM
- **Pydantic**: Data validation
- **Scikit-learn**: ML library
- **TensorFlow/PyTorch**: Deep learning
- **Celery**: Task queue (training jobs)
- **Redis**: Cache + message broker
- **PostgreSQL**: Database

---

## Component Structure

### Directory Layout

```
frontend/src/features/ml-models/
├── components/
│   ├── __tests__/
│   │   ├── ModelRegistry.test.tsx
│   │   ├── TrainingForm.test.tsx
│   │   └── ModelCard.test.tsx
│   ├── ModelRegistry.tsx          # Main registry view
│   ├── ModelCard.tsx              # Individual model card
│   ├── ModelCard_Mobile.tsx       # Mobile-optimized card
│   ├── TrainingForm.tsx           # Model training form
│   ├── TrainingProgressMonitor.tsx # Real-time training progress
│   ├── ModelComparison.tsx        # Compare multiple models
│   ├── FeatureImportance.tsx      # Feature importance chart
│   ├── PerformanceCharts.tsx      # Performance visualization
│   ├── analytics.ts               # Analytics logic
│   └── AnalyticsLazy.tsx          # Lazy-loaded analytics
├── hooks/
│   ├── useMLModels.ts             # ML API hooks
│   ├── useTrainingProgress.ts     # Training websocket
│   └── useModelComparison.ts      # Comparison logic
├── pages/
│   ├── MLModelsPage.tsx           # Main page
│   ├── ModelDetailsPage.tsx       # Model details
│   └── TrainingPage.tsx           # Training interface
├── types/
│   └── models.ts                  # TypeScript types
└── utils/
    └── modelHelpers.ts            # Helper functions
```

### Component Hierarchy

```
MLModelsPage
├── PageHeader
│   ├── Title
│   ├── SearchBar (with ARIA)
│   └── ActionButtons
├── FilterPanel
│   ├── StatusFilter (with ARIA)
│   ├── TypeFilter (with ARIA)
│   └── SortControl
└── ModelRegistry
    ├── LoadingState (with announcements)
    ├── EmptyState (accessible)
    └── ModelList
        └── ModelCard (repeated)
            ├── ModelHeader
            │   ├── Name + Version
            │   ├── StatusBadge
            │   └── TypeBadge
            ├── ModelMetrics
            │   ├── AccuracyBadge
            │   ├── PerformanceStats
            │   └── FeatureCount
            ├── ModelInfo
            │   ├── CreatedDate
            │   ├── LastTrained
            │   └── Description
            └── ModelActions (with ARIA labels)
                ├── ViewDetailsButton
                ├── ActivateButton
                ├── ExportButton
                └── DeleteButton
```

---

## State Management

### React Query (Server State)

**Purpose**: Cache and synchronize server data

**Key Queries**:
```typescript
// Query all models
const { data: models, isLoading, error } = useMLModels();

// Query single model
const { data: model } = useMLModel(modelId);

// Query training progress
const { data: progress } = useTrainingProgress(trainingId);
```

**Key Mutations**:
```typescript
// Train new model
const trainMutation = useTrainModel({
  onSuccess: (data) => {
    queryClient.invalidateQueries(['ml-models']);
    navigate(`/ml-models/training/${data.id}`);
  },
});

// Delete model
const deleteMutation = useDeleteModel({
  onSuccess: () => {
    queryClient.invalidateQueries(['ml-models']);
    message.success('Model deleted');
  },
});

// Activate model
const activateMutation = useActivateModel({
  onMutate: async (modelId) => {
    // Optimistic update
    await queryClient.cancelQueries(['ml-models']);
    const previous = queryClient.getQueryData(['ml-models']);
    queryClient.setQueryData(['ml-models'], (old) => {
      // Update optimistically
    });
    return { previous };
  },
  onError: (err, variables, context) => {
    // Rollback on error
    queryClient.setQueryData(['ml-models'], context.previous);
  },
});
```

**Cache Configuration**:
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      cacheTime: 10 * 60 * 1000, // 10 minutes
      refetchOnWindowFocus: true,
      refetchOnMount: true,
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    },
  },
});
```

### Zustand (Client State)

**Purpose**: Manage UI state (filters, selections, etc.)

**Store Definition**:
```typescript
interface MLModelsStore {
  // Filters
  searchQuery: string;
  statusFilter: ModelStatus | 'all';
  typeFilter: ModelType | 'all';
  
  // Selections
  selectedModels: string[];
  
  // UI State
  isComparisonOpen: boolean;
  isTrainingFormOpen: boolean;
  
  // Actions
  setSearchQuery: (query: string) => void;
  setStatusFilter: (status: ModelStatus | 'all') => void;
  setTypeFilter: (type: ModelType | 'all') => void;
  toggleModelSelection: (modelId: string) => void;
  clearSelection: () => void;
  openComparison: () => void;
  closeComparison: () => void;
}

const useMLModelsStore = create<MLModelsStore>((set) => ({
  searchQuery: '',
  statusFilter: 'all',
  typeFilter: 'all',
  selectedModels: [],
  isComparisonOpen: false,
  isTrainingFormOpen: false,
  
  setSearchQuery: (query) => set({ searchQuery: query }),
  setStatusFilter: (status) => set({ statusFilter: status }),
  setTypeFilter: (type) => set({ typeFilter: type }),
  toggleModelSelection: (modelId) => set((state) => ({
    selectedModels: state.selectedModels.includes(modelId)
      ? state.selectedModels.filter(id => id !== modelId)
      : [...state.selectedModels, modelId],
  })),
  clearSelection: () => set({ selectedModels: [] }),
  openComparison: () => set({ isComparisonOpen: true }),
  closeComparison: () => set({ isComparisonOpen: false }),
}));
```

**Usage in Components**:
```typescript
function ModelRegistry() {
  const { searchQuery, statusFilter, setSearchQuery } = useMLModelsStore();
  const { data: models } = useMLModels();
  
  const filteredModels = useMemo(() => {
    return models?.filter(model => {
      const matchesSearch = model.name.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === 'all' || model.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [models, searchQuery, statusFilter]);
  
  return (
    <div>
      <Search value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
      {filteredModels?.map(model => <ModelCard key={model.id} model={model} />)}
    </div>
  );
}
```

### WebSocket State

**Purpose**: Real-time training progress updates

**Connection Management**:
```typescript
function useTrainingProgress(trainingId: string) {
  const [progress, setProgress] = useState<TrainingProgress>(null);
  const socketRef = useRef<Socket>();
  
  useEffect(() => {
    const socket = io('ws://localhost:8000/training', {
      query: { trainingId },
    });
    
    socket.on('progress', (data: TrainingProgress) => {
      setProgress(data);
      
      // Announce to screen readers
      if (data.epoch % 10 === 0) {
        announce(`Training progress: ${data.progress}%. Epoch ${data.epoch} of ${data.totalEpochs}`);
      }
    });
    
    socket.on('complete', (data) => {
      setProgress({ ...data, status: 'complete' });
      announce('Training complete');
      queryClient.invalidateQueries(['ml-models']);
    });
    
    socket.on('error', (error) => {
      setProgress(prev => ({ ...prev, status: 'failed', error }));
      announce(`Training failed: ${error.message}`);
    });
    
    socketRef.current = socket;
    
    return () => {
      socket.disconnect();
    };
  }, [trainingId]);
  
  return progress;
}
```

---

## API Integration

### API Client Setup

```typescript
// src/services/api.ts
import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor (add auth token)
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor (handle errors)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

### API Endpoints

**Model Management**:
```typescript
// GET /api/ml-models - List all models
export const getModels = () => 
  apiClient.get<ModelInfo[]>('/ml-models');

// GET /api/ml-models/:id - Get single model
export const getModel = (id: string) => 
  apiClient.get<ModelInfo>(`/ml-models/${id}`);

// POST /api/ml-models/train - Train new model
export const trainModel = (data: TrainingConfig) => 
  apiClient.post<{ trainingId: string }>('/ml-models/train', data);

// DELETE /api/ml-models/:id - Delete model
export const deleteModel = (id: string) => 
  apiClient.delete(`/ml-models/${id}`);

// PUT /api/ml-models/:id/activate - Activate model
export const activateModel = (id: string) => 
  apiClient.put(`/ml-models/${id}/activate`);

// GET /api/ml-models/:id/analytics - Get model analytics
export const getModelAnalytics = (id: string) => 
  apiClient.get<ModelAnalytics>(`/ml-models/${id}/analytics`);

// POST /api/ml-models/compare - Compare models
export const compareModels = (ids: string[]) => 
  apiClient.post<ComparisonResult>('/ml-models/compare', { ids });

// GET /api/ml-models/:id/export - Export model
export const exportModel = (id: string, format: 'pkl' | 'onnx' | 'tf') => 
  apiClient.get(`/ml-models/${id}/export`, {
    params: { format },
    responseType: 'blob',
  });
```

### Custom Hooks

```typescript
// useMLModels.ts
export function useMLModels() {
  return useQuery({
    queryKey: ['ml-models'],
    queryFn: async () => {
      const { data } = await getModels();
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useMLModel(id: string) {
  return useQuery({
    queryKey: ['ml-models', id],
    queryFn: async () => {
      const { data } = await getModel(id);
      return data;
    },
    enabled: !!id,
  });
}

export function useTrainModel() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: trainModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] });
    },
  });
}

export function useDeleteModel() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: deleteModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] });
    },
  });
}

export function useActivateModel() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: activateModel,
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['ml-models'] });
      const previous = queryClient.getQueryData(['ml-models']);
      
      queryClient.setQueryData<ModelInfo[]>(['ml-models'], (old) => {
        return old?.map(model => ({
          ...model,
          status: model.id === id ? 'active' : model.status,
        }));
      });
      
      return { previous };
    },
    onError: (err, variables, context) => {
      queryClient.setQueryData(['ml-models'], context?.previous);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] });
    },
  });
}
```

---

## Testing Strategy

### Unit Tests

**Component Tests** (`*.test.tsx`):
```typescript
describe('ModelRegistry', () => {
  it('should render model list', () => {
    render(<ModelRegistry />);
    expect(screen.getByText(/ML Model Registry/i)).toBeInTheDocument();
  });
  
  it('should filter models by search query', async () => {
    const user = userEvent.setup();
    render(<ModelRegistry />);
    
    const searchInput = screen.getByLabelText(/Search ML models/i);
    await user.type(searchInput, 'LSTM');
    
    await waitFor(() => {
      expect(screen.getByText('LSTM Predictor')).toBeInTheDocument();
      expect(screen.queryByText('Random Forest')).not.toBeInTheDocument();
    });
  });
  
  it('should be keyboard accessible', () => {
    render(<ModelRegistry />);
    
    const searchInput = screen.getByLabelText(/Search ML models/i);
    searchInput.focus();
    expect(document.activeElement).toBe(searchInput);
  });
});
```

**Hook Tests** (`*.test.ts`):
```typescript
describe('useMLModels', () => {
  it('should fetch models', async () => {
    const { result } = renderHook(() => useMLModels(), {
      wrapper: createWrapper(),
    });
    
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(3);
  });
  
  it('should handle errors', async () => {
    server.use(
      rest.get('/api/ml-models', (req, res, ctx) => {
        return res(ctx.status(500));
      })
    );
    
    const { result } = renderHook(() => useMLModels(), {
      wrapper: createWrapper(),
    });
    
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
```

### Integration Tests

**Workflow Tests**:
```typescript
describe('Training Workflow', () => {
  it('should complete full training flow', async () => {
    const user = userEvent.setup();
    render(<MLModelsPage />);
    
    // Open training form
    await user.click(screen.getByText(/Train New Model/i));
    
    // Fill form
    await user.type(screen.getByLabelText(/Model name/i), 'Test LSTM');
    await user.click(screen.getByLabelText(/Model type/i));
    await user.click(screen.getByText('LSTM'));
    
    // Submit
    await user.click(screen.getByRole('button', { name: /Start Training/i }));
    
    // Verify submission
    await waitFor(() => {
      expect(screen.getByText(/Training started/i)).toBeInTheDocument();
    });
    
    // Verify model appears in registry
    await waitFor(() => {
      expect(screen.getByText('Test LSTM')).toBeInTheDocument();
    });
  });
});
```

### Accessibility Tests

**Automated A11y Tests**:
```typescript
import { runAccessibilityAudit } from '@/utils/accessibilityTesting';

describe('ModelRegistry Accessibility', () => {
  it('should pass automated accessibility audit', async () => {
    const { container } = render(<ModelRegistry />);
    
    const results = await runAccessibilityAudit(container);
    
    expect(results.violations).toEqual([]);
    expect(results.passes.length).toBeGreaterThan(0);
  });
  
  it('should have proper ARIA labels', () => {
    render(<ModelRegistry />);
    
    expect(screen.getByLabelText(/Search ML models/i)).toHaveAttribute('aria-label');
    expect(screen.getByLabelText(/Filter models by status/i)).toHaveAttribute('aria-label');
  });
  
  it('should announce filter results', async () => {
    const mockAnnounce = vi.fn();
    vi.mocked(useAnnouncer).mockReturnValue(mockAnnounce);
    
    const user = userEvent.setup();
    render(<ModelRegistry />);
    
    await user.type(screen.getByLabelText(/Search/i), 'LSTM');
    
    await waitFor(() => {
      expect(mockAnnounce).toHaveBeenCalledWith(expect.stringContaining('Found 1 model'));
    });
  });
});
```

### Running Tests

```bash
# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test file
npm test ModelRegistry.test.tsx

# Run in watch mode
npm test -- --watch

# Run with UI
npm test -- --ui
```

**Coverage Targets**:
- Overall: >80%
- Components: >85%
- Hooks: >90%
- Utils: >95%

---

## Accessibility Implementation

### WCAG 2.1 AA Compliance

**Checklist**:
- ✅ 1.1.1 Non-text Content: All images have alt text
- ✅ 1.3.1 Info and Relationships: Semantic HTML, ARIA labels
- ✅ 1.4.3 Contrast (Minimum): 4.5:1 for text, 3:1 for UI
- ✅ 2.1.1 Keyboard: All functionality keyboard accessible
- ✅ 2.1.2 No Keyboard Trap: Focus can move freely
- ✅ 2.4.1 Bypass Blocks: Skip links provided
- ✅ 2.4.3 Focus Order: Logical tab order
- ✅ 2.4.7 Focus Visible: Clear focus indicators
- ✅ 3.3.1 Error Identification: Errors clearly identified
- ✅ 3.3.2 Labels or Instructions: All inputs labeled
- ✅ 4.1.2 Name, Role, Value: ARIA for custom controls

### Implementation Details

**Skip Links**:
```typescript
<SkipLinks>
  <a href="#main-content">Skip to main content</a>
  <a href="#main-navigation">Skip to navigation</a>
</SkipLinks>

<main id="main-content" tabIndex={-1}>
  {/* Main content */}
</main>
```

**ARIA Labels**:
```typescript
<Input
  aria-label="Search ML models by name, type, or version"
  aria-describedby="search-help"
  placeholder="Search models..."
/>
<span id="search-help" className="sr-only">
  Type to filter models in real-time
</span>
```

**Screen Reader Announcements**:
```typescript
function ModelRegistry() {
  const announce = useAnnouncer();
  
  useEffect(() => {
    if (filteredModels) {
      announce(`Found ${filteredModels.length} model${filteredModels.length !== 1 ? 's' : ''}`);
    }
  }, [filteredModels]);
}
```

**Keyboard Navigation**:
```typescript
function ModelCard({ model }: Props) {
  const handleKeyPress = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onViewDetails();
    }
  };
  
  return (
    <div
      role="article"
      tabIndex={0}
      onKeyPress={handleKeyPress}
      aria-label={`Model: ${model.name}`}
    >
      {/* Model content */}
    </div>
  );
}
```

### Testing Accessibility

**Manual Testing**:
1. Test with keyboard only (no mouse)
2. Test with screen reader (NVDA, JAWS, VoiceOver)
3. Test with high contrast mode
4. Test with reduced motion
5. Test at 200% zoom

**Automated Testing**:
```typescript
import { runAccessibilityAudit } from '@/utils/accessibilityTesting';

test('accessibility audit', async () => {
  const { container } = render(<ModelRegistry />);
  const results = await runAccessibilityAudit(container);
  
  // Check for violations
  expect(results.violations).toEqual([]);
  
  // Check contrast ratios
  const contrastIssues = results.passes.filter(p => p.id === 'color-contrast');
  expect(contrastIssues).toHaveLength(0);
  
  // Check keyboard access
  const keyboardIssues = results.violations.filter(v => v.id === 'keyboard');
  expect(keyboardIssues).toHaveLength(0);
});
```

---

## Performance Optimization

### Code Splitting

**Route-based Splitting**:
```typescript
const MLModelsPage = lazy(() => import('./pages/MLModelsPage'));
const ModelDetailsPage = lazy(() => import('./pages/ModelDetailsPage'));
const TrainingPage = lazy(() => import('./pages/TrainingPage'));

<Routes>
  <Route path="/ml-models" element={
    <Suspense fallback={<LoadingSpinner />}>
      <MLModelsPage />
    </Suspense>
  } />
</Routes>
```

**Component-based Splitting**:
```typescript
// analytics.tsx
const AnalyticsLazy = lazy(() => import('./AnalyticsLazy'));

export function Analytics() {
  return (
    <Suspense fallback={<Spin />}>
      <AnalyticsLazy />
    </Suspense>
  );
}
```

### Memoization

**Expensive Calculations**:
```typescript
const filteredModels = useMemo(() => {
  return models?.filter(model => {
    const matchesSearch = model.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || model.status === statusFilter;
    const matchesType = typeFilter === 'all' || model.type === typeFilter;
    return matchesSearch && matchesStatus && matchesType;
  });
}, [models, searchQuery, statusFilter, typeFilter]);
```

**Callbacks**:
```typescript
const handleDelete = useCallback((id: string) => {
  deleteMutation.mutate(id);
}, [deleteMutation]);

const handleActivate = useCallback((id: string) => {
  activateMutation.mutate(id);
}, [activateMutation]);
```

### Virtualization

**Large Lists**:
```typescript
import { FixedSizeList } from 'react-window';

function ModelList({ models }: Props) {
  return (
    <FixedSizeList
      height={600}
      itemCount={models.length}
      itemSize={200}
      width="100%"
    >
      {({ index, style }) => (
        <div style={style}>
          <ModelCard model={models[index]} />
        </div>
      )}
    </FixedSizeList>
  );
}
```

### Image Optimization

**Lazy Loading**:
```typescript
<img
  src={model.imageUrl}
  alt={model.name}
  loading="lazy"
  decoding="async"
/>
```

**Responsive Images**:
```typescript
<picture>
  <source srcSet={`${model.imageUrl}-800.webp`} type="image/webp" media="(min-width: 800px)" />
  <source srcSet={`${model.imageUrl}-400.webp`} type="image/webp" media="(min-width: 400px)" />
  <img src={`${model.imageUrl}.jpg`} alt={model.name} />
</picture>
```

### Bundle Optimization

**Vite Configuration**:
```typescript
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'ml-components': [
            './src/features/ml-models/components/ModelRegistry.tsx',
            './src/features/ml-models/components/TrainingForm.tsx',
          ],
          'ml-hooks': [
            './src/features/ml-models/hooks/useMLModels.ts',
          ],
          'charts': [
            'chart.js',
            'react-chartjs-2',
            'recharts',
          ],
        },
      },
    },
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
  },
});
```

---

## Extending the Feature

### Adding a New Model Type

1. **Update Types**:
```typescript
// types/models.ts
export type ModelType = 
  | 'lstm'
  | 'random_forest'
  | 'xgboost'
  | 'transformer'
  | 'your_new_type'; // Add here
```

2. **Update Training Form**:
```typescript
// components/TrainingForm.tsx
const MODEL_TYPES = [
  { value: 'lstm', label: 'LSTM' },
  { value: 'random_forest', label: 'Random Forest' },
  { value: 'xgboost', label: 'XGBoost' },
  { value: 'transformer', label: 'Transformer' },
  { value: 'your_new_type', label: 'Your New Type' }, // Add here
];
```

3. **Update Backend**:
```python
# backend/ml/model_types.py
class YourNewTypeModel:
    def __init__(self, config):
        # Initialize model
        pass
    
    def train(self, X, y):
        # Training logic
        pass
    
    def predict(self, X):
        # Prediction logic
        pass
```

4. **Update Icon/Badge**:
```typescript
// components/ModelCard.tsx
function getModelIcon(type: ModelType) {
  switch (type) {
    case 'lstm': return <ThunderboltOutlined />;
    case 'random_forest': return <BranchesOutlined />;
    case 'your_new_type': return <YourNewIcon />; // Add here
    default: return <QuestionOutlined />;
  }
}
```

### Adding a New Analytics Chart

1. **Create Chart Component**:
```typescript
// components/YourNewChart.tsx
export function YourNewChart({ data }: Props) {
  return (
    <Line
      data={{
        labels: data.labels,
        datasets: [
          {
            label: 'Your Metric',
            data: data.values,
            borderColor: 'rgb(75, 192, 192)',
          },
        ],
      }}
      options={{
        responsive: true,
        plugins: {
          legend: { position: 'top' },
          title: { display: true, text: 'Your New Chart' },
        },
      }}
    />
  );
}
```

2. **Add to Analytics Page**:
```typescript
// components/analytics.tsx
export function Analytics() {
  return (
    <div>
      <FeatureImportance data={featureData} />
      <PerformanceCharts data={perfData} />
      <YourNewChart data={yourData} /> {/* Add here */}
    </div>
  );
}
```

3. **Add API Endpoint**:
```typescript
// services/api.ts
export const getYourNewChartData = (modelId: string) => 
  apiClient.get<YourChartData>(`/ml-models/${modelId}/your-chart-data`);
```

4. **Create Hook**:
```typescript
// hooks/useMLModels.ts
export function useYourNewChartData(modelId: string) {
  return useQuery({
    queryKey: ['ml-models', modelId, 'your-chart-data'],
    queryFn: async () => {
      const { data } = await getYourNewChartData(modelId);
      return data;
    },
    enabled: !!modelId,
  });
}
```

### Adding a New Filter

1. **Update Store**:
```typescript
// store or state
interface MLModelsStore {
  yourNewFilter: string;
  setYourNewFilter: (value: string) => void;
}
```

2. **Add Filter UI**:
```typescript
// components/FilterPanel.tsx
<Select
  value={yourNewFilter}
  onChange={setYourNewFilter}
  aria-label="Filter by your criteria"
>
  <Option value="all">All</Option>
  <Option value="option1">Option 1</Option>
</Select>
```

3. **Update Filtering Logic**:
```typescript
const filteredModels = useMemo(() => {
  return models?.filter(model => {
    const matchesYourFilter = yourNewFilter === 'all' || model.yourProperty === yourNewFilter;
    return matchesYourFilter && /* other filters */;
  });
}, [models, yourNewFilter]);
```

---

## Troubleshooting

### Common Development Issues

**TypeScript Errors**:
```
Problem: Type errors with model properties
Solution: Check types/models.ts, ensure API response matches types
```

**React Query Not Refetching**:
```
Problem: Data doesn't update after mutation
Solution: Call queryClient.invalidateQueries(['ml-models']) after mutation
```

**WebSocket Disconnects**:
```
Problem: Training progress stops updating
Solution: Implement reconnection logic with exponential backoff
```

**Performance Issues**:
```
Problem: Slow rendering with many models
Solution: Use virtualization (react-window), memoization, pagination
```

**Accessibility Violations**:
```
Problem: Failing WCAG checks
Solution: Run automated audit, fix violations one by one
Tools: axe DevTools, WAVE, Lighthouse
```

---

## Best Practices

### Component Design

1. **Single Responsibility**: One component, one purpose
2. **Composition Over Inheritance**: Compose small components
3. **Props Interface**: Clear, typed props
4. **Error Boundaries**: Wrap with error boundaries
5. **Loading States**: Handle loading, error, empty states

### State Management

1. **Server State in React Query**: Don't duplicate in Zustand
2. **UI State in Zustand**: Filters, selections, modal state
3. **Local State for Ephemeral**: Use useState for component-only state
4. **Optimistic Updates**: For better UX (with rollback)

### Performance

1. **Memoize Expensive Calculations**: useMemo, useCallback
2. **Code Split**: Route-based and component-based
3. **Virtualize Large Lists**: react-window for >100 items
4. **Debounce Search**: 300ms delay
5. **Lazy Load Images**: loading="lazy"

### Accessibility

1. **Semantic HTML**: Use proper HTML elements
2. **ARIA When Needed**: Don't overuse, HTML first
3. **Keyboard Navigation**: Test without mouse
4. **Screen Reader Testing**: Test with actual screen readers
5. **Focus Management**: Clear focus indicators, logical order

### Testing

1. **Test Behavior, Not Implementation**: Test what user sees
2. **Integration Over Unit**: Test real scenarios
3. **Accessibility Tests**: Automated + manual
4. **Mock External Dependencies**: API, WebSocket, etc.
5. **Test Edge Cases**: Empty states, errors, loading

---

**Document Version:** 1.0.0  
**Last Updated:** October 15, 2024  
**Maintainers:** AlgoTrading Platform Team  
**License:** Proprietary - All Rights Reserved
