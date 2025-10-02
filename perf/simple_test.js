import http from 'k6/http';
import { check } from 'k6';

export const options = {
  duration: '5s',
  vus: 1,
};

export default function () {
  console.log('🚀 K6 is running!');
  const res = http.get('http://localhost:8000/health');
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
  console.log(`Health check: ${res.status}`);
}