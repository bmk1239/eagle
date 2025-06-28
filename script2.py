#!/usr/bin/env python3
"""
EPG builder for FreeTV, Cellcom, Partner, Yes **and HOT**.
Creates a 1-day guide (IL-today 00 : 00 → tomorrow 00 : 00).
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

#  ……………  all fetch_* helpers remain unchanged  ……………

# ───────── main build ─────────
def build_epg():
    since,till=day_window(dt.datetime.now(IL_TZ)); sess=new_session()
    root=ET.Element("tv",{"source-info-name":"FreeTV+Cellcom+Partner+Yes+HOT (Day)",
                          "generator-info-name":"proxyEPG"})
    entries: dict[str,list[tuple[str,str,str,str]]] = {}  # xmltv_id -> list of variants

    # group lines by populated xmltv_id
    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        xml_id = (ch.attrib.get("xmltv_id") or "").strip()
        if not xml_id:
            dbg("skip","empty xmltv_id ignored",flush=True)
            continue
        site = ch.attrib.get("site","").lower()
        raw  = ch.attrib["site_id"]
        logical = raw.split("##")[0] if site=="cellcom.co.il" else raw
        name = (ch.text or xml_id).strip()
        entries.setdefault(xml_id,[]).append((site,raw,name,logical))

    # iterate by xmltv_id
    for xml_id, variants in entries.items():
        # try variants until one returns programmes
        items = []; chosen_site = ""; disp_name=variants[0][2]
        for site,raw,name,logical in variants:
            try:
                items = ( fetch_freetv(sess,raw,since,till)  if site=="freetv.tv"  else
                          fetch_cellcom(sess,raw,since,till) if site=="cellcom.co.il" else
                          fetch_partner(sess,raw,since,till) if site=="partner.co.il" else
                          fetch_yes(sess,raw,since,till)     if site=="yes.co.il"    else
                          fetch_hot(sess,logical,since,till)  if site=="hot.net.il"   else [] )
            except Exception as e:
                dbg(site,"fetch error",xml_id,e,flush=True); items=[]
            dbg(site,f"{xml_id} → {len(items)} items",flush=True)
            if items:
                chosen_site=site; disp_name=name; break

        if not items:
            dbg("skip",f"{xml_id}: no data",flush=True)
            continue

        ch_el = ET.SubElement(root,"channel",id=xml_id)
        ET.SubElement(ch_el,"display-name",lang="he").text = disp_name

        for it in items:
            try:
                if chosen_site=="freetv.tv":
                    s,e=to_dt(it["since"]),to_dt(it["till"]); title=it["title"]; desc=it.get("description") or it.get("summary")
                elif chosen_site=="cellcom.co.il":
                    s,e=to_dt(it["startDate"]),to_dt(it["endDate"]); title=it["name"]; desc=it.get("description")
                elif chosen_site=="partner.co.il":
                    s,e=to_dt(it["start"]),to_dt(it["end"]); title=it["name"]; desc=it.get("shortSynopsis")
                elif chosen_site=="hot.net.il":
                    HOT_DT="%Y/%m/%d %H:%M:%S"
                    s=dt.datetime.strptime(it["programStartTime"],HOT_DT).replace(tzinfo=IL_TZ)
                    e=dt.datetime.strptime(it["programEndTime"],  HOT_DT).replace(tzinfo=IL_TZ)
                    title=it.get("programTitle") or it.get("programName") or it.get("programNameHe") or ""
                    desc =it.get("synopsis") or it.get("shortDescription") or ""
                else:  # yes
                    s,e=to_dt(it["starts"]),to_dt(it["ends"]); title=it["title"]; desc=it.get("description")

                # ---------- UTC formatting change (this is the ONLY modification) ----------
                s_utc = s.astimezone(dt.timezone.utc)
                e_utc = e.astimezone(dt.timezone.utc)
                start_attr = s_utc.strftime("%Y%m%d%H%M%S +0000")
                stop_attr  = e_utc.strftime("%Y%m%d%H%M%S +0000")
                # --------------------------------------------------------------------------

                pr=ET.SubElement(root,"programme",start=start_attr,stop=stop_attr,channel=xml_id)
                ET.SubElement(pr,"title",lang="he").text = escape(title)
                if desc:
                    ET.SubElement(pr,"desc",lang="he").text = escape(desc)
            except Exception as e:
                dbg(chosen_site,"programme error",xml_id,e,flush=True)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML,encoding="utf-8",xml_declaration=True)
    print("✅ wrote",OUT_XML,flush=True)

if __name__=="__main__":
    build_epg()
