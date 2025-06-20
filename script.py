#!/usr/bin/env python3
"""Call curl (works!), capture JSON, convert to XMLTV."""
import json, subprocess, sys, argparse, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# ───---  FILL IN YOUR CONSTANTS  ---─────────────────────────────
BASE_URL   = "https://play.embyil.tv"
USER_ID    = "f77d2537830c404a8a0e616694be0964"
TOKEN      = "a9a768bda323427ea639cb6277d736bb"
CHANNELS   = ["2436645","2299409","2299410","2299411","2299412","2305576","2299413","2305577","2305578"]
LANG       = "he"
# ────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--hours", type=int, default=24)
parser.add_argument("--output", default="epg.xml")
args = parser.parse_args()

now = datetime.now(timezone.utc)
max_start = now + timedelta(hours=args.hours)
# build full URL identical to the working curl
url = (
    f"{BASE_URL}/emby/LiveTv/Programs"
    f"?UserId={USER_ID}"
    f"&MinEndDate={now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    f"&MaxStartDate={max_start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    f"&channelIds={','.join(CHANNELS)}"
    f"&ImageTypeLimit=1&SortBy=StartDate"
    f"&EnableTotalRecordCount=false&EnableUserData=false&EnableImages=false"
)

# call curl exactly as you did by hand
result = subprocess.run(
    ["curl", "-s", "-H", f"X-Emby-Token: {TOKEN}", url],
    capture_output=True, text=True
)

if result.returncode != 0:
    sys.exit(f"curl failed (code {result.returncode})")

data = json.loads(result.stdout)
print(f"✔ received {len(data.get('Items', []))} programmes")

# build XMLTV
root = ET.Element("tv")
for item in data.get("Items", []):
    start = datetime.fromisoformat(item["StartDate"].replace("Z","+00:00"))
    end   = datetime.fromisoformat(item["EndDate"].replace("Z","+00:00"))
    prog  = ET.SubElement(root, "programme", {
        "channel": str(item["ChannelId"]),
        "start":   start.strftime("%Y%m%d%H%M%S +0000"),
        "stop":    end.strftime("%Y%m%d%H%M%S +0000")
    })
    ET.SubElement(prog, "title", {"lang": LANG}).text = item.get("Name","")
    if item.get("EpisodeTitle"):
        ET.SubElement(prog, "sub-title", {"lang": LANG}).text = item["EpisodeTitle"]
    if item.get("Overview"):
        ET.SubElement(prog, "desc", {"lang": LANG}).text = item["Overview"]

for cid in CHANNELS:
    ch = ET.SubElement(root, "channel", {"id": cid})
    ET.SubElement(ch, "display-name").text = cid

ET.indent(root)  # 3.9+
ET.ElementTree(root).write(args.output, encoding="utf-8", xml_declaration=True)
print(f"XMLTV written → {args.output}")
