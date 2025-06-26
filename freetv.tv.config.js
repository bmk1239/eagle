const dayjs = require('dayjs')
const utc = require('dayjs/plugin/utc')
const timezone = require('dayjs/plugin/timezone')
const customParseFormat = require('dayjs/plugin/customParseFormat')

dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(customParseFormat)

const TZ = 'Asia/Jerusalem'          // one place to change if needed
const ISO_NO_COLON = 'YYYY-MM-DDTHH:mmZZ'  // 04:00+0300 ➜ “2025-06-26T04:00+0300”

module.exports = {
  site: 'freetv.tv',
  days: 2,

  /** Build the request URL exactly the way the FreeTV API wants it */
  url ({ channel, date }) {
    // API window: 04:00 local time → 04:00 next day
    const start = dayjs(date).tz(TZ).startOf('day').add(4, 'hour')
    const since = start.format(ISO_NO_COLON)
    const till  = start.add(1, 'day').format(ISO_NO_COLON)

    return `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`
  },

  /** Convert API JSON into an array of EPG programme objects */
  parser ({ content }) {
    let items
    try {
      items = JSON.parse(content)
    } catch {
      return []
    }

    return items
      .map(item => {
        const start = parseDate(item.since)
        const stop  = parseDate(item.till)
        if (!start.isValid() || !stop.isValid()) return null

        return {
          title:       item.title,
          description: item.description || item.lead || '',
          image:       getImageUrl(item),
          icon:        getImageUrl(item),
          start,
          stop
        }
      })
      .filter(Boolean)               // drop nulls
  }
}

/* ---------- helpers ----------------------------------------------------- */

function parseDate (str) {
  return str ? dayjs(str).tz(TZ) : dayjs.invalid()
}

function getImageUrl (item) {
  const url = item?.images?.['16x9']?.[0]?.url
  return url ? `https:${url}` : null
}
