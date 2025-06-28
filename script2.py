#!/usr/bin/env python3
"""
Generate a one-day XMLTV guide from FreeTV *and* Cellcom, routed through an Israeli proxy.
Only each request URL is printed; all other logging is silent.
Channels are written first in the XML, and all programme elements afterwards.
"""

from __future__ import annotations

import datetime as dt
import os
import warnings
from html import escape
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import cloudscraper
from requests.adapters import HTTPAdapter
import ssl
from urllib3.util.ssl_ import create_urllib3_context
import urllib3

# ────────────────────────── proxy helper ─────────────────────────
class InsecureTunnel(HTTPAdapter):
    """Disable TLS checks when talking *to* the upstream proxy itself."""
    def _new_ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def init_poolmanager(self, *a, **kw):
        kw["ssl_context"] = self._new_ctx()
        return super().init_poolmanager(*a, **kw)

    def proxy_manager_for(self, *a, **kw):
        kw["ssl_context"] = self._new_ctx()
        return super().proxy_manager_for(*a, **kw)

# ────────────────────────── constants ───────────────────────────
# FreeTV
FREETV_API_URL  = "https://web.freetv.tv/api/products/lives/programmes"
FREETV_SITE_HOME = "https://web.freetv.tv/"

# Cellcom
CELLCOM_LOGIN_URL      = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELLCOM_ASSET_LIST_URL = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"

IL_TZ = ZoneInfo("Asia/Jerusalem")

CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
        "Gecko/20100101 Firefox/126.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": FREETV_SITE_HOME,
    "Referer": FREETV_SITE_HOME,
}

CELLCOM_HEADERS = {
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip, deflate, br",
    "User-Agent": BASE_HEADERS["User-Agent"],
}

# Silence SSL warnings (we deliberately skip TLS validation toward proxy)
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

# ────────────────────────── helpers ───────────────────────────
def day_window(now: dt.datetime):
    start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)

def configure_session():
    sess = cloudscraper.create_scraper()
    sess.mount("https://", InsecureTunnel())
    sess.headers.update(BASE_HEADERS)

    proxy = os.getenv("IL_PROXY")
    if not proxy:
        raise RuntimeError("IL_PROXY secret is missing!")
    sess.proxies = {"http": proxy, "https": proxy}

    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        sess.verify = False

    if cookies := os.getenv("IL_FTV_COOKIES"):
        sess.headers["Cookie"] = cookies

    return sess

# ────────────────────── FreeTV fetch ─────────────────────────
def fetch_freetv_programmes(sess, site_id, since, till):
    params = {
        "liveId[]": site_id,
        "since": since.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  till.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }
    for attempt in (1, 2):
        r = sess.get(FREETV_API_URL, params=params, timeout=30)
        print(r.url)          # required print
        if r.status_code == 403 and attempt == 1:
            sess.get(FREETV_SITE_HOME, timeout=20)
            continue
        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data

# ────────────────────── Cellcom fetch ────────────────────────
def fetch_cellcom_programmes(sess, site_id, since, till):
    """
    Cellcom site_id looks like:
        '3728##f53ca55a5b454260bc82ccd7e45ba5d8/version/0'
    Channel ID = part before '##'
    """
    channel_id = site_id.split("##")[0]

    # 1) login → ks
    login_payload = {
        "apiVersion": "5.4.0.28193",
        "partnerId":  "3197",
        "udid":       "f4423331-81a2-4a08-8c62-95515d080d79",
    }
    r_login = sess.post(CELLCOM_LOGIN_URL, json=login_payload,
                        headers=CELLCOM_HEADERS, timeout=30)
    print(r_login.url)        # required print
    r_login.raise_for_status()
    data = r_login.json()
    ks = data.get("ks") or data.get("result", {}).get("ks")
    if not ks:
        raise RuntimeError("Failed to obtain Cellcom KS token")

    # 2) asset list
    since_ts = int(since.timestamp())
    till_ts  = int(till.timestamp())
    asset_payload = {
        "apiVersion": "5.4.0.28193",
        "clientTag": "2500009-Android",
        "filter": {
            "kSql": (
                f"(and epg_channel_id='{channel_id}' "
                f"start_date>{since_ts} end_date<{till_ts} asset_type='epg')"
            ),
            "objectType": "KalturaSearchAssetFilter",
            "orderBy": "START_DATE_ASC",
        },
        "ks": ks,
        "pager": {
            "objectType": "KalturaFilterPager",
            "pageIndex": 1,
            "pageSize": 1000,
        },
    }
    r_assets = sess.post(CELLCOM_ASSET_LIST_URL, json=asset_payload,
                         headers=CELLCOM_HEADERS, timeout=30)
    print(r_assets.url)       # required print
    r_assets.raise_for_status()
    return r_assets.json().get("objects", [])

# ────────────────────────── main build ─────────────────────────
def build_epg():
    start, end = day_window(dt.datetime.now(IL_TZ))
    sess = configure_session()

    root = ET.Element("tv", {
        "source-info-name": "Combined FreeTV + Cellcom",
        "generator-info-name": "proxy-EPG-builder",
    })

    programmes: list[tuple[str, dict, str]] = []  # (xmltv_id, record, site)

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site      = ch.attrib.get("site", "").lower()
        site_id   = ch.attrib["site_id"]
        xmltv_id  = ch.attrib["xmltv_id"]
        name      = (ch.text or xmltv_id).strip()

        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        try:
            if site == "freetv.tv":
                recs = fetch_freetv_programmes(sess, site_id, start, end)
                programmes.extend((xmltv_id, r, site) for r in recs)

            elif site == "cellcom.co.il":
                recs = fetch_cellcom_programmes(sess, site_id, start, end)
                programmes.extend((xmltv_id, r, site) for r in recs)

            else:
                print(f"Unknown site '{site}' for channel {xmltv_id} – skipped")

        except Exception as exc:
            print(f"Fetch error for {xmltv_id} ({site}): {exc}")

    # write <programme> elements
    for xmltv_id, rec, site in programmes:
        try:
            if site == "freetv.tv":
                s = dt.datetime.fromisoformat(rec["since"]).astimezone(IL_TZ)
                e = dt.datetime.fromisoformat(rec["till"]).astimezone(IL_TZ)
                title = rec["title"]
                desc  = rec.get("description") or rec.get("summary")

            else:  # cellcom
                s = dt.datetime.fromisoformat(rec["startDate"]).astimezone(IL_TZ)
                e = dt.datetime.fromisoformat(rec["endDate"]).astimezone(IL_TZ)
                title = rec["name"]
                desc  = rec.get("description")

            pr = ET.SubElement(root, "programme",
                               start=s.strftime("%Y%m%d%H%M%S %z"),
                               stop=e.strftime("%Y%m%d%H%M%S %z"),
                               channel=xmltv_id)
            ET.SubElement(pr, "title", lang="he").text = escape(title)
            if desc:
                ET.SubElement(pr, "desc", lang="he").text = escape(desc)

        except Exception as exc:
            print(f"Programme error for {xmltv_id}: {exc}")

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML)


if __name__ == "__main__":
    build_epg()
