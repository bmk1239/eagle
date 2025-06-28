#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes and HOT.
Creates a 1-day guide: today 00 : 00 IL → tomorrow 00 : 00 IL
Output: file2.xml
"""

from __future__ import annotations
import datetime as dt, os, re, json, warnings, xml.etree.ElementTree as ET
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo

import cloudscraper, ssl, urllib3, requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ── proxy helper ────────────────────────────────────────────────
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

# ── API endpoints ───────────────────────────────────────────────
FREETV_API   = "https://web.freetv.tv/api/products/lives/programmes"
FREETV_HOME  = "https://web.freetv.tv/"
CELL_LOGIN   = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELL_LIST    = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"
PARTNER_EPG  = "https://my.partner.co.il/TV.Services/MyTvSrv.svc/SeaChange/GetEpg"
YES_CH_BASE  = "https://svc.yes.co.il/api/content/broadcast-schedule/channels"
HOT_API      = "https://www.hot.net.il/HotCmsApiFront/api/ProgramsSchedual/GetProgramsSchedual"

HOT_TIMEOUT  = int(os.getenv("HOT_TIMEOUT", "90"))   # seconds per HOT request

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

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG", "1") not in ("0", "false", "False", "no")
def dbg(site, *m, flush=False):
    if _DBG:
        print(f"[DBG {site}]", *m, flush=True if flush else False)

# ── helpers ─────────────────────────────────────────────────────
_Z_RE = re.compile(r"Z$")
_SLASH_FMT = "%d/%m/%Y %H:%M"          # Partner: “26/06/2025 23:30”

def to_dt(val):
    if isinstance(val, (int, float)):
        return dt.datetime.fromtimestamp(int(val), tz=IL_TZ)
    if isinstance(val, str):
        if "/" in val:
            return datetime.strptime(val, _SLASH_FMT).replace(tzinfo=IL_TZ)
        iso = _Z_RE.sub("+00:00", val)
        return dt.datetime.fromisoformat(iso).astimezone(IL_TZ)
    raise TypeError("unsupported datetime value")

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

# ── FreeTV ─────────────────────────────────────────────
def fetch_freetv(sess, sid, since, till):
    p = {"liveId[]": sid,
         "since": since.strftime("%Y-%m-%dT%H:%M%z"),
         "till":  till.strftime("%Y-%m-%dT%H:%M%z"),
         "lang": "HEB", "platform": "BROWSER"}
    for a in (1, 2):
        r = sess.get(FREETV_API, params=p, timeout=30)
        print(r.url, flush=True)
        if r.status_code == 403 and a == 1:
            sess.get(FREETV_HOME, timeout=20)
            continue
        r.raise_for_status()
        d = r.json()
        return d.get("data", d) if isinstance(d, dict) else d

# ── Cellcom ───────────────────────────────────────────
def _cell_req(sess, ks, chan, sts, ets, quoted):
    q = "'" if quoted else ""
    ksql = (f"(and epg_channel_id='{chan}' start_date>{q}{sts}{q} "
            f"end_date<{q}{ets}{q} asset_type='epg')")
    payload = {"apiVersion": "5.4.0.28193", "clientTag": "2500009-Android",
               "filter": {"kSql": ksql, "objectType": "KalturaSearchAssetFilter",
                          "orderBy": "START_DATE_ASC"},
               "ks": ks,
               "pager": {"objectType": "KalturaFilterPager", "pageIndex": 1, "pageSize": 1000}}
    r = sess.post(CELL_LIST, json=payload, headers=CELL_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    return r.json()

def fetch_cellcom(sess, site_id, since, till):
    chan = site_id.split("##")[0]
    sts, ets = int(since.timestamp()), int(till.timestamp())
    login = {"apiVersion": "5.4.0.28193", "partnerId": "3197",
             "udid": "f4423331-81a2-4a08-8c62-95515d080d79"}
    r = sess.post(CELL_LOGIN, json=login, headers=CELL_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    ks = r.json().get("ks") or r.json().get("result", {}).get("ks")

    data = _cell_req(sess, ks, chan, sts, ets, False)
    objs = data.get("objects") or data.get("result", {}).get("objects", [])
    if objs: return objs
    if data.get("result", {}).get("error", {}).get("code") == "4004":
        data = _cell_req(sess, ks, chan, sts, ets, True)
    return data.get("objects") or data.get("result", {}).get("objects", [])

# ── Partner ───────────────────────────────────────────
def fetch_partner(sess, site_id, since, till):
    chan = site_id.strip()
    body = {"_keys": ["param"], "_values": [f"{chan}|{since:%Y-%m-%d}|UTC"],
            "param": f"{chan}|{since:%Y-%m-%d}|UTC"}
    r = sess.post(PARTNER_EPG, json=body, headers=PARTNER_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    for ch in r.json().get("data", []):
        if ch.get("id") == chan:
            return ch.get("events", [])
    return []

# ── Yes ───────────────────────────────────────────────
def fetch_yes(sess, site_id, since, till):
    chan = site_id.strip()
    url = f"{YES_CH_BASE}/{chan}?date={since:%Y-%m-%d}&ignorePastItems=false"
    r = sess.get(url, headers=YES_HEADERS, timeout=30)
    print(r.url, flush=True)
    r.raise_for_status()
    return r.json().get("items", [])

# ── HOT (hourly shared-cache) ───────────────────────────────────
_hot_cache: dict[int, list[dict]] = {}          # {hour 0-23: [rows]}

def _hot_fetch_hour(sess, day_start: dt.datetime, hour: int) -> list[dict]:
    """Download (once) the full HOT grid for a single hour and cache it."""
    if hour in _hot_cache:                       # reuse if already fetched
        return _hot_cache[hour]

    block_start = day_start + dt.timedelta(hours=hour)
    block_end   = block_start + dt.timedelta(hours=1)

    payload = {
        # ChannelId=0 ⇒ server returns ALL channels for that hour
        "ChannelId": 0,
        "ProgramsStartDateTime": block_start.strftime("%Y-%m-%dT%H:%M:%S"),
        "ProgramsEndDateTime":   block_end.strftime("%Y-%m-%dT%H:%M:%S"),
        "Hour": hour
    }

    dbg("hot.net.il", f"fetch hour {hour:02d}", flush=True)
    r = sess.post(HOT_API, json=payload, headers=HOT_HEADERS, timeout=60)
    print(r.url, flush=True)                     # one URL per hour
    r.raise_for_status()

    data = r.json()
    _hot_cache[hour] = data.get("data", []) if data.get("isSuccess") else []
    return _hot_cache[hour]


def fetch_hot(sess, site_id: str,
              since: dt.datetime, till: dt.datetime) -> list[dict]:
    """
    Collect all rows whose 'channelID' matches site_id
    over the 24 cached hourly blocks.
    """
    chan = site_id.zfill(3)                      # "71" → "071"
    dbg("hot.net.il", f"channel {chan}", flush=True)

    items: list[dict] = []
    for hour in range(24):
        for row in _hot_fetch_hour(sess, since, hour):
            if row.get("channelID", "").zfill(3) == chan:
                items.append(row)
    return items

# ── main build ─────────────────────────────────────────
def build_epg():
    day_start, day_end = day_window(dt.datetime.now(IL_TZ))
    sess = new_session()

    root = ET.Element("tv", {
        "source-info-name": "FreeTV+Cellcom+Partner+Yes+HOT (Day)",
        "generator-info-name": "proxyEPG"
    })

    programmes: list[tuple[str, dict, str]] = []
    id_state: dict[tuple[str, str], bool] = {}

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site = ch.attrib.get("site", "").lower()
        raw  = ch.attrib["site_id"]
        logical = raw.split("##")[0] if site == "cellcom.co.il" else raw
        xmltv = ch.attrib["xmltv_id"]
        name  = (ch.text or xmltv).strip()
        key = (site, logical)

        if key not in id_state:
            ce = ET.SubElement(root, "channel", id=xmltv)
            ET.SubElement(ce, "display-name", lang="he").text = name

        if id_state.get(key):
            dbg(site, "skip duplicate", key, flush=True)
            continue

        try:
            items = (
                fetch_freetv(sess, raw, day_start, day_end) if site == "freetv.tv" else
                fetch_cellcom(sess, raw, day_start, day_end) if site == "cellcom.co.il" else
                fetch_partner(sess, raw, day_start, day_end) if site == "partner.co.il" else
                fetch_yes(sess, raw, day_start, day_end) if site == "yes.co.il" else
                fetch_hot(sess, raw, day_start, day_end) if site == "hot.net.il" else
                []
            )
        except Exception as e:
            dbg(site, "fetch error", xmltv, e, flush=True)
            items = []

        dbg(site, f"{xmltv} → {len(items)} items", flush=True)
        if items:
            id_state[key] = True
            programmes.extend((xmltv, it, site) for it in items)

    for xid, it, site in programmes:
        try:
            if site == "freetv.tv":
                s, e = to_dt(it["since"]), to_dt(it["till"])
                title = it["title"]
                desc  = it.get("description") or it.get("summary")
            elif site == "cellcom.co.il":
                s, e = to_dt(it["startDate"]), to_dt(it["endDate"])
                title = it["name"]
                desc  = it.get("description")
            elif site == "partner.co.il":
                s, e = to_dt(it["start"]), to_dt(it["end"])
                title = it["name"]
                desc  = it.get("shortSynopsis")
            elif site == "hot.net.il":
                s, e = to_dt(it["programStartTime"]), to_dt(it["programEndTime"])
                title = it.get("programTitle") or it.get("programNameHe")
                desc  = it.get("synopsis")
            else:   # yes
                s, e = to_dt(it["starts"]), to_dt(it["ends"])
                title = it["title"]
                desc  = it.get("description")

            pr = ET.SubElement(root, "programme",
                               start=s.strftime("%Y%m%d%H%M%S %z"),
                               stop=e.strftime("%Y%m%d%H%M%S %z"),
                               channel=xid)
            ET.SubElement(pr, "title", lang="he").text = escape(title or "")
            if desc:
                ET.SubElement(pr, "desc", lang="he").text = escape(desc)
        except Exception as e:
            dbg(site, "programme error", xid, e, flush=True)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML, flush=True)

if __name__ == "__main__":
    build_epg()
