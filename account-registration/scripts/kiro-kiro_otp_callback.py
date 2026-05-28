#!/usr/bin/env python3
"""Reusable OTP callback for qhvip.cc Kiro accounts using CF Worker email API.

Usage:
    from kiro_otp_callback import build_otp_callback

    cb = build_otp_callback("calebzhang88@qhvip.cc")
    otp = cb()  # Blocks up to 120s, returns 6-digit code or None

    # Or integrate with KiroBrowserLogin:
    from platforms.kiro.browser_register import KiroBrowserLogin
    login = KiroBrowserLogin(headless=True, proxy=proxy, otp_callback=cb)
    result = login.run(email, password)
"""

import os
import re
import time
import quopri

import requests

# --- Configuration ---
# Override via environment or edit inline
API_URL = os.environ.get("KIRO_CFWORKER_API_URL", "https://temp-email.khchen1985.workers.dev")
ADMIN_TOKEN = os.environ.get("KIRO_CFWORKER_ADMIN_TOKEN", "kiro2024!@")
OTP_TIMEOUT = int(os.environ.get("KIRO_OTP_TIMEOUT", "120"))


def _fetch_mails(email: str, limit: int = 10) -> list[dict]:
    """Fetch recent mails for an address from CF Worker API."""
    r = requests.get(
        f"{API_URL}/admin/mails",
        params={"limit": limit, "offset": 0, "address": email},
        headers={"x-admin-auth": ADMIN_TOKEN},
        timeout=10,
    )
    if r.status_code != 200:
        return []
    data = r.json()
    if isinstance(data, dict):
        return data.get("results", data.get("data", [])) or []
    return data if isinstance(data, list) else []


def _extract_otp(raw: str) -> str | None:
    """Extract 6-digit OTP from raw email content."""
    # Decode quoted-printable
    try:
        decoded = quopri.decodestring(raw.encode()).decode("utf-8", errors="replace")
    except Exception:
        decoded = raw

    patterns = [
        r'验证码[:\uFF1A]\s*(\d{6})',
        r'verification code is:?\s*(\d{6})',
        r'Verification code:?\s*(\d{6})',
        r'>\s*(\d{6})\s*<',
        r'\b(\d{6})\b',
    ]
    for pat in patterns:
        m = re.search(pat, decoded, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def build_otp_callback(email: str, verbose: bool = True):
    """Build an OTP callback function for the given email.

    The returned function polls the CF Worker email API for
    new AWS verification emails. It skips emails that existed
    before the callback was created (to avoid stale OTPs).

    Args:
        email: The qhvip.cc email address to check
        verbose: Whether to print status messages

    Returns:
        A callable that returns a 6-digit OTP string or None on timeout.
    """

    def log(msg: str):
        if verbose:
            print(f"  [otp] {msg}")

    # Snapshot existing emails
    seen_ids: set[str] = set()
    try:
        for mail in _fetch_mails(email, limit=50):
            mid = mail.get("id")
            if mid:
                seen_ids.add(str(mid))
    except Exception:
        pass

    log(f"已记录 {len(seen_ids)} 封已有邮件")

    def _poll() -> str | None:
        nonlocal seen_ids
        start = time.time()
        while time.time() - start < OTP_TIMEOUT:
            try:
                mails = _fetch_mails(email, limit=10)
                for mail in sorted(mails, key=lambda x: str(x.get("id", 0)), reverse=True):
                    mid = str(mail.get("id", ""))
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)

                    raw = mail.get("raw", "")
                    code = _extract_otp(raw)
                    if code:
                        log(f"✅ 找到验证码: {code}")
                        return code

                    subject = mail.get("subject", "") or ""
                    log(f"新邮件 mid={mid}, subject={subject[:50]}, 未找到验证码")

            except Exception as e:
                log(f"查询异常: {e}")

            elapsed = int(time.time() - start)
            if elapsed % 15 == 0:
                log(f"等待... ({elapsed}s)")
            time.sleep(3)

        log("❌ OTP 超时")
        return None

    return _poll


# --- Self-test ---
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <email@qhvip.cc>")
        sys.exit(1)

    test_email = sys.argv[1]
    if "@" not in test_email:
        print("Error: Provide full email address")
        sys.exit(1)

    print(f"Testing OTP callback for {test_email}")
    cb = build_otp_callback(test_email, verbose=True)
    code = cb()
    if code:
        print(f"\nOTP: {code}")
    else:
        print("\nNo OTP found (timeout)")
        sys.exit(1)
