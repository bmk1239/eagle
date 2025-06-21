import gzip
import requests
import xml.etree.ElementTree as ET

URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
]

def download_and_parse(url):
    response = requests.get(url)
    response.raise_for_status()
    return ET.fromstring(gzip.decompress(response.content).decode('utf-8'))

def main():
    seen_ids = set()
    part_a = []
    part_b = []

    for url in URLS:
        root = download_and_parse(url)

        # Collect "channel" elements (but avoid using that word in variables)
        for el in root.findall("channel"):
            el_id = el.attrib.get("id")
            if el_id and el_id not in seen_ids:
                seen_ids.add(el_id)
                part_a.append(el)

        # Collect all "programme" elements
        part_b.extend(root.findall("programme"))

    # Create the root of the new EPG XML
    out_root = ET.Element("tv")
    for el in part_a:
        out_root.append(el)
    for el in part_b:
        out_root.append(el)

    ET.ElementTree(out_root).write("file1.xml", encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    main()
