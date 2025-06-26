//  ──────────────────────────────────────────────────────────────────────
//  FreeTV EPG grabber for epg-grabber v3+
//  • Keeps local Israel time with dayjs.tz(keepLocalTime=true)
//  • Sends browser-style headers so FreeTV’s edge lets us in
//  • Throttles to one request every 1.2 s to avoid burst bans
//  • Works both locally and in CI (if the runner has an IL IP)
//  ──────────────────────────────────────────────────────────────────────

const dayjs             = require('dayjs')
const utc                = require('dayjs/plugin/utc')
const timezone           = require('dayjs/plugin/timezone')
const customParseFormat  = require('dayjs/plugin/customParseFormat')
dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(customParseFormat)

// ── Constants ───────────────────────────────────────────────────────────

const TZ            = 'Asia/Jerusalem'
const ISO_NO_COLON  = 'YYYY-MM-DDTHH:mmZZ'      // 04:00+0300

// ── Exported grabber spec ───────────────────────────────────────────────

module.exports = {
  site:  'freetv.tv',
  days:  2,

  /* Throttle & single worker keep us below FreeTV’s rate-limit */
  delay:       1200,   // ms between requests  (≈0 .8 req/s)
  concurrency: 1,      // never more than one open request

  /* Browser-like headers: pass Cloudflare / Akamai checks */
  request: {
    headers () {
      return {
        'User-Agent':
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept':           'application/json, text/plain, */*',
        'Accept-Language':  'he-IL,he;q=0.9,en;q=0.8',
        'Origin':           'https://web.freetv.tv',
        'Referer':          'https://web.freetv.tv/'
      }
    }
  },

  /* Build one-day window that matches FreeTV’s 04:00→04:00 schedule */
  url ({ channel, date }) {
    // keepLocalTime=true by using instance .tz(zone, true)
    const start = dayjs(date)
      .tz(TZ, true)           // tag 2025-06-26 as Israel time, no shift
      .startOf('day')         // 00:00 local
      .add(4, 'hour')         // API wants 04:00 → next-day 04:00

    const since = start.format(ISO_NO_COLON)
    const till  = start.add(1, 'day').format(ISO_NO_COLON)

    const url = `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`

    /* Handy for debugging in CI */
    console.log('▶️  URL', url)
    return url
  },
  
  /* Parse the JSON payload into EPG items */
  parser ({ content }) {
    // ── 1) Normalise ────────────────────────────────────────────────
    let data
    if (typeof content === 'string') {
      // we got a JSON string → parse it
      try {
        data = JSON.parse(content)
      } catch (e) {
        console.error('❌ JSON parse failed:', e.message)
        return []                 // bail out on bad JSON
      }
    } else if (content && typeof content === 'object') {
      // epg-grabber (or the proxy layer) already parsed it for us
      data = content
    } else {
      return []                   // anything else is unusable
    }

    // ── 2) Convert records into EPG items ───────────────────────────
    return data.flatMap(item => {
      const start = parseDate(item.since)
      const stop  = parseDate(item.till)
      if (!start.isValid() || !stop.isValid()) return []

      return {
        title:       item.title,
        description: item.description || item.lead || '',
        image:       getImageUrl(item),
        icon:        getImageUrl(item),
        start,
        stop
      }
    })
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────

function parseDate (str) {
  return str ? dayjs.tz(str, TZ) : dayjs.invalid()
}

function getImageUrl (item) {
  const url = item?.images?.['16x9']?.[0]?.url
  return url ? `https:${url}` : null
}
