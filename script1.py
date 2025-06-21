#!/usr/bin/env python3
"""
merge_epg.py  –  create a proper XMLTV file (file1.xml) from two .xml.gz sources
"""
import gzip
import io
import requests
import xml.etree.ElementTree as ET
from pathlib import Path

# ----- URLs in the required order -----
URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
]

# ---------- helpers -----------------------------------------------------------

def download_and_parse(url: str) -> ET.Element:
    """Return the <tv> root element of the remote .xml.gz document."""
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    xml_bytes = gzip.decompress(r.content)
    # ElementTree needs a bytes-stream or str.  Use BytesIO so we keep UTF-8 exactly.
    return ET.parse(io.BytesIO(xml_bytes)).getroot()

def indent(elem: ET.Element, level: int = 0) -> None:
    """In-place pretty-printer for ElementTree (no extra blank lines)."""
    i = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = i

# ---------- merge logic -------------------------------------------------------

def main() -> None:
    kept_ids: set[str] = set()       # ids we keep
    pruned_ids: set[str] = set()     # duplicate ids we skip
    first_group: list[ET.Element] = []
    second_group: list[ET.Element] = []

    # pass 1 – collect unique <channel> equivalents
    for url in URLS:
        root = download_and_parse(url)
        for node in root:
            if node.tag == "channel":
                cid = node.get("id")
                if cid in kept_ids:
                    pruned_ids.add(cid)
                else:
                    kept_ids.add(cid)
                    first_group.append(node)

    # pass 2 – collect programme elements whose channel is kept
    for url in URLS:
        root = download_and_parse(url)
        for node in root:
            if node.tag == "programme":
                if node.get("channel") in kept_ids and node.get("channel") not in pruned_ids:
                    second_group.append(node)

    # build unified tree
    out_root = ET.Element("tv")
    out_root.extend(first_group)
    out_root.extend(second_group)

    # pretty-print
    indent(out_root)

    # write with UTF-8, LF, no BOM
    out_path = Path("file1.xml")
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        ET.ElementTree(out_root).write(fh, encoding="unicode")

    # sanity-check: try to re-parse what we wrote
    ET.parse(out_path)

if __name__ == "__main__":
    main()
