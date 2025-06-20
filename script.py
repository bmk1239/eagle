#!/usr/bin/env python3
import os, sys, json, requests, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

BASE = os.getenv("MY_BASE")
USERNAME = os.getenv("MY_USER")
PASSWORD = os.getenv("MY_PASS")

if not BASE or not USERNAME or not PASSWORD:
    sys.exit("❌ Missing MY_BASE / MY_USER / MY_PASS")

# Login to get token
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

# Get EPG window
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
print(f"📺 Found {len(programs)} programmes")

# Begin XML
ET.register_namespace('', "http://xmltv.org/xmltv")  # optional
tv = ET.Element("tv")

# Build channel set
channels = {}
for prog in programs:
    ch_id = str(prog["ChannelId"])
    ch_name = prog.get("ChannelName", f"Channel {ch_id}")
    if ch_id not in channels:
        channels[ch_id] = ch_name

# Add <channel> elements
for ch_id, ch_name in sorted(channels.items()):
    ch_elem = ET.SubElement(tv, "channel", {"id": ch_id})
    ET.SubElement(ch_elem, "display-name").text = ch_name

# Add <programme> elements
for prog in programs:
    ch_id = str(prog["ChannelId"])
    start = datetime.fromisoformat(prog["StartDate"].replace("Z", "+00:00"))
    stop = datetime.fromisoformat(prog["EndDate"].replace("Z", "+00:00"))
    p_elem = ET.SubElement(tv, "programme", {
        "channel": ch_id,
        "start": start.strftime("%Y%m%d%H%M%S +0000"),
        "stop": stop.strftime("%Y%m%d%H%M%S +0000")
    })
    ET.SubElement(p_elem, "title", {"lang": "he"}).text = prog.get("Name", "")
    if prog.get("EpisodeTitle"):
        ET.SubElement(p_elem, "sub-title", {"lang": "he"}).text = prog["EpisodeTitle"]
    if prog.get("Overview"):
        ET.SubElement(p_elem, "desc", {"lang": "he"}).text = prog["Overview"]

# Output file
tree = ET.ElementTree(tv)
tree.write("file.xml", encoding="utf-8", xml_declaration=True)
print("✅ file.xml created (with channels)")
