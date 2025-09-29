/**
 * K6 Authorized Smoke Test for Phase G Gate Validation
 * 
 * Tests concurrent load on authenticated endpoints to verify performance
 * under realistic user scenarios.
 * 
 * Thresholds:
 * - health < 100ms p95
 * - signals < 300ms p95  
 * - positions < 300ms p95
 * 
 * Usage: k6 run perf/k6_auth_smoke.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const authFailureRate = new Rate('auth_failures');
const endpointErrors = new Rate('endpoint_errors');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 2 },  // Ramp up
    { duration: '1m', target: 5 },   // Stay at 5 VUs
    { duration: '30s', target: 0 },  // Ramp down
  ],
  thresholds: {
    // HTTP request duration thresholds
    'http_req_duration{name:health}': ['p(95)<100'],      // health < 100ms p95
    'http_req_duration{name:signals}': ['p(95)<300'],     // signals < 300ms p95
    'http_req_duration{name:positions}': ['p(95)<300'],   // positions < 300ms p95
    
    // Success rate thresholds
    'http_req_failed': ['rate<0.1'],          // Less than 10% failures
    'auth_failures': ['rate<0.05'],           // Less than 5% auth failures
    'endpoint_errors': ['rate<0.05'],         // Less than 5% endpoint errors
    
    // Response time targets
    'http_req_duration': ['p(95)<500'],       // Overall 95th percentile < 500ms
    'http_req_duration': ['avg<100'],         // Average response time < 100ms
  },
};

// Base configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const USERNAME = __ENV.USERNAME || 'admin';
const PASSWORD = __ENV.PASSWORD || 'admin123';
const STAGING_API_KEY = __ENV.STAGING_API_KEY;

// Global auth token (obtained in setup)
let authToken = '';

/**
 * Setup phase - runs once before all VUs
 * Obtains authentication token for use in test scenarios
 */
export function setup() {
  console.log(`🚀 Starting K6 smoke test against ${BASE_URL}`);
  
  // Try STAGING_API_KEY first if available
  if (STAGING_API_KEY) {
    console.log('✅ Using STAGING_API_KEY for authentication');
    return { authToken: STAGING_API_KEY, authType: 'api-key' };
  }
  
  // Otherwise, get JWT token via login
  console.log('🔐 Obtaining JWT token via login...');
  
  // Use form data format as expected by the backend
  const loginPayload = `username=${USERNAME}&password=${PASSWORD}`;
  
  const loginResponse = http.post(
    `${BASE_URL}/auth/login`,
    loginPayload,
    {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      tags: { name: 'login' },
    }
  );
  
  console.log(`Login response status: ${loginResponse.status}`);
  console.log(`Login response body: ${loginResponse.body}`);
  
  const loginSuccess = check(loginResponse, {
    'login successful': (r) => r.status === 200,
    'login returns token': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.access_token && body.access_token.length > 0;
      } catch (e) {
        console.log(`❌ Token parsing error: ${e.message}`);
        return false;
      }
    },
  });
  
  if (!loginSuccess) {
    console.error(`❌ Login failed: ${loginResponse.status} ${loginResponse.body}`);
    console.error(`❌ Request URL: ${BASE_URL}/auth/login`);
    console.error(`❌ Request payload: ${loginPayload}`);
    return { authToken: null, authType: null };
  }
  
  const loginData = JSON.parse(loginResponse.body);
  console.log(`✅ JWT token obtained successfully`);
  
  return { 
    authToken: loginData.access_token, 
    authType: 'jwt',
    loginTime: loginResponse.timings.duration 
  };
}

/**
 * Main test scenario - runs for each VU iteration
 */
export default function (data) {
  if (!data.authToken) {
    console.error('❌ No auth token available, skipping iteration');
    authFailureRate.add(1);
    return;
  }
  
  // Prepare authorization header
  const authHeaders = data.authType === 'api-key' 
    ? { 'X-API-Key': data.authToken }
    : { 'Authorization': `Bearer ${data.authToken}` };
  
  // Test 1: Health endpoint (unauthenticated)
  const healthResponse = http.get(`${BASE_URL}/health`, {
    tags: { name: 'health' },
  });
  
  const healthOk = check(healthResponse, {
    'health status 200': (r) => r.status === 200,
    'health response time < 100ms': (r) => r.timings.duration < 100,
    'health returns json': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.status === 'ok';
      } catch (e) {
        return false;
      }
    },
  });
  
  if (!healthOk) {
    endpointErrors.add(1);
  }
  
  // Small delay between requests
  sleep(0.1);
  
  // Test 2: Signals endpoint (authenticated)
  const signalsResponse = http.get(
    `${BASE_URL}/api/v1/signals?symbol=AAPL`, 
    {
      headers: authHeaders,
      tags: { name: 'signals' },
    }
  );
  
  const signalsOk = check(signalsResponse, {
    'signals status 200': (r) => r.status === 200,
    'signals response time < 300ms': (r) => r.timings.duration < 300,
    'signals auth working': (r) => r.status !== 401,
  });
  
  if (!signalsOk) {
    endpointErrors.add(1);
    if (signalsResponse.status === 401) {
      authFailureRate.add(1);
    }
  }
  
  // Small delay between requests
  sleep(0.1);
  
  // Test 3: Positions endpoint (authenticated)
  const positionsResponse = http.get(
    `${BASE_URL}/api/v1/positions`, 
    {
      headers: authHeaders,
      tags: { name: 'positions' },
    }
  );
  
  const positionsOk = check(positionsResponse, {
    'positions status 200': (r) => r.status === 200,
    'positions response time < 300ms': (r) => r.timings.duration < 300,
    'positions auth working': (r) => r.status !== 401,
    'positions returns array': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body);
      } catch (e) {
        return false;
      }
    },
  });
  
  if (!positionsOk) {
    endpointErrors.add(1);
    if (positionsResponse.status === 401) {
      authFailureRate.add(1);
    }
  }
  
  // Sleep between iterations to simulate realistic user behavior
  sleep(1);
}

/**
 * Teardown phase - runs once after all VUs complete
 */
export function teardown(data) {
  console.log('🏁 K6 smoke test completed');
  
  if (data.authType === 'jwt' && data.loginTime) {
    console.log(`📊 Login performance: ${data.loginTime.toFixed(2)}ms`);
  }
  
  console.log('📈 Check K6 output above for detailed performance metrics');
}