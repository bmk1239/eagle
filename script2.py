#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.
Creates a 1-week guide (IL-time Sunday 00:00 → Saturday 23:59).
Output: file2.xml
"""

from __future__ import annotations
import datetime as dt, os, re, warnings, json, xml.etree.ElementTree as ET
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

IL_TZ = ZoneInfo("Asia/Jerusalem")
CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; rv:126.0) Gecko/20100101 Firefox/126.0"
BASE_HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
CELL_HEADERS = {"Content-Type": "application/json",
                "Accept-Encoding": "gzip, deflate, br", "User-Agent": UA}
PARTNER_HEADERS = {"Content-Type":"application/json;charset=UTF-8",
                   "Accept":"application/json, text/plain, */*",
                   "brand":"orange","category":"TV","platform":"WEB",
                   "subCategory":"EPG","lang":"he-il",
                   "Accept-Encoding":"gzip,deflate,br","User-Agent": UA}
YES_HEADERS  = {"Accept-Language":"he-IL","Accept":"application/json, text/plain, */*",
                "Referer":"https://www.yes.co.il/","Origin":"https://www.yes.co.il","User-Agent": UA}
HOT_HEADERS  = {"Content-Type":"application/json","Accept":"application/json, text/plain, */*",
                "Origin":"https://www.hot.net.il","Referer":"https://www.hot.net.il/heb/tv/tvguide/","User-Agent": UA}

# ───────── debug helper ─────────
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG","1") not in ("0","false","False","no")
def dbg(tag,*msg,flush=False):
    if _DBG:
        print(f"[DBG {tag}]",*msg,flush=flush)

# ───────── misc helpers ─────────
_Z_RE = re.compile(r"Z$")
def to_dt(v:str|int|float):
    if isinstance(v,(int,float)):
        return dt.datetime.fromtimestamp(int(v),tz=IL_TZ)
    return dt.datetime.fromisoformat(_Z_RE.sub("+00:00",v)).astimezone(IL_TZ)

def week_window(now: dt.datetime):
    # week: Sunday 00:00 → Saturday 23:59:59
    sunday  = dt.datetime.combine(now.date() - dt.timedelta(days=(now.weekday()+1)%7),
                                  dt.time.min, tzinfo=IL_TZ)
    saturday = sunday + dt.timedelta(days=6, hours=23, minutes=59, seconds=59)
    return sunday, saturday

def new_session():
    s = cloudscraper.create_scraper()
    s.mount("https://", InsecureTunnel())
    s.headers.update(BASE_HEADERS)
    proxy = os.getenv("IL_PROXY") or (_ for _ in ()).throw(RuntimeError("IL_PROXY env missing"))
    s.proxies = {"http": proxy, "https": proxy}
    if os.getenv("IL_PROXY_INSECURE","").lower() in ("1","true","yes"):
        s.verify = False
    return s

def fmt_ts(d,_):  # XMLTV UTC timestamp
    return d.astimezone(dt.timezone.utc).strftime("%Y%m%d%H%M%S +0000")

# ───────── FreeTV ─────────
def fetch_freetv(sess,sid,since,till):
    p={"liveId[]":sid,"since":since.strftime("%Y-%m-%dT%H:%M%z"),
       "till":till.strftime("%Y-%m-%dT%H:%M%z"),"lang":"HEB","platform":"BROWSER"}
    r=sess.get(FREETV_API,params=p,timeout=30); print(r.url,flush=True)
    if r.status_code==403:
        sess.get(FREETV_HOME,timeout=20)
        r=sess.get(FREETV_API,params=p,timeout=30); print(r.url,flush=True)
    r.raise_for_status()
    d=r.json()
    return d.get("data",d) if isinstance(d,dict) else d

# ───────── Cellcom ─────────
def _cell_req(sess,ks,chan):
    ksql=f"(and epg_channel_id='{chan}' asset_type='epg')"
    payload={"apiVersion":"5.4.0.28193","clientTag":"2500009-Android",
             "filter":{"kSql":ksql,"objectType":"KalturaSearchAssetFilter",
                       "orderBy":"START_DATE_ASC"},
             "ks":ks,
             "pager":{"objectType":"KalturaFilterPager","pageIndex":1,"pageSize":1000}}
    r=sess.post(CELL_LIST,json=payload,headers=CELL_HEADERS,timeout=30)
    print(r.url,flush=True); r.raise_for_status(); return r.json()

def fetch_cellcom(sess,site_id,since,till):
    chan=site_id.split("##")[0]
    r=sess.post(CELL_LOGIN,
                json={"apiVersion":"5.4.0.28193","partnerId":"3197","udid":"f442..."},
                headers=CELL_HEADERS,timeout=30)
    r.raise_for_status()
    ks=r.json().get("ks") or r.json().get("result",{}).get("ks")

    resp=_cell_req(sess,ks,chan)
    dbg("cellcom.co.il-RAW",json.dumps(resp)[:300])
    objs=resp.get("objects") or resp.get("result",{}).get("objects",[])
    return [o for o in objs
            if to_dt(o["endDate"])>since and to_dt(o["startDate"])<till]

# ───────── Partner (one day) ─────────
def fetch_partner(sess,site_id,since,_):
    chan=site_id.strip()
    body={"_keys":["param"],"_values":[f"{chan}|{since:%Y-%m-%d}|UTC"],
          "param":f"{chan}|{since:%Y-%m-%d}|UTC"}
    r=sess.post(PARTNER_EPG,json=body,headers=PARTNER_HEADERS,timeout=30); r.raise_for_status()
    for ch in r.json().get("data",[]):
        if ch.get("id")==chan: return ch.get("events",[])
    return []

# ───────── Yes (one day) ─────────
def fetch_yes(sess,site_id,since,_):
    url=f"{YES_CH_BASE}/{site_id.strip()}?date={since:%Y-%m-%d}&ignorePastItems=false"
    r=sess.get(url,headers=YES_HEADERS,timeout=30); print(r.url,flush=True); r.raise_for_status()
    return r.json().get("items",[])

# ───────── HOT (single day cached) ─────────
_HOT_CACHE=None; HOT_DT="%Y/%m/%d %H:%M:%S"
def _collect_hot(sess,start):
    payload={"ChannelId":"0",
             "ProgramsStartDateTime":start.strftime("%Y-%m-%dT00:00:00"),
             "ProgramsEndDateTime": start.strftime("%Y-%m-%dT23:59:59"),
             "Hour":0}
    r=sess.post(HOT_API,json=payload,headers=HOT_HEADERS,timeout=60); print(r.url,flush=True)
    rows=r.json().get("data",{}).get("programsDetails",[])
    by={}
    for it in rows: by.setdefault(str(it.get("channelID","")).zfill(3),[]).append(it)
    return by
def fetch_hot(sess,site_id,start,_):
    global _HOT_CACHE
    if _HOT_CACHE is None: _HOT_CACHE=_collect_hot(sess,start)
    return _HOT_CACHE.get(site_id.zfill(3),[])

# ───────── main build ─────────
def build_epg():
    since,till=week_window(dt.datetime.now(IL_TZ)); sess=new_session()
    root=ET.Element("tv",{
        "source-info-name":"FreeTV+Cellcom+Partner+Yes+HOT (Week)",
        "generator-info-name":"proxyEPG"})

    # read channels file
    entries={}
    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        xmltv=(ch.attrib.get("xmltv_id") or "").strip()
        if not xmltv: continue
        entries.setdefault(xmltv,[]).append((
            ch.attrib.get("site","").lower(), ch.attrib["site_id"], (ch.text or xmltv).strip()
        ))

    programmes=[]
    for xmltv,variants in entries.items():
        chosen_items=None; chosen_site=None; chosen_name=None
        for site,raw,name in variants:
            try:
                data=( fetch_freetv(sess,raw,since,till)  if site=="freetv.tv"  else
                       fetch_cellcom(sess,raw,since,till) if site=="cellcom.co.il" else
                       fetch_partner(sess,raw,since,till) if site=="partner.co.il" else
                       fetch_yes(sess,raw,since,till)     if site=="yes.co.il"    else
                       fetch_hot(sess,raw,since,till)     if site=="hot.net.il"   else [] )
            except Exception as e:
                dbg(site,"fetch error",xmltv,e); data=[]
            dbg(site,f"{xmltv} → {len(data)} items")
            if data:
                chosen_items,chosen_site,chosen_name=data,site,name
                break
        if not chosen_items: continue

        CE=ET.SubElement(root,"channel",id=xmltv)
        ET.SubElement(CE,"display-name",lang="he").text=chosen_name

        for it in chosen_items:
            try:
                if chosen_site=="freetv.tv":
                    s,e=to_dt(it["since"]),to_dt(it["till"]); title=it["title"]; desc=it.get("description") or it.get("summary")
                elif chosen_site=="cellcom.co.il":
                    s,e=to_dt(it["startDate"]),to_dt(it["endDate"]); title=it["name"]; desc=it.get("description")
                elif chosen_site=="partner.co.il":
                    s,e=to_dt(it["start"]),to_dt(it["end"]); title=it["name"]; desc=it.get("shortSynopsis")
                elif chosen_site=="hot.net.il":
                    s=dt.datetime.strptime(it["programStartTime"],HOT_DT).replace(tzinfo=IL_TZ)
                    e=dt.datetime.strptime(it["programEndTime"],HOT_DT).replace(tzinfo=IL_TZ)
                    title=it.get("programTitle") or it.get("programName") or it.get("programNameHe") or ""
                    desc =it.get("synopsis") or it.get("shortDescription") or ""
                else:  # yes
                    s,e=to_dt(it["starts"]),to_dt(it["ends"]); title=it["title"]; desc=it.get("description")
                programmes.append((s,e,title,desc,chosen_site,xmltv))
            except Exception as e:
                dbg(chosen_site,"programme error",xmltv,e)

    programmes.sort(key=lambda x:x[0])
    for s,e,title,desc,site,xmltv in programmes:
        pr=ET.SubElement(root,"programme",start=fmt_ts(s,site),stop=fmt_ts(e,site),channel=xmltv)
        ET.SubElement(pr,"title",lang="he").text=escape(title,quote=False)
        if desc:
            ET.SubElement(pr,"desc",lang="he").text=escape(desc,quote=False)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML,encoding="utf-8",xml_declaration=True)
    print("✅ wrote",OUT_XML,flush=True)

if __name__=="__main__":
    build_epg()
