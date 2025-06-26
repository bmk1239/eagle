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

  delay: 1200,
  concurrency: 1,

  url ({ channel, date }) {
    const start = dayjs(date).tz(TZ).startOf('day').add(4, 'hour')
    const since = start.format(ISO)
    const till  = start.add(1, 'day').format(ISO)

    return `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`
  },

  /* robust parser: handles Buffer, string, or already-parsed object */
  parser ({ content }) {
    let items
    try {
      const raw = Buffer.isBuffer(content)
        ? content.toString()
        : typeof content === 'string'
        ? content
        : JSON.stringify(content)       // object → string
      items = JSON.parse(raw)
    } catch { return [] }

    return items.flatMap(item => {
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
function img (o)   { const u=o?.images?.['16x9']?.[0]?.url; return u?`https:${u}`:null }
