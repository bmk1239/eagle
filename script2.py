#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.
• One-day guide: IL-today 00:00 → IL-tomorrow 00:00
• HOT: single full-day JSON download, per-channel split – no extra tweaking
• Skips channels whose xmltv_id is empty; first variant with data wins.
• <programme> times are written in UTC (+0000)
• Output file: file2.xml
"""

from __future__ import annotations
import datetime as dt, os, re, warnings, xml.etree.ElementTree as ET
from html import escape
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import cloudscraper, ssl, urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ── proxy helper ───────────────────────────────────────────────
class InsecureTunnel(HTTPAdapter):
    def _ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    def init_poolmanager(self, *a, **kw):
        kw["ssl_context"] = self._ctx()
        return super().init_poolmanager(*a, **kw)
    def proxy_manager_for(self, *a, **kw):
        kw["ssl_context"] = self._ctx()
        return super().proxy_manager_for(*a, **kw)

# ── endpoints & constants ──────────────────────────────────────
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
UA            = "Mozilla/5.0 (Windows NT 10.0; Win64; rv:126.0) Gecko/20100101 Firefox/126.0"

BASE_HEADERS   = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
CELL_HEADERS   = {"Content-Type": "application/json", "Accept-Encoding": "gzip, deflate, br", "User-Agent": UA}
PARTNER_HEADERS = {"Content-Type": "application/json;charset=UTF-8",
                   "Accept": "application/json, text/plain, */*",
                   "brand": "orange", "category": "TV", "platform": "WEB",
                   "subCategory": "EPG", "lang": "he-il",
                   "Accept-Encoding": "gzip,deflate,br", "User-Agent": UA}
YES_HEADERS    = {"Accept-Language": "he-IL", "Accept": "application/json, text/plain, */*",
                  "Referer": "https://www.yes.co.il/", "Origin": "https://www.yes.co.il",
                  "User-Agent": UA}
HOT_HEADERS    = {"Content-Type": "application/json",
                  "Accept": "application/json, text/plain, */*",
                  "Origin": "https://www.hot.net.il",
                  "Referer": "https://www.hot.net.il/heb/tv/tvguide/",
                  "User-Agent": UA}

# ── debug helper ───────────────────────────────────────────────
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG", "1").lower() not in ("0", "false", "no")
def dbg(site, *msg, flush=False):
    if _DBG:
        print(f"[DBG {site}]", *msg, flush=flush)

# ── parsing helpers ────────────────────────────────────────────
_Z_RE      = re.compile(r"Z$")
SLASH_FMT  = "%d/%m/%Y %H:%M"
HOT_FMT    = "%Y/%m/%d %H:%M:%S"   # raw string from HOT

def to_dt(v: str | int | float) -> dt.datetime:
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(int(v), tz=IL_TZ)
    if isinstance(v, str):
        if "/" in v:
            return datetime.strptime(v, SLASH_FMT).replace(tzinfo=IL_TZ)
        return dt.datetime.fromisoformat(_Z_RE.sub("+00:00", v)).astimezone(IL_TZ)
    raise TypeError("bad datetime")

def day_window(now: dt.datetime):
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

# ── FreeTV ─────────────────────────────────────────────────────
def fetch_freetv(sess, sid, since, till):
    p = {"liveId[]": sid, "since": since.strftime("%Y-%m-%dT%H:%M%z"),
         "till": till.strftime("%Y-%m-%dT%H:%M%z"), "lang": "HEB", "platform": "BROWSER"}
    for attempt in (1, 2):
        r = sess.get(FREETV_API, params=p, timeout=30); print(r.url, flush=True)
        if r.status_code == 403 and attempt == 1:
            sess.get(FREETV_HOME, timeout=20); continue
        r.raise_for_status(); d = r.json(); return d.get("data", d) if isinstance(d, dict) else d

# ── Cellcom / Partner / Yes (unchanged logic) ─────────────────
def _cell_req(sess, ks, chan, sts, ets, quoted):
    q = "'" if quoted else ""
    ksql = f"(and epg_channel_id='{chan}' start_date>{q}{sts}{q} end_date<{q}{ets}{q} asset_type='epg')"
    payload = {"apiVersion": "5.4.0.28193", "clientTag": "2500009-Android",
               "filter": {"kSql": ksql, "objectType": "KalturaSearchAssetFilter",
                          "orderBy": "START_DATE_ASC"},
               "ks": ks,
               "pager": {"objectType": "KalturaFilterPager", "pageIndex": 1, "pageSize": 1000}}
    r = sess.post(CELL_LIST, json=payload, headers=CELL_HEADERS, timeout=30); print(r.url, flush=True); r.raise_for_status()
    return r.json()

def fetch_cellcom(sess, site_id, since, till):
    chan = site_id.split("##")[0]; sts, ets = int(since.timestamp()), int(till.timestamp())
    ks = sess.post(CELL_LOGIN, json={"apiVersion":"5.4.0.28193","partnerId":"3197","udid":"f442..."},
                   headers=CELL_HEADERS, timeout=30).json().get("ks")
    data = _cell_req(sess, ks, chan, sts, ets, False); objs = data.get("objects") or data.get("result", {}).get("objects", [])
    return objs or _cell_req(sess, ks, chan, sts, ets, True).get("objects", [])

def fetch_partner(sess, site_id, since, _):
    chan = site_id.strip()
    r = sess.post(PARTNER_EPG,
                  json={"_keys":["param"],"_values":[f"{chan}|{since:%Y-%m-%d}|UTC"],
                        "param":f"{chan}|{since:%Y-%m-%d}|UTC"},
                  headers=PARTNER_HEADERS, timeout=30)
    for ch in r.json().get("data", []):
        if ch.get("id") == chan:
            return ch.get("events", [])
    return []

def fetch_yes(sess, site_id, since, _):
    url = f"{YES_CH_BASE}/{site_id.strip()}?date={since:%Y-%m-%d}&ignorePastItems=false"
    return sess.get(url, headers=YES_HEADERS, timeout=30).json().get("items", [])

# ── HOT (single download – **no further filtering or edits**) ──
_HOT_CACHE: dict[str, list] | None = None
def _collect_hot_day(sess, start):
    dbg("hot.net.il", "collect whole day once", flush=True)
    payload = {"ChannelId": "0",
               "ProgramsStartDateTime": start.strftime("%Y-%m-%dT00:00:00"),
               "ProgramsEndDateTime":   start.strftime("%Y-%m-%dT23:59:59"),
               "Hour": 0}
    rows = sess.post(HOT_API, json=payload, headers=HOT_HEADERS, timeout=60) \
               .json().get("data", {}).get("programsDetails", [])
    chan_map: dict[str, list] = {}
    for it in rows:
        cid = str(it.get("channelID", "")).zfill(3)
        chan_map.setdefault(cid, []).append(it)
    dbg("hot.net.il", f"rows total: {sum(len(v) for v in chan_map.values())}", flush=True)
    return chan_map

def fetch_hot(sess, site_id, since, _):
    global _HOT_CACHE
    if _HOT_CACHE is None:
        _HOT_CACHE = _collect_hot_day(sess, since)
    items = _HOT_CACHE.get(site_id.zfill(3), [])
    dbg("hot.net.il", f"channel {site_id} items: {len(items)}", flush=True)
    return items

# ── build XMLTV ────────────────────────────────────────────────
def build_epg():
    since, till = day_window(dt.datetime.now(IL_TZ))
    sess = new_session()

    root = ET.Element("tv", {"source-info-name": "FreeTV+Cellcom+Partner+Yes+HOT (Day)",
                             "generator-info-name": "proxyEPG"})

    grouped: dict[str, list[tuple[str, str, str]]] = {}
    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        xml_id = (ch.attrib.get("xmltv_id") or "").strip()
        if not xml_id:
            continue
        grouped.setdefault(xml_id, []).append(
            (ch.attrib.get("site","").lower(), ch.attrib["site_id"], (ch.text or xml_id).strip())
        )

    for xml_id, variants in grouped.items():
        items = []; origin = ""; disp_name = variants[0][2]
        for site, sid, _ in variants:
            try:
                items = (fetch_freetv(sess, sid, since, till)  if site == "freetv.tv"  else
                         fetch_cellcom(sess, sid, since, till) if site == "cellcom.co.il" else
                         fetch_partner(sess, sid, since, till) if site == "partner.co.il" else
                         fetch_yes(sess, sid, since, till)     if site == "yes.co.il"    else
                         fetch_hot(sess, sid, since, till)     if site == "hot.net.il"   else [])
            except Exception as e:
                dbg(site, "fetch error", xml_id, e, flush=True); items = []
            if items:
                origin = site; break
        if not items:
            continue

        ch_el = ET.SubElement(root, "channel", id=xml_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = disp_name

        for it in items:
            try:
                if origin == "freetv.tv":
                    s, e = to_dt(it["since"]), to_dt(it["till"])
                    title = it["title"]; desc = it.get("description") or it.get("summary")
                elif origin == "cellcom.co.il":
                    s, e = to_dt(it["startDate"]), to_dt(it["endDate"])
                    title = it["name"]; desc = it.get("description")
                elif origin == "partner.co.il":
                    s, e = to_dt(it["start"]), to_dt(it["end"])
                    title = it["name"]; desc = it.get("shortSynopsis")
                elif origin == "hot.net.il":
                    s = datetime.strptime(it["programStartTime"], HOT_FMT).replace(tzinfo=IL_TZ)
                    e = datetime.strptime(it["programEndTime"],   HOT_FMT).replace(tzinfo=IL_TZ)
                    title = (it.get("programTitle") or it.get("programName") or it.get("programNameHe") or "")
                    desc  = it.get("synopsis") or it.get("shortDescription") or ""
                else:  # yes
                    s, e = to_dt(it["starts"]), to_dt(it["ends"])
                    title = it["title"]; desc = it.get("description")

                p = ET.SubElement(root, "programme",
                                  start=s.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000"),
                                  stop =e.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000"),
                                  channel=xml_id)
                ET.SubElement(p, "title", lang="he").text = escape(title)
                if desc:
                    ET.SubElement(p, "desc", lang="he").text = escape(desc)
            except Exception as e:
                dbg(origin, "programme error", xml_id, e, flush=True)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML, flush=True)

if __name__ == "__main__":
    build_epg()
