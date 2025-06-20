#!/usr/bin/env python3
"""
Login to EmbyIL, fetch 24-hour EPG, export to epg.xml.
"""
import sys, json, requests, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

BASE = "https://play.embyil.tv"

# Your real credentials (be careful with these!)
USERNAME = "2200620"
PASSWORD = "2200620"
CHANNELS = [
    "2436645", "2299409", "2299410", "2299411", "2299412",
    "2305576", "2299413", "2305577", "2305578"
]

# Parameters
HOURS = 24
OUTPUT_FILE = "epg.xml"

# ───────────────── 1) LOGIN  ──────────────────
auth_hdr = ('MediaBrowser '
            'Client="Emby Web", '
            'Device="PythonScript", '
            'DeviceId="python-epg-fetch", '
            'Version="4.9.0.42"')

login_r = requests.post(
    f"{BASE}/emby/Users/AuthenticateByName",
    headers={
        "Content-Type": "application/json",
        "X-Emby-Authorization": auth_hdr
    },
    json={"Username": USERNAME, "Pw": PASSWORD},
    timeout=20
)
if login_r.status_code != 200:
    sys.exit(f"❌  Login failed ({login_r.status_code}): {login_r.text[:200]}")

login = login_r.json()
token   = login["AccessToken"]
user_id = login["User"]["Id"]
print("✅ Logged in, got fresh token.")

# ──────────────── 2) FETCH PROGRAMMES ────────────────
now    = datetime.now(timezone.utc)
future = now + timedelta(hours=HOURS)
params = {
    "UserId": user_id,
    "MinEndDate":  now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "MaxStartDate":future.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "channelIds":  ",".join(CHANNELS),
    "ImageTypeLimit": 1,
    "SortBy": "StartDate",
    "EnableTotalRecordCount": "false",
    "EnableUserData": "false",
    "EnableImages": "false"
}
prog_r = requests.get(
    f"{BASE}/emby/LiveTv/Programs",
    params=params,
    headers={"X-Emby-Token": token},
    timeout=30
)
prog_r.raise_for_status()
items = prog_r.json().get("Items", [])
print(f"✅  Received {len(items)} programmes.")

# ─────────────── 3) BUILD XMLTV  ───────────────
root = ET.Element("tv")
for it in items:
    st = datetime.fromisoformat(it["StartDate"].replace("Z","+00:00"))
    en = datetime.fromisoformat(it["EndDate"].replace("Z","+00:00"))
    p  = ET.SubElement(root, "programme", {
        "channel": str(it["ChannelId"]),
        "start":   st.strftime("%Y%m%d%H%M%S +0000"),
        "stop":    en.strftime("%Y%m%d%H%M%S +0000")
    })
    ET.SubElement(p, "title", {"lang":"he"}).text = it.get("Name","")
    if it.get("EpisodeTitle"):
        ET.SubElement(p, "sub-title", {"lang":"he"}).text = it["EpisodeTitle"]
    if it.get("Overview"):
        ET.SubElement(p, "desc", {"lang":"he"}).text = it["Overview"]

for cid in CHANNELS:
    ch = ET.SubElement(root, "channel", {"id": cid})
    ET.SubElement(ch, "display-name").text = cid

ET.indent(root)
ET.ElementTree(root).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
print(f"📄  Wrote {OUTPUT_FILE}")
