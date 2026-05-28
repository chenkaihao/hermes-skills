#!/usr/bin/env python3
"""
Sync any-auto-register platform accounts (Kiro, ChatGPT, etc.) to 9Router db.json.
Deduplicates by email; updates existing or creates new connections.

Usage:
    python sync_platform_template.py --platform kiro [--db /path/to/account_manager.db] [--router-db /root/src/9router-data/db.json]
    python sync_platform_template.py --platform chatgpt --dry-run
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any

try:
    import requests
except ImportError:
    print("⚠️  requests not installed. Run: pip install requests")
    sys.exit(1)


def load_platform_accounts(db_path: str, platform: str) -> list[dict]:
    """Load all accounts for a given platform with their credentials."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT a.id, a.email, a.password,
               MAX(CASE WHEN ac.key = 'accessToken' THEN ac.value END) AS accessToken,
               MAX(CASE WHEN ac.key = 'access_token' THEN ac.value END) AS access_token,
               MAX(CASE WHEN ac.key = 'refreshToken' THEN ac.value END) AS refreshToken,
               MAX(CASE WHEN ac.key = 'clientId' THEN ac.value END) AS clientId,
               MAX(CASE WHEN ac.key = 'clientSecret' THEN ac.value END) AS clientSecret,
               MAX(CASE WHEN ac.key = 'id_token' THEN ac.value END) AS id_token,
               MAX(CASE WHEN ac.key = 'legacy_token' THEN ac.value END) AS legacy_token
        FROM accounts a
        LEFT JOIN account_credentials ac ON a.id = ac.account_id AND ac.provider_name = ?
        WHERE a.platform = ?
        GROUP BY a.id
        """,
        (platform, platform),
    )
    rows = cur.fetchall()
    conn.close()

    accounts = []
    for row in rows:
        acc_id, email, password, access_token, access_token_alt, refresh_token, client_id, client_secret, id_token, legacy_token = row
        accounts.append({
            "id": acc_id,
            "email": email,
            "password": password,
            "accessToken": access_token or access_token_alt or "",
            "refreshToken": refresh_token or "",
            "clientId": client_id or "",
            "clientSecret": client_secret or "",
            "idToken": id_token or "",
            "legacyToken": legacy_token or "",
        })
    return accounts


def load_router_db(router_db_path: str) -> dict:
    """Load 9Router db.json."""
    with open(router_db_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_connection(acc: dict, platform: str) -> dict:
    """Build a 9Router providerConnection entry."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entry: dict[str, Any] = {
        "id": f"imported-{acc['id']}-{platform}",
        "provider": platform,
        "authType": "oauth",
        "name": f"Account {acc['id']}",
        "priority": 1,
        "isActive": True,
        "createdAt": now,
        "updatedAt": now,
        "testStatus": "untested",
        "backoffLevel": 0,
        "accessToken": acc["accessToken"],
        "refreshToken": acc.get("refreshToken", ""),
        "expiresAt": "1970-01-01T00:00:00.000Z",
        "email": acc["email"],
        "lastUsedAt": now,
        "consecutiveUseCount": 0,
    }

    if platform == "kiro":
        entry["providerSpecificData"] = {
            "clientId": acc.get("clientId", ""),
            "clientSecret": acc.get("clientSecret", ""),
            "authMethod": "builder-id",
            "provider": "BuilderId",
            "region": "us-east-1",
            "profileArn": None,
        }
    elif platform == "chatgpt" or platform == "codex":
        entry["provider"] = "codex"
        entry["providerSpecificData"] = {}
        if acc.get("idToken"):
            try:
                import base64
                payload = acc["idToken"].split(".")[1]
                payload += "=" * (-len(payload) % 4)
                decoded = json.loads(base64.b64decode(payload))
                entry["name"] = decoded.get("name", f"Account {acc['id']}")
            except Exception:
                pass

    return entry


def sync_platform(accounts: list[dict], router_data: dict, platform: str, dry_run: bool = False) -> dict:
    """Sync accounts to 9Router db.json, deduplicating by email."""
    connections = router_data.get("providerConnections", [])
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    existing_by_email: dict[str, int] = {}
    for i, conn in enumerate(connections):
        if conn.get("provider") == platform and conn.get("email"):
            existing_by_email[conn["email"].lower()] = i

    added = 0
    updated = 0
    skipped = 0
    results = []

    for acc in accounts:
        email = acc["email"]
        access_token = acc["accessToken"]

        if not access_token:
            skipped += 1
            results.append({"email": email, "action": "skipped", "reason": "missing accessToken"})
            continue

        idx = existing_by_email.get(email.lower())
        if idx is not None:
            if not dry_run:
                connections[idx]["accessToken"] = access_token
                if acc.get("refreshToken"):
                    connections[idx]["refreshToken"] = acc["refreshToken"]
                connections[idx]["updatedAt"] = now
            updated += 1
            results.append({"email": email, "action": "updated", "conn_id": connections[idx]["id"]})
        else:
            new_conn = build_connection(acc, platform)
            if not dry_run:
                connections.append(new_conn)
            added += 1
            results.append({"email": email, "action": "added", "conn_id": new_conn["id"]})

    router_data["providerConnections"] = connections

    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "total_processed": len(accounts),
        "details": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Sync any-auto-register platform accounts to 9Router")
    parser.add_argument("--platform", required=True, choices=["kiro", "chatgpt", "codex"], help="Platform to sync")
    parser.add_argument("--db", default="/root/src/any-auto-register/account_manager.db", help="any-auto-register DB path")
    parser.add_argument("--router-db", default="/root/src/9router-data/db.json", help="9Router db.json path")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    accounts = load_platform_accounts(args.db, args.platform)
    if not accounts:
        print(f"⚠️  No {args.platform} accounts found in {args.db}")
        sys.exit(1)

    router_data = load_router_db(args.router_db)

    print(f"Loaded {len(accounts)} {args.platform} accounts from any-auto-register")
    print(f"9Router has {len([c for c in router_data.get('providerConnections', []) if c.get('provider') == args.platform])} existing {args.platform} connections")
    if args.dry_run:
        print("🔍 DRY RUN — no changes will be written\n")
    else:
        print(f"Syncing to {args.router_db}...\n")

    result = sync_platform(accounts, router_data, args.platform, dry_run=args.dry_run)

    print(f"\n{'='*60}")
    print(f"Sync Summary ({'DRY RUN' if args.dry_run else 'LIVE'})")
    print(f"{'='*60}")
    print(f"  Added:    {result['added']}")
    print(f"  Updated:  {result['updated']}")
    print(f"  Skipped:  {result['skipped']}")
    print(f"  Total:    {result['total_processed']}")

    if not args.dry_run:
        with open(args.router_db, "w", encoding="utf-8") as f:
            json.dump(router_data, f, indent=4, ensure_ascii=False)
        print(f"\n✅ 9Router db.json updated: {args.router_db}")
    else:
        print(f"\n🔍 DRY RUN complete — no files written")


if __name__ == "__main__":
    main()
