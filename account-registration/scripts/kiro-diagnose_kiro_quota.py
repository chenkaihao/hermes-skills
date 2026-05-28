#!/usr/bin/env python3
"""
diagnose_kiro_quota.py — Diagnose Kiro account freeTrial status and quota structure.

Analyzes the raw AWS Q API response to determine whether an account has
an active freeTrial (500 credits) or only the base 50 credits.

Usage:
    # Diagnose specific account IDs
    python diagnose_kiro_quota.py --ids 22,23,24

    # Use custom DB
    python diagnose_kiro_quota.py --db /path/to/account_manager.db

    # With proxy
    PROXY="http://user:pass@host:port" python diagnose_kiro_quota.py
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

# Add any-auto-register to path
sys.path.insert(0, '/root/src/any-auto-register')

from platforms.kiro.usage import _fetch_usage
from platforms.kiro.switch import refresh_kiro_token

PROXY_CONFIG = {
    "http": "http://4GJSsuSsb3vci2UA:4D9N9XyBb0weKTy8_country-us@geo.iproyal.com:12321",
    "https": "http://4GJSsuSsb3vci2UA:4D9N9XyBb0weKTy8_country-us@geo.iproyal.com:12321",
}


def get_proxy() -> dict | None:
    """Get proxy from env or PROXY_CONFIG."""
    http = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    https = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if http or https:
        return {"http": http or https, "https": https or http}
    if PROXY_CONFIG.get("http"):
        return PROXY_CONFIG
    return None


def load_accounts(db_path: str, ids: list[int] | None = None) -> list[dict]:
    """Load accounts with complete credentials from any-auto-register DB."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT a.id, a.email,
               MAX(CASE WHEN ac.key = 'refreshToken' THEN ac.value END) as refreshToken,
               MAX(CASE WHEN ac.key = 'clientId' THEN ac.value END) as clientId,
               MAX(CASE WHEN ac.key = 'clientSecret' THEN ac.value END) as clientSecret
        FROM accounts a
        LEFT JOIN account_credentials ac ON a.id = ac.account_id
        WHERE a.platform = 'kiro'
    """
    params = []

    if ids:
        placeholders = ','.join('?' * len(ids))
        query += f" AND a.id IN ({placeholders})"
        params = ids

    query += " GROUP BY a.id, a.email ORDER BY a.id"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    accounts = []
    for row in rows:
        acc_id, email, refresh_token, client_id, client_secret = row
        if refresh_token and client_id and client_secret:
            accounts.append({
                'id': acc_id,
                'email': email,
                'refreshToken': refresh_token,
                'clientId': client_id,
                'clientSecret': client_secret,
            })
    return accounts


def diagnose_account(acc: dict, proxy: dict | None = None) -> dict:
    """Diagnose a single account's freeTrial status and quota structure."""
    result = {
        'id': acc['id'],
        'email': acc['email'],
        'timestamp': datetime.now().isoformat(),
    }

    # Step 1: Refresh token
    ok, token_result = refresh_kiro_token(
        acc['refreshToken'],
        acc['clientId'],
        acc['clientSecret']
    )

    if not ok:
        result.update({
            'valid': False,
            'error': f"Token refresh failed: {token_result.get('error', '')}",
            'freeTrialStatus': None,
            'hasFreeTrial': False,
        })
        return result

    result['token_refresh'] = 'ok'

    # Step 2: Fetch raw usage
    raw = _fetch_usage(token_result['accessToken'])

    if raw is None:
        result.update({
            'valid': False,
            'error': 'AWS Q API request failed',
            'freeTrialStatus': None,
            'hasFreeTrial': False,
        })
        return result

    result['api_response'] = 'ok'

    # Step 3: Parse freeTrialInfo
    breakdown = raw.get('usageBreakdownList', [])
    credit_item = next((x for x in breakdown if x.get('resourceType') == 'CREDIT'), None)

    if not credit_item:
        result.update({
            'valid': False,
            'error': 'No CREDIT entry in response',
            'freeTrialStatus': None,
            'hasFreeTrial': False,
        })
        return result

    ft = credit_item.get('freeTrialInfo')

    if ft and ft.get('freeTrialStatus') == 'ACTIVE':
        result.update({
            'valid': True,
            'freeTrialStatus': 'ACTIVE',
            'hasFreeTrial': True,
            'freeTrialLimit': ft.get('usageLimit'),
            'freeTrialCurrent': ft.get('currentUsage'),
            'freeTrialExpiry': ft.get('freeTrialExpiry'),
            'baseLimit': credit_item.get('usageLimitWithPrecision'),
            'baseCurrent': credit_item.get('currentUsageWithPrecision'),
            'totalLimit': credit_item.get('usageLimitWithPrecision') + ft.get('usageLimit', 0),
            'totalCurrent': credit_item.get('currentUsageWithPrecision') + ft.get('currentUsage', 0),
        })
    else:
        result.update({
            'valid': True,
            'freeTrialStatus': None,
            'hasFreeTrial': False,
            'freeTrialLimit': 0,
            'freeTrialCurrent': 0,
            'baseLimit': credit_item.get('usageLimitWithPrecision'),
            'baseCurrent': credit_item.get('currentUsageWithPrecision'),
            'totalLimit': credit_item.get('usageLimitWithPrecision'),
            'totalCurrent': credit_item.get('currentUsageWithPrecision'),
        })

    result['subscription'] = raw.get('subscriptionInfo', {})
    return result


def main():
    parser = argparse.ArgumentParser(description='Diagnose Kiro account freeTrial status')
    parser.add_argument('--db', default='/root/src/any-auto-register/account_manager.db')
    parser.add_argument('--ids', help='Comma-separated account IDs (default: all)')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()

    ids = [int(x) for x in args.ids.split(',')] if args.ids else None
    accounts = load_accounts(args.db, ids)

    if not accounts:
        print("No accounts found")
        return

    proxy = get_proxy()
    if proxy:
        print(f"Using proxy: {proxy['http'][:60]}...")

    results = []

    for i, acc in enumerate(accounts, 1):
        print(f"\n[{i}/{len(accounts)}] Diagnosing {acc['email']} (ID {acc['id']})...")

        try:
            result = diagnose_account(acc, proxy)
            results.append(result)

            if result.get('hasFreeTrial'):
                ft_limit = result.get('freeTrialLimit', 0)
                ft_current = result.get('freeTrialCurrent', 0)
                print(f"  ✅ HAS freeTrial: {ft_limit} credits ({ft_current} used)")
                print(f"     base: {result.get('baseLimit')} / free: {ft_limit} / total: {result.get('totalLimit')}")
            else:
                print(f"  ❌ NO freeTrial (freeTrialInfo is null)")
                print(f"     base: {result.get('baseLimit')} / total: {result.get('totalLimit')}")

            if 'error' in result:
                print(f"  ⚠️ Error: {result['error']}")

        except Exception as e:
            print(f"  ❌ Exception: {str(e)[:200]}")
            results.append({'id': acc['id'], 'email': acc['email'], 'exception': str(e)})

    # Summary
    print("\n" + "=" * 80)
    print(f"\n📊 Diagnosed {len(results)} accounts\n")

    with_ft = [r for r in results if r.get('hasFreeTrial')]
    without_ft = [r for r in results if not r.get('hasFreeTrial') and 'error' not in r]
    errors = [r for r in results if 'error' in r or 'exception' in r]

    print(f"  ✅ With freeTrial: {len(with_ft)} accounts")
    for r in with_ft:
        print(f"     - {r['email']}: base={r.get('baseLimit')}, freeTrial={r.get('freeTrialLimit')}, total={r.get('totalLimit')}")

    print(f"\n  ❌ Without freeTrial: {len(without_ft)} accounts")
    for r in without_ft:
        print(f"     - {r['email']}: base={r.get('baseLimit')}, total={r.get('totalLimit')}")

    if errors:
        print(f"\n  ⚠️ Errors: {len(errors)} accounts")
        for r in errors:
            print(f"     - {r['email']}: {r.get('error', r.get('exception', ''))[:80]}")

    # JSON output
    if args.json:
        output = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total': len(results),
                'withFreeTrial': len(with_ft),
                'withoutFreeTrial': len(without_ft),
                'errors': len(errors),
            },
            'accounts': results,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
