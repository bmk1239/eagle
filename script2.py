#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.

• One-day guide: IL today 00:00 ➜ IL tomorrow 00:00
• HOT schedule is downloaded once (ChannelId=0) and split by channelID.
• <channel> entries whose xmltv_id is empty are skipped.
• If several lines map to the same logical channel, the first provider
  that returns programme data “wins”.
• All <channel> elements are written first, then all <programme>s.
• Output file: file2.xml
"""

from __future__ import annotations
import datetime as dt, os, re, warnings, xml.etree.ElementTree as ET
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo

import cloudscraper, ssl, urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ───────── proxy helper ─────────────────────────────────────────
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

# ───────── API endpoints ────────────────────────────────────────
FREETV_API  = "https://web.freetv.tv/api/products/lives/programmes"
FREETV_HOME = "https://web.freetv.tv/"
CELL_LOGIN  = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELL_LIST   = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"
PARTNER_EPG = "https://my.partner.co.il/TV.Services/MyTvSrv.svc/SeaChange/GetEpg"
YES_CH_BASE = "https://svc.yes.co.il/api/content/broadcast-schedule/channels"
HOT_API     = "https://www.hot.net.il/HotCmsApiFront/api/ProgramsSchedual/GetProgramsSchedual"

# ───────── misc constants ───────────────────────────────────────
IL_TZ         = ZoneInfo("Asia/Jerusalem")
CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"
UA            = "Mozilla/5.0 (Windows NT 10.0; Win64; rv:126.0) Gecko/20100101 Firefox/126.0"

BASE_HEADERS   = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
CELL_HEADERS   = {"Content-Type": "application/json", "Accept-Encoding": "gzip, deflate, br",
                  "User-Agent": UA}
PARTNER_HEADERS= {"Content-Type": "application/json;charset=UTF-8",
                  "Accept": "application/json, text/plain, */*",
                  "brand":"orange","category":"TV","platform":"WEB",
                  "subCategory":"EPG","lang":"he-il",
                  "Accept-Encoding":"gzip,deflate,br","User-Agent": UA}
YES_HEADERS    = {"Accept-Language":"he-IL","Accept":"application/json, text/plain, */*",
                  "Referer":"https://www.yes.co.il/","Origin":"https://www.yes.co.il",
                  "User-Agent": UA}
HOT_HEADERS    = {"Content-Type":"application/json","Accept":"application/json, text/plain, */*",
                  "Origin":"https://www.hot.net.il",
                  "Referer":"https://www.hot.net.il/heb/tv/tvguide/",
                  "User-Agent": UA}

# ───────── debug helper ─────────────────────────────────────────
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG","1").lower() not in ("0","false","no")
def dbg(site,*msg,flush=False):
    if _DBG:
        print(f"[DBG {site}]",*msg,flush=flush)

# ───────── helpers ──────────────────────────────────────────────
_Z_RE, _SLASH_FMT = re.compile(r"Z$"), "%d/%m/%Y %H:%M"
HOT_DT = "%Y/%m/%d %H:%M:%S"

def to_dt(v):
    if isinstance(v,(int,float)):
        return dt.datetime.fromtimestamp(int(v),tz=IL_TZ)
    if isinstance(v,str):
        if "/" in v:
            return datetime.strptime(v,_SLASH_FMT).replace(tzinfo=IL_TZ)
        return dt.datetime.fromisoformat(_Z_RE.sub("+00:00",v)).astimezone(IL_TZ)
    raise TypeError

def day_window(now):
    start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=IL_TZ)
    return start, start + dt.timedelta(days=1)

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)

    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE","").lower() in ("1","true","yes"):
        s.verify = False
    return s

# ───────── provider fetchers (unchanged for non-HOT) ───────────
def fetch_freetv(sess,sid,since,till):
    p={"liveId[]":sid,"since":since.strftime("%Y-%m-%dT%H:%M%z"),
       "till":till.strftime("%Y-%m-%dT%H:%M%z"),"lang":"HEB","platform":"BROWSER"}
    for a in (1,2):
        r=sess.get(FREETV_API,params=p,timeout=30); print(r.url,flush=True)
        if r.status_code==403 and a==1:
            sess.get(FREETV_HOME,timeout=20); continue
        r.raise_for_status(); data=r.json()
        return data.get("data",data) if isinstance(data,dict) else data

def _cell_req(sess,ks,chan,sts,ets,quoted):
    q="'" if quoted else ""
    ksql=f"(and epg_channel_id='{chan}' start_date>{q}{sts}{q} end_date<{q}{ets}{q} asset_type='epg')"
    body={"apiVersion":"5.4.0.28193","clientTag":"2500009-Android",
          "filter":{"kSql":ksql,"objectType":"KalturaSearchAssetFilter","orderBy":"START_DATE_ASC"},
          "ks":ks,"pager":{"objectType":"KalturaFilterPager","pageIndex":1,"pageSize":1000}}
    r=sess.post(CELL_LIST,json=body,headers=CELL_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status()
    return r.json()

def fetch_cellcom(sess,site_id,since,till):
    chan=site_id.split("##")[0]
    sts,ets=int(since.timestamp()),int(till.timestamp())
    login={"apiVersion":"5.4.0.28193","partnerId":"3197","udid":"f442..."}
    r=sess.post(CELL_LOGIN,json=login,headers=CELL_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status()
    ks=r.json().get("ks") or r.json().get("result",{}).get("ks")
    d=_cell_req(sess,ks,chan,sts,ets,False)
    objs=d.get("objects") or d.get("result",{}).get("objects",[])
    if objs: return objs
    if d.get("result",{}).get("error",{}).get("code")=="4004":
        d=_cell_req(sess,ks,chan,sts,ets,True)
        return d.get("objects") or d.get("result",{}).get("objects",[])
    return []

def fetch_partner(sess,site_id,since,_):
    chan=site_id.strip()
    body={"_keys":["param"],"_values":[f"{chan}|{since:%Y-%m-%d}|UTC"],
          "param":f"{chan}|{since:%Y-%m-%d}|UTC"}
    r=sess.post(PARTNER_EPG,json=body,headers=PARTNER_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status()
    for ch in r.json().get("data",[]):
        if ch.get("id")==chan: return ch.get("events",[])
    return []

def fetch_yes(sess,site_id,since,_):
    url=f"{YES_CH_BASE}/{site_id.strip()}?date={since:%Y-%m-%d}&ignorePastItems=false"
    r=sess.get(url,headers=YES_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status()
    return r.json().get("items",[])

# ───────── HOT (single cached request) ─────────────────────────
_HOT_CACHE: dict[str,list] | None = None
def _collect_hot_day(sess,start):
    dbg("hot.net.il","collecting whole day once",flush=True)
    payload={"ChannelId":"0",
             "ProgramsStartDateTime": start.strftime("%Y-%m-%dT00:00:00"),
             "ProgramsEndDateTime":   start.strftime("%Y-%m-%dT23:59:59"),
             "Hour":0}
    r=sess.post(HOT_API,json=payload,headers=HOT_HEADERS,timeout=60); print(r.url,flush=True)
    try:
        rows=r.json().get("data",{}).get("programsDetails",[])
    except Exception as e:
        dbg("hot.net.il","json decode error",e,flush=True); return {}
    dbg("hot.net.il",f"rows total: {len(rows)}",flush=True)
    by={}
    for it in rows:
        cid=str(it.get("channelID","")).zfill(3)
        by.setdefault(cid,[]).append(it)
    return by

def fetch_hot(sess,site_id,start,_):
    global _HOT_CACHE
    if _HOT_CACHE is None:
        _HOT_CACHE=_collect_hot_day(sess,start)
    items=_HOT_CACHE.get(site_id.zfill(3),[])
    dbg("hot.net.il",f"channel {site_id} items: {len(items)}",flush=True)
    return items

# ───────── build EPG ───────────────────────────────────────────
def build_epg():
    since,till = day_window(dt.datetime.now(IL_TZ))
    sess       = new_session()

    root=ET.Element("tv",{"source-info-name":"FreeTV+Cellcom+Partner+Yes+HOT (Day)",
                          "generator-info-name":"proxyEPG"})

    # group by xmltv_id
    variants: dict[str,list[tuple[str,str,str]]] = {}
    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        xmltv=(ch.attrib.get("xmltv_id") or "").strip()
        if not xmltv:
            dbg("skip","empty xmltv_id",flush=True); continue
        site=ch.attrib.get("site","").lower()
        raw =ch.attrib["site_id"]
        name=(ch.text or xmltv).strip()
        variants.setdefault(xmltv,[]).append((site,raw,name))

    # winner selection & channel list
    chosen: dict[str,tuple[str,list,str]] = {}  # xmltv → (site,items,name)
    for xmltv,opts in variants.items():
        for site,raw,name in opts:
            try:
                items=( fetch_freetv(sess,raw,since,till)  if site=="freetv.tv"  else
                        fetch_cellcom(sess,raw,since,till) if site=="cellcom.co.il" else
                        fetch_partner(sess,raw,since,till) if site=="partner.co.il" else
                        fetch_yes(sess,raw,since,till)     if site=="yes.co.il"    else
                        fetch_hot(sess,raw,since,till)     if site=="hot.net.il"   else [] )
            except Exception as e:
                dbg(site,"fetch error",xmltv,e,flush=True); items=[]
            dbg(site,f"{xmltv} → {len(items)} items",flush=True)
            if items:
                chosen[xmltv]=(site,items,name)
                break

    # write <channel> list first
    for xmltv,(site,items,name) in sorted(chosen.items()):
        ch_el=ET.SubElement(root,"channel",id=xmltv)
        ET.SubElement(ch_el,"display-name",lang="he").text=name

    # then write all <programme>s
    for xmltv,(site,items,_) in chosen.items():
        for it in items:
            try:
                if site=="freetv.tv":
                    s,e=to_dt(it["since"]),to_dt(it["till"])
                    title=it["title"]; desc=it.get("description") or it.get("summary")
                elif site=="cellcom.co.il":
                    s,e=to_dt(it["startDate"]),to_dt(it["endDate"])
                    title=it["name"]; desc=it.get("description")
                elif site=="partner.co.il":
                    s,e=to_dt(it["start"]),to_dt(it["end"])
                    title=it["name"]; desc=it.get("shortSynopsis")
                elif site=="hot.net.il":
                    s=dt.datetime.strptime(it["programStartTime"],HOT_DT).replace(tzinfo=IL_TZ)
                    e=dt.datetime.strptime(it["programEndTime"],  HOT_DT).replace(tzinfo=IL_TZ)
                    title=(it.get("programTitle") or it.get("programName") or it.get("programNameHe") or "")
                    desc =it.get("synopsis") or it.get("shortDescription") or ""
                else:   # yes
                    s,e=to_dt(it["starts"]),to_dt(it["ends"])
                    title=it["title"]; desc=it.get("description")

                prog=ET.SubElement(root,"programme",
                                   start=s.strftime("%Y%m%d%H%M%S %z"),
                                   stop =e.strftime("%Y%m%d%H%M%S %z"),
                                   channel=xmltv)
                ET.SubElement(prog,"title",lang="he").text = escape(title)
                if desc:
                    ET.SubElement(prog,"desc",lang="he").text  = escape(desc)
            except Exception as e:
                dbg(site,"programme error",xmltv,e,flush=True)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML,encoding="utf-8",xml_declaration=True)
    print("✅ wrote",OUT_XML,flush=True)

if __name__=="__main__":
    build_epg()
