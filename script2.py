#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes and HOT.
Creates a 1-day guide, from 00:00 today (IL) to 00:00 next day.
Output: file2.xml
"""

from __future__ import annotations
import datetime as dt, os, re, warnings, xml.etree.ElementTree as ET
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo

import cloudscraper, ssl, urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ── proxy helper ────────────────────────────────────────────────
class InsecureTunnel(HTTPAdapter):
    def _ctx(self):
        ctx = create_urllib3_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        return ctx
    def init_poolmanager(self, con, maxsize, block=False, **kw):
        kw["ssl_context"] = self._ctx(); return super().init_poolmanager(con, maxsize, block, **kw)
    def proxy_manager_for(self, proxy, **kw):
        kw["ssl_context"] = self._ctx(); return super().proxy_manager_for(proxy, **kw)

# ── API endpoints ───────────────────────────────────────────────
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
PARTNER_HEADERS = {"Content-Type": "application/json;charset=UTF-8",
                   "Accept": "application/json, text/plain, */*",
                   "brand": "orange", "category": "TV", "platform": "WEB",
                   "subCategory": "EPG", "lang": "he-il",
                   "Accept-Encoding": "gzip,deflate,br", "User-Agent": UA}
YES_HEADERS  = {"Accept-Language": "he-IL", "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.yes.co.il/", "Origin": "https://www.yes.co.il", "User-Agent": UA}
HOT_HEADERS  = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.hot.net.il", "Referer": "https://www.hot.net.il/heb/tv/tvguide/",
                "User-Agent": UA}

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG", "1") not in ("0", "false", "False", "no")
def dbg(site, *m):                # unified debug helper
    if _DBG: print(f"[DBG {site}]", *m)

# ── helpers ─────────────────────────────────────────────────────
_Z_RE = re.compile(r"Z$")
_SLASH_FMT = "%d/%m/%Y %H:%M"      # Partner’s “26/06/2025 23:30”

def to_dt(v):
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(int(v), tz=IL_TZ)
    if isinstance(v, str):
        if "/" in v:  return datetime.strptime(v, _SLASH_FMT).replace(tzinfo=IL_TZ)
        return dt.datetime.fromisoformat(_Z_RE.sub("+00:00", v)).astimezone(IL_TZ)
    raise TypeError("bad datetime")

def day_window(now):
    start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)

def new_session():
    s = cloudscraper.create_scraper(); s.mount("https://", InsecureTunnel()); s.headers.update(BASE_HEADERS)
    s.proxies = {"http": os.environ["IL_PROXY"], "https": os.environ["IL_PROXY"]}
    if os.getenv("IL_PROXY_INSECURE", "").lower() in ("1", "true", "yes"): s.verify = False
    return s

# ── FreeTV / Cellcom / Partner / Yes  – unchanged functions here ──
# … (omitted for brevity – they are identical to what you supplied) …

# ── HOT (modified: debug only) ───────────────────────────────────
def fetch_hot(sess, site_id, since, _):
    chan = site_id.lstrip("0") or "0"
    dbg("hot.net.il", f"fetch {chan}")          # single debug line instead of 24 URLs
    items: list[dict] = []
    for hour in range(24):
        start = since + dt.timedelta(hours=hour)
        end   = start + dt.timedelta(hours=1)
        payload = {
            "ChannelId": chan,
            "ProgramsStartDateTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "ProgramsEndDateTime":   end.strftime("%Y-%m-%dT%H:%M:%S"),
            "Hour": hour
        }
        r = sess.post(HOT_API, json=payload, headers=HOT_HEADERS, timeout=30)
        r.raise_for_status()
        if r.json().get("isSuccess"): items.extend(r.json().get("data", []))
    return items

# ── build_epg (unchanged apart from HOT branch already included) ──
# … full build_epg exactly as in your last message …

if __name__ == "__main__":
    build_epg()
