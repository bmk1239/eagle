#!/usr/bin/env python3
"""
Generate a one-day XMLTV EPG for all channels in channels.xml.

▪ Reads channels.xml in the same directory.
▪ Queries FreeTV’s programme API for the coming calendar day
  (00:00-24:00 Asia/Jerusalem on the day the script runs).
▪ Writes freetv_epg.xml next to the script.
"""

import datetime as dt
from pathlib import Path
from html import escape
from zoneinfo import ZoneInfo  # Python ≥3.9
import xml.etree.ElementTree as ET
import requests

# ---------- constants ----------
API_URL = "https://web.freetv.tv/api/products/lives/programmes"
IL_TZ   = ZoneInfo("Asia/Jerusalem")
OUT_XML = "freetv_epg.xml"
CHANNELS_FILE = "channels.xml"
HEADERS = {"User-Agent": "FreeTV-EPG/1.0"}
# --------------------------------


def day_window(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """Return start (00:00) and end (next 00:00) in IL time."""
    start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)


def fetch_programmes(site_id: str, start: dt.datetime, end: dt.datetime) -> list[dict]:
    """Call FreeTV API and return the list of programmes for a channel."""
    params = {
        "liveId[]": site_id,
        "since": start.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  end.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }
    r = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    # API sometimes returns bare list, sometimes {"data": [...]}
    return data.get("data", data) if isinstance(data, dict) else data


def build_epg():
    root = ET.Element(
        "tv",
        attrib={
            "source-info-name": "FreeTV",
            "generator-info-name": "FreeTV-EPG-script",
        },
    )

    today_il = dt.datetime.now(IL_TZ)
    start, end = day_window(today_il)

    channels_tree = ET.parse(CHANNELS_FILE)
    for ch in channels_tree.findall("channel"):
        site_id   = ch.attrib["site_id"]
        xmltv_id  = ch.attrib["xmltv_id"]
        disp_name = (ch.text or xmltv_id).strip()

        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = disp_name

        try:
            for p in fetch_programmes(site_id, start, end):
                # Parse start/stop that come back from API (ISO-8601)
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
                desc = p.get("description") or p.get("summary") or ""
                if desc:
                    ET.SubElement(prog_el, "desc", lang="he").text = escape(desc)
        except Exception as exc:
            # Non-fatal: leave channel but log error
            print(f"[warn] {xmltv_id}: {exc}")

    # Pretty-print (Python ≥3.9)
    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print(f"✅  Wrote {OUT_XML}")


if __name__ == "__main__":
    build_epg()
