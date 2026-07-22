#!/usr/bin/env python3
"""
Resolve a linux64 chromedriver zip URL when the primary storage.googleapis.com
URL for the installed Chrome version is missing (404).

Reads Chrome version from `google-chrome --version` and uses official
known-good-versions-with-downloads.json (exact match, then same-major newest).
"""
import json
import subprocess
import sys
import urllib.request
from typing import Optional, Tuple

KNOWN_GOOD_JSON = (
    "https://googlechromelabs.github.io/chrome-for-testing/"
    "known-good-versions-with-downloads.json"
)


def chrome_version() -> str:
    out = subprocess.check_output(["google-chrome", "--version"], text=True)
    return out.split()[2]


def linux64_chromedriver_url(entry: dict) -> Optional[str]:
    for d in entry.get("downloads", {}).get("chromedriver", []):
        if d.get("platform") == "linux64":
            return d["url"]
    return None


def main() -> None:
    target = chrome_version()

    with urllib.request.urlopen(KNOWN_GOOD_JSON, timeout=180) as resp:
        data = json.load(resp)

    for entry in data.get("versions", []):
        if entry.get("version") == target:
            u = linux64_chromedriver_url(entry)
            if u:
                print(u)
                return

    major = target.split(".")[0]
    best_key: Optional[Tuple[int, ...]] = None
    best_url: Optional[str] = None
    for entry in data.get("versions", []):
        v = entry.get("version") or ""
        if not v.startswith(major + "."):
            continue
        u = linux64_chromedriver_url(entry)
        if not u:
            continue
        parts: list[int] = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        while len(parts) < 4:
            parts.append(0)
        key = tuple(parts)
        if best_key is None or key > best_key:
            best_key, best_url = key, u

    if best_url:
        print(best_url)
        return

    print(
        f"Could not resolve chromedriver URL for Chrome {target}.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
