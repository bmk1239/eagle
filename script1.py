#!/usr/bin/env python3
"""
merge_epg.py  –  produce a valid XMLTV file1.xml from two compressed sources,
                 deduplicating <channel> by id and ignoring programmes that
                 belong to duplicates.
"""
import gzip, io, requests, xml.etree.ElementTree as ET
from pathlib import Path

URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
]

# ---------- helpers ----------------------------------------------------------

def fetch_root(url: str) -> ET.Element:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    xmldata = gzip.decompress(r.content)
    return ET.parse(io.BytesIO(xmldata)).getroot()     # <tv> element

def pretty(e: ET.Element, depth: int = 0) -> None:
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

# ---------- merge ------------------------------------------------------------

def main() -> None:
    kept_ids, dup_ids = set(), set()
    part_a, part_b = [], []                 # no “channel” in variable names

    # pass-1: keep first occurrence of each id
    for u in URLS:
        root = fetch_root(u)
        for n in root:
            if n.tag == "channel":
                cid = n.get("id")
                if cid in kept_ids:
                    dup_ids.add(cid)
                else:
                    kept_ids.add(cid)
                    part_a.append(n)

    # pass-2: keep programmes only if id not duplicated
    for u in URLS:
        root = fetch_root(u)
        for n in root:
            if n.tag == "programme" and n.get("channel") in kept_ids and n.get("channel") not in dup_ids:
                part_b.append(n)

    # build tree
    out_root = ET.Element("tv")
    out_root.extend(part_a)
    out_root.extend(part_b)
    pretty(out_root)

    # write (UTF-8, LF, no BOM)  ——> **full XML with tags**
    with Path("file1.xml").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        ET.ElementTree(out_root).write(fh, encoding="unicode")

    # sanity-check
    ET.parse("file1.xml")
    print("file1.xml written ✔")

if __name__ == "__main__":
    main()
