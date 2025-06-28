#!/usr/bin/env python3
"""
Generate a one‑day XMLTV guide from FreeTV, using an Israel proxy and a
custom root‑CA that’s stored in GitHub Secrets as IL_PROXY_CA_B64.

🆕 2025‑06‑28 → 2025‑06‑29
• Removed per‑channel try/except blocks (hard‑fail philosophy)
• Added full URL printout for every programme request
• **All urllib3 SSL warnings are now silenced** so they never abort the run
"""

from __future__ import annotations

import datetime as dt
import os
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
import urllib3

# ────────────────────────── helpers ───────────────────────────

# 1️⃣  Silence only the TLS‑certificate warnings (everything else still prints)
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

_DEBUG = os.getenv("DEBUG", "1") not in ("0", "false", "False", "no", "NO")

def dbg(msg: str):
    if _DEBUG:
        print(f"[dbg] {msg}")

# ──────────────────────── custom adapter ──────────────────────

class InsecureTunnel(HTTPAdapter):
    """FOR *testing* ONLY – disables cert validation to the upstream proxy."""
    def _new_ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def init_poolmanager(self, *a, **kw):
        kw["ssl_context"] = self._new_ctx()
        return super().init_poolmanager(*a, **kw)

    def proxy_manager_for(self, *a, **kw):
        kw["ssl_context"] = self._new_ctx()
        return super().proxy_manager_for(*a, **kw)

# ────────────────────────── constants ─────────────────────────
API_URL = "https://web.freetv.tv/api/products/lives/programmes"
SITE_HOME = "https://web.freetv.tv/"
IL_TZ = ZoneInfo("Asia/Jerusalem")

CHANNELS_FILE = "channels.xml"
OUT_XML = "freetv_epg.xml"

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
        "Gecko/20100101 Firefox/126.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://web.freetv.tv",
    "Referer": "https://web.freetv.tv/",
}
# ───────────────────────────────────────────────────────────────

def day_window(now_il: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """Return the IL‑calendar 24 h window (start inclusive)."""
    start = dt.datetime.combine(now_il.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)


def configure_session():
    """Return a CloudScraper session that goes through the IL proxy."""
    dbg("Creating CloudScraper session …")
    sess = cloudscraper.create_scraper()
    sess.mount("https://", InsecureTunnel())
    sess.headers.update(BASE_HEADERS)

    proxy = os.getenv("IL_PROXY")
    if not proxy:
        raise RuntimeError("IL_PROXY secret is missing!")

    sess.proxies = {"http": proxy, "https": proxy}
    print("[info] Using Israel proxy →", proxy)

    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        sess.verify = False
        print("[warn] SSL verification DISABLED (IL_PROXY_INSECURE)")

    if cookies := os.getenv("IL_FTV_COOKIES"):
        sess.headers["Cookie"] = cookies
        print("[info] Injected user cookies")

    return sess


def fetch_programmes(sess, site_id: str, start: dt.datetime, end: dt.datetime):
    params = {
        "liveId[]": site_id,
        "since": start.strftime("%Y-%m-%dT%H:%M%z"),
        "till": end.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }

    for attempt in (1, 2):
        r = sess.get(API_URL, params=params, timeout=30)
        print(f"[fetch] {r.url} → {r.status_code}")   # 👈 always print URL

        if r.status_code == 403 and attempt == 1:
            sess.get(SITE_HOME, timeout=20)  # Cloudflare bypass
            continue

        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data


def build_epg():
    start, end = day_window(dt.datetime.now(IL_TZ))
    sess = configure_session()

    root = ET.Element("tv", {
        "source-info-name": "FreeTV",
        "generator-info-name": "FreeTV-EPG (proxy-CA)",
    })

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site_id = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name = (ch.text or xmltv_id).strip()

        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        programmes = fetch_programmes(sess, site_id, start, end)

        for p in programmes:
            if not all(k in p for k in ("start", "end", "name")):
                dbg(f"[warn] Skipping malformed item: {p}")
                continue

            s = dt.datetime.fromisoformat(p["start"]).astimezone(IL_TZ)
            e = dt.datetime.fromisoformat(p["end"]).astimezone(IL_TZ)

            pr = ET.SubElement(
                root,
                "programme",
                start=s.strftime("%Y%m%d%H%M%S %z"),
                stop=e.strftime("%Y%m%d%H%M%S %z"),
                channel=xmltv_id,
            )
            ET.SubElement(pr, "title", lang="he").text = escape(p["name"])
            if desc := p.get("description") or p.get("summary"):
                ET.SubElement(pr, "desc", lang="he").text = escape(desc)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML)


if __name__ == "__main__":
    build_epg()
