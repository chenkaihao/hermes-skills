#!/usr/bin/env python3
"""
Kiro Chat API verification — the authoritative account health test.
CodeWhisperer may return 403 for accounts that work perfectly on chat API.

Usage:
    python scripts/test_chat_api.py [--proxy URL] [--ids 9,10,11]
"""
import argparse, json, sqlite3, sys
from datetime import datetime, timezone

sys.path.insert(0, "/root/src/any-auto-register")
from platforms.kiro.switch import refresh_kiro_token
from curl_cffi import requests as cffi_requests

CHAT_URL = "https://q.us-east-1.amazonaws.com/chat"
PROXY_CONFIG = {
    "http": "http://100.64.247.23:7890",
    "https": "http://100.64.247.23:7890",
}

def test_chat(access_token, proxy):
    """Send a simple chat request. Returns (ok, reply_preview)."""
    r = cffi_requests.post(
        CHAT_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "aws-sdk-js/1.0.18",
        },
        json={"messages": [{"role": "user", "content": "Hi"}], "maxTokens": 50},
        proxies=proxy,
        impersonate="chrome131",
        timeout=30,
    )
    if r.status_code == 200:
        return True, "OK"
    return False, f"HTTP {r.status_code}: {r.text[:80]}"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--proxy", default=PROXY_CONFIG["http"], help="Proxy URL")
    p.add_argument("--ids", help="Comma-separated account IDs to test")
    p.add_argument("--db", default="/root/src/any-auto-register/account_manager.db")
    args = p.parse_args()

    proxy = {"http": args.proxy, "https": args.proxy} if args.proxy else None
    ids = set(int(x.strip()) for x in (args.ids or "").split(",") if x.strip())

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row

    passed = 0
    failed = 0
    for a in db.execute("SELECT id, email FROM accounts WHERE platform='kiro' ORDER BY id"):
        if ids and a["id"] not in ids:
            continue

        creds = {}
        for c in db.execute(
            "SELECT key, value FROM account_credentials WHERE account_id=? AND value!=''",
            [a["id"]],
        ):
            creds[c["key"]] = c["value"]

        rt = creds.get("refreshToken", "")
        cid = creds.get("clientId", "")
        csec = creds.get("clientSecret", "")

        if not (rt and cid and csec):
            print(f"ID={a['id']:<4} {a['email']:<38} ⏭  no refreshToken")
            continue

        ok, tr = refresh_kiro_token(rt, cid, csec)
        if not ok:
            print(f"ID={a['id']:<4} {a['email']:<38} ❌ token refresh failed")
            failed += 1
            continue

        chat_ok, msg = test_chat(tr["accessToken"], proxy)
        if chat_ok:
            print(f"ID={a['id']:<4} {a['email']:<38} ✅ chat OK")
            passed += 1
        else:
            print(f"ID={a['id']:<4} {a['email']:<38} ❌ {msg}")
            failed += 1

    db.close()
    print(f"\nChat API: {passed} passed, {failed} failed, {passed+failed} total")

if __name__ == "__main__":
    main()
