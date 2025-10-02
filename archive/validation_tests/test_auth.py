import os
import json
import requests
import threading
import time
import uvicorn
from contextlib import asynccontextmanager
from backend.api.factory import create_app

def test_auth():
    time.sleep(3)
    base_url = 'http://127.0.0.1:8002'
    try:
        print('Testing login...')
        login_resp = requests.post(f'{base_url}/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
        if login_resp.status_code == 200:
            token = login_resp.json()['access_token']
            print(f'Token: {token[:50]}...')
            auth_resp = requests.get(f'{base_url}/api/v1/positions', headers={'Authorization': f'Bearer {token}'}, timeout=5)
            print(f'Auth result: {auth_resp.status_code} - {auth_resp.text}')
        else:
            print(f'Login failed: {login_resp.status_code}')
    except Exception as e:
        print(f'Error: {e}')

def run_server():
    os.environ['SECURITY_JWT_SECRET'] = 'your-super-secret-jwt-key-for-development-only-change-in-production'
    app = create_app()
    @asynccontextmanager
    async def simple_lifespan(app):
        yield
    app.router.lifespan_context = simple_lifespan
    uvicorn.run(app, host='127.0.0.1', port=8002, log_level='info')

if __name__ == '__main__':
    import threading
    threading.Thread(target=run_server, daemon=True).start()
    test_auth()
