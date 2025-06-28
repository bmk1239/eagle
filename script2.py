#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes and HOT.
 • Generates a one-day guide: 00:00 (IL) → 00:00 next day.
 • Prints every network request; DEBUG=1 also prints   [DBG <site>] …   lines.
 • HOT is fetched **once** (24 hourly blocks) and cached for every HOT channel.
 • Output file:  file2.xml
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import cloudscraper
import ssl
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ─────────────────────────── Proxy helper ──────────────────────────
class InsecureTunnel(HTTPAdapter):
    """TLS verification is disabled only *toward the proxy* itself."""
    def _ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        return ctx
    def init_poolmanager(self, *a, **kw):
        kw["ssl_context"] = self._ctx()
        return super().init_poolmanager(*a, **kw)
    def proxy_manager_for(self, *a, **kw):
        kw["ssl_context"] = self._ctx()
        return super().proxy_manager_for(*a, **kw)

# ─────────────────────────── API endpoints ─────────────────────────
FREETV_API   = "https://web.freetv.tv/api/products/lives/programmes"
FREETV_HOME  = "https://web.freetv.tv/"
CELL_LOGIN   = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELL_LIST    = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"
PARTNER_EPG  = "https://my.partner.co.il/TV.Services/MyTvSrv.svc/SeaChange/GetEpg"
YES_CH_BASE  = "https://svc.yes.co.il/api/content/broadcast-schedule/channels"
HOT_API      = "https://www.hot.net.il/HotCmsApiFront/api/ProgramsSchedual/GetProgramsSchedual"

# ─────────────────────────── Constants ─────────────────────────────
IL_TZ         = ZoneInfo("Asia/Jerusalem")
CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; rv:126.0) Gecko/20100101 Firefox/126.0"

BASE_HEADERS   = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
CELL_HEADERS   = {"Content-Type": "application/json",
                  "Accept-Encoding": "gzip, deflate, br",
                  "User-Agent": UA}
PARTNER_HEADERS = {"Content-Type": "application/json;charset=UTF-8",
                   "Accept": "application/json, text/plain, */*",
                   "brand": "orange", "category": "TV", "platform": "WEB",
                   "subCategory": "EPG", "lang": "he-il",
                   "Accept-Encoding": "gzip,deflate,br", "User-Agent": UA}
YES_HEADERS    = {"Accept-Language": "he-IL",
                  "Accept": "application/json, text/plain, */*",
                  "Referer": "https://www.yes.co.il/",
                  "Origin":  "https://www.yes.co.il",
                  "User-Agent": UA}
HOT_HEADERS    = {"Content-Type": "application/json",
                  "Accept": "application/json, text/plain, */*",
                  "Origin": "https://www.hot.net.il",
                  "Referer": "https://www.hot.net.il/heb/tv/tvguide/",
                  "User-Agent": UA}

# ─────────────────────────── Debug helper ──────────────────────────
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG", "1") not in ("0", "false", "False", "no")
def dbg(site: str, *msg, **kw):
    """Print only when DEBUG is truthy; transparently forwards print() kwargs."""
    if _DBG:
        print(f"[DBG {site}]", *msg, **kw)

# ─────────────────────────── Utilities ─────────────────────────────
_Z_RE        = re.compile(r"Z$")
_SLASH_FMT   = "%d/%m/%Y %H:%M"      # Partner’s “26/06/2025 23:30”

def to_dt(value) -> dt.datetime:
    """Convert unix-seconds, ISO-8601 or DD/MM/YYYY HH:MM → aware IL datetime."""
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(int(value), tz=IL_TZ)
    if isinstance(value, str):
        if "/" in value:
            return datetime.strptime(value, _SLASH_FMT).replace(tzinfo=IL_TZ)
        return dt.datetime.fromisoformat(_Z_RE.sub("+00:00", value)).astimezone(IL_TZ)
    raise TypeError("unsupported time value")

def day_window(now: dt.datetime):
    start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)

    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        s.verify = False
    return s

# ──────────────────────── FreeTV helper ───────────────────────────
def fetch_freetv(sess, sid, since, till):
    params = {"liveId[]": sid,
              "since": since.strftime("%Y-%m-%dT%H:%M%z"),
              "till":  till.strftime("%Y-%m-%dT%H:%M%z"),
              "lang": "HEB", "platform": "BROWSER"}
    for a in (1, 2):
        r = sess.get(FREETV_API, params=params, timeout=30)
        print(r.url, flush=True)
        if r.status_code == 403 and a == 1:
            sess.get(FREETV_HOME, timeout=20)          # warm Cloudflare cookie
            continue
        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data

# ─────────────────────── Cellcom helper ───────────────────────────
def _cell_call(sess, ks, chan, start_ts, end_ts, quoted):
    q = "'" if quoted else ""
    ksql = f"(and epg_channel_id='{chan}' start_date>{q}{start_ts}{q} end_date<{q}{end_ts}{q} asset_type='epg')"
    payload = {"apiVersion": "5.4.0.28193", "clientTag": "2500009-Android",
               "filter": {"kSql": ksql, "objectType": "KalturaSearchAssetFilter",
                          "orderBy": "START_DATE_ASC"},
               "ks": ks, "pager": {"objectType": "KalturaFilterPager",
                                   "pageIndex": 1, "pageSize": 1000}}
    r = sess.post(CELL_LIST, json=payload, headers=CELL_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    return r.json()

def fetch_cellcom(sess, site_id, since, till):
    chan = site_id.split("##")[0]
    st, et = int(since.timestamp()), int(till.timestamp())

    # login (anonymous)
    login = {"apiVersion": "5.4.0.28193", "partnerId": "3197",
             "udid": "f4423331-81a2-4a08-8c62-95515d080d79"}
    lr = sess.post(CELL_LOGIN, json=login, headers=CELL_HEADERS, timeout=30)
    print(lr.url, flush=True)
    lr.raise_for_status()
    ks = lr.json().get("ks") or lr.json().get("result", {}).get("ks")

    data = _cell_call(sess, ks, chan, st, et, quoted=False)
    objs = data.get("objects") or data.get("result", {}).get("objects", [])
    if objs:
        return objs

    # retry with quoted timestamps (API quirk)
    if data.get("result", {}).get("error", {}).get("code") == "4004":
        data2 = _cell_call(sess, ks, chan, st, et, quoted=True)
        return data2.get("objects") or data2.get("result", {}).get("objects", [])
    return []

# ─────────────────────── Partner helper ──────────────────────────
def fetch_partner(sess, site_id, since, _):
    chan  = site_id.strip()
    param = f"{chan}|{since:%Y-%m-%d}|UTC"
    body  = {"_keys": ["param"], "_values": [param], "param": param}
    r = sess.post(PARTNER_EPG, json=body, headers=PARTNER_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    for ch in r.json().get("data", []):
        if ch.get("id") == chan:
            return ch.get("events", [])
    return []

# ───────────────────────── Yes helper ────────────────────────────
def fetch_yes(sess, site_id, since, _):
    chan = site_id.strip()
    url  = f"{YES_CH_BASE}/{chan}?date={since:%Y-%m-%d}&ignorePastItems=false"
    r = sess.get(url, headers=YES_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    return r.json().get("items", [])

# ───────────────────────── HOT helper ────────────────────────────
_HOT_CACHE: dict[str, list] | None = None        # filled once per run

def _hot_collect_day(sess, day_start: dt.datetime) -> dict[str, list]:
    dbg("hot.net.il", "collecting whole day once", flush=True)
    collected: dict[str, list] = {}

    for hour in range(24):
        st = (day_start + dt.timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M:%S")
        et = (day_start + dt.timedelta(hours=hour+1)).strftime("%Y-%m-%dT%H:%M:%S")
        payload = {
            "ChannelId": "0",                       # any id – API ignores it
            "ProgramsStartDateTime": st,
            "ProgramsEndDateTime":   et,
            "Hour": hour
        }
        r = sess.post(HOT_API, json=payload, headers=HOT_HEADERS, timeout=60)
        print(r.url, flush=True)
        r.raise_for_status()
        data = r.json()

        if data.get("isError"):
            continue

        for raw in data.get("data", []):
            if not raw or not str(raw).strip():
                continue                          # skip empty rows
            try:
                item = json.loads(raw) if isinstance(raw, str) else raw
                cid  = str(item.get("channelID", "")).zfill(3)
                collected.setdefault(cid, []).append(item)
            except Exception as exc:
                dbg("hot.net.il", "bad row skipped", exc, flush=True)

    return collected


def fetch_hot(sess, site_id: str, since: dt.datetime, _till: dt.datetime):
    """
    Returns the list of programme dicts for a single HOT channel.
    Data for the entire day is cached on the first call so subsequent
    channels are instantaneous.
    """
    global _HOT_CACHE
    if _HOT_CACHE is None:
        _HOT_CACHE = _hot_collect_day(sess, since)
    return _HOT_CACHE.get(site_id.zfill(3), [])


# ───────────────────────── Main build ────────────────────────────
def build_epg():
    start, end = day_window(dt.datetime.now(IL_TZ))
    sess = new_session()

    root = ET.Element("tv", {"source-info-name": "FreeTV+Cellcom+Partner+Yes+HOT",
                             "generator-info-name": "proxyEPG"})
    id_state: dict[tuple[str, str], bool] = {}
    programmes  : list[tuple[str, dict, str]] = []

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site = ch.attrib.get("site", "").lower()
        raw  = ch.attrib["site_id"]
        logical = raw.split("##")[0] if site == "cellcom.co.il" else raw
        xmltv_id = ch.attrib["xmltv_id"]
        name     = (ch.text or xmltv_id).strip()
        key      = (site, logical)

        # <channel> written once per logical id
        if key not in id_state:
            ce = ET.SubElement(root, "channel", id=xmltv_id)
            ET.SubElement(ce, "display-name", lang="he").text = name

        # skip duplicate logical id if one already produced data
        if id_state.get(key):
            dbg(site, "skip duplicate", key)
            continue

        try:
            items = (
                fetch_freetv(sess, raw, start, end) if site == "freetv.tv"   else
                fetch_cellcom(sess, raw, start, end) if site == "cellcom.co.il" else
                fetch_partner(sess, raw, start, end) if site == "partner.co.il" else
                fetch_yes(sess, raw, start, end)     if site == "yes.co.il"     else
                fetch_hot(sess, raw, start, end)     if site == "hot.net.il"    else
                []
            )
        except Exception as e:
            dbg(site, "fetch error", xmltv_id, e)
            items = []

        dbg(site, f"{xmltv_id} → {len(items)} items")
        if items:
            id_state[key] = True
            programmes.extend((xmltv_id, item, site) for item in items)

    # ---------------- emit <programme> elements ------------------
    for xid, it, site in programmes:
        try:
            if site == "freetv.tv":
                s, e = to_dt(it["since"]), to_dt(it["till"])
                title = it["title"]
                desc  = it.get("description") or it.get("summary")
            elif site == "cellcom.co.il":
                s, e = to_dt(it["startDate"]), to_dt(it["endDate"])
                title = it["name"];  desc = it.get("description")
            elif site == "partner.co.il":
                s, e = to_dt(it["start"]), to_dt(it["end"])
                title = it["name"];  desc = it.get("shortSynopsis")
            elif site == "hot.net.il":
                s, e = to_dt(it["programStartTime"]), to_dt(it["programEndTime"])
                title = it.get("programTitle") or it.get("programNameHe")
                desc  = it.get("synopsis")
            else:  # yes.co.il
                s, e = to_dt(it["starts"]), to_dt(it["ends"])
                title = it["title"]; desc = it.get("description")

            pr = ET.SubElement(root, "programme",
                               start=s.strftime("%Y%m%d%H%M%S %z"),
                               stop=e.strftime("%Y%m%d%H%M%S %z"),
                               channel=xid)
            ET.SubElement(pr, "title", lang="he").text = escape(title or "")
            if desc:
                ET.SubElement(pr, "desc", lang="he").text = escape(desc)
        except Exception as e:
            dbg(site, "programme error", xid, e)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML, flush=True)

if __name__ == "__main__":
    build_epg()
