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
    xml_content = gzip.decompress(response.content).decode('utf-8')
    return ET.fromstring(xml_content)

def main():
    seen_ids = set()
    group_a = []
    group_b = []

    for url in URLS:
        root = download_and_parse(url)

        for el in root.findall("channel"):
            el_id = el.attrib.get("id")
            if el_id and el_id not in seen_ids:
                seen_ids.add(el_id)
                group_a.append(el)

        group_b.extend(root.findall("programme"))

    output_root = ET.Element("tv")
    for el in group_a:
        output_root.append(el)
    for el in group_b:
        output_root.append(el)

    ET.ElementTree(output_root).write("file1.xml", encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    main()
