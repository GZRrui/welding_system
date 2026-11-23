"""Verify the deployed HTTPS API against the Windows model release's golden cases."""

import argparse
import csv
import io
import json
import math
import time
from getpass import getpass
from pathlib import Path

import httpx


def assert_close(actual, expected):
    if isinstance(expected, bool):
        assert actual is expected, (actual, expected)
    elif isinstance(expected, (int, float)):
        assert math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-12), (actual, expected)
    elif isinstance(expected, dict):
        for key, value in expected.items():
            assert_close(actual[key], value)
    elif isinstance(expected, list):
        assert len(actual) == len(expected), (len(actual), len(expected))
        for found, wanted in zip(actual, expected, strict=True):
            assert_close(found, wanted)
    else:
        assert actual == expected, (actual, expected)


def run(url, expected, password, wait_seconds, ssl_ca=None):
    import ssl

    verification = ssl.create_default_context(cafile=ssl_ca) if ssl_ca else True
    with httpx.Client(base_url=url.rstrip("/") + "/api/v1/", verify=verification, timeout=20) as browser:
        def api(method, path, **kwargs):
            return browser.request(method, path, **kwargs).raise_for_status().json()

        assert browser.get("history").status_code == 401
        session = api("POST", "auth/login", json={"username": "admin", "password": password})
        browser.headers["X-CSRF-Token"] = session["csrf_token"]
        ids = []
        try:
            for model, result in expected["predictions"].items():
                observed = api("POST", "predict", json={"model": model, "current": expected["current"]})
                assert_close(observed, result)
                ids.append(observed["id"])
            task_id = api("POST", "tasks", json=expected["search"])["id"]
            deadline = time.monotonic() + wait_seconds
            while True:
                task = api("GET", f"tasks/{task_id}")
                if task["status"] not in {"queued", "running"} or time.monotonic() >= deadline:
                    break
                time.sleep(1)
            assert task["status"] == "completed", task
            assert_close(task["result"]["recommendations"], expected["recommendations"])
            exported = browser.get(f"tasks/{task_id}/exports/all_candidates").raise_for_status().text
            candidates = list(csv.DictReader(io.StringIO(exported)))
            assert len(candidates) == len(expected["candidates"])
            for row, reference in zip(candidates, expected["candidates"], strict=True):
                for key, value in reference.items():
                    observed = row[key]
                    if isinstance(value, bool):
                        assert observed.lower() == str(value).lower()
                    elif isinstance(value, (int, float)):
                        assert_close(float(observed), value)
                    else:
                        assert_close(observed, value)
            for rid in [*ids, task_id]:
                assert api("GET", f"tasks/{rid}")["id"] == rid
        finally:
            api("POST", "auth/logout")
        assert browser.get("history").status_code == 401
        return {"predictions": ids, "recommendation": task_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("golden", type=Path)
    parser.add_argument("--ca")
    parser.add_argument("--wait-seconds", type=int, default=240)
    args = parser.parse_args()
    if not args.url.startswith("https://"):
        parser.error("Use an HTTPS URL")
    model = json.loads(args.golden.read_text(encoding="utf-8"))
    print(json.dumps(run(args.url, model, getpass("Admin password: "), args.wait_seconds, args.ca)))


if __name__ == "__main__":
    main()
