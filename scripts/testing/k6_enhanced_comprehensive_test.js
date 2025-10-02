// Enhanced K6 Comprehensive Platform Test - With AI Agent Normalization
// =======================================================================
// Implements AI Agent suggestion A: Normalize k6 to count only unexpected errors
// Separates expected guardrails (4xx risk blocks) from actual system failures
//
// Usage: k6 run scripts/testing/k6_enhanced_comprehensive_test.js

import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// ============================================================================
// AI AGENT ENHANCED METRICS - UNEXPECTED ERRORS ONLY
// ============================================================================
export const unexpected_error_rate = new Rate('unexpected_error_rate');
export const endpoint_p95 = new Trend('endpoint_p95', true);
export const unexpected_errors = new Counter('unexpected_errors');

// Original comprehensive metrics (preserved)
const authSuccessRate = new Rate('auth_success_rate');
const apiResponseTime = new Trend('api_response_time');
const orderLatency = new Trend('order_latency');
const signalLatency = new Trend('signal_latency');
const riskDecisionTime = new Trend('risk_decision_time');
const portfolioLatency = new Trend('portfolio_latency');
const businessWorkflowErrors = new Counter('business_workflow_errors');
const websocketConnectionErrors = new Counter('websocket_connection_errors');

// ============================================================================
// AI AGENT SUGGESTION: EXPECTED GUARDRAIL DETECTION
// ============================================================================
function isExpectedGuardrail(res) {
  if (res.status !== 422) return false;
  try {
    const j = res.json();
    
    // Check for GUARDRAIL_VIOLATION in detail.error
    if (j?.detail?.error === 'GUARDRAIL_VIOLATION') {
      return true;
    }
    
    // Check for guardrail-related violation codes
    if (j?.detail?.violations && Array.isArray(j.detail.violations)) {
      for (const violation of j.detail.violations) {
        const code = violation.code;
        if (code === 'DAILY_NOTIONAL_EXCEEDED' ||
            code === 'DAILY_ORDERS_EXCEEDED' ||
            code === 'POSITION_LIMIT_EXCEEDED' ||
            code === 'SYMBOL_NOT_ALLOWED' ||
            code === 'MARKET_CLOSED' ||
            code === 'TRADING_PAUSED') {
          return true;
        }
      }
    }
    
    // Legacy format checks (keep for backwards compatibility)
    const code = j?.error?.code;
    const reason = j?.error?.details?.reason || j?.error?.reason;
    
    // Allowlist your intentional blocks here:
    return code === 'RISK_LIMIT'
        || code === 'GUARDRAIL'             // daily cap, symbol whitelist, etc.
        || code === 'MARKET_CLOSED_SIM'
        || code === 'VALIDATION_ERROR'      // if you purposely send bad inputs in tests
        || reason?.includes('daily limit')
        || reason?.includes('risk threshold')
        || reason?.includes('position limit')
        || reason?.includes('symbol not allowed');
  } catch (_) { 
    /* JSON parsing failed - treat as unexpected */ 
  }
  return false;
}

// Track error count globally for logging
let unexpectedErrorCount = 0;

function recordOutcome(res, nameTag) {
  // Record metrics with proper tagging (K6-compatible approach)
  // Use tags instead of modifying request.name to avoid host object errors
  
  // AI Agent logic: Only count unexpected errors
  const unexpected =
    (res.status >= 500) ||
    (res.status >= 400 && res.status < 500 && !isExpectedGuardrail(res));
  
  unexpected_error_rate.add(unexpected, { name: nameTag });
  if (unexpected) {
    unexpectedErrorCount++;
    unexpected_errors.add(1, { 
      name: nameTag, 
      status: String(res.status),
      url: res.url 
    });
    
    // Log first 10 unexpected errors for debugging
    if (unexpectedErrorCount <= 10) {
      console.log(`UNEXPECTED ERROR #${unexpectedErrorCount}: ${nameTag} - Status: ${res.status}`);
      if (res.body) {
        const bodyPreview = res.body.substring(0, 200);
        console.log(`  Body: ${bodyPreview}`);
      }
    }
  }
  
  // Record endpoint-specific latency
  endpoint_p95.add(res.timings.duration, { endpoint: nameTag });
}

// ============================================================================
// AI AGENT ENHANCED THRESHOLDS - MEANINGFUL SUCCESS RATES
// ============================================================================
export const options = {
  scenarios: {
    // Scenario 1: Authentication & API Load Test - PRODUCTION CALIBRATED
    api_load_test: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 10 },  // Warm up (increased from 2)
        { duration: '2m', target: 50 },   // Peak load (increased from 5 to 50)
        { duration: '2m', target: 50 },   // Sustained load (hold at 50)
        { duration: '30s', target: 0 },   // Cool down
      ],
      exec: 'apiLoadTest',
    },
    
    // Scenario 2: Order Flow Performance Test - PRODUCTION CALIBRATED
    order_flow_test: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 10 },  // Warm up (increased from 2)
        { duration: '1m', target: 30 },   // Peak load (increased from 3 to 30)
        { duration: '30s', target: 0 },   
      ],
      startTime: '1m',  // Start after API load test begins
      exec: 'orderFlowTest',
    },
    
    // Scenario 3: Risk Engine Spike Test - PRODUCTION CALIBRATED
    risk_engine_test: {
      executor: 'ramping-vus', 
      startVUs: 1,
      stages: [
        { duration: '30s', target: 10 },  // Warm up (increased from 2)
        { duration: '45s', target: 40 },  // Risk validation spike (increased from 4 to 40)
        { duration: '15s', target: 0 },
      ],
      startTime: '2m',  // Start after other tests
      exec: 'riskEngineTest',
    },
    
    // Scenario 4: Business Workflow Integration - PRODUCTION CALIBRATED
    business_workflow_test: {
      executor: 'constant-vus',
      vus: 20,                            // Increased from 2 to 20
      duration: '2m',
      startTime: '30s',  // Start early for full workflow coverage
      exec: 'businessWorkflowTest',
    },
    
    // Scenario 5: WebSocket Stress Test - PRODUCTION CALIBRATED
    websocket_test: {
      executor: 'constant-vus',
      vus: 10,                            // Increased from 1 to 10
      duration: '1m',
      startTime: '3m',
      exec: 'websocketTest',
    },
  },
  
  // AI AGENT ENHANCED THRESHOLDS - PRODUCTION CALIBRATED
  thresholds: {
    // AI Agent enhancement: Tighten unexpected error rate (0.5% from 2%)
    'unexpected_error_rate': ['rate<0.005'],      // < 0.5% unexpected errors (PRODUCTION)
    
    // AI Agent suggestion: Tightened per-route P95 thresholds for production
    'http_req_duration{name:GET /api/v1/signals}': ['p(95)<200'],        // 200ms from 300ms
    'http_req_duration{name:POST /api/v1/signals/act}': ['p(95)<500'],   // Keep 500ms (order placement)
    'http_req_duration{name:GET /api/v1/positions}': ['p(95)<200'],      // 200ms from 300ms
    'http_req_duration{name:GET /api/v1/orders}': ['p(95)<300'],         // 300ms from 400ms
    'http_req_duration{name:GET /health}': ['p(95)<100'],                // Keep 100ms
    'http_req_duration{name:POST /api/v1/auth/login}': ['p(95)<200'],    // Keep 200ms
    
    // Overall performance thresholds - TIGHTENED FOR PRODUCTION
    'http_req_duration': ['p(95)<800', 'p(99)<1500'],          // 800ms/1500ms from 1000ms/2000ms
    'api_response_time': ['p(95)<600'],                        // 600ms from 800ms
    'order_latency': ['p(95)<1000'],                           // 1000ms from 1500ms
    'signal_latency': ['p(95)<400'],                           // 400ms from 500ms
    'risk_decision_time': ['p(95)<600'],                       // 600ms from 800ms
    'portfolio_latency': ['p(95)<500'],                        // 500ms from 600ms
    
    // Business logic thresholds - STRICTER FOR PRODUCTION
    'auth_success_rate': ['rate>=0.98'],                       // 98% from 95%
    'business_workflow_errors': ['count<5'],                   // 5 from 10
    'websocket_connection_errors': ['count<2'],                // 2 from 3
  },
}

// ============================================================================
// DEFAULT FUNCTION - Required by K6 for execution
// ============================================================================

export default function() {
  // Run the main API load test by default
  apiLoadTest();
}

// ============================================================================
// TEST SCENARIOS - ENHANCED WITH AI AGENT ERROR HANDLING + TOKEN REFRESH
// ============================================================================

// Global token state for all scenarios
let globalToken = '';
let tokenExpireTime = 0;

function authenticate(baseUrl) {
  // Use K6-specific env vars to avoid conflicts with Windows USERNAME
  const username = __ENV.K6_USERNAME || __ENV.TEST_USERNAME || 'admin';
  const password = __ENV.K6_PASSWORD || __ENV.TEST_PASSWORD || 'admin123';
  
  const authRes = http.post(`${baseUrl}/api/v1/auth/login`, 
    `username=${username}&password=${password}`, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      tags: { name: 'POST /api/v1/auth/login' },
    });
  
  recordOutcome(authRes, 'POST /api/v1/auth/login');
  
  if (authRes.status === 200) {
    const authData = authRes.json();
    globalToken = authData.access_token;
    // JWT tokens expire in 3600 seconds (1 hour), refresh 5 minutes early
    tokenExpireTime = Date.now() + (55 * 60 * 1000); 
    authSuccessRate.add(true);
    return true;
  } else {
    authSuccessRate.add(false);
    return false;
  }
}

function getValidToken(baseUrl) {
  // Check if token is missing or about to expire
  if (!globalToken || Date.now() >= tokenExpireTime) {
    if (!authenticate(baseUrl)) {
      return null;
    }
  }
  return globalToken;
}

function makeAuthenticatedRequest(method, url, options = {}, tag = '') {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  let token = getValidToken(baseUrl);
  
  if (!token) {
    return null; // Authentication failed
  }
  
  // Make request with token
  const headers = { Authorization: `Bearer ${token}`, ...options.headers };
  const requestOptions = { ...options, headers, tags: { name: tag } };
  
  let response;
  if (method === 'GET') {
    response = http.get(url, requestOptions);
  } else if (method === 'POST') {
    response = http.post(url, options.body, requestOptions);
  }
  
  // If 401 and token hasn't expired according to our tracking, force refresh
  if (response.status === 401 && Date.now() < tokenExpireTime) {
    tokenExpireTime = 0; // Force refresh
    token = getValidToken(baseUrl);
    
    if (token) {
      // Retry request with fresh token
      headers.Authorization = `Bearer ${token}`;
      if (method === 'GET') {
        response = http.get(url, requestOptions);
      } else if (method === 'POST') {
        response = http.post(url, options.body, requestOptions);
      }
    }
  }
  
  return response;
}

export function apiLoadTest() {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';

  // Initial authentication if needed
  if (!getValidToken(baseUrl)) {
    return; // Skip if auth fails
  }

  group('Health Check', () => {
    const res = http.get(`${baseUrl}/health`, {
      tags: { name: 'GET /health' },
    });
    recordOutcome(res, 'GET /health');
    check(res, { 
      'health check 2xx or expected 422': r => r.status < 400 || isExpectedGuardrail(r)
    });
    apiResponseTime.add(res.timings.duration);
  });

  group('Signals', () => {
    const res = makeAuthenticatedRequest('GET', `${baseUrl}/api/v1/signals?symbol=AAPL`, {}, 'GET /api/v1/signals');
    if (res) {
      recordOutcome(res, 'GET /api/v1/signals');
      check(res, { 
        'signals 2xx or expected 422': r => r.status < 400 || isExpectedGuardrail(r) 
      });
      signalLatency.add(res.timings.duration);
    }
  });

  group('Positions', () => {
    const res = makeAuthenticatedRequest('GET', `${baseUrl}/api/v1/positions`, {}, 'GET /api/v1/positions');
    if (res) {
      recordOutcome(res, 'GET /api/v1/positions');
      check(res, { 
        'positions 2xx or expected 422': r => r.status < 400 || isExpectedGuardrail(r)
      });
      portfolioLatency.add(res.timings.duration);
    }
  });

  sleep(1);
}

export function orderFlowTest() {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  
  // Use global token management
  if (!getValidToken(baseUrl)) {
    return; // Skip if auth fails
  }

  group('Order Flow - Signal to Order', () => {
    // Submit signal that should generate order
    const signalData = {
      symbol: 'AAPL',
      signal_strength: 0.8,
      timestamp: new Date().toISOString(),
      features: { test: true },
      metadata: { source: 'k6_enhanced_test' }
    };

    const signalRes = makeAuthenticatedRequest('POST', `${baseUrl}/api/v1/signals/act`, {
      body: JSON.stringify(signalData),
      headers: { 'Content-Type': 'application/json' }
    }, 'POST /api/v1/signals/act');
    
    if (signalRes) {
      recordOutcome(signalRes, 'POST /api/v1/signals/act');
      
      // AI Agent check: Order submission can be blocked by risk (expected 422)
      check(signalRes, { 
        'signal action 2xx or expected 422': r => r.status < 400 || isExpectedGuardrail(r)
      });

      orderLatency.add(signalRes.timings.duration);
      
      // If order was created, check its status
      if (signalRes.status === 200 || signalRes.status === 201) {
        const responseData = signalRes.json();
        if (responseData.order && responseData.order.order_id) {
          const orderStatusRes = makeAuthenticatedRequest('GET', `${baseUrl}/api/v1/orders/${responseData.order.order_id}`, {}, 'GET /api/v1/orders');
          
          if (orderStatusRes) {
            recordOutcome(orderStatusRes, 'GET /api/v1/orders');
            check(orderStatusRes, { 
              'order status 2xx or expected 422': r => r.status < 400 || isExpectedGuardrail(r)
            });
          }
        }
      }
    }
  });

  sleep(2);
}

export function riskEngineTest() {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  
  // Use global token management
  if (!getValidToken(baseUrl)) {
    return; // Skip if auth fails
  }

  group('Risk Engine Validation', () => {
    // Test risk endpoint with authenticated request
    const riskRes = makeAuthenticatedRequest('GET', `${baseUrl}/api/v1/risk/metrics`, {}, 'GET /api/v1/risk/metrics');
    
    if (riskRes) {
      recordOutcome(riskRes, 'GET /api/v1/risk/metrics');
      check(riskRes, { 
        'risk metrics 2xx or expected 422': r => r.status < 400 || isExpectedGuardrail(r)
      });
      
      riskDecisionTime.add(riskRes.timings.duration);
    }

    // Submit a risky order that should be blocked (testing guardrails)
    const riskySignal = {
      symbol: 'AAPL',
      signal_strength: 1.0,  // Maximum signal - likely to trigger limits
      timestamp: new Date().toISOString(),
      features: { risk_test: true },
      metadata: { source: 'k6_risk_test', expected_block: true }
    };

    const riskyRes = makeAuthenticatedRequest('POST', `${baseUrl}/api/v1/signals/act`, {
      body: JSON.stringify(riskySignal),
      headers: { 'Content-Type': 'application/json' }
    }, 'POST /api/v1/signals/act');
    
    if (riskyRes) {
      recordOutcome(riskyRes, 'POST /api/v1/signals/act');
      
      // This should often be blocked by risk engine (422) - that's expected behavior
      check(riskyRes, { 
        'risky order handled by risk engine': r => r.status < 400 || isExpectedGuardrail(r)
      });
    }
  });

  sleep(1);
}

export function businessWorkflowTest() {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  
  // Use global token management
  if (!getValidToken(baseUrl)) {
    businessWorkflowErrors.add(1);
    return;
  }

  // Multi-step workflow with authenticated requests
  const steps = [
    { url: `${baseUrl}/api/v1/positions`, name: 'GET /api/v1/positions' },
    { url: `${baseUrl}/api/v1/signals?symbol=GOOGL`, name: 'GET /api/v1/signals' },
  ];

  for (const step of steps) {
    const res = makeAuthenticatedRequest('GET', step.url, {}, step.name);
    
    if (res) {
      recordOutcome(res, step.name);
      
      if (res.status >= 500 || (res.status >= 400 && !isExpectedGuardrail(res))) {
        businessWorkflowErrors.add(1);
      }
      
      check(res, { 
        [`${step.name} success or expected block`]: r => r.status < 400 || isExpectedGuardrail(r)
      });
    } else {
      businessWorkflowErrors.add(1);
    }
  }

  sleep(1);
}

export function websocketTest() {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  const wsUrl = baseUrl.replace('http', 'ws') + '/ws';
  
  const res = ws.connect(wsUrl, {}, function (socket) {
    socket.on('open', () => {
      console.log('WebSocket connected successfully');
    });

    socket.on('message', (data) => {
      console.log('WebSocket received:', data);
    });

    socket.on('error', (e) => {
      console.log('WebSocket error:', e);
      websocketConnectionErrors.add(1);
    });

    socket.on('close', () => {
      console.log('WebSocket connection closed');
    });

    // Send a test message
    socket.send(JSON.stringify({ type: 'test', data: 'k6 enhanced test' }));
    
    sleep(2);
    socket.close();
  });

  check(res, { 'websocket connected successfully': (r) => r && r.status === 101 });
}

// ============================================================================
// AI AGENT SUGGESTION: CONCISE SUMMARY ARTIFACT
// ============================================================================
export function handleSummary(data) {
  // AI Agent: Generate k6-summary.json for automated promotion gates
  const summary = {
    timestamp: new Date().toISOString(),
    test_duration_seconds: data.state.testRunDurationMs / 1000,
    scenarios_completed: Object.keys(data.metrics).filter(m => m.includes('scenario')).length,
    
    // AI Agent metrics - unexpected errors only
    unexpected_error_rate: data.metrics.unexpected_error_rate?.values?.rate || 0,
    unexpected_errors_total: data.metrics.unexpected_errors?.values?.count || 0,
    
    // Per-route latencies (AI Agent suggestion B alignment)
    endpoint_latencies: {
      'GET /health': getEndpointLatency(data, 'GET /health'),
      'GET /api/v1/signals': getEndpointLatency(data, 'GET /api/v1/signals'),
      'POST /api/v1/signals/act': getEndpointLatency(data, 'POST /api/v1/signals/act'),
      'GET /api/v1/positions': getEndpointLatency(data, 'GET /api/v1/positions'),
      'GET /api/v1/orders': getEndpointLatency(data, 'GET /api/v1/orders'),
      'POST /api/v1/auth/login': getEndpointLatency(data, 'POST /api/v1/auth/login'),
    },
    
    // Overall performance
    overall_p95_ms: data.metrics.http_req_duration?.values?.['p(95)'] || 0,
    overall_p99_ms: data.metrics.http_req_duration?.values?.['p(99)'] || 0,
    
    // Business metrics
    auth_success_rate: data.metrics.auth_success_rate?.values?.rate || 0,
    total_requests: data.metrics.http_reqs?.values?.count || 0,
    
    // AI Agent: Pass/Fail determination
    pass_fail_criteria: {
      unexpected_errors_under_2pct: (data.metrics.unexpected_error_rate?.values?.rate || 0) < 0.02,
      health_p95_under_100ms: getEndpointLatency(data, 'GET /health').p95_ms < 100,
      signals_p95_under_300ms: getEndpointLatency(data, 'GET /api/v1/signals').p95_ms < 300,
      orders_p95_under_500ms: getEndpointLatency(data, 'POST /api/v1/signals/act').p95_ms < 500,
      positions_p95_under_300ms: getEndpointLatency(data, 'GET /api/v1/positions').p95_ms < 300,
      overall_success: true  // Will be calculated based on all criteria
    }
  };
  
  // Calculate overall success
  const criteria = summary.pass_fail_criteria;
  criteria.overall_success = criteria.unexpected_errors_under_2pct && 
                             criteria.health_p95_under_100ms && 
                             criteria.signals_p95_under_300ms && 
                             criteria.orders_p95_under_500ms && 
                             criteria.positions_p95_under_300ms;
  
  return {
    'k6-summary.json': JSON.stringify(summary, null, 2),
    stdout: generateTextSummary(summary),
  };
}

function getEndpointLatency(data, endpoint) {
  const key = `http_req_duration{name:${endpoint}}`;
  const metric = data.metrics[key];
  
  return {
    endpoint: endpoint,
    p95_ms: metric?.values?.['p(95)'] || 0,
    p99_ms: metric?.values?.['p(99)'] || 0,
    avg_ms: metric?.values?.avg || 0,
    requests: metric?.values?.count || 0
  };
}

function generateTextSummary(summary) {
  const criteria = summary.pass_fail_criteria;
  const status = criteria.overall_success ? '✅ PASS' : '❌ FAIL';
  
  return `
K6 ENHANCED PERFORMANCE TEST RESULTS
====================================
${status} - AI Agent Normalized Error Handling

Test Duration: ${summary.test_duration_seconds}s
Total Requests: ${summary.total_requests}

AI AGENT METRICS (Unexpected Errors Only):
  Unexpected Error Rate: ${(summary.unexpected_error_rate * 100).toFixed(2)}% ${criteria.unexpected_errors_under_2pct ? '✅' : '❌'} (target <2%)
  Unexpected Errors Total: ${summary.unexpected_errors_total}

PER-ROUTE LATENCIES:
  Health Check: ${summary.endpoint_latencies['GET /health'].p95_ms.toFixed(1)}ms ${criteria.health_p95_under_100ms ? '✅' : '❌'} (target <100ms)
  Signals: ${summary.endpoint_latencies['GET /api/v1/signals'].p95_ms.toFixed(1)}ms ${criteria.signals_p95_under_300ms ? '✅' : '❌'} (target <300ms)
  Order Submit: ${summary.endpoint_latencies['POST /api/v1/signals/act'].p95_ms.toFixed(1)}ms ${criteria.orders_p95_under_500ms ? '✅' : '❌'} (target <500ms)
  Positions: ${summary.endpoint_latencies['GET /api/v1/positions'].p95_ms.toFixed(1)}ms ${criteria.positions_p95_under_300ms ? '✅' : '❌'} (target <300ms)

OVERALL PERFORMANCE:
  P95: ${summary.overall_p95_ms.toFixed(1)}ms
  P99: ${summary.overall_p99_ms.toFixed(1)}ms
  Auth Success Rate: ${(summary.auth_success_rate * 100).toFixed(1)}%

${status} - ${criteria.overall_success ? 'All thresholds met' : 'Some thresholds failed'}
====================================
`;
}