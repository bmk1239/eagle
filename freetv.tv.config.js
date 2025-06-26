console.log(' freetv.tv.js LOADED - checksum 20250626');

const dayjs            = require('dayjs')
const utc               = require('dayjs/plugin/utc')
const timezone          = require('dayjs/plugin/timezone')
const customParseFormat = require('dayjs/plugin/customParseFormat')
dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(customParseFormat)

const TZ           = 'Asia/Jerusalem'
const ISO_NO_COLON = 'YYYY-MM-DDTHH:mmZZ'   // 04:00+0300

module.exports = {
  site: 'freetv.tv',
  days: 2,

  // keep the throttling: FreeTV blocks bursts
  delay:       1200,
  concurrency: 1,

  // browser-style headers so Cloudflare lets us in
  request: {
    headers () {
      return {
        'User-Agent':       'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept':           'application/json, text/plain, */*',
        'Accept-Language':  'he-IL,he;q=0.9,en;q=0.8',
        'Origin':           'https://web.freetv.tv',
        'Referer':          'https://web.freetv.tv/'
      }
    }
  },

  url ({ channel, date }) {
    const start = dayjs(date)
      .tz(TZ, true)      // keepLocalTime=true
      .startOf('day')
      .add(4, 'hour')

    const since = start.format(ISO_NO_COLON)
    const till  = start.add(1, 'day').format(ISO_NO_COLON)

    return `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`
  },

  /* robust parser: handles string, Buffer, or already-parsed object */
  parser ({ content }) {
    let data

    if (Buffer.isBuffer(content)) {
      try { data = JSON.parse(content.toString('utf8')) } catch { return [] }
    } else if (typeof content === 'string') {
      try { data = JSON.parse(content) } catch { return [] }
    } else if (content && typeof content === 'object') {
      data = content
    } else {
      return []
    }

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

/* helpers */
function parseDate (str) {
  return str ? dayjs.tz(str, TZ) : dayjs.invalid()
}

function getImageUrl (item) {
  const url = item?.images?.['16x9']?.[0]?.url
  return url ? `https:${url}` : null
}
