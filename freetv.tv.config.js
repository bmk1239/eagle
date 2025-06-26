/*  FreeTV grabber — minimal, stable  */
const dayjs             = require('dayjs')
const utc                = require('dayjs/plugin/utc')
const timezone           = require('dayjs/plugin/timezone')
const customParseFormat  = require('dayjs/plugin/customParseFormat')
dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(customParseFormat)

const TZ = 'Asia/Jerusalem'
const ISO_NO_COLON = 'YYYY-MM-DDTHH:mmZZ'

module.exports = {
  site: 'freetv.tv',
  days: 2,

  /* gentle throttle so FreeTV doesn’t ban the proxy IP */
  delay:       1200,   // ms between requests
  concurrency: 1,      // one socket at a time

  /* headers that make the request look like a browser tab */
  request: {
    headers () {
      return {
        'User-Agent':
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        Origin:  'https://web.freetv.tv',
        Referer: 'https://web.freetv.tv/'
      }
    }
  },

  /* same URL logic you had before */
  url ({ channel, date }) {
    const local = dayjs(date).tz(TZ)
    const since = local.startOf('day').format(ISO_NO_COLON)
    const till  = local.add(1, 'day').startOf('day').format(ISO_NO_COLON)

    return `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`
  },

  /* robust parser: accepts Buffer, string, or object */
  parser ({ content }) {
    let items

    if (Buffer.isBuffer(content)) {
      try { items = JSON.parse(content.toString('utf8')) } catch { return [] }
    } else if (typeof content === 'string') {
      try { items = JSON.parse(content) } catch { return [] }
    } else if (content && typeof content === 'object') {
      items = content
    } else {
      return []
    }

    return items.flatMap(item => {
      const start = parseDate(item.since)
      const stop  = parseDate(item.till)
      if (!start?.isValid() || !stop?.isValid()) return []

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
  return str ? dayjs.utc(str).tz(TZ) : null
}

function getImageUrl (item) {
  const url = item?.images?.['16x9']?.[0]?.url
  return url ? `https:${url}` : null
}
