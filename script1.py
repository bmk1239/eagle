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
    root = ET.fromstring(xml_content)
    return root

def main():
    seen_channel_ids = set()
    all_channels = []
    all_programmes = []

    for url in URLS:
        root = download_and_parse(url)

        # Extract channels and programmes separately
        channels = [ch for ch in root.findall('channel')]
        programmes = [pr for pr in root.findall('programme')]

        # Add channels if not duplicate id
        for ch in channels:
            ch_id = ch.attrib.get('id')
            if ch_id and ch_id not in seen_channel_ids:
                seen_channel_ids.add(ch_id)
                all_channels.append(ch)

        # Add all programmes (no deduplication)
        all_programmes.extend(programmes)

    # Build unified root
    unified_root = ET.Element('tv')

    # Append all unique channels first
    for ch in all_channels:
        unified_root.append(ch)

    # Then append all programmes
    for pr in all_programmes:
        unified_root.append(pr)

    # Write output file with XML declaration and UTF-8 encoding
    tree = ET.ElementTree(unified_root)
    tree.write("unified_epg.xml", encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    main()
