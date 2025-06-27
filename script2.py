#!/usr/bin/env python3
"""
generate_epg.py  –  Create a one-day XMLTV EPG from FreeTV

• Reads channels.xml in the same directory (each <channel site_id="" xmltv_id="">).
• Queries FreeTV’s programme API for 00:00-24:00 (Asia/Jerusalem) of the
  day the script runs, using real-browser headers plus the cookies the
  site sets on its front page (avoids 403s).
• Runs through the Israel proxy if the environment variable IL_PROXY is set.
• Writes freetv_epg.xml in the same directory.

Requires: Python ≥ 3.9, requests (pip install requests),
          backports.zoneinfo for Python < 3.9 (already in workflow).
"""

from __future__ import annotations

import datetime as dt
import os
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

# Real-browser headers FreeTV expects
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


def day_window(now_il: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """Return (start, end) for 00:00-24:00 Israel time on ``now_il``’s date."""
    start = dt.datetime.combine(now_il.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)


def fetch_programmes(
    session: requests.Session,
    site_id: str,
    start: dt.datetime,
    end: dt.datetime,
) -> list[dict]:
    """
    Call the FreeTV API for one channel.

    If the first request is rejected with 403, prime cookies on SITE_HOME
    then retry once.
    """
    params = {
        "liveId[]": site_id,
        "since": start.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  end.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }

    for attempt in (1, 2):
        response = session.get(API_URL, params=params, timeout=30)
        try:
            response.raise_for_status()
            data = response.json()
            return data.get("data", data) if isinstance(data, dict) else data
        except HTTPError as exc:
            if response.status_code == 403 and attempt == 1:
                # First attempt failed – grab cookies then retry
                session.get(SITE_HOME, timeout=15)
                continue
            raise exc


def build_epg() -> None:
    """Main routine – iterate channels, call API, emit XMLTV."""
    now_il = dt.datetime.now(IL_TZ)
    start, end = day_window(now_il)

    # One session for all calls (shares cookies & proxy)
    session = requests.Session()
    session.headers.update(BASE_HEADERS)

    # Proxy (if supplied)
    if proxy := os.getenv("IL_PROXY"):
        print("[info] Using Israel proxy")
        session.proxies = {"http": proxy, "https": proxy}

    # Root <tv>
    root = ET.Element(
        "tv",
        attrib={
            "source-info-name": "FreeTV",
            "generator-info-name": "FreeTV-EPG-script",
        },
    )

    # Read channel list
    channels_tree = ET.parse(CHANNELS_FILE)
    for ch in channels_tree.findall("channel"):
        site_id  = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name     = (ch.text or xmltv_id).strip()

        # <channel>
        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        # Download and add <programme>s
        try:
            progs = fetch_programmes(session, site_id, start, end)
            for p in progs:
                p_start = dt.datetime.fromisoformat(p["start"]).astimezone(IL_TZ)
                p_end   = dt.datetime.fromisoformat(p["end"]).astimezone(IL_TZ)

                prog_el = ET.SubElement(
                    root,
                    "programme",
                    start=p_start.strftime("%Y%m%d%H%M%S %z"),
                    stop=p_end.strftime("%Y%m%d%H%M%S %z"),
                    channel=xmltv_id,
                )
                ET.SubElement(prog_el, "title", lang="he").text = escape(p.get("name", ""))
                if desc := (p.get("description") or p.get("summary") or ""):
                    ET.SubElement(prog_el, "desc", lang="he").text = escape(desc)

        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {name}: {exc}")

    # Pretty print (requires Python ≥ 3.9)
    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print(f"✅ Wrote {OUT_XML}")


if __name__ == "__main__":
    build_epg()
