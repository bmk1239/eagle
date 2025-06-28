#!/usr/bin/env python3
"""
Generate a one‑day XMLTV guide from FreeTV, routed through an Israeli proxy.
Only each request URL is printed; all other logging is silent.
Channels are written **first** in the XML, and *all* programme elements come
**after** the channel list, per XMLTV best‑practice.
"""

from __future__ import annotations

import datetime as dt
import os
import warnings
from html import escape
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import cloudscraper
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
import ssl
from urllib3.util.ssl_ import create_urllib3_context
import urllib3

# ────────────────────────── proxy helper ─────────────────────────
class InsecureTunnel(HTTPAdapter):
    """Disable TLS checks when talking *to* the upstream proxy itself."""
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

# ────────────────────────── constants ───────────────────────────
API_URL   = "https://web.freetv.tv/api/products/lives/programmes"
SITE_HOME = "https://web.freetv.tv/"
IL_TZ     = ZoneInfo("Asia/Jerusalem")

CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
        "Gecko/20100101 Firefox/126.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://web.freetv.tv",
    "Referer": "https://web.freetv.tv/",
}

# Silence SSL warnings (we deliberately skip TLS validation toward proxy)
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

# ────────────────────────── helpers ───────────────────────────

def day_window(now: dt.datetime):
    start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
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

    if cookies := os.getenv("IL_FTV_COOKIES"):
        sess.headers["Cookie"] = cookies

    return sess


def fetch_programmes(sess, site_id, since, till):
    params = {
        "liveId[]": site_id,
        "since": since.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  till.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }

    for attempt in (1, 2):
        r = sess.get(API_URL, params=params, timeout=30)
        print(r.url)                   # single required print
        if r.status_code == 403 and attempt == 1:
            sess.get(SITE_HOME, timeout=20)
            continue                  # Cloudflare challenge bypass once
        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data


# ────────────────────────── main build ─────────────────────────

def build_epg():
    start, end = day_window(dt.datetime.now(IL_TZ))
    sess = configure_session()

    root = ET.Element("tv", {
        "source-info-name": "FreeTV",
        "generator-info-name": "FreeTV-EPG (proxy)",
    })

    programmes_buffer: list[tuple[str, dict]] = []  # (xmltv_id, item)

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site_id  = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name     = (ch.text or xmltv_id).strip()

        # -- write <channel> immediately
        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        # -- fetch and stash programmes
        for item in fetch_programmes(sess, site_id, start, end):
            programmes_buffer.append((xmltv_id, item))

    # ----- after all channels are listed, emit <programme> elements ------
    for xmltv_id, p in programmes_buffer:
        if not all(k in p for k in ("since", "till", "title")):
            continue
        s = dt.datetime.fromisoformat(p["since"]).astimezone(IL_TZ)
        e = dt.datetime.fromisoformat(p["till"]).astimezone(IL_TZ)
        pr = ET.SubElement(root, "programme",
                           start=s.strftime("%Y%m%d%H%M%S %z"),
                           stop=e.strftime("%Y%m%d%H%M%S %z"),
                           channel=xmltv_id)
        ET.SubElement(pr, "title", lang="he").text = escape(p["title"])
        if desc := p.get("description") or p.get("summary"):
            ET.SubElement(pr, "desc", lang="he").text = escape(desc)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML)


if __name__ == "__main__":
    build_epg()
