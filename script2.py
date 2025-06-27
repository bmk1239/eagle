#!/usr/bin/env python3
"""
generate_epg.py  –  FreeTV one-day XMLTV generator (Option A)

• Reads channels.xml in the same directory.
• Fetches programmes for 00:00–24:00 (Asia/Jerusalem) on the day the script runs.
• Beats Cloudflare automatically with cloudscraper.
• Uses the Israel proxy in $IL_PROXY.
• Loads a base64-encoded PEM root certificate from $IL_PROXY_CA_B64 and
  adds it to the trust store, so TLS validation stays intact.

Dependencies (pip):  requests  cloudscraper
Python ≥ 3.9 (for zoneinfo & ET.indent).
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import tempfile
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import cloudscraper                      # handles Cloudflare JS challenge
from requests.exceptions import HTTPError


# ONE command – produces ONE long line
base64 -w0 proxy_root_ca.pem > ca.b64          # Linux/macOS
# or PowerShell:
# [Convert]::ToBase64String([IO.File]::ReadAllBytes("proxy_root_ca.pem")) > ca.b64
python - <<'PY'
import base64, sys
b = open("ca.b64").read().strip()
try:
    base64.b64decode(b, validate=True)
    print("✔ looks like valid base-64 (length:", len(b), ")")
except Exception as e:
    print("✘ not valid base-64:", e)
PY
# ──────────────────────────────────────────────────────────────────────────────
API_URL   = "https://web.freetv.tv/api/products/lives/programmes"
SITE_HOME = "https://web.freetv.tv/"
IL_TZ     = ZoneInfo("Asia/Jerusalem")

CHANNELS_FILE = "channels.xml"
OUT_XML       = "freetv_epg.xml"

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0)"
                  " Gecko/20100101 Firefox/126.0",
    "Accept":     "application/json, text/plain, */*",
    "Origin":     "https://web.freetv.tv",
    "Referer":    "https://web.freetv.tv/",
}
# ──────────────────────────────────────────────────────────────────────────────


def day_window(now_il: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(now_il.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)


def configure_session():
    """Return a cloudscraper.Session configured with proxy and custom CA."""
    sess = cloudscraper.create_scraper()   # requests-compatible
    sess.headers.update(BASE_HEADERS)

    # ── Proxy (required) ────────────────────────────────────────────────────
    if proxy := os.getenv("IL_PROXY"):
        sess.proxies = {"http": proxy, "https": proxy}
        print("[info] Using Israel proxy")

    # ── Custom CA bundle (required for TLS pass-through proxy) ──────────────
    b64_pem = os.getenv("IL_PROXY_CA_B64")
    if not b64_pem:
        raise RuntimeError("IL_PROXY_CA_B64 secret is missing!")

    # base64 must be correctly padded; fail fast if it isn't
    pem_bytes = base64.b64decode(b64_pem, validate=True)
    ca_file = Path(tempfile.gettempdir()) / "proxy_root_ca.pem"
    ca_file.write_bytes(pem_bytes)
    sess.verify = str(ca_file)
    print(f"[info] Custom CA loaded ➜ {ca_file}")

    # ── Optional: site login cookies (geo-blocked channels) ────────────────
    if cookies := os.getenv("IL_FTV_COOKIES"):
        sess.headers["Cookie"] = cookies
        print("[info] Injected user cookies")

    return sess


def fetch_programmes(sess, site_id: str, start: dt.datetime, end: dt.datetime):
    """Call FreeTV API for one channel, retrying once after Cloudflare solve."""
    params = {
        "liveId[]": site_id,
        "since": start.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  end.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }
    for attempt in (1, 2):
        r = sess.get(API_URL, params=params, timeout=30)
        try:
            r.raise_for_status()
            data = r.json()
            return data.get("data", data) if isinstance(data, dict) else data
        except HTTPError as exc:
            if r.status_code == 403 and attempt == 1:
                # First call failed – trigger Cloudflare solve & retry
                sess.get(SITE_HOME, timeout=20)
                continue
            raise exc


def build_epg():
    now_il = dt.datetime.now(IL_TZ)
    start, end = day_window(now_il)
    sess = configure_session()

    root = ET.Element("tv", {
        "source-info-name": "FreeTV",
        "generator-info-name": "FreeTV-EPG (proxy-CA)",
    })

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site_id  = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name     = (ch.text or xmltv_id).strip()

        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        try:
            for p in fetch_programmes(sess, site_id, start, end):
                s = dt.datetime.fromisoformat(p["start"]).astimezone(IL_TZ)
                e = dt.datetime.fromisoformat(p["end"]).astimezone(IL_TZ)
                prog = ET.SubElement(
                    root, "programme",
                    start=s.strftime("%Y%m%d%H%M%S %z"),
                    stop=e.strftime("%Y%m%d%H%M%S %z"),
                    channel=xmltv_id,
                )
                ET.SubElement(prog, "title", lang="he").text = escape(p.get("name", ""))
                if desc := (p.get("description") or p.get("summary") or ""):
                    ET.SubElement(prog, "desc", lang="he").text = escape(desc)
        except Exception as exc:
            print(f"[warn] {name}: {exc}")

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print(f"✅ Wrote {OUT_XML}")


if __name__ == "__main__":
    build_epg()
