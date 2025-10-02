import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 1,
  iterations: 1,
};

export default function() {
  console.log('Testing login...');
  
  const loginPayload = 'username=admin&password=admin123';
  
  const loginResponse = http.post(
    'http://localhost:8000/auth/login',
    loginPayload,
    {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      }
    }
  );
  
  console.log(`Status: ${loginResponse.status}`);
  console.log(`Body: ${loginResponse.body}`);
  
  const success = check(loginResponse, {
    'login successful': (r) => r.status === 200,
  });
  
  if (success) {
    console.log('✅ Authentication working correctly');
  } else {
    console.log('❌ Authentication failed');
  }
}