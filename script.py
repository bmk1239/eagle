#!/usr/bin/env python3
"""Fetch EmbyIL /LiveTv/Programs JSON and export XMLTV."""
import os, sys, json, argparse
from datetime import datetime, timedelta, timezone
import requests
import xml.etree.ElementTree as ET

BASE_URL = os.getenv("EMBY_BASE_URL", "https://play.embyil.tv")
USER_ID   = os.getenv("EMBY_USER_ID")
TOKEN     = os.getenv("EMBY_TOKEN")
CHANNELS  = os.getenv("CHANNEL_IDS", "").split(",")
DEVICE_ID = os.getenv("DEVICE_ID", "embyil-xmltv-export")
CLIENT    = os.getenv("CLIENT_VERSION", "4.9.0.42")
LANG      = os.getenv("EMBY_LANG", "he")

parser = argparse.ArgumentParser(description="Export EmbyIL EPG to XMLTV")
parser.add_argument("--hours", type=int, default=24, help="Guide look-ahead hours (default 24)")
parser.add_argument("--output", default="epg.xml", help="Output XMLTV filename")
args = parser.parse_args()

if not USER_ID or not TOKEN or not CHANNELS:
    sys.exit("❌ Missing EMBY_USER_ID / EMBY_TOKEN / CHANNEL_IDS env vars")

now = datetime.utcnow().replace(tzinfo=timezone.utc)
max_start = now + timedelta(hours=args.hours)

params = {
    "UserId": USER_ID,
    "MinEndDate": now.isoformat(timespec="seconds") + "Z",
    "MaxStartDate": max_start.isoformat(timespec="seconds") + "Z",
    "channelIds": ",".join(CHANNELS),
    "ImageTypeLimit": 1,
    "SortBy": "StartDate",
    "EnableTotalRecordCount": "false",
    "EnableUserData": "false",
    "EnableImages": "false",
}
headers = {
    "X-Emby-Token": TOKEN,
    "X-Emby-Client": "Emby Web",
    "X-Emby-Device-Name": "GitHubAction",
    "X-Emby-Device-Id": DEVICE_ID,
    "X-Emby-Client-Version": CLIENT,
    "X-Emby-Language": LANG,
}

print("→ Fetching programs …", file=sys.stderr)
r = requests.get(f"{BASE_URL}/emby/LiveTv/Programs", params=params, headers=headers, timeout=30)
r.raise_for_status()
items = r.json().get("Items", [])
print(f"   {len(items)} programmes received", file=sys.stderr)

# Build XMLTV
root = ET.Element("tv")
for prog in items:
    cid = str(prog["ChannelId"])
    start = datetime.fromisoformat(prog["StartDate"].replace("Z", "+00:00"))
    end   = datetime.fromisoformat(prog["EndDate"].replace("Z", "+00:00"))

    p = ET.SubElement(root, "programme", {
        "channel": cid,
        "start": start.strftime("%Y%m%d%H%M%S +0000"),
        "stop":  end.strftime("%Y%m%d%H%M%S +0000"),
    })
    ET.SubElement(p, "title", {"lang": LANG}).text = prog.get("Name", "Untitled")
    if prog.get("EpisodeTitle"):
        ET.SubElement(p, "sub-title", {"lang": LANG}).text = prog["EpisodeTitle"]
    if prog.get("Overview"):
        ET.SubElement(p, "desc", {"lang": LANG}).text = prog["Overview"]

# Optional minimal <channel> entries
for cid in CHANNELS:
    ch = ET.SubElement(root, "channel", {"id": cid})
    ET.SubElement(ch, "display-name").text = cid

ET.indent(root)  # Python 3.9+
ET.ElementTree(root).write(args.output, encoding="utf-8", xml_declaration=True)
print(f"✔  XMLTV written to {args.output}")
