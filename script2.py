#!/usr/bin/env python3
"""
Generate a one-day XMLTV guide from FreeTV, using an Israel proxy and a
custom root-CA that’s stored in GitHub Secrets as IL_PROXY_CA_B64.

🆕 2025-06-28
• Removed all per-channel try/except blocks.
• All warnings are now treated as errors, so even SSL warnings stop the run.
• Any exception anywhere ends the process with a non-zero exit status.
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import tempfile
import warnings
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import cloudscraper
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
import ssl
from urllib3.util.ssl_ import create_urllib3_context

# ────────────────────────── helpers ───────────────────────────

import urllib3                            # ← import the library first
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DEBUG = os.getenv("DEBUG", "1") not in ("0", "false", "False", "no", "NO")

def dbg(msg: str):
    if _DEBUG:
        print(f"[dbg] {msg}")

# ──────────────────────── custom adapter ──────────────────────

class InsecureTunnel(HTTPAdapter):
    """FOR *testing* ONLY – turns off all cert checks."""
    def _new_ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False          # 1️⃣ order matters
        ctx.verify_mode    = ssl.CERT_NONE  # 2️⃣
        return ctx
    def init_poolmanager(self, *a, **kw):
        kw["ssl_context"] = self._new_ctx()
        return super().init_poolmanager(*a, **kw)
    def proxy_manager_for(self, *a, **kw):
        kw["ssl_context"] = self._new_ctx()
        return super().proxy_manager_for(*a, **kw)

# ────────────────────────── constants ───────────────────────────
API_URL   = "https://web.freetv.tv/api/products/lives/programmes"
SITE_HOME = "https://web.freetv.tv/"
IL_TZ     = ZoneInfo("Asia/Jerusalem")

CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

BASE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
                   "Gecko/20100101 Firefox/126.0"),
    "Accept":   "application/json, text/plain, */*",
    "Origin":   "https://web.freetv.tv",
    "Referer":  "https://web.freetv.tv/",
}
# ─────────────────────────────────────────────────────────────────

# Treat every warning as an exception so the script aborts even on SSLWarnings
warnings.filterwarnings("error")

def day_window(now_il: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """Return the UTC span of the requested IL calendar day."""
    start = dt.datetime.combine(now_il.date(), dt.time.min, tzinfo=IL_TZ)
    dbg(f"day_window: {start.isoformat()} → {(start + dt.timedelta(days=1)).isoformat()}")
    return start, start + dt.timedelta(days=1)


def configure_session():
    """Create a cloudscraper session routed through IL proxy.
       TLS validation is skipped if IL_PROXY_INSECURE=true."""
    dbg("Creating CloudScraper session …")
    sess = cloudscraper.create_scraper()
    sess.mount("https://", InsecureTunnel())
    sess.headers.update(BASE_HEADERS)

    # ---- proxy (required) ----------------------------------
    proxy = os.getenv("IL_PROXY")
    if not proxy:
        raise RuntimeError("IL_PROXY secret is missing!")
    sess.proxies = {"http": proxy, "https": proxy}
    print("[info] Using Israel proxy")
    dbg(f"Proxy URL: {proxy}")

    # ---- Disable TLS checks if flag present ----------------
    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        sess.verify = False
        # the warning will now raise, so announce why we’re ignoring it
        print("[warn] SSL verification DISABLED (IL_PROXY_INSECURE)")

    # ---- Optional login cookies ----------------------------
    if coco := os.getenv("IL_FTV_COOKIES"):
        sess.headers["Cookie"] = coco
        print("[info] Injected user cookies")

    dbg("Session headers: " + str({k: v for k, v in sess.headers.items() if k != "Cookie"}))
    return sess


def fetch_programmes(sess, site_id, start: dt.datetime, end: dt.datetime):
    params = {
        "liveId[]": site_id,
        "since": start.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  end.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }
    dbg(f"Fetching programmes for site_id={site_id} between {params['since']} and {params['till']}")
    for attempt in (1, 2):
        dbg(f"HTTP GET attempt {attempt} …")
        r = sess.get(API_URL, params=params, timeout=30)
        dbg(f"Status {r.status_code}; URL: {r.url}")
        try:
            r.raise_for_status()
            data = r.json()
            programmes = data.get("data", data) if isinstance(data, dict) else data
            dbg(f"Fetched {len(programmes)} items")
            return programmes
        except HTTPError as exc:
            dbg(f"HTTPError: {exc}; response text: {r.text[:250]}")
            if r.status_code == 403 and attempt == 1:
                dbg("Attempting Cloudflare challenge bypass …")
                sess.get(SITE_HOME, timeout=20)
                continue
            raise  # re-raise → abort script immediately


def build_epg():
    now_il = dt.datetime.now(IL_TZ)
    dbg(f"Current IL time: {now_il.isoformat()}")
    start, end = day_window(now_il)
    sess = configure_session()

    root = ET.Element("tv", {
        "source-info-name": "FreeTV",
        "generator-info-name": "FreeTV-EPG (proxy-CA)",
    })

    channels_tree = ET.parse(CHANNELS_FILE)
    channels = channels_tree.findall("channel")
    dbg(f"Loaded {len(channels)} channels from {CHANNELS_FILE}")

    for ch in channels:
        site_id  = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name     = (ch.text or xmltv_id).strip()

        dbg(f"\nProcessing channel '{name}' (site_id={site_id}, xmltv_id={xmltv_id})")

        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        # 🚨 No try/except here – any failure kills the entire run
        programmes = fetch_programmes(sess, site_id, start, end)

        for p in programmes:
            s = dt.datetime.fromisoformat(p["start"]).astimezone(IL_TZ)
            e = dt.datetime.fromisoformat(p["end"]).astimezone(IL_TZ)
            pr = ET.SubElement(root, "programme",
                               start=s.strftime("%Y%m%d%H%M%S %z"),
                               stop=e.strftime("%Y%m%d%H%M%S %z"),
                               channel=xmltv_id)
            ET.SubElement(pr, "title", lang="he").text = escape(p.get("name", ""))
            if desc := p.get("description") or p.get("summary"):
                ET.SubElement(pr, "desc", lang="he").text = escape(desc)
        dbg(f"Added {len(programmes)} programmes for {name}")

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print(f"✅ wrote {OUT_XML}")


if __name__ == "__main__":
    # Any uncaught exception will exit with a non-zero code.
    build_epg()
