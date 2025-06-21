import gzip
import requests
import re

URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
]

def get_inner_tv_content(xml_text):
    m = re.search(r"<tv[^>]*>(.*)</tv>", xml_text, flags=re.S)
    if not m:
        raise ValueError("Invalid XML: missing <tv> tags")
    return m.group(1)

def main():
    seen_ids = set()
    duplicate_ids = set()
    channels = []
    programmes = []

    for url in URLS:
        response = requests.get(url)
        response.raise_for_status()
        decompressed = gzip.decompress(response.content).decode("utf-8")

        inner = get_inner_tv_content(decompressed)

        # Extract channels
        channel_blocks = re.findall(r"(<channel\b[^>]*>.*?</channel>)", inner, flags=re.S)
        for block in channel_blocks:
            id_match = re.search(r'id="([^"]+)"', block)
            if not id_match:
                continue
            cid = id_match.group(1)
            if cid in seen_ids:
                duplicate_ids.add(cid)
            else:
                seen_ids.add(cid)
                channels.append(block)

    # Now process programmes, ignoring any whose channel is a duplicate id
    for url in URLS:
        response = requests.get(url)
        response.raise_for_status()
        decompressed = gzip.decompress(response.content).decode("utf-8")

        inner = get_inner_tv_content(decompressed)
        programme_blocks = re.findall(r"(<programme\b[^>]*>.*?</programme>)", inner, flags=re.S)
        for pr in programme_blocks:
            ch_match = re.search(r'channel="([^"]+)"', pr)
            if not ch_match:
                continue
            ch_id = ch_match.group(1)
            if ch_id not in duplicate_ids:
                programmes.append(pr)

    # Write merged output
    with open("file1.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write("<tv>\n")
        for ch in channels:
            f.write(ch)
            f.write("\n")
        for pr in programmes:
            f.write(pr)
            f.write("\n")
        f.write("</tv>\n")

if __name__ == "__main__":
    main()
