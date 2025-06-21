import gzip
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom

URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
]

def download_and_parse(url):
    response = requests.get(url)
    response.raise_for_status()
    xml_data = gzip.decompress(response.content).decode("utf-8")
    return ET.fromstring(xml_data)

def main():
    seen_ids = set()
    part_a = []  # <channel>
    part_b = []  # <programme>

    for url in URLS:
        root = download_and_parse(url)

        for el in root:
            if el.tag == "channel":
                cid = el.attrib.get("id")
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    part_a.append(el)
            elif el.tag == "programme":
                part_b.append(el)

    # Build merged XML
    root_out = ET.Element("tv")
    for el in part_a:
        root_out.append(el)
    for el in part_b:
        root_out.append(el)

    # Convert to string and pretty-print with minidom
    raw_str = ET.tostring(root_out, encoding="utf-8")
    parsed = minidom.parseString(raw_str)
    pretty_xml = parsed.toprettyxml(indent="  ", encoding="utf-8")

    # Write final output
    with open("file1.xml", "wb") as f:
        f.write(pretty_xml)

if __name__ == "__main__":
    main()
