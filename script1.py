import gzip
import requests
import re

URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz",
    "https://www.open-epg.com/files/israel1.xml.gz",
]

def extract_text_parts(url):
    data = gzip.decompress(requests.get(url).content).decode('utf-8')
    # capture content between <tv> and </tv>
    inner = re.search(r"<tv[^>]*>(.*)</tv>", data, flags=re.S).group(1)
    return inner

def main():
    seen = set()
    channel_parts = []
    programme_parts = []

    for url in URLS:
        inner = extract_text_parts(url)
        # split by tags
        for match in re.finditer(r"<(channel|programme)\b.*?</\1>", inner, flags=re.S):
            block = match.group(0)
            if block.startswith("<channel"):
                cid = re.search(r'id="([^"]+)"', block).group(1)
                if cid not in seen:
                    seen.add(cid)
                    channel_parts.append(block)
            else:
                programme_parts.append(block)

    with open("file1.xml", "wb") as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n<tv>\n')
        for ch in channel_parts:
            f.write(ch.encode('utf-8') + b"\n")
        for pr in programme_parts:
            f.write(pr.encode('utf-8') + b"\n")
        f.write(b"</tv>\n")

if __name__ == "__main__":
    main()
