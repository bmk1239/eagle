import gzip
import requests
import xml.etree.ElementTree as ET

URLS = [
    "https://www.open-epg.com/files/israel1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
]

def download_and_parse(url):
    response = requests.get(url)
    response.raise_for_status()
    xml_content = gzip.decompress(response.content).decode('utf-8')
    root = ET.fromstring(xml_content)
    return root

def main():
    trees = []
    for url in URLS:
        root = download_and_parse(url)
        trees.append(root)

    # Assuming root.tag == 'tv'
    unified_root = ET.Element("tv")

    # To unify, combine <channel> and <programme> from both trees
    for tree in trees:
        for child in tree:
            unified_root.append(child)

    unified_tree = ET.ElementTree(unified_root)
    unified_tree.write("file1.xml", encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    main()
