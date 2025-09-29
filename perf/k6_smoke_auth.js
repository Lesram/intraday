/**
 * K6 Smoke Test with Authentication
 * 
 * This script tests the core trading platform API endpoints with authentication.
 * Tests the complete flow from login to order placement and status checking.
 * 
 * Usage:
 *   k6 run k6_smoke_auth.js
 *   k6 run --vus 10 --duration 30s k6_smoke_auth.js
 * 
 * Environment Variables:
 *   BASE_URL - API base URL (default: http://localhost:8000)
 *   API_TOKEN - Predefined API token (overrides login flow)
 *   TARGET_SYMBOL - Symbol to test with (default: AAPL)
 */

import http from 'k6/http';
import { check, sleep, fail } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const authSuccessRate = new Rate('auth_success_rate');
const signalLatency = new Trend('signal_latency');
const orderLatency = new Trend('order_latency');
const orderSuccessRate = new Rate('order_success_rate');
const apiErrors = new Counter('api_errors');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_TOKEN = __ENV.API_TOKEN || '6Av--QEcw6s7O0U7i4nxbNqwSUtL3PfNzC07BIOIzFI'; // From seeding
const TARGET_SYMBOL = __ENV.TARGET_SYMBOL || 'AAPL';

// Test configuration
export const options = {
  stages: [
    { duration: '10s', target: 1 },   // Warm up with 1 user
    { duration: '20s', target: 5 },   // Scale up to 5 users
    { duration: '30s', target: 10 },  // Scale up to 10 users  
    { duration: '20s', target: 5 },   // Scale down
    { duration: '10s', target: 0 },   // Cool down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<2000'],     // 95% of requests under 2s
    'http_req_failed': ['rate<0.05'],        // Less than 5% failures
    'auth_success_rate': ['rate>=0.95'],     // 95% auth success
    'order_success_rate': ['rate>=0.90'],    // 90% order success
    'signal_latency': ['p(95)<1000'],        // Signal requests under 1s
    'order_latency': ['p(95)<3000'],         // Order requests under 3s
  },
};

/**
 * Setup function - runs once per VU
 */
export function setup() {
  console.log(`Starting K6 smoke test against ${BASE_URL}`);
  console.log(`Testing with symbol: ${TARGET_SYMBOL}`);
  
  // Health check
  const healthResponse = http.get(`${BASE_URL}/health`);
  if (!check(healthResponse, { 'health check passed': (r) => r.status === 200 })) {
    fail('Health check failed - API may be down');
  }
  
  return {
    baseUrl: BASE_URL,
    symbol: TARGET_SYMBOL,
  };
}

/**
 * Main test function
 */
export default function(data) {
  let authToken = API_TOKEN;
  
  // Step 1: Authentication (if no token provided)
  if (!API_TOKEN) {
    authToken = authenticateUser(data.baseUrl);
    if (!authToken) {
      apiErrors.add(1);
      return; // Skip test if auth failed
    }
  }
  
  // Step 2: Get trading signals
  const signals = getSignals(data.baseUrl, data.symbol, authToken);
  if (!signals) {
    apiErrors.add(1);
    return;
  }
  
  // Step 3: Place order based on signal (small quantity)
  const orderId = placeOrder(data.baseUrl, data.symbol, authToken);
  if (!orderId) {
    apiErrors.add(1);
    return;
  }
  
  // Step 4: Monitor order status until not "submitted"
  const finalStatus = waitForOrderCompletion(data.baseUrl, orderId, authToken);
  
  // Verify final status
  check(finalStatus, {
    'order completed successfully': (status) => 
      status && status !== 'submitted' && status !== 'failed'
  });
  
  // Brief pause between iterations
  sleep(1);
}

/**
 * Authenticate user and return token
 */
function authenticateUser(baseUrl) {
  const loginPayload = {
    username: 'admin@staging.local',
    password: 'admin123',
  };
  
  const params = {
    headers: { 'Content-Type': 'application/json' },
  };
  
  const response = http.post(`${baseUrl}/auth/login`, JSON.stringify(loginPayload), params);
  
  const success = check(response, {
    'login successful': (r) => r.status === 200,
    'login response has token': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.access_token !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  authSuccessRate.add(success);
  
  if (success) {
    const body = JSON.parse(response.body);
    return body.access_token;
  }
  
  console.error(`Login failed: ${response.status} ${response.body}`);
  return null;
}

/**
 * Get trading signals for symbol
 */
function getSignals(baseUrl, symbol, token) {
  const params = {
    headers: { 'Authorization': `Bearer ${token}` },
  };
  
  const startTime = Date.now();
  const response = http.get(`${baseUrl}/api/v1/signals?symbol=${symbol}`, params);
  const latency = Date.now() - startTime;
  
  signalLatency.add(latency);
  
  const success = check(response, {
    'signals request successful': (r) => r.status === 200,
    'signals response is JSON': (r) => {
      try {
        JSON.parse(r.body);
        return true;
      } catch (e) {
        return false;
      }
    },
  });
  
  if (success) {
    try {
      return JSON.parse(response.body);
    } catch (e) {
      console.error('Failed to parse signals response');
      return null;
    }
  }
  
  console.error(`Signals request failed: ${response.status} ${response.body}`);
  return null;
}

/**
 * Place a small test order
 */
function placeOrder(baseUrl, symbol, token) {
  const orderPayload = {
    symbol: symbol,
    side: 'buy',
    qty: 1,  // Small quantity for testing
    order_type: 'market',
    tif: 'gtc',
    client_order_id: `k6_test_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  };
  
  const params = {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  };
  
  const startTime = Date.now();
  const response = http.post(`${baseUrl}/api/v1/signals/act`, JSON.stringify(orderPayload), params);
  const latency = Date.now() - startTime;
  
  orderLatency.add(latency);
  
  const success = check(response, {
    'order placement successful': (r) => r.status === 200 || r.status === 201,
    'order response has id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.id !== undefined || body.order_id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });
  
  orderSuccessRate.add(success);
  
  if (success) {
    try {
      const body = JSON.parse(response.body);
      return body.id || body.order_id;
    } catch (e) {
      console.error('Failed to parse order response');
      return null;
    }
  }
  
  console.error(`Order placement failed: ${response.status} ${response.body}`);
  return null;
}

/**
 * Wait for order completion (status != "submitted")
 */
function waitForOrderCompletion(baseUrl, orderId, token, maxWait = 30) {
  const params = {
    headers: { 'Authorization': `Bearer ${token}` },
  };
  
  let status = 'submitted';
  let attempts = 0;
  const maxAttempts = maxWait; // 1 second intervals
  
  while (status === 'submitted' && attempts < maxAttempts) {
    const response = http.get(`${baseUrl}/api/v1/orders/${orderId}`, params);
    
    if (check(response, { 'order status check successful': (r) => r.status === 200 })) {
      try {
        const body = JSON.parse(response.body);
        status = body.status;
        
        if (status !== 'submitted') {
          console.log(`Order ${orderId} completed with status: ${status}`);
          return status;
        }
      } catch (e) {
        console.error(`Failed to parse order status response: ${e}`);
        break;
      }
    } else {
      console.error(`Order status check failed: ${response.status} ${response.body}`);
      break;
    }
    
    sleep(1); // Wait 1 second before next check
    attempts++;
  }
  
  if (attempts >= maxAttempts) {
    console.warn(`Order ${orderId} still in submitted status after ${maxWait}s`);
  }
  
  return status;
}

/**
 * Teardown function - runs once at end
 */
export function teardown(data) {
  console.log('K6 smoke test completed');
  
  // Could add cleanup logic here if needed
  // e.g., cancel any pending orders, cleanup test data
}

/**
 * Handle summary - custom summary output
 */
export function handleSummary(data) {
  const summary = {
    'Test Summary': {
      'Total Requests': data.metrics.http_reqs.values.count,
      'Request Failures': `${data.metrics.http_req_failed.values.rate * 100}%`,
      'P95 Response Time': `${data.metrics.http_req_duration.values['p(95)']}ms`,
      'Authentication Success': `${data.metrics.auth_success_rate?.values.rate * 100 || 0}%`,
      'Order Success Rate': `${data.metrics.order_success_rate?.values.rate * 100 || 0}%`,
      'API Errors': data.metrics.api_errors?.values.count || 0,
    }
  };
  
  console.log('\n=== K6 Smoke Test Results ===');
  Object.entries(summary['Test Summary']).forEach(([key, value]) => {
    console.log(`${key}: ${value}`);
  });
  
  return {
    'stdout': JSON.stringify(summary, null, 2),
    'summary.json': JSON.stringify(data, null, 2),
  };
}