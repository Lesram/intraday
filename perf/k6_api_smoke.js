// k6 Performance Test for Algorithmic Trading Platform API
// Tests critical API endpoints under load with realistic trading scenarios

import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Custom metrics for trading-specific measurements
const tradingOrderLatency = new Trend('trading_order_latency');
const tradingRiskDecisions = new Counter('trading_risk_decisions');
const tradingErrorRate = new Rate('trading_error_rate');
const websocketConnectionErrors = new Counter('websocket_connection_errors');

// Test configuration
export const options = {
  scenarios: {
    // API load test - simulates normal trading activity
    api_load: {
      executor: 'ramping-vus',
      startVUs: 5,
      stages: [
        { duration: '2m', target: 20 },   // Ramp up
        { duration: '5m', target: 50 },   // Stay at 50 users
        { duration: '2m', target: 100 },  // Ramp to peak
        { duration: '3m', target: 100 },  // Peak load
        { duration: '2m', target: 0 },    // Ramp down
      ],
      exec: 'apiLoadTest',
    },
    
    // WebSocket stress test - tests real-time data handling
    websocket_stress: {
      executor: 'constant-vus',
      vus: 20,
      duration: '5m',
      exec: 'websocketStressTest',
    },
    
    // Risk engine specific test - high-frequency risk decisions
    risk_engine_spike: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 100,
      stages: [
        { duration: '1m', target: 50 },   // Ramp up to 50 RPS
        { duration: '3m', target: 200 },  // Spike to 200 RPS
        { duration: '1m', target: 50 },   // Back down
      ],
      exec: 'riskEngineTest',
    },
  },
  
  // SLA thresholds - fail the test if not met
  thresholds: {
    http_req_duration: ['p(95)<2000', 'p(99)<5000'],  // 95% < 2s, 99% < 5s
    http_req_failed: ['rate<0.05'],                    // Error rate < 5%
    trading_order_latency: ['p(95)<1000'],             // Trading orders < 1s p95
    trading_error_rate: ['rate<0.02'],                 // Trading errors < 2%
    websocket_connection_errors: ['count<10'],         // < 10 WebSocket errors total
  },
};

// Base URL - can be overridden by environment variable
const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';
const WS_URL = __ENV.WS_URL || 'ws://localhost:8000';

// Test data
const TEST_SYMBOLS = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'];
const ORDER_TYPES = ['market', 'limit'];
const ORDER_SIDES = ['buy', 'sell'];

// Helper function to get random element
function randomChoice(array) {
  return array[Math.floor(Math.random() * array.length)];
}

// Helper function to generate test order
function generateTestOrder() {
  return {
    symbol: randomChoice(TEST_SYMBOLS),
    quantity: Math.floor(Math.random() * 100) + 1,
    side: randomChoice(ORDER_SIDES),
    type: randomChoice(ORDER_TYPES),
    price: Math.random() * 1000 + 50, // Random price between 50-1050
  };
}

// Test authentication token (mock)
let authToken = null;

export function setup() {
  console.log('Setting up performance test...');
  
  // Mock authentication for testing
  const loginResponse = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    username: 'test-trader',
    password: 'test-password-123'
  }), {
    headers: { 'Content-Type': 'application/json' },
  });
  
  if (loginResponse.status === 200) {
    authToken = JSON.parse(loginResponse.body).access_token;
    console.log('Authentication successful');
  }
  
  return { authToken };
}

// API Load Test - Normal trading operations
export function apiLoadTest(data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.authToken}`,
  };

  // Health check
  let response = http.get(`${BASE_URL}/health`);
  check(response, {
    'health check status is 200': (r) => r.status === 200,
    'health check response time < 500ms': (r) => r.timings.duration < 500,
  });

  // Get account info
  response = http.get(`${BASE_URL}/api/v1/account`, { headers });
  check(response, {
    'account info status is 200': (r) => r.status === 200,
    'account response time < 1s': (r) => r.timings.duration < 1000,
  });

  // Get market data for a random symbol
  const symbol = randomChoice(TEST_SYMBOLS);
  response = http.get(`${BASE_URL}/api/v1/market/quote/${symbol}`, { headers });
  check(response, {
    'market data status is 200': (r) => r.status === 200,
    'market data response time < 500ms': (r) => r.timings.duration < 500,
  });

  // Submit a test order
  const order = generateTestOrder();
  response = http.post(`${BASE_URL}/api/v1/orders`, JSON.stringify(order), { headers });
  
  const orderSuccess = check(response, {
    'order submission status is 200 or 201': (r) => r.status === 200 || r.status === 201,
    'order response time < 2s': (r) => r.timings.duration < 2000,
  });

  // Track trading-specific metrics
  tradingOrderLatency.add(response.timings.duration);
  tradingErrorRate.add(!orderSuccess);

  // Get order history
  response = http.get(`${BASE_URL}/api/v1/orders`, { headers });
  check(response, {
    'order history status is 200': (r) => r.status === 200,
    'order history response time < 1s': (r) => r.timings.duration < 1000,
  });

  // Check portfolio positions
  response = http.get(`${BASE_URL}/api/v1/portfolio/positions`, { headers });
  check(response, {
    'portfolio status is 200': (r) => r.status === 200,
    'portfolio response time < 1s': (r) => r.timings.duration < 1000,
  });

  sleep(Math.random() * 3 + 1); // Random sleep 1-4 seconds
}

// WebSocket Stress Test - Real-time data connections
export function websocketStressTest(data) {
  const url = `${WS_URL}/ws/market-data`;
  const params = {
    headers: {
      'Authorization': `Bearer ${data.authToken}`,
    },
  };

  let messageCount = 0;
  let errorCount = 0;

  const response = ws.connect(url, params, function(socket) {
    socket.on('open', function() {
      console.log('WebSocket connected');
      
      // Subscribe to market data for multiple symbols
      TEST_SYMBOLS.forEach(symbol => {
        socket.send(JSON.stringify({
          action: 'subscribe',
          channel: 'quotes',
          symbol: symbol
        }));
      });
    });

    socket.on('message', function(data) {
      messageCount++;
      
      const message = JSON.parse(data);
      check(message, {
        'websocket message has required fields': (m) => m.symbol && m.price,
        'websocket price is numeric': (m) => typeof m.price === 'number',
      });
    });

    socket.on('error', function(error) {
      console.log('WebSocket error:', error);
      errorCount++;
      websocketConnectionErrors.add(1);
    });

    socket.on('close', function() {
      console.log(`WebSocket closed. Messages received: ${messageCount}, Errors: ${errorCount}`);
    });

    // Keep connection alive for test duration
    socket.setTimeout(function() {
      console.log('Closing WebSocket connection after timeout');
      socket.close();
    }, 60000); // 1 minute per connection

    // Send periodic heartbeat
    socket.setInterval(function() {
      socket.send(JSON.stringify({ action: 'ping' }));
    }, 10000); // Every 10 seconds
  });

  check(response, {
    'websocket connection established': (r) => r && r.status === 101,
  });
}

// Risk Engine Test - High-frequency risk decisions
export function riskEngineTest(data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.authToken}`,
  };

  // Generate a high-risk order to test risk engine
  const riskOrder = {
    symbol: randomChoice(TEST_SYMBOLS),
    quantity: Math.floor(Math.random() * 10000) + 1000, // Large quantity
    side: randomChoice(ORDER_SIDES),
    type: 'market',
    risk_override: false, // Force risk evaluation
  };

  const startTime = Date.now();
  
  const response = http.post(`${BASE_URL}/api/v1/orders/validate`, JSON.stringify(riskOrder), { headers });
  
  const riskDecisionTime = Date.now() - startTime;
  
  const riskCheck = check(response, {
    'risk validation responds': (r) => r.status === 200 || r.status === 400,
    'risk validation time < 500ms': (r) => r.timings.duration < 500,
    'risk response has decision': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.risk_status !== undefined;
      } catch {
        return false;
      }
    },
  });

  tradingRiskDecisions.add(1);
  
  // If risk validation passed, try to submit the order
  if (response.status === 200) {
    const orderResponse = http.post(`${BASE_URL}/api/v1/orders`, JSON.stringify(riskOrder), { headers });
    
    check(orderResponse, {
      'high-risk order processed': (r) => r.status === 200 || r.status === 201 || r.status === 400,
      'order processing time < 1s': (r) => r.timings.duration < 1000,
    });
  }

  // Short sleep to allow for high-frequency testing
  sleep(0.1);
}

// Teardown function
export function teardown(data) {
  console.log('Performance test completed');
  console.log(`Auth token used: ${data.authToken ? 'Yes' : 'No'}`);
}

// Default function for simple load testing
export default function(data) {
  apiLoadTest(data);
}
