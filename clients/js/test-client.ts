/**
 * Integration test for TypeScript API client
 * Run this to verify the client works with your backend
 */

import { TradingApiClient, isApiError } from './api';

async function testApiClient() {
  console.log('🚀 Testing Trading Platform API Client');
  console.log('=====================================');
  
  // Initialize client
  const client = new TradingApiClient('http://localhost:8000');
  
  // Test 1: Health check (unauthenticated)
  console.log('\n1. Testing health check...');
  try {
    // This should work without authentication
    const response = await fetch('http://localhost:8000/health');
    if (response.ok) {
      console.log('✅ Health check passed');
    } else {
      console.log('❌ Health check failed:', response.status);
    }
  } catch (error) {
    console.log('❌ Health check failed - is the backend running?');
    return;
  }
  
  // Test 2: Authentication required endpoint (should fail)
  console.log('\n2. Testing unauthenticated request (should fail)...');
  try {
    await client.getSignals('AAPL');
    console.log('❌ Expected authentication error but succeeded');
  } catch (error) {
    if (isApiError(error) && error.status === 401) {
      console.log('✅ Correctly rejected unauthenticated request');
    } else {
      console.log('❌ Unexpected error:', error);
    }
  }
  
  // Test 3: Set auth token (you need to replace with actual token)
  console.log('\n3. Testing with authentication...');
  
  // Check for environment variable (Node.js) or manually set token
  let testToken = 'test-token-here';
  try {
    // @ts-ignore - process may not exist in browser
    testToken = process?.env?.TEST_JWT_TOKEN || 'test-token-here';
  } catch {
    // Running in browser - token needs to be manually set
  }
  
  if (testToken === 'test-token-here') {
    console.log('⚠️  No test token provided. Set TEST_JWT_TOKEN environment variable');
    console.log('   Example: TEST_JWT_TOKEN=eyJ... node test-client.js');
    return;
  }
  
  client.setAuthToken(testToken);
  
  try {
    // Test authenticated endpoint
    const signals = await client.getSignals('AAPL');
    console.log('✅ Successfully retrieved signals:', signals.signals.length);
    
    // Test other endpoints if signals work
    if (signals.signals.length > 0 && signals.signals[0]) {
      console.log('\n4. Testing signal details...');
      const signal = await client.getSignal(signals.signals[0].id);
      console.log('✅ Successfully retrieved signal details');
    }
    
    console.log('\n5. Testing positions...');
    const positions = await client.getPositions();
    console.log('✅ Successfully retrieved positions:', positions.positions.length);
    
  } catch (error) {
    if (isApiError(error)) {
      console.log(`❌ API Error ${error.status}: ${error.message}`);
      if (error.status === 401) {
        console.log('   → Check if your JWT token is valid');
      }
    } else {
      console.log('❌ Network error:', error);
    }
  }
  
  console.log('\n🎉 API Client test completed!');
}

// Test configuration validation
function testConfiguration() {
  console.log('\n📋 Testing Client Configuration');
  console.log('===============================');
  
  // Test 1: Basic instantiation
  try {
    const client = new TradingApiClient('http://localhost:8000');
    console.log('✅ Client instantiation successful');
  } catch (error) {
    console.log('❌ Client instantiation failed:', error);
    return;
  }
  
  // Test 2: Custom configuration
  try {
    const client = new TradingApiClient('http://localhost:8000', {
      timeout: 5000,
      defaultHeaders: {
        'X-Test': 'true'
      }
    });
    console.log('✅ Custom configuration successful');
  } catch (error) {
    console.log('❌ Custom configuration failed:', error);
  }
  
  // Test 3: Token management
  const client = new TradingApiClient('http://localhost:8000');
  client.setAuthToken('test-token');
  console.log('✅ Token setting successful');
  
  client.clearAuthToken();
  console.log('✅ Token clearing successful');
}

// Run tests (for Node.js execution)
// Uncomment for Node.js usage:
// if (typeof require !== 'undefined' && require.main === module) {
//   console.log('Trading Platform API Client - Integration Test');
//   console.log('==============================================');
//   
//   testConfiguration();
//   testApiClient();
// }

export { testApiClient, testConfiguration };