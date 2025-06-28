#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.
Creates a 1-day guide (IL-time today 00:00 → tomorrow 00:00).
Times are written in Israel local offset.  Output: file2.xml
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

def day_window(now):
    s = dt.datetime.combine(now.date(),dt.time.min,tzinfo=IL_TZ)
    return s,s+dt.timedelta(days=1)

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)
    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE","").lower() in ("1","true","yes"):
        s.verify = False
    return s

# ───────── FreeTV ─────────
def fetch_freetv(sess,sid,since,till):
    p = {"liveId[]":sid,"since":since.strftime("%Y-%m-%dT%H:%M%z"),
         "till":till.strftime("%Y-%m-%dT%H:%M%z"),"lang":"HEB","platform":"BROWSER"}
    for a in (1,2):
        r=sess.get(FREETV_API,params=p,timeout=30); print(r.url,flush=True)
        if r.status_code==403 and a==1: sess.get(FREETV_HOME,timeout=20); continue
        r.raise_for_status(); d=r.json(); return d.get("data",d) if isinstance(d,dict) else d

# ───────── Cellcom ─────────
def _cell_req(sess,ks,chan,sts,ets,q):
    q="'"+q if q else ""
    ksql=f"(and epg_channel_id='{chan}' start_date>{q}{sts}{q} end_date<{q}{ets}{q} asset_type='epg')"
    payload={"apiVersion":"5.4.0.28193","clientTag":"2500009-Android",
             "filter":{"kSql":ksql,"objectType":"KalturaSearchAssetFilter","orderBy":"START_DATE_ASC"},
             "ks":ks,"pager":{"objectType":"KalturaFilterPager","pageIndex":1,"pageSize":1000}}
    r=sess.post(CELL_LIST,json=payload,headers=CELL_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status(); return r.json()
def fetch_cellcom(sess,site_id,since,till):
    chan=site_id.split("##")[0]; sts,ets=int(since.timestamp()),int(till.timestamp())
    r=sess.post(CELL_LOGIN,json={"apiVersion":"5.4.0.28193","partnerId":"3197","udid":"f442..."},
                headers=CELL_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status()
    ks=r.json().get("ks") or r.json().get("result",{}).get("ks")
    d=_cell_req(sess,ks,chan,sts,ets,""); objs=d.get("objects") or d.get("result",{}).get("objects",[])
    if objs: return objs
    if d.get("result",{}).get("error",{}).get("code")=="4004":
        d=_cell_req(sess,ks,chan,sts,ets,"'"); return d.get("objects") or d.get("result",{}).get("objects",[])
    return []

# ───────── Partner ─────────
def fetch_partner(sess,site_id,since,_):
    chan=site_id.strip(); body={"_keys":["param"],"_values":[f"{chan}|{since:%Y-%m-%d}|UTC"],"param":f"{chan}|{since:%Y-%m-%d}|UTC"}
    r=sess.post(PARTNER_EPG,json=body,headers=PARTNER_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status()
    for ch in r.json().get("data",[]): 
        if ch.get("id")==chan: return ch.get("events",[])
    return []

# ───────── Yes ─────────
def fetch_yes(sess,site_id,since,_):
    url=f"{YES_CH_BASE}/{site_id.strip()}?date={since:%Y-%m-%d}&ignorePastItems=false"
    r=sess.get(url,headers=YES_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status(); return r.json().get("items",[])

# ───────── HOT (day cache) ─────────
_HOT_CACHE=None; HOT_DT="%Y/%m/%d %H:%M:%S"
def _collect_hot_day(sess,start):
    dbg("hot.net.il","collecting whole day once",flush=True)
    payload={"ChannelId":"0","ProgramsStartDateTime":start.strftime("%Y-%m-%dT00:00:00"),
             "ProgramsEndDateTime": start.strftime("%Y-%m-
