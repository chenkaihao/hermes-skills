#!/usr/bin/env python3
"""
Preflight check for any-auto-register environment.
Verifies all dependencies before starting registration tasks.
"""

import os
import sys
import sqlite3
import subprocess
from pathlib import Path

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def ok(msg):
    print(f"{GREEN}✅{RESET} {msg}")

def fail(msg):
    print(f"{RED}❌{RESET} {msg}")

def warn(msg):
    print(f"{YELLOW}⚠️{RESET} {msg}")

def check_xvfb():
    """Check Xvfb installation and running status."""
    print("\n=== Xvfb Check ===")
    
    # Check if Xvfb is installed
    try:
        subprocess.run(["which", "Xvfb"], check=True, capture_output=True)
        ok("Xvfb is installed")
    except subprocess.CalledProcessError:
        fail("Xvfb is not installed")
        print("  Fix: apt-get update && apt-get install -y xvfb")
        return False
    
    # Check if Xvfb is running
    try:
        result = subprocess.run(["pgrep", "-x", "Xvfb"], capture_output=True, text=True)
        if result.returncode == 0:
            ok(f"Xvfb is running (PID: {result.stdout.strip()})")
        else:
            warn("Xvfb is not running")
            print("  Fix: Xvfb :99 -screen 0 1920x1080x24 -ac &")
    except Exception as e:
        fail(f"Cannot check Xvfb: {e}")
    
    # Check DISPLAY variable
    display = os.environ.get("DISPLAY", "")
    if display == ":99":
        ok(f"DISPLAY={display}")
    elif display:
        warn(f"DISPLAY={display} (expected :99)")
    else:
        fail("DISPLAY is not set")
        print("  Fix: export DISPLAY=:99")
    
    return True

def check_service():
    """Check any-auto-register service status."""
    print("\n=== Service Check ===")
    
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "any-auto-register"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            ok(f"Service is running: {result.stdout.strip()}")
        else:
            fail(f"Service is not running: {result.stdout.strip()}")
            print("  Fix: systemctl start any-auto-register")
            return False
    except Exception as e:
        fail(f"Cannot check service: {e}")
        return False
    
    return True

def check_database():
    """Check database connection and configuration."""
    print("\n=== Database Check ===")
    
    db_path = "/root/src/any-auto-register/account_manager.db"
    if not Path(db_path).exists():
        fail(f"Database not found: {db_path}")
        return False
    
    ok(f"Database exists: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        ok(f"Tables: {', '.join(tables)}")
        
        # Check proxies
        cursor.execute("SELECT id, url, is_active FROM proxies")
        proxies = cursor.fetchall()
        if proxies:
            for p in proxies:
                status = "active" if p[2] else "inactive"
                print(f"  Proxy {p[0]}: {p[1]} ({status})")
        else:
            warn("No proxies configured")
        
        # Check SMS providers
        cursor.execute(
            "SELECT provider_key, config_json FROM provider_settings WHERE provider_type='sms'"
        )
        sms_providers = cursor.fetchall()
        if sms_providers:
            for p in sms_providers:
                print(f"  SMS: {p[0]} → {p[1]}")
        else:
            warn("No SMS providers configured")
        
        conn.close()
        return True
        
    except Exception as e:
        fail(f"Database error: {e}")
        return False

def check_api():
    """Check API endpoint availability."""
    print("\n=== API Check ===")
    
    try:
        import requests
        resp = requests.get("http://localhost:8000/api/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            ok(f"API is healthy: {data.get('service', 'unknown')}")
            return True
        else:
            fail(f"API returned {resp.status_code}")
            return False
    except Exception as e:
        fail(f"Cannot connect to API: {e}")
        print("  Fix: Ensure service is running and port 8000 is accessible")
        return False

def main():
    print("=" * 60)
    print("any-auto-register Preflight Check")
    print("=" * 60)
    
    checks = [
        ("Xvfb", check_xvfb),
        ("Service", check_service),
        ("Database", check_database),
        ("API", check_api),
    ]
    
    results = {}
    for name, check_fn in checks:
        try:
            results[name] = check_fn()
        except Exception as e:
            fail(f"{name} check crashed: {e}")
            results[name] = False
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_ok = True
    for name, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  {name}: {status}")
        if not passed:
            all_ok = False
    
    if all_ok:
        print(f"\n{GREEN}✅ All checks passed!{RESET}")
        sys.exit(0)
    else:
        print(f"\n{RED}❌ Some checks failed. Please fix the issues above.{RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
