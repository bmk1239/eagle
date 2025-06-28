#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes and HOT.
Creates a 1-day guide (IL-time today 00:00 → tomorrow 00:00).
Output: file2.xml
"""

from __future__ import annotations
import datetime as dt, os, re, warnings, xml.etree.ElementTree as ET
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo

import cloudscraper, ssl, urllib3, json
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ───────── proxy helper ─────────
class InsecureTunnel(HTTPAdapter):
    def _ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    def init_poolmanager(self, con, maxsize, block=False, **kw):
        kw["ssl_context"] = self._ctx()
        return super().init_poolmanager(con, maxsize, block, **kw)
    def proxy_manager_for(self, proxy, **kw):
        kw["ssl_context"] = self._ctx()
        return super().proxy_manager_for(proxy, **kw)

# ───────── API endpoints ─────────
FREETV_API  = "https://web.freetv.tv/api/products/lives/programmes"
FREETV_HOME = "https://web.freetv.tv/"
CELL_LOGIN  = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELL_LIST   = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"
PARTNER_EPG = "https://my.partner.co.il/TV.Services/MyTvSrv.svc/SeaChange/GetEpg"
YES_CH_BASE = "https://svc.yes.co.il/api/content/broadcast-schedule/channels"
HOT_API     = "https://www.hot.net.il/HotCmsApiFront/api/ProgramsSchedual/GetProgramsSchedual"

IL_TZ         = ZoneInfo("Asia/Jerusalem")
CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; rv:126.0) Gecko/20100101 Firefox/126.0"
BASE_HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
CELL_HEADERS = {"Content-Type": "application/json", "Accept-Encoding": "gzip, deflate, br", "User-Agent": UA}
PARTNER_HEADERS = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json, text/plain, */*", "brand": "orange", "category": "TV", "platform": "WEB", "subCategory": "EPG", "lang": "he-il", "User-Agent": UA}
YES_HEADERS = {"Accept-Language": "he-IL", "Accept": "application/json, text/plain, */*", "Referer": "https://www.yes.co.il/", "Origin": "https://www.yes.co.il", "User-Agent": UA}
HOT_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*", "Origin": "https://www.hot.net.il", "Referer": "https://www.hot.net.il/heb/tv/tvguide/", "User-Agent": UA}

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG", "1").lower() not in ("0", "false", "no")
def dbg(site, *msg, flush=False):
    if _DBG:
        print(f"[DBG {site}]", *msg, flush=flush)

_Z_RE = re.compile(r"Z$")
_SLASH_FMT = "%d/%m/%Y %H:%M"
HOT_DT = "%Y/%m/%d %H:%M:%S"

def to_dt(v):
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(int(v), tz=IL_TZ)
    if isinstance(v, str):
        if "/" in v:
            return datetime.strptime(v, _SLASH_FMT).replace(tzinfo=IL_TZ)
        return dt.datetime.fromisoformat(_Z_RE.sub("+00:00", v)).astimezone(IL_TZ)
    raise TypeError

def day_window(now):
    s = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
    return s, s + dt.timedelta(days=1)

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)
    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        s.verify = False
    return s

def fetch_freetv(sess, sid, since, till):
    p = {"liveId[]": sid, "since": since.strftime("%Y-%m-%dT%H:%M%z"),
         "till": till.strftime("%Y-%m-%dT%H:%M%z"), "lang": "HEB", "platform": "BROWSER"}
    for a in (1, 2):
        r = sess.get(FREETV_API, params=p, timeout=30)
        print(r.url, flush=True)
        if r.status_code == 403 and a == 1:
            sess.get(FREETV_HOME, timeout=20)
            continue
        r.raise_for_status()
        d = r.json()
        return d.get("data", d) if isinstance(d, dict) else d

def fetch_cellcom(sess, site_id, since, till):
    chan = site_id.split("##")[0]
    sts, ets = int(since.timestamp()), int(till.timestamp())
    r = sess.post(CELL_LOGIN, json={"apiVersion": "5.4.0.28193", "partnerId": "3197", "udid": "f442..."}, headers=CELL_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    ks = r.json().get("ks") or r.json().get("result", {}).get("ks")
    def _cell_req(q):
        ksql = f"(and epg_channel_id='{chan}' start_date>{q}{sts}{q} end_date<{q}{ets}{q} asset_type='epg')"
        payload = {"apiVersion": "5.4.0.28193", "clientTag": "2500009-Android",
                   "filter": {"kSql": ksql, "objectType": "KalturaSearchAssetFilter", "orderBy": "START_DATE_ASC"},
                   "ks": ks, "pager": {"objectType": "KalturaFilterPager", "pageIndex": 1, "pageSize": 1000}}
        r2 = sess.post(CELL_LIST, json=payload, headers=CELL_HEADERS, timeout=30)
        print(r2.url, flush=True)
        r2.raise_for_status()
        return r2.json()
    d = _cell_req("")
    objs = d.get("objects") or d.get("result", {}).get("objects", [])
    if objs:
        return objs
    if d.get("result", {}).get("error", {}).get("code") == "4004":
        return _cell_req("'").get("objects", [])
    return []

def fetch_partner(sess, site_id, since, _):
    chan = site_id.strip()
    body = {"_keys": ["param"], "_values": [f"{chan}|{since:%Y-%m-%d}|UTC"], "param": f"{chan}|{since:%Y-%m-%d}|UTC"}
    r = sess.post(PARTNER_EPG, json=body, headers=PARTNER_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    for ch in r.json().get("data", []):
        if ch.get("id") == chan:
            return ch.get("events", [])
    return []

def fetch_yes(sess, site_id, since, _):
    url = f"{YES_CH_BASE}/{site_id.strip()}?date={since:%Y-%m-%d}&ignorePastItems=false"
    r = sess.get(url, headers=YES_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    return r.json().get("items", [])

# HOT uses full day request with caching
_HOT_CACHE = None
def _collect_hot_day(sess, start):
    dbg("hot.net.il", "collecting full day", flush=True)
    payload = {"ChannelId": "0", "ProgramsStartDateTime": start.strftime("%Y-%m-%dT00:00:00"),
               "ProgramsEndDateTime": start.strftime("%Y-%m-%dT23:59:59"), "Hour": 0}
    r = sess.post(HOT_API, json=payload, headers=HOT_HEADERS, timeout=60)
    print(r.url, flush=True)
    rows = r.json().get("data", {}).get("programsDetails", [])
    today = start.strftime("%Y/%m/%d")
    by = {}
    for it in rows:
        if "programStartTime" not in it: continue
        cid = str(it.get("channelID", "")).zfill(3)
        by.setdefault(cid, []).append(it)
    return by

def fetch_hot(sess, site_id, start, _):
    global _HOT_CACHE
    if _HOT_CACHE is None:
        _HOT_CACHE = _collect_hot_day(sess, start)
    return _HOT_CACHE.get(site_id.zfill(3), [])

# ───────── main builder ─────────
def build_epg():
    since, till = day_window(dt.datetime.now(IL_TZ))
    sess = new_session()
    root = ET.Element("tv", {"source-info-name": "FreeTV+Cellcom+Partner+Yes+HOT", "generator-info-name": "proxyEPG"})
    channels = []
    programmes = []
    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        xmltv = (ch.attrib.get("xmltv_id") or "").strip()
        if not xmltv:
            continue
        site = ch.attrib.get("site", "").lower()
        raw = ch.attrib["site_id"]
        name = (ch.text or xmltv).strip()
        sources = [(site, raw, name)]

        items, used_site = None, None
        for s, r, n in sources:
            try:
                items = (fetch_freetv(sess, r, since, till) if s == "freetv.tv" else
                         fetch_cellcom(sess, r, since, till) if s == "cellcom.co.il" else
                         fetch_partner(sess, r, since, till) if s == "partner.co.il" else
                         fetch_yes(sess, r, since, till) if s == "yes.co.il" else
                         fetch_hot(sess, r, since, till) if s == "hot.net.il" else [])
            except Exception as e:
                dbg(s, "error", xmltv, e, flush=True)
                items = []
            if items:
                used_site = s
                break
        if not items:
            continue

        CE = ET.SubElement(root, "channel", id=xmltv)
        ET.SubElement(CE, "display-name", lang="he").text = name
        channels.append(CE)

        for it in items:
            try:
                if used_site == "freetv.tv":
                    s, e = to_dt(it["since"]), to_dt(it["till"])
                    title = it["title"]
                    desc = it.get("description") or it.get("summary")
                elif used_site == "cellcom.co.il":
                    s, e = to_dt(it["startDate"]), to_dt(it["endDate"])
                    title = it["name"]
                    desc = it.get("description")
                elif used_site == "partner.co.il":
                    s, e = to_dt(it["start"]), to_dt(it["end"])
                    title = it["name"]
                    desc = it.get("shortSynopsis")
                elif used_site == "hot.net.il":
                    s = dt.datetime.strptime(it["programStartTime"], HOT_DT).replace(tzinfo=IL_TZ)
                    e = dt.datetime.strptime(it["programEndTime"], HOT_DT).replace(tzinfo=IL_TZ)
                    title = it.get("programTitle") or it.get("programName") or it.get("programNameHe") or ""
                    desc = it.get("synopsis") or it.get("shortDescription") or ""
                else:
                    s, e = to_dt(it["starts"]), to_dt(it["ends"])
                    title = it["title"]
                    desc = it.get("description")

                if not (since <= s < till): continue
                P = ET.Element("programme", start=s.strftime("%Y%m%d%H%M%S %z"),
                               stop=e.strftime("%Y%m%d%H%M%S %z"), channel=xmltv)
                ET.SubElement(P, "title", lang="he").text = escape(title)
                if desc: ET.SubElement(P, "desc", lang="he").text = escape(desc)
                programmes.append(P)
            except Exception as e:
                dbg(used_site, "programme error", xmltv, e, flush=True)

    for ch in channels:
        root.append(ch)
    for pr in programmes:
        root.append(pr)
    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML, flush=True)

if __name__ == "__main__":
    build_epg()
