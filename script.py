#!/usr/bin/env python3
import os, sys, json, requests, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

BASE = os.getenv("MY_BASE")
USERNAME = os.getenv("MY_USER")
PASSWORD = os.getenv("MY_PASS")

if not BASE or not USERNAME or not PASSWORD:
    sys.exit("❌  Missing MY_BASE / MY_USER / MY_PASS")

# Login to get token + userId
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
token   = login["AccessToken"]
user_id = login["User"]["Id"]
print("✅ Logged in")

# Prepare date window (24 hours from now)
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

# Make the request like curl
r = requests.get(f"{BASE}/emby/LiveTv/Programs",
                 params=params,
                 headers={"X-Emby-Token": token}, timeout=30)
r.raise_for_status()
data = r.json().get("Items", [])
print(f"📺 {len(data)} programmes")

# Write XMLTV
root = ET.Element("tv")
for prog in data:
    st = datetime.fromisoformat(prog["StartDate"].replace("Z", "+00:00"))
    en = datetime.fromisoformat(prog["EndDate"].replace("Z", "+00:00"))
    p = ET.SubElement(root, "programme", {
        "channel": str(prog["ChannelId"]),
        "start": st.strftime("%Y%m%d%H%M%S +0000"),
        "stop": en.strftime("%Y%m%d%H%M%S +0000")
    })
    ET.SubElement(p, "title", {"lang": "he"}).text = prog.get("Name", "")
    if prog.get("EpisodeTitle"):
        ET.SubElement(p, "sub-title", {"lang": "he"}).text = prog["EpisodeTitle"]
    if prog.get("Overview"):
        ET.SubElement(p, "desc", {"lang": "he"}).text = prog["Overview"]

ET.indent(root)
ET.ElementTree(root).write("file.xml", encoding="utf-8", xml_declaration=True)
print("✅ file.xml saved")
