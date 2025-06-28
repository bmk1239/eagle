#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.
Creates a 1-day guide (IL-time: today 00:00 → tomorrow 00:00).
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
        ctx = create_urllib3_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        return ctx
    def init_poolmanager(self, *a, **kw):
        kw["ssl_context"] = self._ctx(); return super().init_poolmanager(*a, **kw)
    def proxy_manager_for(self, *a, **kw):
        kw["ssl_context"] = self._ctx();  return super().proxy_manager_for(*a, **kw)

# ───────── endpoints ─────────
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
PARTNER_HEADERS= {"Content-Type": "application/json;charset=UTF-8","Accept":"application/json, text/plain, */*",
                  "brand":"orange","category":"TV","platform":"WEB","subCategory":"EPG","lang":"he-il",
                  "Accept-Encoding":"gzip,deflate,br","User-Agent": UA}
YES_HEADERS    = {"Accept-Language":"he-IL","Accept":"application/json, text/plain, */*",
                  "Referer":"https://www.yes.co.il/","Origin":"https://www.yes.co.il","User-Agent": UA}
HOT_HEADERS    = {"Content-Type":"application/json","Accept":"application/json, text/plain, */*",
                  "Origin":"https://www.hot.net.il","Referer":"https://www.hot.net.il/heb/tv/tvguide/","User-Agent": UA}

# ───────── debug ─────────
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
_DBG = os.getenv("DEBUG","1").lower() not in ("0","false","no")
def dbg(site,*msg,flush=False):
    if _DBG:
        print(f"[DBG {site}]",*msg,flush=flush)

# ───────── helpers ─────────
_Z_RE, _SLASH_FMT = re.compile(r"Z$"), "%d/%m/%Y %H:%M"
HOT_DT = "%Y/%m/%d %H:%M:%S"

def to_dt(v):
    if isinstance(v,(int,float)): return dt.datetime.fromtimestamp(int(v),tz=IL_TZ)
    if isinstance(v,str):
        if "/" in v: return datetime.strptime(v,_SLASH_FMT).replace(tzinfo=IL_TZ)
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

# ───────── FreeTV / Cellcom / Partner / Yes – unchanged functions here ─────────
# (omitted for brevity – they are identical to your last working copy)

# ───────── HOT (single cached download, **no filtering**) ─────────
_HOT_CACHE: dict[str,list] | None = None
def _collect_hot_day(sess, start):
    dbg("hot.net.il","collecting once",flush=True)
    payload = {"ChannelId":"0",
               "ProgramsStartDateTime": start.strftime("%Y-%m-%dT00:00:00"),
               "ProgramsEndDateTime":   start.strftime("%Y-%m-%dT23:59:59"),
               "Hour": 0}
    r = sess.post(HOT_API, json=payload, headers=HOT_HEADERS, timeout=60)
    print(r.url, flush=True)
    try:
        rows = r.json().get("data",{}).get("programsDetails",[])
    except Exception as e:
        dbg("hot.net.il","json decode error",e,flush=True)
        return {}
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

# ───────── main build (identical to your last working copy) ─────────
def build_epg():
    since,till=day_window(dt.datetime.now(IL_TZ))
    sess=new_session()

    root=ET.Element("tv",{"source-info-name":"FreeTV+Cellcom+Partner+Yes+HOT (Day)",
                          "generator-info-name":"proxyEPG"})
    grouped: dict[str,list[tuple[str,str,str,str]]] = {}

    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        xmltv=(ch.attrib.get("xmltv_id") or "").strip()
        if not xmltv:
            dbg("skip","empty xmltv_id",flush=True); continue
        site=ch.attrib.get("site","").lower()
        raw=ch.attrib["site_id"]
        logical=raw.split("##")[0] if site=="cellcom.co.il" else raw
        name=(ch.text or xmltv).strip()
        grouped.setdefault(xmltv,[]).append((site,raw,name,logical))

    for xmltv,variants in grouped.items():
        got=None; got_site=""; disp_name=variants[0][2]
        for site,raw,_,_ in variants:
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
                got,got_site=items,site; break
        if not got:
            dbg("skip",f"{xmltv}: no data",flush=True); continue

        ch_el=ET.SubElement(root,"channel",id=xmltv)
        ET.SubElement(ch_el,"display-name",lang="he").text=disp_name

        for it in got:
            try:
                if got_site=="freetv.tv":
                    s,e=to_dt(it["since"]),to_dt(it["till"])
                    title=it["title"]; desc=it.get("description") or it.get("summary")
                elif got_site=="cellcom.co.il":
                    s,e=to_dt(it["startDate"]),to_dt(it["endDate"])
                    title=it["name"]; desc=it.get("description")
                elif got_site=="partner.co.il":
                    s,e=to_dt(it["start"]),to_dt(it["end"])
                    title=it["name"]; desc=it.get("shortSynopsis")
                elif got_site=="hot.net.il":
                    s=dt.datetime.strptime(it["programStartTime"],HOT_DT).replace(tzinfo=IL_TZ)
                    e=dt.datetime.strptime(it["programEndTime"],  HOT_DT).replace(tzinfo=IL_TZ)
                    title=(it.get("programTitle") or it.get("programName") or it.get("programNameHe") or "")
                    desc=it.get("synopsis") or it.get("shortDescription") or ""
                else:  # yes
                    s,e=to_dt(it["starts"]),to_dt(it["ends"])
                    title=it["title"]; desc=it.get("description")

                P=ET.SubElement(root,"programme",
                                start=s.strftime("%Y%m%d%H%M%S %z"),
                                stop=e.strftime("%Y%m%d%H%M%S %z"),
                                channel=xmltv)
                ET.SubElement(P,"title",lang="he").text=escape(title)
                if desc: ET.SubElement(P,"desc",lang="he").text=escape(desc)
            except Exception as e:
                dbg(got_site,"programme error",xmltv,e,flush=True)

    ET.indent(root); ET.ElementTree(root).write(OUT_XML,encoding="utf-8",xml_declaration=True)
    print("✅ wrote",OUT_XML,flush=True)

if __name__=="__main__":
    build_epg()
