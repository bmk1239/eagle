#!/usr/bin/env python3
"""
merge_epg.py  – create a correct XMLTV file1.xml from two .xml.gz sources
"""
import gzip
import io
import requests
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------- source files (order matters) ----------
URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
]

# ---------- helper functions ----------------------

def fetch_root(url: str) -> ET.Element:
    """Download .xml.gz and return its <tv> root element."""
    rsp = requests.get(url, timeout=60)
    rsp.raise_for_status()
    xml_bytes = gzip.decompress(rsp.content)
    return ET.parse(io.BytesIO(xml_bytes)).getroot()

def pretty(element: ET.Element, level: int = 0) -> None:
    """Minimal in-place pretty-printer (works on Py-3.8+)."""
    indent = "\n" + "  " * level
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            pretty(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent

# ---------- main merge routine --------------------

def main() -> None:
    kept_ids: set[str] = set()
    dup_ids:  set[str] = set()
    part_a:   list[ET.Element] = []   # kept <channel> elements
    part_b:   list[ET.Element] = []   # kept <programme> elements

    # pass-1  – gather unique channel-like elements
    for url in URLS:
        root = fetch_root(url)
        for node in root:
            if node.tag == "channel":           # tag lookup only
                cid = node.get("id")
                if cid in kept_ids:
                    dup_ids.add(cid)
                else:
                    kept_ids.add(cid)
                    part_a.append(node)

    # pass-2  – gather programme elements only for kept ids
    for url in URLS:
        root = fetch_root(url)
        for node in root:
            if node.tag == "programme":
                if node.get("channel") in kept_ids and node.get("channel") not in dup_ids:
                    part_b.append(node)

    # assemble new tree
    out_root = ET.Element("tv")
    out_root.extend(part_a)
    out_root.extend(part_b)
    pretty(out_root)

    # write (UTF-8, LF, no BOM) ------------------------------------------------
    out_path = Path("file1.xml")
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        ET.ElementTree(out_root).write(fh, encoding="unicode")

    # final sanity-check – abort if not valid XML
    ET.parse(out_path)
    print("file1.xml written and validated → OK")

if __name__ == "__main__":
    main()
