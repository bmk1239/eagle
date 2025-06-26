const dayjs = require('dayjs')
const utc = require('dayjs/plugin/utc')
const timezone = require('dayjs/plugin/timezone')
dayjs.extend(utc)
dayjs.extend(timezone)

const TZ = 'Asia/Jerusalem'
const ISO = 'YYYY-MM-DDTHH:mmZZ'

module.exports = {
  site: 'freetv.tv',
  days: 2,

  delay: 1200,
  concurrency: 1,

  url({ channel, date }) {
    const start = dayjs(date).tz(TZ).startOf('day').add(4, 'hour')
    const since = start.format(ISO)
    const till = start.add(1, 'day').format(ISO)

    return `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`
  },

  parser({ content }) {
    let items

    try {
      // force string first (CI-safe), then parse
      const str = Buffer.isBuffer(content)
        ? content.toString()
        : typeof content === 'string'
        ? content
        : JSON.stringify(content)

      items = JSON.parse(str)
    } catch (err) {
      console.error('❌ Failed to parse JSON:', err.message)
      return []
    }

    return items.flatMap(item => {
      const start = parseDate(item.since)
      const stop = parseDate(item.till)
      if (!start?.isValid() || !stop?.isValid()) return []

      return {
        title: item.title,
        description: item.description || item.lead || '',
        image: getImageUrl(item),
        icon: getImageUrl(item),
        start,
        stop
      }
    })
  }
}

function parseDate(str) {
  return str ? dayjs.utc(str).tz(TZ) : null
}

function getImageUrl(item) {
  const url = item?.images?.['16x9']?.[0]?.url
  return url ? `https:${url}` : null
}
