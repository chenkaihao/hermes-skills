#!/usr/bin/env python3
"""
ChatGPT → 9Router 同步脚本
验证本地 ChatGPT 账号 token 并注入 9Router 数据库。

用法：
    python3 sync_chatgpt_to_9router.py [--dry-run] [--proxy http://127.0.0.1:10809]

环境变量：
    ANY_AUTO_REGISTER_DIR   any-auto-register 项目路径（默认 /root/src/any-auto-register）
    NINE_ROUTER_DB         9Router 数据库路径（默认 /root/src/9router-data/db.json）
"""

import argparse
import json
import base64
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# 尝试导入依赖
try:
    from curl_cffi import requests as cffi_requests
    from sqlmodel import Session, text
except ImportError as e:
    print(f"缺少依赖: {e}")
    print("请安装: pip install curl-cffi sqlmodel")
    sys.exit(1)


def get_db_paths():
    """获取数据库路径"""
    any_auto_dir = os.getenv('ANY_AUTO_REGISTER_DIR', '/root/src/any-auto-register')
    nine_router_db = os.getenv('NINE_ROUTER_DB', '/root/src/9router-data/db.json')
    return any_auto_dir, nine_router_db


def load_oauth_constants(any_auto_dir):
    """加载 OAuth 常量"""
    constants_path = os.path.join(any_auto_dir, 'platforms/chatgpt/constants.py')
    if not os.path.exists(constants_path):
        raise FileNotFoundError(f"OAuth 配置文件不存在: {constants_path}")
    
    # 使用 exec 读取常量（避免复杂导入依赖）
    with open(constants_path, 'r') as f:
        code = f.read()
    
    # 提取 OAUTH_CLIENT_ID 和 OAUTH_REDIRECT_URI
    namespace = {}
    exec(code, namespace)
    return {
        'OAUTH_CLIENT_ID': namespace.get('OAUTH_CLIENT_ID'),
        'OAUTH_REDIRECT_URI': namespace.get('OAUTH_REDIRECT_URI'),
    }


def query_accounts_with_tokens(any_auto_dir):
    """查询有完整 token 的账号"""
    sys.path.insert(0, any_auto_dir)
    from core.db import engine
    
    with Session(engine) as sess:
        rows = sess.exec(text('''
            SELECT a.id, a.email,
              (SELECT ac.value FROM account_credentials ac
               WHERE ac.account_id=a.id AND ac.key='refresh_token' AND ac.value != '' LIMIT 1),
              (SELECT ac.value FROM account_credentials ac
               WHERE ac.account_id=a.id AND ac.key='id_token' AND ac.value != '' LIMIT 1),
              (SELECT ac.value FROM account_credentials ac
               WHERE ac.account_id=a.id AND ac.key='access_token' AND ac.value != '' LIMIT 1)
            FROM accounts a WHERE a.platform='chatgpt' ORDER BY a.id
        ''')).all()

    accounts = []
    for r in rows:
        if r[2] and r[3] and r[4]:
            accounts.append({
                "db_id": r[0],
                "email": r[1],
                "refresh_token": r[2],
                "id_token": r[3],
                "access_token": r[4],
            })
    return accounts


def validate_token(acct, oauth_consts, proxy=None):
    """
    验证 refresh_token 是否有效
    
    Returns:
        Tuple[bool, dict]: (是否有效, 包含新 token 的字典或错误信息)
    """
    from curl_cffi import requests as cffi_requests
    
    try:
        session = cffi_requests.Session(impersonate="chrome120", proxy=proxy)
        
        token_data = {
            "client_id": oauth_consts['OAUTH_CLIENT_ID'],
            "grant_type": "refresh_token",
            "refresh_token": acct["refresh_token"],
            "redirect_uri": oauth_consts['OAUTH_REDIRECT_URI']
        }
        
        resp = session.post(
            "https://auth.openai.com/oauth/token",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "accept": "application/json"
            },
            data=token_data,
            timeout=30
        )
        
        if resp.status_code != 200:
            return False, {"error": f"HTTP {resp.status_code}", "detail": resp.text[:200]}
        
        data = resp.json()
        access_token = data.get("access_token")
        
        if not access_token:
            return False, {"error": "No access_token in response", "detail": data}
        
        return True, {
            "access_token": access_token,
            "refresh_token": data.get("refresh_token", acct["refresh_token"]),
            "id_token": data.get("id_token", acct["id_token"]),
        }
        
    except Exception as e:
        return False, {"error": str(e)}


def update_local_db(acct, tokens, any_auto_dir):
    """更新本地数据库中的 token"""
    sys.path.insert(0, any_auto_dir)
    from core.db import engine
    from sqlmodel import Session, text
    
    with Session(engine) as sess:
        for key, val in [
            ("access_token", tokens["access_token"]),
            ("refresh_token", tokens["refresh_token"]),
            ("id_token", tokens["id_token"]),
        ]:
            if val:
                sess.exec(text(
                    "UPDATE account_credentials SET value=:v, updated_at=CURRENT_TIMESTAMP "
                    "WHERE account_id=:aid AND key=:k"
                ).bindparams(v=val, aid=acct["db_id"], k=key))
        sess.commit()


def decode_jwt_payload(token):
    """解码 JWT payload 部分"""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        return json.loads(base64.b64decode(payload_b64))
    except Exception:
        return {}


def inject_into_9router(valid_accounts, nine_router_db_path, dry_run=False):
    """
    将有效账号注入 9Router 数据库
    
    Returns:
        dict: {"added": int, "updated": int, "total": int}
    """
    with open(nine_router_db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    existing_codex = [c for c in db["providerConnections"] if c["provider"] == "codex"]
    existing_emails = {c.get("email", "") for c in existing_codex}
    existing_names = {c.get("name", "") for c in existing_codex}
    
    next_num = 1
    while f"Account {next_num}" in existing_names:
        next_num += 1
    
    added, updated = 0, 0
    now = datetime.now(timezone.utc).isoformat()
    
    for acct in valid_accounts:
        email = acct["email"]
        
        id_payload = decode_jwt_payload(acct["id_token"])
        display_name = id_payload.get("name", email)
        
        exp_payload = decode_jwt_payload(acct["access_token"])
        expires_at = None
        if exp_payload.get("exp"):
            expires_at = datetime.fromtimestamp(exp_payload["exp"], tz=timezone.utc).isoformat()
        
        existing = [c for c in existing_codex if c.get("email") == email]
        
        if existing:
            conn = existing[0]
            if not dry_run:
                conn.update({
                    "accessToken": acct["access_token"],
                    "refreshToken": acct["refresh_token"],
                    "expiresAt": expires_at,
                    "updatedAt": now,
                    "testStatus": "active",
                    "backoffLevel": 0,
                })
                for k in ("lastError", "errorCode", "lastErrorAt"):
                    conn.pop(k, None)
            print(f"  UPDATED: {conn['name']} | {email}")
            updated += 1
        else:
            account_name = f"Account {next_num}"
            conn = {
                "id": str(__import__('uuid').uuid4()),
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
            if not dry_run:
                db["providerConnections"].append(conn)
            existing_names.add(account_name)
            print(f"  ADDED: {account_name} | {email} | expires: {expires_at}")
            next_num += 1
            added += 1
    
    if not dry_run:
        with open(nine_router_db_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
    
    total = len([c for c in db["providerConnections"] if c["provider"] == "codex"])
    return {"added": added, "updated": updated, "total": total}


def main():
    parser = argparse.ArgumentParser(description="ChatGPT → 9Router 账号同步")
    parser.add_argument('--dry-run', action='store_true', help='只打印不修改')
    parser.add_argument('--proxy', default=None, help='代理 URL，默认不使用')
    args = parser.parse_args()
    
    any_auto_dir, nine_router_db = get_db_paths()
    
    print(f"any-auto-register 路径: {any_auto_dir}")
    print(f"9Router 数据库路径: {nine_router_db}")
    print(f"代理: {args.proxy or '无'}")
    print(f"模式: {'预览' if args.dry_run else '执行'}")
    
    if not os.path.exists(nine_router_db):
        print(f"错误: 9Router 数据库不存在: {nine_router_db}")
        sys.exit(1)
    
    try:
        oauth_consts = load_oauth_constants(any_auto_dir)
    except Exception as e:
        print(f"加载 OAuth 配置失败: {e}")
        sys.exit(1)
    
    print("\n=== 查询本地账号 ===")
    accounts = query_accounts_with_tokens(any_auto_dir)
    print(f"找到 {len(accounts)} 个有完整 token 的账号")
    for a in accounts:
        print(f"  id={a['db_id']} {a['email']}")
    
    if not accounts:
        print("没有可同步的账号")
        sys.exit(0)
    
    print("\n=== 验证 Token ===")
    valid = []
    invalid = []
    
    for acct in accounts:
        print(f"\n验证: id={acct['db_id']} {acct['email']}")
        is_valid, result = validate_token(acct, oauth_consts, proxy=args.proxy)
        
        if is_valid:
            valid.append({**acct, **result})
            print(f"  ✓ VALID")
            
            if not args.dry_run:
                try:
                    update_local_db(acct, result, any_auto_dir)
                    print(f"  ✓ 本地 DB 已更新")
                except Exception as e:
                    print(f"  ! 本地 DB 更新失败: {e}")
        else:
            invalid.append(acct)
            print(f"  ✗ INVALID: {result.get('error', 'unknown')}")
    
    print(f"\n验证完成: {len(valid)} 有效, {len(invalid)} 无效")
    
    if valid:
        print("\n=== 注入 9Router ===")
        result = inject_into_9router(valid, nine_router_db, dry_run=args.dry_run)
        print(f"\n完成: 新增 {result['added']}, 更新 {result['updated']}, 9Router 中 codex 总数 {result['total']}")
    else:
        print("\n没有有效账号，跳过注入")


if __name__ == "__main__":
    main()
