#!/usr/bin/env python3
"""
Generate a one-day XMLTV guide from FreeTV *and* Cellcom, routed through an IL proxy.
For every request the full URL is printed.  
Extra debug prints (`[DBG]`) show the number of items fetched per channel.

Set env:
    IL_PROXY              – http://host:port
    IL_PROXY_INSECURE=1   – (optional) skip TLS check toward proxy
"""

from __future__ import annotations
import datetime as dt, os, warnings, xml.etree.ElementTree as ET
from html import escape
from zoneinfo import ZoneInfo

import cloudscraper, ssl, urllib3, json
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ────────────────────────── proxy helper ─────────────────────────
class InsecureTunnel(HTTPAdapter):
    def _new_ctx(self):
        ctx = create_urllib3_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
        return ctx
    def init_poolmanager(self,*a,**kw): kw["ssl_context"]=self._new_ctx(); return super().init_poolmanager(*a,**kw)
    def proxy_manager_for(self,*a,**kw): kw["ssl_context"]=self._new_ctx(); return super().proxy_manager_for(*a,**kw)

# ────────────────────────── constants ───────────────────────────
FREETV_API_URL   = "https://web.freetv.tv/api/products/lives/programmes"
FREETV_SITE_HOME = "https://web.freetv.tv/"
CELLCOM_LOGIN_URL      = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELLCOM_ASSET_LIST_URL = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"

IL_TZ = ZoneInfo("Asia/Jerusalem")
CHANNELS_FILE = "channels.xml"
OUT_XML       = "file2.xml"

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": FREETV_SITE_HOME,
    "Referer": FREETV_SITE_HOME,
}
CELLCOM_HEADERS = {"Content-Type":"application/json","Accept-Encoding":"gzip, deflate, br","User-Agent":BASE_HEADERS["User-Agent"]}
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

_DEBUG = os.getenv("DEBUG","1") not in ("0","false","False","no")

def dbg(msg:str): 
    if _DEBUG: print("[DBG]",msg)

# ────────────────────────── helpers ───────────────────────────
def day_window(now:dt.datetime):
    start=dt.datetime.combine(now.date(),dt.time.min,tzinfo=IL_TZ)
    return start,start+dt.timedelta(days=1)

def configure_session():
    sess=cloudscraper.create_scraper(); sess.mount("https://",InsecureTunnel()); sess.headers.update(BASE_HEADERS)
    proxy=os.getenv("IL_PROXY"); 
    if not proxy: raise RuntimeError("IL_PROXY env missing")
    sess.proxies={"http":proxy,"https":proxy}
    if os.getenv("IL_PROXY_INSECURE","").lower() in ("1","true","yes"): sess.verify=False
    if c:=os.getenv("IL_FTV_COOKIES"): sess.headers["Cookie"]=c
    return sess

# ────────────────────── FreeTV fetch ─────────────────────────
def fetch_freetv(sess, site_id, since, till):
    params={"liveId[]":site_id,"since":since.strftime("%Y-%m-%dT%H:%M%z"),
            "till":till.strftime("%Y-%m-%dT%H:%M%z"),"lang":"HEB","platform":"BROWSER"}
    for attempt in (1,2):
        r=sess.get(FREETV_API_URL,params=params,timeout=30); print(r.url)
        if r.status_code==403 and attempt==1: sess.get(FREETV_SITE_HOME,timeout=20); continue
        r.raise_for_status(); data=r.json()
        return data.get("data",data) if isinstance(data,dict) else data

# ────────────────────── Cellcom fetch ────────────────────────
def fetch_cellcom(sess, site_id, since, till):
    channel_id=site_id.split("##")[0]
    # login
    login_payload={"apiVersion":"5.4.0.28193","partnerId":"3197","udid":"f4423331-81a2-4a08-8c62-95515d080d79"}
    r_login=sess.post(CELLCOM_LOGIN_URL,json=login_payload,headers=CELLCOM_HEADERS,timeout=30)
    print(r_login.url); r_login.raise_for_status()
    data=r_login.json(); ks=data.get("ks") or data.get("result",{}).get("ks")
    if not ks: raise RuntimeError("Cellcom KS token missing")

    since_ts=int(since.timestamp()); till_ts=int(till.timestamp())
    payload={
        "apiVersion":"5.4.0.28193","clientTag":"2500009-Android",
        "filter":{
            "kSql":f"(and epg_channel_id='{channel_id}' start_date>{since_ts} end_date<{till_ts} asset_type='epg')",
            "objectType":"KalturaSearchAssetFilter","orderBy":"START_DATE_ASC"},
        "ks":ks,"pager":{"objectType":"KalturaFilterPager","pageIndex":1,"pageSize":1000}}
    r=sess.post(CELLCOM_ASSET_LIST_URL,json=payload,headers=CELLCOM_HEADERS,timeout=30)
    print(r.url); r.raise_for_status()
    data=r.json(); return data.get("objects") or data.get("result",{}).get("objects",[])

# ────────────────────────── main build ─────────────────────────
def build_epg():
    since,till=day_window(dt.datetime.now(IL_TZ)); sess=configure_session()
    root=ET.Element("tv",{"source-info-name":"FreeTV+Cellcom","generator-info-name":"proxyEPG"})
    progs:list[tuple[str,dict,str]]=[]
    for ch in ET.parse(CHANNELS_FILE).findall("channel"):
        site=ch.attrib.get("site","").lower(); site_id=ch.attrib["site_id"]; xid=ch.attrib["xmltv_id"]; name=(ch.text or xid).strip()
        ch_el=ET.SubElement(root,"channel",id=xid); ET.SubElement(ch_el,"display-name",lang="he").text=name
        try:
            if site=="freetv.tv":
                items=fetch_freetv(sess,site_id,since,till)
            elif site=="cellcom.co.il":
                items=fetch_cellcom(sess,site_id,since,till)
            else:
                dbg(f"Unknown site {site} for {xid}"); continue
            dbg(f"{xid} ({site}) -> {len(items)} items")
            progs.extend((xid,i,site) for i in items)
        except Exception as e:
            dbg(f"Fetch error {xid}: {e}")

    for xid,item,site in progs:
        try:
            if site=="freetv.tv":
                s=dt.datetime.fromisoformat(item["since"]).astimezone(IL_TZ)
                e=dt.datetime.fromisoformat(item["till"]).astimezone(IL_TZ)
                title=item["title"]; desc=item.get("description") or item.get("summary")
            else:
                s=dt.datetime.fromisoformat(item["startDate"]).astimezone(IL_TZ)
                e=dt.datetime.fromisoformat(item["endDate"]).astimezone(IL_TZ)
                title=item["name"]; desc=item.get("description")
            pr=ET.SubElement(root,"programme",
                             start=s.strftime("%Y%m%d%H%M%S %z"),
                             stop=e.strftime("%Y%m%d%H%M%S %z"),
                             channel=xid)
            ET.SubElement(pr,"title",lang="he").text=escape(title)
            if desc: ET.SubElement(pr,"desc",lang="he").text=escape(desc)
        except Exception as e:
            dbg(f"Programme error {xid}: {e}")

    ET.indent(root); ET.ElementTree(root).write(OUT_XML,encoding="utf-8",xml_declaration=True)
    print("✅ wrote",OUT_XML)

if __name__=="__main__":
    build_epg()
