const dayjs = require('dayjs')
const utc = require('dayjs/plugin/utc')
const tz  = require('dayjs/plugin/timezone')
dayjs.extend(utc)
dayjs.extend(tz)

const TZ = 'Asia/Jerusalem'
const ISO = 'YYYY-MM-DDTHH:mmZZ'

module.exports = {
  site: 'freetv.tv',
  days: 2,

  delay: 1200,
  concurrency: 1,

  /* ← plain object, not a function */
  request: {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
      Origin:  'https://web.freetv.tv',
      Referer: 'https://web.freetv.tv/'
    },
    /* this is the key that stops auto-JSON */
    responseType: 'arraybuffer'   // always returns Buffer
  },

  url ({ channel, date }) {
    const d   = dayjs(date).tz(TZ)
    const since = d.startOf('day').format(ISO)
    const till  = d.add(1, 'day').startOf('day').format(ISO)
    return `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`
  },

  parser ({ content }) {
    /* content is now ALWAYS Buffer or string */
    let arr
    try {
      arr = JSON.parse(Buffer.isBuffer(content) ? content.toString() : content)
    } catch { return [] }

    return arr.flatMap(item => {
      const start = parseDate(item.since)
      const stop  = parseDate(item.till)
      if (!start?.isValid() || !stop?.isValid()) return []
      return {
        title: item.title,
        description: item.description || item.lead || '',
        image: getImg(item),
        icon:  getImg(item),
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
