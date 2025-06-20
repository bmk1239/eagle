#!/usr/bin/env python3
import os, sys, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import html
from xml.dom import minidom

BASE = os.getenv("MY_BASE")
USERNAME = os.getenv("MY_USER")
PASSWORD = os.getenv("MY_PASS")

if not BASE or not USERNAME or not PASSWORD:
    sys.exit("❌ Missing MY_BASE / MY_USER / MY_PASS")

# Authenticate
auth_hdr = (
    'MediaBrowser Client="GitHubAction", Device="CI", '
    'DeviceId="gh-epg", Version="4.9.0.42"'
)
resp = requests.post(
    f"{BASE}/emby/Users/AuthenticateByName",
    headers={"Content-Type": "application/json",
             "X-Emby-Authorization": auth_hdr},
    json={"Username": USERNAME, "Pw": PASSWORD},
    timeout=20
)
resp.raise_for_status()
login = resp.json()
token = login["AccessToken"]
user_id = login["User"]["Id"]
print("✅ Logged in")

# Fetch programmes
now = datetime.now(timezone.utc)
later = now + timedelta(hours=24)
params = {
    "UserId": user_id,
    "MinEndDate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "MaxStartDate": later.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "ImageTypeLimit": 1,
    "SortBy": "StartDate",
    "EnableTotalRecordCount": "false",
    "EnableUserData": "false",
    "EnableImages": "false"
}
r = requests.get(f"{BASE}/emby/LiveTv/Programs",
                 params=params,
                 headers={"X-Emby-Token": token}, timeout=30)
r.raise_for_status()
programs = r.json().get("Items", [])
print(f"📺 {len(programs)} programmes")

# Build XMLTV
tv = ET.Element("tv")
channels = {}

# <channel> entries
for prog in programs:
    ch_id = str(prog["ChannelId"])
    ch_name = prog.get("ChannelName", f"Channel {ch_id}")
    channels[ch_id] = ch_name

for ch_id, ch_name in channels.items():
    ch = ET.SubElement(tv, "channel", {"id": ch_id})
    ET.SubElement(ch, "display-name").text = ch_name

# <programme> entries
for prog in programs:
    ch_id = str(prog["ChannelId"])
    start = datetime.fromisoformat(prog["StartDate"].replace("Z", "+00:00"))
    stop = datetime.fromisoformat(prog["EndDate"].replace("Z", "+00:00"))

    p = ET.SubElement(tv, "programme", {
        "channel": ch_id,
        "start": start.strftime("%Y%m%d%H%M%S +0000"),
        "stop": stop.strftime("%Y%m%d%H%M%S +0000")
    })
    ET.SubElement(p, "title", {"lang": "he"}).text = html.escape(prog.get("Name", ""))
    if prog.get("EpisodeTitle"):
        ET.SubElement(p, "sub-title", {"lang": "he"}).text = html.escape(prog["EpisodeTitle"])
    if prog.get("Overview"):
        ET.SubElement(p, "desc", {"lang": "he"}).text = html.escape(prog["Overview"])

# Pretty-print using minidom
rough_string = ET.tostring(tv, encoding="utf-8")
reparsed = minidom.parseString(rough_string)
with open("file.xml", "w", encoding="utf-8") as f:
    f.write(reparsed.toprettyxml(indent="  "))

print("✅ Valid and pretty file.xml saved")
