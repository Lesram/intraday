# Trading Platform API Client

A TypeScript client library for the Trading Platform API, providing strongly typed interfaces and convenient methods for all API operations.

## Installation

```bash
# If published to npm
npm install @trading-platform/api-client

# Or copy the api.ts file directly into your project
cp clients/js/api.ts src/lib/trading-api.ts
```

## Quick Start

```typescript
import { TradingApiClient, createTradingApiClient } from '@trading-platform/api-client';

// Create client instance
const client = new TradingApiClient('http://localhost:8000');

// Or use the convenience function
const client = createTradingApiClient(
  'http://localhost:8000',
  'your-jwt-token'  // Optional: set token immediately
);

// Set authentication token
client.setAuthToken('your-jwt-token');

// Make API calls
try {
  const signals = await client.getSignals('AAPL');
  console.log('Signals for AAPL:', signals);
} catch (error) {
  console.error('API Error:', error);
}
```

## API Methods

### Authentication

```typescript
// Set JWT token for authenticated requests
client.setAuthToken('your-jwt-token');

// Clear token
client.clearAuthToken();

// Get current token
const token = client.getAuthToken();
```

### Trading Signals

```typescript
// Get signals for a symbol
const signals = await client.getSignals('AAPL', {
  page: 1,
  limit: 10,
  strategy: 'momentum_v1',
  signal_type: 'buy'
});

// Get a specific signal
const signal = await client.getSignal('signal-id-123');

// Act on a signal (place order based on signal)
const order = await client.actOnSignal({
  symbol: 'AAPL',
  side: 'buy',
  qty: 100,
  order_type: 'market',
  tif: 'gtc',
  signal_id: 'signal-id-123'
});
```

### Orders

```typescript
// Create an order directly
const order = await client.createOrder({
  symbol: 'AAPL',
  side: 'buy',
  qty: 100,
  order_type: 'market',
  tif: 'gtc',
  client_order_id: 'my-order-123'
});

// Get an order by ID
const order = await client.getOrder('order-id-456');

// Get all orders with filtering
const orders = await client.getOrders({
  symbol: 'AAPL',
  status: 'filled',
  page: 1,
  limit: 20
});

// Cancel an order
const cancelledOrder = await client.cancelOrder('order-id-456');
```

### Positions

```typescript
// Get all positions
const positions = await client.getPositions();

// Get a specific position
const position = await client.getPosition('AAPL');
```

### Health & Diagnostics

```typescript
// Health check
const health = await client.healthCheck();

// Get OpenAPI specification
const apiSpec = await client.getOpenApiSpec();
```

## Error Handling

The client provides typed error handling:

```typescript
import { isApiError } from '@trading-platform/api-client';

try {
  const order = await client.createOrder(orderData);
} catch (error) {
  if (isApiError(error)) {
    console.error(`API Error ${error.status}: ${error.message}`);
    console.error('Details:', error.details);
  } else {
    console.error('Unexpected error:', error);
  }
}
```

## Configuration Options

```typescript
const client = new TradingApiClient('http://localhost:8000', {
  timeout: 30000,  // Request timeout in milliseconds
  defaultHeaders: {
    'X-Client-Version': '1.0.0'
  }
});
```

## TypeScript Types

The client includes comprehensive TypeScript types:

```typescript
import type {
  Signal,
  Order,
  Position,
  ActOnSignalRequest,
  CreateOrderRequest,
  ApiError
} from '@trading-platform/api-client';

// All API responses are strongly typed
const signals: Signal[] = await client.getSignals('AAPL');
const order: Order = await client.createOrder(request);
```

## React Integration Example

```typescript
import React, { useEffect, useState } from 'react';
import { TradingApiClient, Signal } from '@trading-platform/api-client';

const client = new TradingApiClient(process.env.REACT_APP_API_URL!);

function SignalsList() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    async function fetchSignals() {
      try {
        // Get auth token from your auth provider
        const token = await getAuthToken();
        client.setAuthToken(token);
        
        const response = await client.getSignals('AAPL');
        setSignals(response.signals);
      } catch (error) {
        console.error('Failed to fetch signals:', error);
      } finally {
        setLoading(false);
      }
    }
    
    fetchSignals();
  }, []);
  
  if (loading) return <div>Loading...</div>;
  
  return (
    <div>
      {signals.map(signal => (
        <div key={signal.id}>
          <h3>{signal.symbol} - {signal.signal_type}</h3>
          <p>Confidence: {signal.confidence}</p>
          <p>Strength: {signal.strength}</p>
        </div>
      ))}
    </div>
  );
}
```

## Vue 3 Integration Example

```typescript
import { ref, onMounted } from 'vue';
import { TradingApiClient } from '@trading-platform/api-client';

export function useSignals(symbol: string) {
  const client = new TradingApiClient(import.meta.env.VITE_API_URL);
  const signals = ref([]);
  const loading = ref(true);
  const error = ref(null);
  
  onMounted(async () => {
    try {
      const token = await getAuthToken();
      client.setAuthToken(token);
      
      const response = await client.getSignals(symbol);
      signals.value = response.signals;
    } catch (err) {
      error.value = err;
    } finally {
      loading.value = false;
    }
  });
  
  return { signals, loading, error };
}
```

## CORS Configuration

The backend is pre-configured with comprehensive CORS support for UI development:

**Supported Origins:**
- `http://localhost:3000` (React Create App default)
- `http://localhost:5173` (Vite default) 
- `https://localhost:3000` (HTTPS development)
- Your staging and production domains

**Supported Methods:** GET, POST, PUT, DELETE, OPTIONS  
**Supported Headers:** Authorization, Content-Type, Accept, X-Requested-With

No additional CORS configuration needed for standard frontend frameworks.

## Development

```bash
# Build the client
npm run build

# Watch for changes during development
npm run build:watch

# Clean build artifacts
npm run clean
```

## License

MIT