#!/usr/bin/env python3
"""
Generate a one-day XMLTV guide from FreeTV, using an Israel proxy and a
custom root-CA that’s stored in GitHub Secrets as IL_PROXY_CA_B64.
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
import urllib3

# ────────────────────── custom adapter ──────────────────────

class InsecureTunnel(HTTPAdapter):
    """FOR *testing* ONLY – turns off all cert checks."""
    def _new_ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
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

# Silence SSL warnings globally
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

def day_window(now_il: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(now_il.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)


def configure_session():
    sess = cloudscraper.create_scraper()
    sess.mount("https://", InsecureTunnel())
    sess.headers.update(BASE_HEADERS)

    proxy = os.getenv("IL_PROXY")
    if not proxy:
        raise RuntimeError("IL_PROXY secret is missing!")
    sess.proxies = {"http": proxy, "https": proxy}

    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        sess.verify = False

    if coco := os.getenv("IL_FTV_COOKIES"):
        sess.headers["Cookie"] = coco

    return sess


def fetch_programmes(sess, site_id, start: dt.datetime, end: dt.datetime):
    params = {
        "liveId[]": site_id,
        "since": start.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  end.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }

    for attempt in (1, 2):
        r = sess.get(API_URL, params=params, timeout=30)
        print(r.url)  # <-- רק ה-URL מודפס כאן

        r.raise_for_status()
        data = r.json()
        programmes = data.get("data", data) if isinstance(data, dict) else data
        return programmes


def build_epg():
    now_il = dt.datetime.now(IL_TZ)
    start, end = day_window(now_il)
    sess = configure_session()

    root = ET.Element("tv", {
        "source-info-name": "FreeTV",
        "generator-info-name": "FreeTV-EPG (proxy-CA)",
    })

    channels_tree = ET.parse(CHANNELS_FILE)
    channels = channels_tree.findall("channel")

    for ch in channels:
        site_id  = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name     = (ch.text or xmltv_id).strip()

        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        programmes = fetch_programmes(sess, site_id, start, end)

        for p in programmes:
            if "since" not in p or "till" not in p or "title" not in p:
                continue  # דילוג על פריטים חסרי מידע חיוני
            s = dt.datetime.fromisoformat(p["since"]).astimezone(IL_TZ)
            e = dt.datetime.fromisoformat(p["till"]).astimezone(IL_TZ)
            pr = ET.SubElement(root, "programme",
                               start=s.strftime("%Y%m%d%H%M%S %z"),
                               stop=e.strftime("%Y%m%d%H%M%S %z"),
                               channel=xmltv_id)
            ET.SubElement(pr, "title", lang="he").text = escape(p.get("title", ""))
            if desc := p.get("description") or p.get("summary"):
                ET.SubElement(pr, "desc", lang="he").text = escape(desc)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    build_epg()
