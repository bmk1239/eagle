#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner and Yes.
Creates a 7-day guide, from the most-recent Sunday 00:00 (IL) through the
following Saturday 23:59.  Output: file2.xml
"""

from __future__ import annotations
import datetime as dt, os, re, json, warnings, xml.etree.ElementTree as ET
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo

import cloudscraper, ssl, urllib3
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

IL_TZ         = ZoneInfo("Asia/Jerusalem")
CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; rv:126.0) "
    "Gecko/20100101 Firefox/126.0"
)
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

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG", "0") not in ("0", "false", "False", "no")
def dbg(site, *m):
    if _DBG:
        print(f"[DBG {site}]", *m)

# ── helpers ─────────────────────────────────────────────────────
_Z_RE = re.compile(r"Z$")
_SLASH_FMT = "%d/%m/%Y %H:%M"          # Partner’s “26/06/2025 23:30”

def to_dt(val):
    """Convert unix-int, ISO-8601, or DD/MM/YYYY HH:MM → aware IL datetime."""
    if isinstance(val, (int, float)):
        return dt.datetime.fromtimestamp(int(val), tz=IL_TZ)
    if isinstance(val, str):
        if "/" in val:
            return datetime.strptime(val, _SLASH_FMT).replace(tzinfo=IL_TZ)
        iso = _Z_RE.sub("+00:00", val)
        return dt.datetime.fromisoformat(iso).astimezone(IL_TZ)
    raise TypeError("unsupported datetime value")

def week_window(now: dt.datetime):
    """Return (Sunday 00:00, next Sunday 00:00) for the week containing `now`."""
    days_back = (now.weekday() - 6) % 7      # Python: Monday=0 … Sunday=6
    start = dt.datetime.combine(
        (now - dt.timedelta(days=days_back)).date(),
        dt.time.min, tzinfo=IL_TZ
    )
    return start, start + dt.timedelta(days=7)

def daterange(start: dt.datetime):
    for i in range(7):
        yield (start + dt.timedelta(days=i)).date()

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)
    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"):
        s.verify = False
    return s

# ── FreeTV ──────────────────────────────────────────────────────
def fetch_freetv(sess, sid, since, till):
    p = {"liveId[]": sid,
         "since": since.strftime("%Y-%m-%dT%H:%M%z"),
         "till":  till.strftime("%Y-%m-%dT%H:%M%z"),
         "lang": "HEB", "platform": "BROWSER"}
    for a in (1, 2):
        r = sess.get(FREETV_API, params=p, timeout=30)
        print(r.url)
        if r.status_code == 403 and a == 1:
            sess.get(FREETV_HOME, timeout=20)
            continue
        r.raise_for_status()
        d = r.json()
        return d.get("data", d) if isinstance(d, dict) else d

# ── Cellcom ─────────────────────────────────────────────────────
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
    print(r.url)
    r.raise_for_status()
    return r.json()

def fetch_cellcom(sess, site_id, since, till):
    chan = site_id.split("##")[0]
    sts, ets = int(since.timestamp()), int(till.timestamp())
    login = {"apiVersion": "5.4.0.28193", "partnerId": "3197",
             "udid": "f4423331-81a2-4a08-8c62-95515d080d79"}
    r = sess.post(CELL_LOGIN, json=login, headers=CELL_HEADERS, timeout=30)
    print(r.url)
    r.raise_for_status()
    ks = r.json().get("ks") or r.json().get("result", {}).get("ks")

    data = _cell_req(sess, ks, chan, sts, ets, quoted=False)
    objs = data.get("objects") or data.get("result", {}).get("objects", [])
    if objs:
        return objs
    if data.get("result", {}).get("error", {}).get("code") == "4004":
        data2 = _cell_req(sess, ks, chan, sts, ets, quoted=True)
        return data2.get("objects") or data2.get("result", {}).get("objects", [])
    return objs

# ── Partner (daily loop) ────────────────────────────────────────
def fetch_partner_week(sess, site_id, week_start):
    chan = site_id.strip()
    out: list[dict] = []
    for d in daterange(week_start):
        body = {"_keys": ["param"],
                "_values": [f"{chan}|{d}|UTC"],
                "param": f"{chan}|{d}|UTC"}
        r = sess.post(PARTNER_EPG, json=body, headers=PARTNER_HEADERS, timeout=30)
        print(r.url)
        r.raise_for_status()
        for ch in r.json().get("data", []):
            if ch.get("id") == chan:
                out.extend(ch.get("events", []))
                break
    return out

# ── Yes (daily loop) ────────────────────────────────────────────
def fetch_yes_week(sess, site_id, week_start):
    chan = site_id.strip()
    out: list[dict] = []
    for d in daterange(week_start):
        url = f"{YES_CH_BASE}/{chan}?date={d}&ignorePastItems=false"
        r = sess.get(url, headers=YES_HEADERS, timeout=30)
        print(r.url)
        r.raise_for_status()
        out.extend(r.json().get("items", []))
    return out

# ── main build ─────────────────────────────────────────────────
def build_epg():
    week_start, week_end = week_window(dt.datetime.now(IL_TZ))
    sess = new_session()

    root = ET.Element("tv", {"source-info-name": "FreeTV+Cellcom+Partner+Yes (Sun–Sat)",
                             "generator-info-name": "proxyEPG"})
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
            dbg(site, "skip duplicate", key)
            continue

        try:
            items = (
                fetch_freetv(sess, raw, week_start, week_end)    if site == "freetv.tv"  else
                fetch_cellcom(sess, raw, week_start, week_end)   if site == "cellcom.co.il" else
                fetch_partner_week(sess, raw, week_start)        if site == "partner.co.il" else
                fetch_yes_week(sess, raw, week_start)            if site == "yes.co.il" else
                []
            )
        except Exception as e:
            dbg(site, "fetch error", xmltv, e)
            items = []

        dbg(site, f"{xmltv} → {len(items)} items")
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
            else:   # yes
                s, e = to_dt(it["starts"]), to_dt(it["ends"])
                title = it["title"]
                desc  = it.get("description")

            pr = ET.SubElement(root, "programme",
                               start=s.strftime("%Y%m%d%H%M%S %z"),
                               stop=e.strftime("%Y%m%d%H%M%S %z"),
                               channel=xid)
            ET.SubElement(pr, "title", lang="he").text = escape(title)
            if desc:
                ET.SubElement(pr, "desc", lang="he").text = escape(desc)
        except Exception as e:
            dbg(site, "programme error", xid, e)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML)

if __name__ == "__main__":
    build_epg()
