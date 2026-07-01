#!/usr/bin/env python3
"""Local API smoke test for the Ghaima APIs.

Exercises a suite of endpoints against a running server and prints a
pass/fail table with the response — the quickest way to see the API working
locally without a browser.

Get a token one of three ways:
  1. --login/--password/--device-uid  -> calls /api/v1/auth/login for you
  2. --token <JWT>                     -> paste one from the backend wizard
  3. --jwt-secret <secret> --uid --device-id  -> mint a dev token (local only)

Examples:
  # tenant, mint a dev token
  python api_smoke_test.py --base-url http://localhost:8015 \
      --jwt-secret <mobile_api.jwt_secret> --uid 53 --device-id 20

  # real login flow
  python api_smoke_test.py --base-url http://localhost:8015 \
      --login cashier@x.com --password secret --device-uid smoke

  # central server
  python api_smoke_test.py --base-url http://localhost:8016 --suite central \
      --login owner@x.com --password secret --device-uid smoke
"""
import argparse
import json
import sys
import time

import requests

# Read-only / safe endpoints per server. (method, path, body)
SUITES = {
    'tenant': [
        ('POST', '/api/v1/sync/config', {}),
        ('POST', '/api/v1/pos/user-configs', {}),
        ('POST', '/api/v1/sync/products', {'limit': 1}),
        ('POST', '/api/v1/sync/partners', {'limit': 1}),
        ('POST', '/api/v1/dashboard/list', {}),
        ('POST', '/api/v1/pos/session/status', {'config_id': 2}),
        ('POST', '/api/v1/sync/stock-levels', {'config_id': 2}),
    ],
    'central': [
        ('GET', '/api/v1/saas/me/profile', {}),
        ('GET', '/api/v1/saas/me/tenants', {}),
        ('GET', '/api/v1/saas/me/subscriptions', {}),
        ('GET', '/api/v1/saas/me/credit', {}),
        ('GET', '/api/v1/saas/me/cards', {}),
        ('GET', '/api/v1/saas/me/billing-events', {}),
    ],
}

C_OK, C_BAD, C_DIM, C_RST = '\033[32m', '\033[31m', '\033[90m', '\033[0m'


def mint_token(secret, uid, device_id, branch_id=False, scope=None, ttl=3600):
    import jwt
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    payload = {'uid': uid, 'device_id': device_id, 'branch_id': branch_id,
               'type': 'access', 'iat': now, 'exp': now + timedelta(seconds=ttl)}
    if scope:
        payload['scope'] = scope
    return jwt.encode(payload, secret, algorithm='HS256')


def login(base, args):
    path = '/api/v1/saas/auth/login' if args.suite == 'central' else '/api/v1/auth/login'
    body = {'login': args.login, 'password': args.password, 'device_uid': args.device_uid}
    r = requests.post(base + path, json=body, timeout=15)
    data = r.json().get('data') or r.json()
    tok = data.get('access_token')
    if not tok:
        print(f"{C_BAD}login failed: {r.status_code} {r.text[:200]}{C_RST}")
        sys.exit(2)
    return tok


def run(base, token, suite):
    hdr = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    rows, ok = [], 0
    for method, path, body in SUITES[suite]:
        t0 = time.time()
        code = 'ERR'
        try:
            kw = {} if method == 'GET' else {'json': body}
            r = requests.request(method, base + path, headers=hdr, timeout=30, **kw)
            ms = int((time.time() - t0) * 1000)
            code = r.status_code
            try:
                j = r.json()
                passed = r.status_code == 200 and (j.get('success') is not False)
                snippet = json.dumps(j.get('data', j), default=str)[:70]
            except ValueError:
                passed = False
                snippet = (r.text or '').replace('\n', ' ')[:70]
        except Exception as e:  # noqa: BLE001
            ms = int((time.time() - t0) * 1000); passed = False; snippet = str(e)[:70]
        ok += bool(passed)
        mark = f"{C_OK}PASS{C_RST}" if passed else f"{C_BAD}FAIL{C_RST}"
        rows.append(f"  {mark}  {str(code):>3}  {ms:>5}ms  {method:<4} {path:<40} {C_DIM}{snippet}{C_RST}")
    print(f"\n=== API smoke test — {suite} @ {base} ===")
    print('\n'.join(rows))
    print(f"\n  {ok}/{len(SUITES[suite])} passed\n")
    return len(SUITES[suite]) - ok


def main():
    p = argparse.ArgumentParser(description='Ghaima API smoke test')
    p.add_argument('--base-url', default='http://localhost:8015')
    p.add_argument('--suite', choices=list(SUITES), default='tenant')
    p.add_argument('--token')
    p.add_argument('--jwt-secret'); p.add_argument('--uid', type=int); p.add_argument('--device-id', type=int)
    p.add_argument('--login'); p.add_argument('--password'); p.add_argument('--device-uid', default='smoke-test')
    a = p.parse_args()
    base = a.base_url.rstrip('/')
    if a.token:
        token = a.token
    elif a.jwt_secret and a.uid:
        token = mint_token(a.jwt_secret, a.uid, a.device_id or 0)
    elif a.login:
        token = login(base, a)
    else:
        p.error('provide --token, or --jwt-secret+--uid+--device-id, or --login+--password')
    sys.exit(run(base, token, a.suite))


if __name__ == '__main__':
    main()
