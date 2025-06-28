import json

CELL_API_LOGIN = "https://api.frp1.ott.kaltura.com/api_v3/service/OTTUser/action/anonymousLogin"
CELL_API_ASSETS = "https://api.frp1.ott.kaltura.com/api_v3/service/asset/action/list"

def cellcom_login(sess):
    """Get 'ks' token from Cellcom login"""
    payload = {
        "apiVersion": "5.4.0.28193",
        "partnerId": "3197",
        "udid": "f4423331-81a2-4a08-8c62-95515d080d79"
    }
    r = sess.post(CELL_API_LOGIN, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("ks")

def fetch_cellcom_programmes(sess, site_id, since, till, ks):
    # site_id example: '3728##f53ca55a5b454260bc82ccd7e45ba5d8/version/0'
    channel_id = site_id.split("##")[0]
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
    till_str = till.strftime("%Y-%m-%dT%H:%M:%S")
    
    payload = {
        "apiVersion": "5.4.0.28193",
        "clientTag": "2500009-Android",
        "filter": {
            "kSql": f"(and epg_channel_id='{channel_id}' start_date>'{since_str}' end_date<'{till_str}' asset_type='epg')",
            "objectType": "KalturaSearchAssetFilter",
            "orderBy": "START_DATE_ASC"
        },
        "ks": ks,
        "pager": {
            "objectType": "KalturaFilterPager",
            "pageIndex": 1,
            "pageSize": 1000
        }
    }
    r = sess.post(CELL_API_ASSETS, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("objects") or data.get("data") or []

# In your main build_epg() replace or add:

def build_epg():
    start, end = day_window(dt.datetime.now(IL_TZ))
    sess = configure_session()

    # If Cellcom channels exist, login once to get ks
    ks = None
    channels = ET.parse(CHANNELS_FILE).findall("channel")

    if any(ch.attrib.get("site") == "cellcom.co.il" for ch in channels):
        ks = cellcom_login(sess)

    root = ET.Element("tv", {
        "source-info-name": "FreeTV+Cellcom",
        "generator-info-name": "Combined-EPG (proxy)",
    })

    programmes_buffer = []

    for ch in channels:
        site = ch.attrib.get("site")
        site_id = ch.attrib["site_id"]
        xmltv_id = ch.attrib["xmltv_id"]
        name = (ch.text or xmltv_id).strip()

        ch_el = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch_el, "display-name", lang="he").text = name

        if site == "freetv.tv":
            for item in fetch_programmes(sess, site_id, start, end):
                programmes_buffer.append((xmltv_id, item))

        elif site == "cellcom.co.il":
            if not ks:
                raise RuntimeError("No Cellcom login KS token available")
            for item in fetch_cellcom_programmes(sess, site_id, start, end, ks):
                # Normalize fields if needed
                programmes_buffer.append((xmltv_id, item))

        else:
            print(f"Unknown site {site} for channel {xmltv_id}")

    # After channels, write programmes
    for xmltv_id, p in programmes_buffer:
        # Cellcom API fields may differ, adapt accordingly
        start_str = p.get("startDate") or p.get("since")
        end_str = p.get("endDate") or p.get("till")
        title = p.get("name") or p.get("title")
        desc = p.get("description") or p.get("summary")

        if not (start_str and end_str and title):
            continue
        s = dt.datetime.fromisoformat(start_str).astimezone(IL_TZ)
        e = dt.datetime.fromisoformat(end_str).astimezone(IL_TZ)

        pr = ET.SubElement(root, "programme",
                           start=s.strftime("%Y%m%d%H%M%S %z"),
                           stop=e.strftime("%Y%m%d%H%M%S %z"),
                           channel=xmltv_id)
        ET.SubElement(pr, "title", lang="he").text = escape(title)
        if desc:
            ET.SubElement(pr, "desc", lang="he").text = escape(desc)

    ET.indent(root)
    ET.ElementTree(root).write(OUT_XML, encoding="utf-8", xml_declaration=True)
    print("✅ wrote", OUT_XML)
