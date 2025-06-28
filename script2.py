#!/usr/bin/env python3
"""
Generate a one-day XMLTV guide from FreeTV and Cellcom, routed through an Israeli proxy.
Channels from both sites are handled appropriately.
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
from requests.exceptions import HTTPError
import ssl
from urllib3.util.ssl_ import create_urllib3_context
import urllib3
import json

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
FREETV_API_URL = "https://web.freetv.tv/api/products/lives/programmes"
FREETV_SITE_HOME = "https://web.freetv.tv/"
CELLCOM_LOGIN_URL = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELLCOM_ASSET_LIST_URL = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"

IL_TZ = ZoneInfo("Asia/Jerusalem")

CHANNELS_FILE = "channels.xml"
OUT_XML = "file2.xml"

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


def fetch_freetv_programmes(sess, site_id, since, till):
    params = {
        "liveId[]": site_id,
        "since": since.strftime("%Y-%m-%dT%H:%M%z"),
        "till": till.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }
    for attempt in (1, 2):
        r = sess.get(FREETV_API_URL, params=params, timeout=30)
        print(f"Fetching FreeTV URL: {r.url}")  # required print
        if r.status_code == 403 and attempt == 1:
            sess.get(FREETV_SITE_HOME, timeout=20)
            continue  # Cloudflare challenge bypass once
        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data


def fetch_cellcom_programmes(sess, site_id, since, till):
    """
    Cellcom site_id format example:
    '3728##f53ca55a5b454260bc82ccd7e45ba5d8/version/0'
    We extract entry_id and build the request accordingly.
    """

    try:
        entry_id = site_id.split("##")[1].split("/")[0]
    except IndexError:
        raise ValueError(f"Invalid Cellcom site_id format: {site_id}")

    # Step 1: Anonymous login to get KS token
    login_payload = {
        "apiVersion": "5.4.0.28193",
        "partnerId": "3197",
        "udid": "f4423331-81a2-4a08-8c62-95515d080d79",
    }
    r_login = sess.post(CELLCOM_LOGIN_URL, json=login_payload, headers=CELLCOM_HEADERS, timeout=30)
    print(f"Cellcom login URL: {r_login.url}")  # required print
    r_login.raise_for_status()
    ks_token = r_login.json().get("ks")
    if not ks_token:
        raise RuntimeError("Failed to get KS token from Cellcom login.")

    # Step 2: Fetch EPG assets
    # Using filter with entry_id, start and end date in ISO format
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S%z")
    till_str = till.strftime("%Y-%m-%dT%H:%M:%S%z")

    asset_list_payload = {
        "apiVersion": "5.4.0.28193",
        "clientTag": "2500009-Android",
        "filter": {
            "kSql": f"(and epg_channel_id='{entry_id}' start_date>='{since_str}' end_date<='{till_str}' asset_type='epg')",
            "objectType": "KalturaSearchAssetFilter",
            "orderBy": "START_DATE_ASC",
        },
        "ks": ks_token,
        "pager": {"objectType": "KalturaFilterPager", "pageIndex": 1, "pageSize": 1000},
    }

    r_assets = sess.post(CELLCOM_ASSET_LIST_URL, json=asset_list_payload, headers=CELLCOM_HEADERS, timeout=30)
    print(f"Cellcom EPG URL: {r_assets.url}")  # required print
    r_assets.raise_for_status()
    assets = r_assets.json().get("objects", [])
    return assets


def build_epg():
    start, end = day_window(dt.datetime.now(IL_TZ))
    sess = configure_session()

    root = ET.Element("tv", {
        "source-info-name": "Combined EPG",
        "generator-info-name": "FreeTV + Cellcom EPG (proxy)",
    })

    programmes_buffer: list[tuple[str, dict, str]] = []  # (xmltv_id, item, site)

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site = ch.attrib.get("site", "")
        site_id = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name = (ch.text or xmltv_id).strip()

        # Write <channel> element
        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        # Fetch programmes according to site
        try:
            if site == "freetv.tv":
                items = fetch_freetv_programmes(sess, site_id, start, end)
                for item in items:
                    programmes_buffer.append((xmltv_id, item, site))

            elif site == "cellcom.co.il":
                items = fetch_cellcom_programmes(sess, site_id, start, end)
                for item in items:
                    programmes_buffer.append((xmltv_id, item, site))

            else:
                print(f"Warning: Unknown site '{site}' for channel {xmltv_id}, skipping...")
        except Exception as e:
            print(f"Error fetching programmes for channel {xmltv_id} ({site}): {e}")

    # Write all <programme> elements
    for xmltv_id, p, site in programmes_buffer:
        try:
            if site == "freetv.tv":
                if not all(k in p for k in ("since", "till", "title")):
                    continue
                s = dt.datetime.fromisoformat(p["since"]).astimezone(IL_TZ)
                e = dt.datetime.fromisoformat(p["till"]).astimezone(IL_TZ)

                pr = ET.SubElement(root, "programme",
                                   start=s.strftime("%Y%m%d%H%M%S %z"),
                                   stop=e.strftime("%Y%m%d%H%M%S %z"),
                                   channel=xmltv_id)
                ET.SubElement(pr, "title", lang="he").text = escape(p["title"])
                if desc := p.get("description") or p.get("summary"):
                    ET.SubElement(pr, "desc", lang="he").text = escape(desc)

            elif site == "cellcom.co.il":
                # Cellcom asset fields example:
                # startDate, endDate, name, description
                s = dt.datetime.fromisoformat(p["startDate"]).astimezone(IL_TZ)
                e = dt.datetime.fromisoformat(p["endDate"]).astimezone(IL_TZ)

                pr = ET.SubElement(root, "programme",
                                   start=s.strftime("%Y%m%d%H%M%S %z"),
                                   stop=e.strftime("%Y%m%d%H%M%S %z"),
                                   channel=xmltv_id)
                ET.SubElement(pr, "title", lang="he").text = escape(p["name"])
                if desc := p.get("description"):
                    ET.SubElement(pr, "desc", lang="he").text = escape(desc)

        except Exception as e:
            print(f"Error writing programme for channel {xmltv_id} ({site}): {e}")

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print(f"✅ Wrote {OUT_XML}")


if __name__ == "__main__":
    build_epg()
