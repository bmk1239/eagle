#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.
Creates a 1-day guide (Israel-time today 00:00 → tomorrow 00:00).
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

# ───────────────────────────────────────────────────────── proxy
class InsecureTunnel(HTTPAdapter):
    def _ctx(self):
        ctx = create_urllib3_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        return ctx
    def init_poolmanager(self, *a, **kw):
        kw["ssl_context"] = self._ctx(); return super().init_poolmanager(*a, **kw)
    def proxy_manager_for(self, *a, **kw):
        kw["ssl_context"] = self._ctx(); return super().proxy_manager_for(*a, **kw)

# ────────────────────────────────────────────────── API endpoints
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
PARTNER_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json, text/plain, */*",
    "brand": "orange", "category": "TV", "platform": "WEB", "subCategory": "EPG", "lang": "he-il",
    "Accept-Encoding": "gzip,deflate,br", "User-Agent": UA
}
YES_HEADERS = {
    "Accept-Language": "he-IL", "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.yes.co.il/", "Origin": "https://www.yes.co.il", "User-Agent": UA
}
HOT_HEADERS = {
    "Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.hot.net.il", "Referer": "https://www.hot.net.il/heb/tv/tvguide/",
    "User-Agent": UA
}

# ───────────────────────────────────────────────────── debug helper
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG", "1").lower() not in ("0", "false", "no")
def dbg(site, *m, flush=False):
    if _DBG:
        print(f"[DBG {site}]", *m, flush=flush)

# ───────────────────────────────────────────────────── tiny helpers
_Z_RE, _SLASH_FMT = re.compile(r"Z$"), "%d/%m/%Y %H:%M"
HOT_DT = "%Y/%m/%d %H:%M:%S"          # 2025/07/02 03:00:00

def to_dt(v):
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(int(v), tz=IL_TZ)
    if isinstance(v, str):
        if "/" in v:
            return datetime.strptime(v, _SLASH_FMT).replace(tzinfo=IL_TZ)
        return dt.datetime.fromisoformat(_Z_RE.sub("+00:00", v)).astimezone(IL_TZ)
    raise TypeError

def day_window(now):
    start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)
    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        s.verify = False
    return s

# ───────────────────────────────────────────────────── FreeTV
def fetch_freetv(sess, sid, since, till):
    p = {"liveId[]": sid, "since": since.strftime("%Y-%m-%dT%H:%M%z"),
         "till": till.strftime("%Y-%m-%dT%H:%M%z"), "lang": "HEB", "platform": "BROWSER"}
    for a in (1, 2):
        r = sess.get(FREETV_API, params=p, timeout=30); print(r.url, flush=True)
        if r.status_code == 403 and a == 1:
            sess.get(FREETV_HOME, timeout=20); continue
        r.raise_for_status(); d = r.json(); return d.get("data", d) if isinstance(d, dict) else d

# ───────────────────────────────────────────────────── Cellcom
def _cell_req(sess, ks, chan, sts, ets, quoted):
    q = "'" if quoted else ""
    ksql = f"(and epg_channel_id='{chan}' start_date>{q}{sts}{q} end_date<{q}{ets}{q} asset_type='epg')"
    payload = {"apiVersion":"5.4.0.28193","clientTag":"2500009-Android",
               "filter":{"kSql": ksql,"objectType":"KalturaSearchAssetFilter","orderBy":"START_DATE_ASC"},
               "ks": ks,"pager":{"objectType":"KalturaFilterPager","pageIndex":1,"pageSize":1000}}
    r = sess.post(CELL_LIST, json=payload, headers=CELL_HEADERS, timeout=30); print(r.url, flush=True)
    r.raise_for_status(); return r.json()

def fetch_cellcom(sess, site_id, since, till):
    chan = site_id.split("##")[0]; sts, ets = int(since.timestamp()), int(till.timestamp())
    login = {"apiVersion":"5.4.0.28193","partnerId":"3197","udid":"f442..."}
    r = sess.post(CELL_LOGIN, json=login, headers=CELL_HEADERS, timeout=30); print(r.url, flush=True); r.raise_for_status()
    ks = r.json().get("ks") or r.json().get("result", {}).get("ks")
    data = _cell_req(sess, ks, chan, sts, ets, False)
    objs = data.get("objects") or data.get("result", {}).get("objects", [])
    if objs: return objs
    if data.get("result", {}).get("error", {}).get("code") == "4004":
        data = _cell_req(sess, ks, chan, sts, ets, True)
        return data.get("objects") or data.get("result", {}).get("objects", [])
    return []

# ───────────────────────────────────────────────────── Partner
def fetch_partner(sess, site_id, since, _):
    chan = site_id.strip()
    body = {"_keys":["param"],"_values":[f"{chan}|{since:%Y-%m-%d}|UTC"],"param":f"{chan}|{since:%Y-%m-%d}|UTC"}
    r = sess.post(PARTNER_EPG, json=body, headers=PARTNER_HEADERS, timeout=30); print(r.url, flush=True); r.raise_for_status()
    for ch in r.json().get("data", []):
        if ch.get("id") == chan: return ch.get("events", [])
    return []

# ───────────────────────────────────────────────────── Yes
def fetch_yes(sess, site_id, since, _):
    url = f"{YES_CH_BASE}/{site_id.strip()}?date={since:%Y-%m-%d}&ignorePastItems=false"
    r = sess.get(url, headers=YES_HEADERS, timeout=30); print(r.url, flush=True); r.raise_for_status()
    return r.json().get("items", [])

# ───────────────────────────────────────────── HOT (cached/sorted)
_HOT_CACHE: dict[str, list] | None = None
def _collect_hot_day(sess, start):
    dbg("hot.net.il", "collect whole day once", flush=True)
    p = {"ChannelId":"0","ProgramsStartDateTime":start.strftime("%Y-%m-%dT00:00:00"),
         "ProgramsEndDateTime": start.strftime("%Y-%m-%dT23:59:59"),"Hour":0}
    r = sess.post(HOT_API, json=p, headers=HOT_HEADERS, timeout=60); print(r.url, flush=True)
    try:
        rows = r.json().get("data", {}).get("programsDetails", [])
    except Exception as e:
        dbg("hot.net.il", "json decode error", e, flush=True); return {}
    today_prefix = start.strftime("%Y/%m/%d")
    chan_map: dict[str, list] = {}
    for row in rows:
        if not str(row.get("programStartTime", "")).startswith(today_prefix):
            continue
        cid = str(row.get("channelID", "")).zfill(3)
        chan_map.setdefault(cid, []).append(row)
    # ---- NEW: sort once per-channel by start-time ---------------------------------
    for lst in chan_map.values():
        lst.sort(key=lambda r: r["programStartTime"])
    # -------------------------------------------------------------------------------
    dbg("hot.net.il", f"kept rows: {sum(len(v) for v in chan_map.values())}", flush=True)
    return chan_map

def fetch_hot(sess, site_id, start, _):
    global _HOT_CACHE
    if _HOT_CACHE is None:
        _HOT_CACHE = _collect_hot_day(sess, start)
    items = _HOT_CACHE.get(site_id.zfill(3), [])
    dbg("hot.net.il", f"channel {site_id} items: {len(items)}", flush=True)
    return items

# ───────────────────────────────────────────────────── main build
def build_epg():
    since, till = day_window(dt.datetime.now(IL_TZ))
    sess = new_session()

    root = ET.Element("tv", {
        "source-info-name": "FreeTV+Cellcom+Partner+Yes+HOT (Day)",
        "generator-info-name": "proxyEPG"
    })

    # 1️⃣ collect all <channel> rows grouped by xmltv_id
    grouped: dict[str, list[tuple[str,str,str,str]]] = {}
    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        xmltv = (ch.attrib.get("xmltv_id") or "").strip()
        if not xmltv:
            dbg("skip", "empty xmltv_id", flush=True); continue
        site = ch.attrib.get("site", "").lower()
        raw  = ch.attrib["site_id"]
        logical = raw.split("##")[0] if site == "cellcom.co.il" else raw
        name = (ch.text or xmltv).strip()
        grouped.setdefault(xmltv, []).append((site, raw, name, logical))

    # 2️⃣ write all channels first, buffer every programme row
    programme_buffer: list[tuple[str, dict, str]] = []   # (xmltv, row, site)

    for xmltv, variants in grouped.items():
        chosen_items = None
        chosen_site  = ""
        display_name = variants[0][2]
        for site, raw, _, _ in variants:
            try:
                items = (
                    fetch_freetv(sess, raw, since, till)  if site == "freetv.tv"  else
                    fetch_cellcom(sess, raw, since, till) if site == "cellcom.co.il" else
                    fetch_partner(sess, raw, since, till) if site == "partner.co.il" else
                    fetch_yes(sess, raw, since, till)     if site == "yes.co.il"    else
                    fetch_hot(sess, raw, since, till)     if site == "hot.net.il"   else []
                )
            except Exception as e:
                dbg(site, "fetch error", xmltv, e, flush=True); items = []
            dbg(site, f"{xmltv} → {len(items)} items", flush=True)
            if items:
                chosen_items, chosen_site = items, site
                break
        if not chosen_items:
            dbg("skip", f"{xmltv}: no data", flush=True); continue

        # write <channel>
        CE = ET.SubElement(root, "channel", id=xmltv)
        ET.SubElement(CE, "display-name", lang="he").text = display_name

        # keep programmes for later
        for row in chosen_items:
            programme_buffer.append((xmltv, row, chosen_site))

    # 3️⃣ after *all* channels, append every <programme>
    for xmltv, row, site in programme_buffer:
        try:
            if site == "freetv.tv":
                s, e = to_dt(row["since"]), to_dt(row["till"])
                title = row["title"]; desc = row.get("description") or row.get("summary")
            elif site == "cellcom.co.il":
                s, e = to_dt(row["startDate"]), to_dt(row["endDate"])
                title = row["name"]; desc = row.get("description")
            elif site == "partner.co.il":
                s, e = to_dt(row["start"]), to_dt(row["end"])
                title = row["name"]; desc = row.get("shortSynopsis")
            elif site == "hot.net.il":
                s = dt.datetime.strptime(row["programStartTime"], HOT_DT).replace(tzinfo=IL_TZ)
                e = dt.datetime.strptime(row["programEndTime"],   HOT_DT).replace(tzinfo=IL_TZ)
                title = row.get("programTitle") or row.get("programName") or row.get("programNameHe") or ""
                desc  = row.get("synopsis") or row.get("shortDescription") or ""
            else:     # yes
                s, e = to_dt(row["starts"]), to_dt(row["ends"])
                title = row["title"]; desc = row.get("description")

            s_utc = s.astimezone(dt.timezone.utc).strftime("%Y%m%d%H%M%S +0000")
            e_utc = e.astimezone(dt.timezone.utc).strftime("%Y%m%d%H%M%S +0000")

            P = ET.SubElement(root, "programme", start=s_utc, stop=e_utc, channel=xmltv)
            ET.SubElement(P, "title", lang="he").text = escape(title)
            if desc:
                ET.SubElement(P, "desc", lang="he").text = escape(desc)
        except Exception as e:
            dbg(site, "programme error", xmltv, e, flush=True)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML, flush=True)

if __name__ == "__main__":
    build_epg()
