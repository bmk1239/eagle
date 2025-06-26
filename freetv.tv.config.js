const dayjs = require('dayjs')
const utc   = require('dayjs/plugin/utc')
const tz    = require('dayjs/plugin/timezone')
dayjs.extend(utc)
dayjs.extend(tz)

const TZ  = 'Asia/Jerusalem'
const ISO = 'YYYY-MM-DDTHH:mmZZ'

module.exports = {
  site: 'freetv.tv',
  days: 2,

  /* 1 request at a time, 1.2 s apart */
  concurrency: 1,
  delay: 1200,

  /* ⇣ THESE HEADERS ARE THE KEY ⇣ */
  request: {
    method: 'GET',
    headers: {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      'Accept': 'application/json, text/plain, */*',
      'Accept-Language': 'he-IL,he;q=0.9,en;q=0.8',
      'Accept-Encoding': 'gzip, deflate, br',
      'Origin':  'https://web.freetv.tv',
      'Referer': 'https://web.freetv.tv/'
    },
    timeout: 20000          // 20 s per request
  },

  /* build the 04:00→04:00 window URL */
  url ({ channel, date }) {
    const start = dayjs(date).tz(TZ).startOf('day').add(4, 'hour')
    const since = start.format(ISO)
    const till  = start.add(1, 'day').format(ISO)

    return `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`
  },

  /* parse JSON whether it arrives as Buffer, string, or object */
  parser ({ content }) {
    let arr
    try {
      const raw = Buffer.isBuffer(content)
        ? content.toString()
        : typeof content === 'string'
        ? content
        : JSON.stringify(content)
      arr = JSON.parse(raw)
    } catch { return [] }

    return arr.flatMap(item => {
      const start = parse(item.since)
      const stop  = parse(item.till)
      if (!start?.isValid() || !stop?.isValid()) return []

      return {
        title: item.title,
        description: item.description || item.lead || '',
        image: img(item),
        icon:  img(item),
        start,
        stop
      }
    })
  }
}

function parse (s) { return s ? dayjs.utc(s).tz(TZ) : null }
function img (o)   { const u=o?.images?.['16x9']?.[0]?.url; return u ? `https:${u}` : null }
