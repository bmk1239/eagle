#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.
Creates a 7-day guide (IL-time Sunday 00:00 → next Sunday 00:00).
Output: file2.xml
"""

from __future__ import annotations
import datetime as dt, os, re, warnings, xml.etree.ElementTree as ET
from html import escape
from zoneinfo import ZoneInfo

import cloudscraper, ssl, urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ───────── proxy helper ─────────
class InsecureTunnel(HTTPAdapter):
    def _ctx(self):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    def init_poolmanager(self,*a,**k):  # type: ignore
        k["ssl_context"] = self._ctx()
        return super().init_poolmanager(*a,**k)
    def proxy_manager_for(self,*a,**k):  # type: ignore
        k["ssl_context"] = self._ctx()
        return super().proxy_manager_for(*a,**k)

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

# ───────── minimal debug helper ─────────
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG","1") not in ("0","false","False","no")
def dbg(tag,*msg): 
    if _DBG:
        print(f"[DBG {tag}]",*msg,flush=True)

# ───────── misc helpers ─────────
_Z_RE = re.compile(r"Z$")
def to_dt(v:str|int|float):
    if isinstance(v,(int,float)):
        return dt.datetime.fromtimestamp(int(v),tz=IL_TZ)
    return dt.datetime.fromisoformat(_Z_RE.sub("+00:00",v)).astimezone(IL_TZ)

def week_window(now: dt.datetime):
    sunday = dt.datetime.combine(
        now.date() - dt.timedelta(days=(now.weekday()+1)%7),
        dt.time.min, tzinfo=IL_TZ)
    return sunday, sunday + dt.timedelta(days=7)

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)
    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE","").lower() in ("1","true","yes"):
        s.verify = False
    return s

def fmt_ts(d,_):                 # XMLTV UTC timestamp
    return d.astimezone(dt.timezone.utc).strftime("%Y%m%d%H%M%S +0000")

# ───────── FreeTV (split by day) ─────────
def fetch_freetv(sess,sid,since,till):
    def _one(a,b):
        p={"liveId[]":sid,
           "since":a.strftime("%Y-%m-%dT%H:%M%z"),
           "till": b.strftime("%Y-%m-%dT%H:%M%z"),
           "lang":"HEB","platform":"BROWSER"}
        for attempt in (1,2):
            r=sess.get(FREETV_API,params=p,timeout=30); print(r.url,flush=True)
            if r.status_code==403 and attempt==1:
                sess.get(FREETV_HOME,timeout=20); continue
            r.raise_for_status(); d=r.json()
            return d.get("data",d) if isinstance(d,dict) else d
    cur,since_items=since,[]
    while cur<till:
        nxt=min(cur+dt.timedelta(days=1),till)
        since_items.extend(_one(cur,nxt)); cur=nxt
    return since_items

# ───────── Cellcom  (single call, in-memory filter) ─────────
def _cell_req(sess,ks,chan):
    ksql=f"(and epg_channel_id='{chan}' asset_type='epg')"   # no date in KSQL
    payload={"apiVersion":"5.4.0.28193","clientTag":"2500009-Android",
             "filter":{"kSql":ksql,"objectType":"KalturaSearchAssetFilter",
                       "orderBy":"START_DATE_ASC"},
             "ks":ks,
             "pager":{"objectType":"KalturaFilterPager","pageIndex":1,"pageSize":1000}}
    r=sess.post(CELL_LIST,json=payload,headers=CELL_HEADERS,timeout=30)
    print(r.url,flush=True); r.raise_for_status(); return r.json()

def fetch_cellcom(sess,site_id,since,till):
    chan=site_id.split("##")[0]
    # login
    r=sess.post(CELL_LOGIN,
                json={"apiVersion":"5.4.0.28193","partnerId":"3197","udid":"f442..."},
                headers=CELL_HEADERS,timeout=30); r.raise_for_status()
    ks=r.json().get("ks") or r.json().get("result",{}).get("ks")

    # pull full list once
    resp=_cell_req(sess,ks,chan)
    objs=resp.get("objects") or resp.get("result",{}).get("objects",[])
    # keep only shows overlapping our 7-day window
    return [o for o in objs
            if to_dt(o["endDate"])>since and to_dt(o["startDate"])<till]

# ───────── Partner (split by day) ─────────
def fetch_partner(sess,site_id,since,till):
    chan=site_id.strip()
    def _one(day:dt.datetime):
        body={"_keys":["param"],"_values":[f"{chan}|{day:%Y-%m-%d}|UTC"],
              "param":f"{chan}|{day:%Y-%m-%d}|UTC"}
        r=sess.post(PARTNER_EPG,json=body,headers=PARTNER_HEADERS,timeout=30)
        print(r.url,flush=True); r.raise_for_status()
        for ch in r.json().get("data",[]):
            if ch.get("id")==chan: return ch.get("events",[])
        return []
    cur,out=since,[]
    while cur<till: out.extend(_one(cur)); cur+=dt.timedelta(days=1)
    return out

# ───────── Yes (split by day) ─────────
def fetch_yes(sess,site_id,since,till):
    def _one(day:dt.datetime):
        url=f"{YES_CH_BASE}/{site_id.strip()}?date={day:%Y-%m-%d}&ignorePastItems=false"
        r=sess.get(url,headers=YES_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status()
        return r.json().get("items",[])
    cur,out=since,[]
    while cur<till: out.extend(_one(cur)); cur+=dt.timedelta(days=1)
    return out

# ───────── HOT (cached per calendar day) ─────────
HOT_DT="%Y/%m/%d %H:%M:%S"; _HOT_CACHE={}
def _collect_hot_day(sess,day_start):
    payload={"ChannelId":"0",
             "ProgramsStartDateTime":day_start.strftime("%Y-%m-%dT00:00:00"),
             "ProgramsEndDateTime":  day_start.strftime("%Y-%m-%dT23:59:59"),
             "Hour":0}
    r=sess.post(HOT_API,json=payload,headers=HOT_HEADERS,timeout=60); print(r.url,flush=True)
    rows=r.json().get("data",{}).get("programsDetails",[])
    by={}
    for it in rows: by.setdefault(str(it.get("channelID","")).zfill(3),[]).append(it)
    return by
def fetch_hot(sess,site_id,start,till):
    items,cur=[],start
    while cur<till:
        d=cur.date()
        if d not in _HOT_CACHE: _HOT_CACHE[d]=_collect_hot_day(sess,cur)
        items.extend(_HOT_CACHE[d].get(site_id.zfill(3),[])); cur+=dt.timedelta(days=1)
    return items

# ───────── main build ─────────
def build_epg():
    since,till=week_window(dt.datetime.now(IL_TZ)); sess=new_session()
    root=ET.Element("tv",{"source-info-name":"FreeTV+Cellcom+Partner+Yes+HOT (Week)",
                          "generator-info-name":"proxyEPG"})

    # read channels
    entries={}
    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        xmltv=(ch.attrib.get("xmltv_id") or "").strip()
        if xmltv:
            entries.setdefault(xmltv,[]).append((ch.attrib.get("site","").lower(),
                                                 ch.attrib["site_id"],
                                                 (ch.text or xmltv).strip()))

    programmes=[]
    for xmltv,variants in entries.items():
        chosen=None
        for site,raw,name in variants:
            try:
                items=( fetch_freetv(sess,raw,since,till)  if site=="freetv.tv"  else
                        fetch_cellcom(sess,raw,since,till) if site=="cellcom.co.il" else
                        fetch_partner(sess,raw,since,till) if site=="partner.co.il" else
                        fetch_yes(sess,raw,since,till)     if site=="yes.co.il"    else
                        fetch_hot(sess,raw,since,till)     if site=="hot.net.il"   else [] )
            except Exception as e:
                dbg(site,"fetch error",xmltv,e); items=[]
            dbg(site,f"{xmltv} → {len(items)} items")
            if items:
                chosen=(site,name,items); break
        if not chosen: continue

        site,name,items=chosen
        CE=ET.SubElement(root,"channel",id=xmltv)
        ET.SubElement(CE,"display-name",lang="he").text=name

        for it in items:
            try:
                if site=="freetv.tv":
                    s,e=to_dt(it["since"]),to_dt(it["till"]); title=it["title"]; desc=it.get("description") or it.get("summary")
                elif site=="cellcom.co.il":
                    s,e=to_dt(it["startDate"]),to_dt(it["endDate"]); title=it["name"]; desc=it.get("description")
                elif site=="partner.co.il":
                    s,e=to_dt(it["start"]),to_dt(it["end"]); title=it["name"]; desc=it.get("shortSynopsis")
                elif site=="hot.net.il":
                    s=dt.datetime.strptime(it["programStartTime"],HOT_DT).replace(tzinfo=IL_TZ)
                    e=dt.datetime.strptime(it["programEndTime"],HOT_DT).replace(tzinfo=IL_TZ)
                    title=it.get("programTitle") or it.get("programName") or it.get("programNameHe") or ""
                    desc=it.get("synopsis") or it.get("shortDescription") or ""
                else:  # yes
                    s,e=to_dt(it["starts"]),to_dt(it["ends"]); title=it["title"]; desc=it.get("description")
                programmes.append((s,e,title,desc,site,xmltv))
            except Exception as e:
                dbg(site,"programme error",xmltv,e)

    programmes.sort(key=lambda x:x[0])
    for s,e,title,desc,site,xmltv in programmes:
        pr=ET.SubElement(root,"programme",
                         start=fmt_ts(s,site),stop=fmt_ts(e,site),channel=xmltv)
        ET.SubElement(pr,"title",lang="he").text=escape(title,quote=False)
        if desc:
            ET.SubElement(pr,"desc",lang="he").text=escape(desc,quote=False)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML,encoding="utf-8",xml_declaration=True)
    print("✅ wrote",OUT_XML,flush=True)

if __name__=="__main__":
    build_epg()
