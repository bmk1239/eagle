import gzip
import requests
import re

URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
]

def get_inner_tv_content(xml_text):
    match = re.search(r"<tv[^>]*>(.*)</tv>", xml_text, flags=re.S)
    if not match:
        raise ValueError("Missing <tv> root element")
    return match.group(1)

def main():
    seen_ids = set()
    duplicate_ids = set()
    channels = []
    programmes = []

    # First pass: collect channels and track duplicates
    for url in URLS:
        data = gzip.decompress(requests.get(url).content).decode("utf-8")
        inner = get_inner_tv_content(data)

        blocks = re.findall(r"(<channel\b[^>]*?>.*?</channel>)", inner, flags=re.S)
        for block in blocks:
            id_match = re.search(r'id="([^"]+)"', block)
            if not id_match:
                continue
            cid = id_match.group(1)
            if cid in seen_ids:
                duplicate_ids.add(cid)
            else:
                seen_ids.add(cid)
                channels.append(block)

    # Second pass: collect programmes only for kept channels
    for url in URLS:
        data = gzip.decompress(requests.get(url).content).decode("utf-8")
        inner = get_inner_tv_content(data)

        prog_blocks = re.findall(r"(<programme\b[^>]*?>.*?</programme>)", inner, flags=re.S)
        for block in prog_blocks:
            ch_id_match = re.search(r'channel="([^"]+)"', block)
            if ch_id_match:
                ch_id = ch_id_match.group(1)
                if ch_id not in duplicate_ids:
                    programmes.append(block)

    # Final output with LF line endings and UTF-8 (no BOM)
    with open("file1.xml", "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write("<tv>\n")
        for ch in channels:
            f.write(ch + "\n")
        for pr in programmes:
            f.write(pr + "\n")
        f.write("</tv>\n")

if __name__ == "__main__":
    main()
