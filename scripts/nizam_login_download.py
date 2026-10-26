"""Download regulation PDFs from the Nizam platform (imamu.edu.sa/laws) after a manual login.

The platform only serves regulation files to signed-in users. This script opens a
visible Edge window (Playwright, persistent profile in .crawl_browser_profile/,
which is git-ignored). The user signs in there themselves; the script never sees
or stores the password. Once the page reports a signed-in user, the script uses
that browser session to download the in-scope regulation files into
raw_university_docs/regulations/ and appends them to INDEX.csv and SUMMARY.md.

Usage:
    python scripts/nizam_login_download.py [--out raw_university_docs]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_university import FOCUS_LAWS, sanitize  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / ".crawl_browser_profile"
LAWS = "https://imamu.edu.sa/laws/"
HANDLER = "https://imamu.edu.sa/laws/_layouts/15/2016/Laws/Handlers/LawsGeneralHandler.ashx"
FILES = "https://fdf.imamu.edu.sa/Regfiles/"
FIELDS = ["category", "file_name", "title", "source_url", "referring_page", "file_type", "size_bytes",
          "sha256", "downloaded_at"]
LOGGED_IN_JS = """() => (typeof _spPageContextInfo !== 'undefined' && _spPageContextInfo.isAnonymousUser === false)
                     || (typeof isLoggedIn !== 'undefined' && isLoggedIn === true)"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_json(page, params: dict):
    url = HANDLER + "?" + urlencode(params)
    time.sleep(1.0)  # politeness
    txt = page.evaluate("async (u) => (await fetch(u, {headers: {Accept: 'application/json'}})).text()", url)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


def wait_for_login(ctx, timeout_min: int = 30):
    print("A browser window is open on the Nizam platform. Please sign in there.", flush=True)
    end = time.time() + timeout_min * 60
    while time.time() < end:
        for p in ctx.pages:
            try:
                if "imamu.edu.sa" in p.url and p.evaluate(LOGGED_IN_JS):
                    print("Login detected.", flush=True)
                    return p
            except Exception:
                pass  # page navigating
        time.sleep(3)
    raise SystemExit("Timed out waiting for login.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "raw_university_docs"))
    ap.add_argument("--wait-crawl-min", type=int, default=120,
                    help="wait for the crawler to finish writing SUMMARY.md before updating the index")
    a = ap.parse_args()
    out = Path(a.out)
    regdir = out / "regulations"

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(PROFILE), channel="msedge", headless=False,
                                                    accept_downloads=True, locale="ar-SA")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LAWS, wait_until="domcontentloaded")
        page = wait_for_login(ctx)
        if "/laws" not in page.url.lower():
            page.goto(LAWS, wait_until="domcontentloaded")

        # 1. list regulations
        regs, n = [], 1
        while True:
            data = fetch_json(page, {"action": "advsearch", "accMode": "G", "modiMode": "G", "notiMode": "G",
                                     "searchText": "", "benef": "-1", "accNumber": "", "cId": "-1",
                                     "statusId": "-1", "fromAcc": "", "toAcc": "", "fromNoti": "", "toNoti": "",
                                     "fromModi": "", "toModi": "", "pageNumber": n, "pageSize": 12})
            if not isinstance(data, list) or not data:
                break
            regs += data
            if n * 12 >= (data[0].get("TotalRows") or 0):
                break
            n += 1
        live = [g for g in regs if g.get("StatusId") == 0 and FOCUS_LAWS.search(g.get("Name") or "")]
        print(f"{len(regs)} regulations listed, {len(live)} in force and in scope by name", flush=True)

        # 2. download files
        got, failed = [], []
        for g in live:
            rid, name = g["Id"], g.get("Name") or f"regulation {g['Id']}"
            d = fetch_json(page, {"action": "getregulationbyid", "itemid": rid})
            d = d[0] if isinstance(d, list) and d else {}
            benef, cls = d.get("Beneficiaries") or "", d.get("ClassificationTxt") or ""
            if not ("الطلاب" in benef or "أكاديمية" in cls):
                continue
            info = fetch_json(page, {"action": "getregulationfilebyregulationid", "itemid": rid, "type": 1})
            if not isinstance(info, list) or not info or not info[0].get("URL"):
                failed.append((name, "no file listed"))
                continue
            url = FILES + info[0]["URL"]
            time.sleep(1.0)
            r = ctx.request.get(url, timeout=120000)
            body = r.body() if r.ok else b""
            if not r.ok or body[:300].lower().lstrip().startswith((b"<!doctype", b"<html")):
                failed.append((name, f"HTTP {r.status}"))
                continue
            ext = Path(info[0]["URL"]).suffix.lstrip(".").lower() or "pdf"
            got.append({"name": name, "rid": rid, "url": url, "ext": ext, "data": body})
            print(f"[downloaded] {name} ({len(body)} bytes)", flush=True)
        ctx.close()

    # 3. wait for the crawler to finish, then add the files
    end = time.time() + a.wait_crawl_min * 60
    while not (out / "SUMMARY.md").exists() and time.time() < end:
        time.sleep(10)
    idx = out / "INDEX.csv"
    known = set()
    if idx.exists():
        with open(idx, encoding="utf-8-sig") as f:
            known = {row["sha256"] for row in csv.DictReader(f)}
    regdir.mkdir(parents=True, exist_ok=True)
    rows, scanned = [], []
    for item in got:
        h = hashlib.sha256(item["data"]).hexdigest()
        if h in known:
            continue
        known.add(h)
        fname = f"{sanitize(item['name'], 100)}.{item['ext']}"
        (regdir / fname).write_bytes(item["data"])
        rows.append({"category": "regulations", "file_name": f"regulations/{fname}", "title": item["name"],
                     "source_url": item["url"],
                     "referring_page": f"https://imamu.edu.sa/Laws/Pages/UCDetails.aspx?rid={item['rid']}&flag=true",
                     "file_type": item["ext"], "size_bytes": len(item["data"]), "sha256": h,
                     "downloaded_at": now_iso()})
        if PdfReader is not None and item["ext"] == "pdf":
            try:
                rd = PdfReader(io.BytesIO(item["data"]))
                chars = sum(len((p.extract_text() or "").strip()) for p in rd.pages[:5])
                if chars < 40 * max(1, min(5, len(rd.pages))):
                    scanned.append(fname)
            except Exception:
                scanned.append(fname + " (unreadable)")
    new_file = not idx.exists()
    with open(idx, "a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(rows)
    lines = ["", "## Regulation files downloaded after login (منصة نظام)", "",
             f"- Downloaded {len(rows)} files into regulations/ (the public-text .md versions are kept too).",
             "- Scanned (need scripts/ocr_pdf.py): " + (", ".join(scanned) or "none")]
    lines += [f"- Failed: {n} — {e}" for n, e in failed]
    with open(out / "SUMMARY.md", "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"done: {len(rows)} regulation files added, {len(failed)} failed", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
