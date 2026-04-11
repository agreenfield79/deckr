"""
Deckr Backend Smoke Test
------------------------
Requires the backend server to already be running:
    cd backend
    python main.py        (or: uvicorn main:app --reload)

Usage:
    python smoke_test.py
    python smoke_test.py --base-url http://localhost:8000

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""

import argparse
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run: pip install requests")
    sys.exit(1)

# Use 127.0.0.1 directly — avoids Windows IPv6 (::1) resolution delay on "localhost"
BASE_URL = "http://127.0.0.1:8000"

CHECKS = [
    {
        "label": "GET /api/health — server reachable + config complete",
        "method": "GET",
        "path": "/api/health",
        "expect_status": 200,
        "assert": lambda r: (
            r.json().get("status") == "ok"
            and all(
                v == "set"
                for k, v in r.json().get("config", {}).items()
                if k in {"IBMCLOUD_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL"}
            )
        ),
        "assert_msg": 'status == "ok" and all credential keys are "set"',
    },
    {
        "label": "GET /api/workspace/tree — workspace router registered",
        "method": "GET",
        "path": "/api/workspace/tree",
        "expect_status": 200,
        "assert": None,
        "assert_msg": "200 OK",
    },
    {
        "label": "GET /api/agent/registry — agent router registered",
        "method": "GET",
        "path": "/api/agent/registry",
        "expect_status": 200,
        "assert": None,
        "assert_msg": "200 OK",
    },
    {
        "label": "GET /api/status — status router registered",
        "method": "GET",
        "path": "/api/status",
        "expect_status": 200,
        "assert": None,
        "assert_msg": "200 OK",
    },
]

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def run(base_url: str) -> int:
    print(f"\n{BOLD}Deckr Backend Smoke Test{RESET}")
    print(f"Target: {base_url}\n")
    print(f"{'Check':<55} {'Status':<8} {'ms':<8} Result")
    print("─" * 100)

    failures = 0

    for check in CHECKS:
        url = base_url + check["path"]
        start = time.monotonic()
        try:
            resp = getattr(requests, check["method"].lower())(url, timeout=5)
            elapsed = int((time.monotonic() - start) * 1000)

            status_ok = resp.status_code == check["expect_status"]
            assert_ok = check["assert"](resp) if (check["assert"] and status_ok) else status_ok

            if status_ok and assert_ok:
                mark = f"{GREEN}PASS{RESET}"
            else:
                mark = f"{RED}FAIL{RESET}"
                failures += 1

            status_display = f"{resp.status_code}"
            print(f"{check['label']:<55} {status_display:<8} {elapsed:<8} {mark}")

            if not status_ok:
                print(f"  {YELLOW}→ expected {check['expect_status']}, got {resp.status_code}{RESET}")
            elif not assert_ok:
                print(f"  {YELLOW}→ assertion failed: {check['assert_msg']}{RESET}")
                try:
                    print(f"  {YELLOW}→ response: {resp.json()}{RESET}")
                except Exception:
                    pass

        except requests.exceptions.ConnectionError:
            elapsed = int((time.monotonic() - start) * 1000)
            print(f"{check['label']:<55} {'ERR':<8} {elapsed:<8} {RED}FAIL{RESET}")
            print(f"  {YELLOW}→ Connection refused. Is the server running at {base_url}?{RESET}")
            failures += 1
        except requests.exceptions.Timeout:
            elapsed = int((time.monotonic() - start) * 1000)
            print(f"{check['label']:<55} {'ERR':<8} {elapsed:<8} {RED}FAIL{RESET}")
            print(f"  {YELLOW}→ Request timed out after 5s{RESET}")
            failures += 1

    print("─" * 100)
    total = len(CHECKS)
    passed = total - failures

    if failures == 0:
        print(f"\n{GREEN}{BOLD}All {total} checks passed.{RESET}\n")
    else:
        print(f"\n{RED}{BOLD}{failures}/{total} checks failed.{RESET}\n")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deckr backend smoke test")
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"Base URL of the running backend (default: {BASE_URL}). Use 127.0.0.1 not localhost on Windows.",
    )
    args = parser.parse_args()
    sys.exit(run(args.base_url))
