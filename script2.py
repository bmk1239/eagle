#!/usr/bin/env python3
"""
Build a one-day XMLTV guide from FreeTV + Cellcom through an Israeli proxy.
Prints every request URL.  DEBUG=1 adds [DBG] lines.
Output file is always file2.xml.
"""

from __future__ import annotations
import datetime as dt, os, warnings, json, xml.etree.ElementTree as ET
from html import escape
from zoneinfo import ZoneInfo
import cloudscraper, ssl, urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ───────────── proxy helper ─────────────
class InsecureTunnel(HTTPAdapter):
    """Adapter that disables TLS verification when talking to the upstream proxy."""
    def _new_ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # pool for direct HTTPS
    def init_poolmanager(self, connections, maxsize, block=False, **kw):
        kw["ssl_context"] = self._new_ctx()
        return super().init_poolmanager(connections, maxsize, block, **kw)

    # pool for proxy HTTPS
    def proxy_manager_for(self, proxy, **kw):
        kw["ssl_context"] = self._new_ctx()
        return super().proxy_manager_for(proxy, **kw)

# ───────────── constants ─────────────
FREETV_API_URL = "https://web.freetv.tv/api/products/lives/programmes"
FREETV_HOME    = "https://web.freetv.tv/"
CELL_LOGIN = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELL_LIST  = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"

IL_TZ = ZoneInfo("Asia/Jerusalem")
CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"
BASE_HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Origin": FREETV_HOME, "Referer": FREETV_HOME}
CELL_HEADERS = {"Content-Type": "application/json", "Accept-Encoding": "gzip, deflate, br", "User-Agent": UA}

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DEBUG = os.getenv("DEBUG", "1") not in ("0", "false", "False", "no")
def dbg(*m): 
    if _DEBUG: print("[DBG]", *m)

# ───────────── helpers ─────────────
def day_window(now):
    s = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
    return s, s + dt.timedelta(days=1)

def configure():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)

    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        s.verify = False
    return s

# ───────────── FreeTV ─────────────
def fetch_freetv(sess, sid, since, till):
    params = {
        "liveId[]": sid,
        "since": since.strftime("%Y-%m-%dT%H:%M%z"),
        "till":  till.strftime("%Y-%m-%dT%H:%M%z"),
        "lang": "HEB",
        "platform": "BROWSER",
    }
    for a in (1, 2):
        r = sess.get(FREETV_API_URL, params=params, timeout=30); print(r.url)
        if r.status_code == 403 and a == 1:
            sess.get(FREETV_HOME, timeout=20); continue
        r.raise_for_status()
        d = r.json()
        return d.get("data", d) if isinstance(d, dict) else d

# ───────────── Cellcom ─────────────
def fetch_cellcom(sess, site_id, since, till):
    chan = site_id.split("##")[0]

    # 1) login → ks
    r = sess.post(CELL_LOGIN,
                  json={"apiVersion":"5.4.0.28193","partnerId":"3197","udid":"f4423331-81a2-4a08-8c62-95515d080d79"},
                  headers=CELL_HEADERS, timeout=30)
    print(r.url); r.raise_for_status()
    ks = r.json().get("ks") or r.json().get("result", {}).get("ks")
    if not ks: raise RuntimeError("KS token missing")

    # 2) asset list
    since_ts, till_ts = int(since.timestamp()), int(till.timestamp())
    payload = {
        "apiVersion": "5.4.0.28193",
        "clientTag": "2500009-Android",
        "filter": {
            "kSql": f"(and epg_channel_id='{chan}' start_date>{since_ts} end_date<{till_ts} asset_type='epg')",
            "objectType": "KalturaSearchAssetFilter",
            "orderBy": "START_DATE_ASC"
        },
        "ks": ks,
        "pager": {"objectType": "KalturaFilterPager", "pageIndex": 1, "pageSize": 1000}
    }
    dbg("Cellcom payload", json.dumps(payload)[:200] + "…")
    r = sess.post(CELL_LIST, json=payload, headers=CELL_HEADERS, timeout=30)
    print(r.url); r.raise_for_status()
    data = r.json()
    objs = data.get("objects") or data.get("result", {}).get("objects", [])
    if not objs: dbg("Cellcom raw response", json.dumps(data)[:400] + "…")
    return objs

# ───────────── main ─────────────
def build_epg():
    since, till = day_window(dt.datetime.now(IL_TZ)); sess = configure()
    root = ET.Element("tv", {"source-info-name": "FreeTV+Cellcom", "generator-info-name": "proxyEPG"})
    progs=[]

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site = ch.attrib.get("site", "").lower()
        sid  = ch.attrib["site_id"]
        xid  = ch.attrib["xmltv_id"]
        name = (ch.text or xid).strip()
        ET.SubElement(ET.SubElement(root, "channel", id=xid), "display-name", lang="he").text = name
        try:
            if site == "freetv.tv":
                items = fetch_freetv(sess, sid, since, till)
            elif site == "cellcom.co.il":
                items = fetch_cellcom(sess, sid, since, till)
            else:
                dbg("unknown site", site); continue
            dbg(f"{xid} → {len(items)} items")
            progs.extend((xid, i, site) for i in items)
        except Exception as e:
            dbg("fetch error", xid, e)

    for xid, it, site in progs:
        try:
            if site == "freetv.tv":
                s = dt.datetime.fromisoformat(it["since"]).astimezone(IL_TZ)
                e = dt.datetime.fromisoformat(it["till"]).astimezone(IL_TZ)
                title = it["title"]; desc = it.get("description") or it.get("summary")
            else:
                s = dt.datetime.fromisoformat(it["startDate"]).astimezone(IL_TZ)
                e = dt.datetime.fromisoformat(it["endDate"]).astimezone(IL_TZ)
                title = it["name"]; desc = it.get("description")

            pr = ET.SubElement(root, "programme",
                               start=s.strftime("%Y%m%d%H%M%S %z"),
                               stop=e.strftime("%Y%m%d%H%M%S %z"),
                               channel=xid)
            ET.SubElement(pr, "title", lang="he").text = escape(title)
            if desc: ET.SubElement(pr, "desc", lang="he").text = escape(desc)
        except Exception as e:
            dbg("programme error", xid, e)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML)

if __name__ == "__main__":
    build_epg()
