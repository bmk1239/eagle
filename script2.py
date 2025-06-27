#!/usr/bin/env python3
"""
generate_epg.py  –  FreeTV one-day EPG

• Handles 403 with real-browser headers and cookie priming.
• Goes through an Israel proxy in $IL_PROXY.
• Trusts a custom CA passed in $IL_PROXY_CA_B64 (base64 PEM).
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

import requests
from requests.exceptions import HTTPError

# ---------------------------------------------------------------------------
API_URL   = "https://web.freetv.tv/api/products/lives/programmes"
SITE_HOME = "https://web.freetv.tv/"
IL_TZ     = ZoneInfo("Asia/Jerusalem")
CHANNELS_FILE = "channels.xml"
OUT_XML       = "freetv_epg.xml"

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0)"
        " Gecko/20100101 Firefox/126.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://web.freetv.tv",
    "Referer": "https://web.freetv.tv/",
}
# ---------------------------------------------------------------------------


def day_window(now_il: dt.datetime):
    start = dt.datetime.combine(now_il.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)


def fetch_programmes(session, site_id, start, end):
    params = {
        "liveId[]": site_id,
        "since": start.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  end.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }
    for attempt in (1, 2):
        r = session.get(API_URL, params=params, timeout=30)
        try:
            r.raise_for_status()
            data = r.json()
            return data.get("data", data) if isinstance(data, dict) else data
        except HTTPError as exc:
            if r.status_code == 403 and attempt == 1:
                session.get(SITE_HOME, timeout=15)  # grab cookies
                continue
            raise exc


def configure_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(BASE_HEADERS)

    # ---------- proxy ----------
    if proxy := os.getenv("IL_PROXY"):
        sess.proxies = {"http": proxy, "https": proxy}
        print("[info] Using Israel proxy")

    # ---------- custom CA bundle ----------
    if b64 := os.getenv("IL_PROXY_CA_B64"):
        pem_bytes = base64.b64decode(b64)
        ca_path = Path(tempfile.gettempdir()) / "proxy_root_ca.pem"
        ca_path.write_bytes(pem_bytes)
        sess.verify = str(ca_path)
        print(f"[info] Loaded custom CA ➜ {ca_path}")

    return sess


def build_epg():
    now_il = dt.datetime.now(IL_TZ)
    start, end = day_window(now_il)

    session = configure_session()

    root = ET.Element(
        "tv",
        {"source-info-name": "FreeTV", "generator-info-name": "FreeTV-EPG-script"},
    )

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site_id  = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name     = (ch.text or xmltv_id).strip()

        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        try:
            for p in fetch_programmes(session, site_id, start, end):
                s = dt.datetime.fromisoformat(p["start"]).astimezone(IL_TZ)
                e = dt.datetime.fromisoformat(p["end"]).astimezone(IL_TZ)
                prog_el = ET.SubElement(
                    root,
                    "programme",
                    start=s.strftime("%Y%m%d%H%M%S %z"),
                    stop=e.strftime("%Y%m%d%H%M%S %z"),
                    channel=xmltv_id,
                )
                ET.SubElement(prog_el, "title", lang="he").text = escape(p.get("name", ""))
                if desc := (p.get("description") or p.get("summary") or ""):
                    ET.SubElement(prog_el, "desc", lang="he").text = escape(desc)
        except Exception as exc:
            print(f"[warn] {name}: {exc}")

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print(f"✅ Wrote {OUT_XML}")


if __name__ == "__main__":
    build_epg()
