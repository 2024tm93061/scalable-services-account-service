#!/usr/bin/env python3
import os
import sys
import time
import requests

BASE = os.environ.get("BASE_URL", "http://localhost:8000")


def wait_for_health(timeout=30):
    url = f"{BASE}/health"
    start = time.time()
    while True:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                print("service healthy")
                return True
        except Exception:
            pass
        if time.time() - start > timeout:
            print("service did not become healthy within timeout", file=sys.stderr)
            return False
        time.sleep(0.5)


def get_account(account_id):
    r = requests.get(f"{BASE}/accounts/{account_id}")
    return r.status_code, r.json() if r.content else None


def do_transfer(frm, to, amount):
    payload = {"from_account": frm, "to_account": to, "amount": float(amount)}
    r = requests.post(f"{BASE}/transfer", json=payload)
    return r.status_code, r.json() if r.content else None


def change_status(account_id, status):
    r = requests.post(f"{BASE}/accounts/{account_id}/status", json={"status": status})
    return r.status_code, r.json() if r.content else None


def main():
    print("Base URL:", BASE)
    if not wait_for_health():
        sys.exit(1)

    # Check an existing seeded account
    sid = 1
    code, body = get_account(sid)
    print(f"GET /accounts/{sid}", code, body)

    # Transfer a small amount (should succeed)
    print("Performing small transfer 1 -> 3 (100.0)")
    code, body = do_transfer(1, 3, 100.0)
    print("POST /transfer", code, body)

    # Check balances after transfer
    for a in (1, 3):
        code, body = get_account(a)
        print(f"after /accounts/{a}", code, body)

    # Attempt to transfer from a frozen account (account 2 in the sample CSV is FROZEN)
    print("Attempt transfer from frozen account 2 -> 3 (1.0) — expect failure")
    code, body = do_transfer(2, 3, 1.0)
    print("POST /transfer (frozen)", code, body)

    # Attempt a transfer that likely exceeds the daily limit (very large)
    print("Attempt large transfer 1 -> 3 (1e9) — expect failure for limit")
    code, body = do_transfer(1, 3, 1e9)
    print("POST /transfer (large)", code, body)

    print("Test run completed.")


if __name__ == "__main__":
    main()
