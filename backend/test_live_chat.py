import urllib.request
import json

def run_test():
    # 1. Login
    login_req = urllib.request.Request(
        'http://127.0.0.1:8000/api/v1/auth/login',
        data=json.dumps({'email': 'admin@familyos.local', 'password': 'AdminPass123!'}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(login_req) as resp:
        tokens = json.loads(resp.read().decode())
        token = tokens['access_token']

    print('Logged in successfully. Sending chat to Purchase Agent...')

    # 2. Chat with Purchase Agent
    chat_req = urllib.request.Request(
        'http://127.0.0.1:8000/api/v1/agents/PURCHASE/chat',
        data=json.dumps({'message': 'Find a wireless mouse under 2000'}).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
    )
    with urllib.request.urlopen(chat_req, timeout=45) as resp:
        res = json.loads(resp.read().decode())
        print('Reply:', res['reply'])
        print('Is Development Data:', res['is_development_data'])
        print('Candidate Count:', len(res.get('candidates') or []))
        for c in (res.get('candidates') or []):
            print(f"  - {c['title'][:55]} | {c['currency']} {c['price_amount']} | Source: {c['source_type']} | Merchant: {c['merchant']}")

if __name__ == "__main__":
    run_test()

