#!/usr/bin/env python3
"""Fetch EmbyIL /LiveTv/Programs JSON and export XMLTV."""
import os, sys, json, argparse
from datetime import datetime, timedelta, timezone
import requests
import xml.etree.ElementTree as ET
import subprocess

#BASE_URL = os.getenv("EMBY_BASE_URL", "https://play.embyil.tv")
#USER_ID   = os.getenv("EMBY_USER_ID")
#TOKEN     = os.getenv("EMBY_TOKEN")
#CHANNELS  = os.getenv("CHANNEL_IDS", "").split(",")
#DEVICE_ID = os.getenv("DEVICE_ID", "embyil-xmltv-export")
#CLIENT    = os.getenv("CLIENT_VERSION", "4.9.0.42")
#LANG      = os.getenv("EMBY_LANG", "he")

BASE_URL = "https://play.embyil.tv"
USER_ID = "f77d2537830c404a8a0e616694be0964"
TOKEN = "a9a768bda323427ea639cb6277d736bb"
CHANNELS = [
    "2436645", "2299409", "2299410", "2299411", "2299412",
    "2305576", "2299413", "2305577", "2305578"
]
DEVICE_ID = "672abf61-bd6c-4838-86a3-561ee37175cd"
CLIENT = "4.9.0.42"
LANG = "he"

parser = argparse.ArgumentParser(description="Export EmbyIL EPG to XMLTV")
parser.add_argument("--hours", type=int, default=24, help="Guide look-ahead hours (default 24)")
parser.add_argument("--output", default="epg.xml", help="Output XMLTV filename")
args = parser.parse_args()

if not USER_ID or not TOKEN or not CHANNELS:
    sys.exit("❌ Missing EMBY_USER_ID / EMBY_TOKEN / CHANNEL_IDS env vars")

now = datetime.utcnow().replace(tzinfo=timezone.utc)
max_start = now + timedelta(hours=args.hours)

url = "https://play.embyil.tv/emby/LiveTv/Programs?UserId=f77d2537830c404a8a0e616694be0964&MinEndDate=2025-06-20T20:46:33Z&MaxStartDate=2025-06-21T20:46:33Z&channelIds=2436645,2299409,2299410&ImageTypeLimit=1&SortBy=StartDate&EnableTotalRecordCount=false&EnableUserData=false&EnableImages=false"
token = "a9a768bda323427ea639cb6277d736bb"

cmd = [
    "curl", "-s",
    "-H", f"X-Emby-Token: {token}",
    url
]

result = subprocess.run(cmd, capture_output=True, text=True)
print("Status:", result.returncode)
print("Output:", result.stdout[:500])  # Print partial output for sanity

params = {
    "UserId": USER_ID,
    "MinEndDate": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    "MaxStartDate": max_start.isoformat(timespec="seconds").replace("+00:00", "Z"),
    #"channelIds": ",".join(CHANNELS),
    "ImageTypeLimit": 1,
    "SortBy": "StartDate",
    "EnableTotalRecordCount": "false",
    "EnableUserData": "false",
    "EnableImages": "false",
}
headers = {
    "X-Emby-Token": "a9a768bda323427ea639cb6277d736bb",
    "User-Agent": "curl/7.81.0"
    #"X-Emby-Client": "Emby Web",
    #"X-Emby-Device-Name": "Google Chrome Android",
    #"X-Emby-Device-Id": DEVICE_ID,
    #"X-Emby-Client-Version": CLIENT,
    #"X-Emby-Language": LANG
}

print("→ Fetching programs …", file=sys.stderr)
print("Request URL:", f"{BASE_URL}/emby/LiveTv/Programs", file=sys.stderr)
print("Params:", json.dumps(params, indent=2), file=sys.stderr)
print("Headers:", json.dumps(headers, indent=2), file=sys.stderr)

r = requests.get(f"{BASE_URL}/emby/LiveTv/Programs", params=params, headers=headers, timeout=30)

if r.status_code != 200:
    print(f"❌ Request failed with status {r.status_code}", file=sys.stderr)
    print("Response body:", r.text[:500], file=sys.stderr)
    r.raise_for_status()

items = r.json().get("Items", [])
print(f"✔  {len(items)} programmes received", file=sys.stderr)

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

ET.indent(root)  # Requires Python 3.9+
ET.ElementTree(root).write(args.output, encoding="utf-8", xml_declaration=True)
print(f"✔  XMLTV written to {args.output}")
