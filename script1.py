#!/usr/bin/env python3
"""
merge_epg.py  –  merge several compressed XMLTV sources into one file
                 (file1.xml), deduplicating channels after optionally mapping
                 id → tvg-id via a CSV, and discarding <programme> nodes that
                 belong to duplicated channels.

Expected CSV header     : channel_id,tvg-id
Example row             : HistoryHD,history.hd
"""

import csv
import gzip
import io
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Set, List
from datetime import datetime, timedelta

# --------------------------------------------------------------------------- #
# 𝐂𝐎𝐍𝐅𝐈𝐆 ––– edit only if you add/remove sources or move the CSV
# --------------------------------------------------------------------------- #
URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
    "https://raw.githubusercontent.com/EPGIL/epg-all/refs/heads/main/epg.xml",
    "https://github.com/Fazzani/grab/raw/refs/heads/master/merge.xml.gz",
    "https://raw.githubusercontent.com/bmk1239/eagle/refs/heads/main/file.xml",
    #"https://only4.tv/epg/epg.xml"
]

CSV_MAP = Path("file1.csv")          # mapping file (channel_id,tvg-id)
OUT_XML = Path("file1.xml")                # Unified EPG that we generate
REQUEST_TIMEOUT = 60                       # seconds
# --------------------------------------------------------------------------- #

# ---------- helpers ---------------------------------------------------------


def load_mapping(csv_path: Path) -> Dict[str, str]:
    """Return {original_id → tvg-id} from the CSV, or empty dict if missing."""
    mapping: Dict[str, str] = {}
    if not csv_path.exists():
        print(f"[warn] Mapping file not found: {csv_path} → using original IDs")
        return mapping
    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            src = row["channel-id"].strip()
            dst = row["tvg-id"].strip()
            if src and dst:
                mapping[src] = dst
    return mapping


def fetch_root(url: str) -> ET.Element:
    print(f"*************************** url: {url}")
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    xml_data = r.content;
    if not url.endswith(".xml"):
      xml_data = gzip.decompress(xml_data)
    return ET.parse(io.BytesIO(xml_data)).getroot()  # <tv> element


def pretty(e: ET.Element, depth: int = 0) -> None:
    """Indent the XML in-place so the output is human-readable."""
    pad = "\n" + "  " * depth
    if len(e):
        if not e.text or not e.text.strip():
            e.text = pad + "  "
        for c in e:
            pretty(c, depth + 1)
        if not c.tail or not c.tail.strip():
            c.tail = pad
    if depth and (not e.tail or not e.tail.strip()):
        e.tail = pad


# ---------- merge -----------------------------------------------------------


def main() -> None:
    id_map = load_mapping(CSV_MAP)  # {old_id → tvg-id} or empty

    kept_ids: Set[str] = set()      # ids kept in the final EPG
    dup_ids: Set[str] = set()       # ids seen more than once (after mapping)
    part_channels: List[ET.Element] = []   # <channel> nodes
    part_programmes: List[ET.Element] = [] # <programme> nodes

    # ── PASS 1: keep first occurrence of every (mapped) id ────────────────── #
    offset = timedelta(hours=2)
    for url in URLS:
        root = fetch_root(url)
        for node in root:
            if node.tag != "programme":
                continue

            old_chan = node.get("channel")
            if not old_chan in id_map:
                continue
            for attr in ["start", "stop"]:
                time_val = node.get(attr)
                if not time_val or not time_val.endswith(" +0200"):
                  continue
                # Extract timestamp and original offset
                timestamp, _ = time_val[:14], time_val[15:]
                dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                dt -= offset  # subtract 2 hours
                # Set new value with +0000
                node.set(attr, dt.strftime("%Y%m%d%H%M%S") + " +0000")
            
            new_chan = id_map.get(old_chan, old_chan)
            node.set("channel", new_chan)  # rewrite reference
            if old_chan in kept_ids or not new_chan in dup_ids:
                kept_ids.add(old_chan)
                part_programmes.append(node)
            dup_ids.add(new_chan)

    # ── PASS 2: keep <channel>s only if their (mapped) channel id is unique ── #
    for url in URLS:
        root = fetch_root(url)
        for node in root:
            if node.tag != "channel":
                continue

            old_id = node.get("id")
            if old_id in kept_ids:
                new_id = id_map.get(old_id, old_id)
                node.set("id", new_id)  # rewrite in-place so later writes are easy
                part_channels.append(node)
            

    # ── assemble output tree ─────────────────────────────────────────────── #
    out_root = ET.Element("tv")
    out_root.extend(part_channels)
    out_root.extend(part_programmes)
    pretty(out_root)

    with OUT_XML.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        ET.ElementTree(out_root).write(fh, encoding="unicode")

    # quick parse to ensure well-formed
    ET.parse(OUT_XML)
    print(f"{OUT_XML.name} written ✔  ({len(part_channels)} channels, "
          f"{len(part_programmes)} programmes)")


if __name__ == "__main__":
    main()
