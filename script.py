#!/usr/bin/env python3
import os, sys, json, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import html
from xml.dom import minidom
from pathlib import Path

BASE = os.getenv("MY_BASE")
USERNAME = os.getenv("MY_USER")
PASSWORD = os.getenv("MY_PASS")
CACHE_FILE = os.getenv("EMBY_TOKEN_CACHE", "token_cache.json")
COUNT_FILE  = Path("count.txt")
FLAG_FILE    = Path("count_changed.flag")

if not BASE or not USERNAME or not PASSWORD:
    sys.exit("❌ Missing MY_BASE / MY_USER / MY_PASS")

# Read cache
def load_cached_token():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("AccessToken")
    except:
        return None, None

# Save cache
def save_cached_token(token):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"AccessToken": token}, f)
    except Exception as e:
        print(f"⚠️ Failed to save token cache: {e}")

# Authenticate
auth_hdr = (
    'MediaBrowser Client="GitHubAction", Device="CI", '
    'DeviceId="gh-epg", Version="4.9.0.42"'
)

try:
    resp = requests.post(
        f"{BASE}/emby/Users/AuthenticateByName",
        headers={
            "Content-Type": "application/json",
            "X-Emby-Authorization": auth_hdr
        },
        json={"Username": USERNAME, "Pw": PASSWORD},
        timeout=20
    )
    resp.raise_for_status()
    login = resp.json()
    token = login["AccessToken"]
    save_cached_token(token)
    print("✅ Logged in")
except Exception as e:
    print(f"⚠️ Authentication failed: {e}")
    token = load_cached_token()
    if not token:
        sys.exit("❌ No valid cached token available")
    print("✅ Using cached token")

headers = {
    "X-Emby-Token": token,
    "X-Emby-Client": "Emby Web",
    "X-Emby-Device-Name": "PythonScript",
    "X-Emby-Device-Id": "script-1234",
    "X-Emby-Client-Version": "4.9.0.42"
}

m3u_lines = ['#EXTM3U']

# Step 1: Get info
url = f"{BASE}/emby/LiveTv/Channels"
params = {
    "IsAiring": "true",
    "EnableUserData": "false",
    "Fields": "PrimaryImageAspectRatio",
    "ImageTypeLimit": "1",
    "EnableImageTypes": "Primary",
    "SortBy": "DefaultChannelOrder",  # << gets server-side order
    "SortOrder": "Ascending"
}
response = requests.get(url, headers=headers, params=params)
info = response.json().get("Items", []) 

# Count check
current_count = len(info) - 1
try:
    previous_count = int(COUNT_FILE.read_text().strip())
except Exception:
    previous_count = None

print(f"Previous count: {previous_count}")
print(f"Current  count: {current_count}")
changed = previous_count is not None and previous_count != current_count
if changed:
    print("⚠️ count changed!")
else:
    print("No change in count.")

# Step 2: Process
for ch in info:
    id = ch["Id"]
    name = ch["Name"]
    image_tag = ch.get("ImageTags", {}).get("Primary")

    if not image_tag:
        continue  # skip if no image

    # Icon URL
    logo_url = f"{BASE}/emby/Items/{id}/Images/Primary?tag={image_tag}"

    # M3U8 URL (this works if the server is configured properly)
    m3u8_url = (
        f"{BASE}/emby/videos/{id}/master.m3u8"
    )

    # Write M3U line
    extinf = f'#EXTINF:-1 tvg-id="{id}" tvg-name="{name}" tvg-logo="{logo_url}",{name}'
    m3u_lines.append(extinf)
    m3u_lines.append(m3u8_url)

# Step 3: Output to file
with open("file.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(m3u_lines))

print("✅ M3U playlist saved as file.m3u")

# Fetch programmes
now = datetime.now(timezone.utc)
later = now + timedelta(hours=24)
params = {
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
info = {}

# entries
for prog in programs:
    ch_id = str(prog["ChannelId"])
    ch_name = prog.get("ChannelName", f"Channel {ch_id}")
    info[ch_id] = ch_name

for ch_id, ch_name in info.items():
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

COUNT_FILE.write_text(str(current_count))
FLAG_FILE.write_text("1" if changed else "0")
