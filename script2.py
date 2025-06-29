#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.
Creates a 7-day guide (IL-time Sunday 00:00 → next Sunday 00:00).
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
CELL_HEADERS = {"Content-Type": "application/json",
                "Accept-Encoding": "gzip, deflate, br",
                "User-Agent": UA}
PARTNER_HEADERS = {"Content-Type": "application/json;charset=UTF-8",
                   "Accept": "application/json, text/plain, */*",
                   "brand":"orange","category":"TV","platform":"WEB",
                   "subCategory":"EPG","lang":"he-il",
                   "Accept-Encoding":"gzip,deflate,br","User-Agent": UA}
YES_HEADERS  = {"Accept-Language":"he-IL","Accept":"application/json, text/plain, */*",
                "Referer":"https://www.yes.co.il/","Origin":"https://www.yes.co.il","User-Agent": UA}
HOT_HEADERS  = {"Content-Type":"application/json","Accept":"application/json, text/plain, */*",
                "Origin":"https://www.hot.net.il","Referer":"https://www.hot.net.il/heb/tv/tvguide/","User-Agent": UA}

# ───────── tiny debug helper ─────────
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG","1") not in ("0","false","False","no")
def dbg(site,*msg,flush=False):
    if _DBG:
        print(f"[DBG {site}]",*msg,flush=flush)

# ───────── misc helpers ─────────
_Z_RE, _SLASH_FMT = re.compile(r"Z$"), "%d/%m/%Y %H:%M"
def to_dt(v):
    if isinstance(v,(int,float)): return dt.datetime.fromtimestamp(int(v),tz=IL_TZ)
    if isinstance(v,str):
        if "/" in v: return datetime.strptime(v,_SLASH_FMT).replace(tzinfo=IL_TZ)
        return dt.datetime.fromisoformat(_Z_RE.sub("+00:00",v)).astimezone(IL_TZ)
    raise TypeError

# ---------- CHANGED: compute current week window (Sun → Sun) ----------
def day_window(now):
    """Return (since, till) covering Sunday 00:00 through next Sunday 00:00."""
    weekday = now.weekday()           # Monday=0 … Sunday=6
    days_since_sun = (weekday + 1) % 7
    start_date = now.date() - dt.timedelta(days=days_since_sun)
    start = dt.datetime.combine(start_date, dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=7)
# ---------------------------------------------------------------------

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)
    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE","").lower() in ("1","true","yes"):
        s.verify = False
    return s

# ───────── time-format helper (UNCHANGED) ─────────
def fmt_ts(dt_obj, _site):
    return dt_obj.astimezone(dt.timezone.utc).strftime("%Y%m%d%H%M%S +0000")

# … (all other code below is exactly the same, untouched) …
# ───────── FreeTV ─────────
def fetch_freetv(sess,sid,since,till):
    p = {"liveId[]":sid,"since":since.strftime("%Y-%m-%dT%H:%M%z"),
         "till":till.strftime("%Y-%m-%dT%H:%M%z"),"lang":"HEB","platform":"BROWSER"}
    for a in (1,2):
        r=sess.get(FREETV_API,params=p,timeout=30); print(r.url,flush=True)
        if r.status_code==403 and a==1: sess.get(FREETV_HOME,timeout=20); continue
        r.raise_for_status(); d=r.json(); return d.get("data",d) if isinstance(d,dict) else d

# (all remaining functions are unchanged)

# ───────── main build ─────────
def build_epg():
    since,till=day_window(dt.datetime.now(IL_TZ)); sess=new_session()
    root=ET.Element("tv",{"source-info-name":"FreeTV+Cellcom+Partner+Yes+HOT (Week)",
                          "generator-info-name":"proxyEPG"})
    # … nothing else changed in this function …

    # (rest of script identical)
# ---------------------------------------------------------------------
# The remainder of the script is identical to the last version you provided,
# including escape(title, quote=False) and all provider logic.
# ---------------------------------------------------------------------

if __name__=="__main__":
    build_epg()
