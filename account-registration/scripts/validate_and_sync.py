#!/usr/bin/env python3
"""
ChatGPT 账号验证并同步到 9Router
用法: python3 validate_and_sync.py [--emails email1,email2,...]
"""

import json, base64, uuid, time, sys, os
from datetime import datetime, timezone
from curl_cffi import requests as cffi_requests
import sqlite3

sys.path.insert(0, '/root/src/any-auto-register')
from core.db import engine
from sqlmodel import Session, text

NINE_ROUTER_DB = "/root/src/9router-data/db.json"
WAIT_BEFORE_VALIDATE = 120  # 等待秒数（让 Cloudflare 封锁缓解）

def get_accounts(emails=None):
    """查询有完整 token 的账号"""
    with Session(engine) as sess:
        if emails:
            placeholders = ",".join([f":e{i}" for i in range(len(emails))])
            params = {f"e{i}": e for i, e in enumerate(emails)}
            rows = sess.exec(text(f'''
                SELECT a.id, a.email,
                  (SELECT ac.value FROM account_credentials ac WHERE ac.account_id=a.id AND ac.key='refresh_token' AND ac.value != '' LIMIT 1),
                  (SELECT ac.value FROM account_credentials ac WHERE ac.account_id=a.id AND ac.key='id_token' AND ac.value != '' LIMIT 1),
                  (SELECT ac.value FROM account_credentials ac WHERE ac.account_id=a.id AND ac.key='access_token' AND ac.value != '' LIMIT 1)
                FROM accounts a WHERE a.platform='chatgpt' AND a.email IN ({placeholders}) ORDER BY a.id
            '''), params).all()
        else:
            rows = sess.exec(text('''
                SELECT a.id, a.email,
                  (SELECT ac.value FROM account_credentials ac WHERE ac.account_id=a.id AND ac.key='refresh_token' AND ac.value != '' LIMIT 1),
                  (SELECT ac.value FROM account_credentials ac WHERE ac.account_id=a.id AND ac.key='id_token' AND ac.value != '' LIMIT 1),
                  (SELECT ac.value FROM account_credentials ac WHERE ac.account_id=a.id AND ac.key='access_token' AND ac.value != '' LIMIT 1)
                FROM accounts a WHERE a.platform='chatgpt' ORDER BY a.id
            ''')).all()

    accounts = []
    for r in rows:
        if r[2] and r[3] and r[4]:
            accounts.append({"db_id": r[0], "email": r[1], "refresh_token": r[2], "id_token": r[3], "access_token": r[4]})
    return accounts

def validate_token(acct):
    """验证单个账号 token"""
    session = cffi_requests.Session(impersonate="chrome120", proxy=None)
    resp = session.get(
        "https://chatgpt.com/backend-api/me",
        headers={"authorization": f"Bearer {acct['access_token']}", "accept": "application/json"},
        timeout=30
    )
    return resp.status_code == 200

def refresh_token(acct):
    """刷新 token"""
    session = cffi_requests.Session(impersonate="chrome120", proxy=None)
    
    with open('/root/src/any-auto-register/platforms/chatgpt/constants.py', 'r') as f:
        exec(f.read(), globals())
    
    token_data = {
        "client_id": OAUTH_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": acct["refresh_token"],
        "redirect_uri": OAUTH_REDIRECT_URI
    }
    
    resp = session.post(
        "https://auth.openai.com/oauth/token",
        headers={"content-type": "application/x-www-form-urlencoded", "accept": "application/json"},
        data=token_data,
        timeout=30
    )
    
    if resp.status_code == 200:
        data = resp.json()
        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token", acct["refresh_token"]),
            "id_token": data.get("id_token", ""),
        }
    return None

def update_db_tokens(acct, tokens):
    """更新数据库中的 token"""
    with Session(engine) as sess:
        for key, val in [("access_token", tokens["access_token"]),
                         ("refresh_token", tokens["refresh_token"]),
                         ("id_token", tokens["id_token"])]:
            if val:
                sess.exec(text(
                    "UPDATE account_credentials SET value=:v, updated_at=CURRENT_TIMESTAMP "
                    "WHERE account_id=:aid AND key=:k"
                ).bindparams(v=val, aid=acct["db_id"], k=key))
        sess.commit()

def sync_to_ninerouter(valid_accounts):
    """同步到 9Router"""
    with open(NINE_ROUTER_DB, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    existing_codex = [c for c in db["providerConnections"] if c["provider"] == "codex"]
    existing_emails = {c.get("email", "") for c in existing_codex}
    existing_names = {c.get("name", "") for c in existing_codex}
    
    next_num = 1
    while f"Account {next_num}" in existing_names:
        next_num += 1
    
    added, updated = 0, 0
    
    for acct in valid_accounts:
        email, display_name = acct["email"], ""
        try:
            payload_b64 = acct["id_token"].split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            email = payload.get("email", email)
            display_name = payload.get("name", "")
        except:
            pass
        
        expires_at = None
        try:
            payload_b64 = acct["access_token"].split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            if payload.get("exp"):
                expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat()
        except:
            pass
        
        existing = [c for c in existing_codex if c.get("email") == email]
        now = datetime.now(timezone.utc).isoformat()
        
        if existing:
            conn = existing[0]
            conn["accessToken"] = acct["access_token"]
            conn["refreshToken"] = acct["refresh_token"]
            conn["expiresAt"] = expires_at
            conn["updatedAt"] = now
            conn["testStatus"] = "active"
            conn["backoffLevel"] = 0
            for k in ("lastError", "errorCode", "lastErrorAt"):
                conn.pop(k, None)
            updated += 1
        else:
            account_name = f"Account {next_num}"
            conn = {
                "id": str(uuid.uuid4()),
                "provider": "codex",
                "authType": "oauth",
                "name": account_name,
                "priority": next_num,
                "isActive": True,
                "createdAt": now,
                "updatedAt": now,
                "testStatus": "active",
                "backoffLevel": 0,
                "accessToken": acct["access_token"],
                "refreshToken": acct["refresh_token"],
                "expiresAt": expires_at,
                "email": email,
                "displayName": display_name or email,
            }
            db["providerConnections"].append(conn)
            existing_names.add(account_name)
            next_num += 1
            added += 1
    
    with open(NINE_ROUTER_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    
    total = len([c for c in db["providerConnections"] if c["provider"] == "codex"])
    return {"added": added, "updated": updated, "total": total}

def main():
    emails = None
    if len(sys.argv) > 1 and sys.argv[1] == "--emails":
        emails = sys.argv[2].split(",")
    
    print("=== 查询账号 ===")
    accounts = get_accounts(emails)
    print(f"找到 {len(accounts)} 个账号")
    
    print(f"\n等待 {WAIT_BEFORE_VALIDATE} 秒...")
    time.sleep(WAIT_BEFORE_VALIDATE)
    
    print("\n=== 验证 token ===")
    valid = []
    for acct in accounts:
        try:
            if validate_token(acct):
                print(f"  ✓ {acct['email']}")
                valid.append(acct)
            else:
                print(f"  ✗ {acct['email']}")
        except Exception as e:
            print(f"  ✗ {acct['email']}: {e}")
    
    print(f"\n有效: {len(valid)}/{len(accounts)}")
    
    if not valid:
        print("无有效账号，退出")
        return
    
    print("\n=== 刷新 token ===")
    refreshed = []
    for acct in valid:
        tokens = refresh_token(acct)
        if tokens:
            print(f"  ✓ {acct['email']}")
            update_db_tokens(acct, tokens)
            refreshed.append({**acct, **tokens})
        else:
            print(f"  ✗ {acct['email']}")
    
    if not refreshed:
        print("刷新失败，退出")
        return
    
    print("\n=== 同步 9Router ===")
    result = sync_to_ninerouter(refreshed)
    print(f"新增: {result['added']}, 更新: {result['updated']}, 总数: {result['total']}")

if __name__ == "__main__":
    main()
