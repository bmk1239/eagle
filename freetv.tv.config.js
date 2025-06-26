const dayjs = require('dayjs')
const utc = require('dayjs/plugin/utc')
const timezone = require('dayjs/plugin/timezone')
const customParseFormat = require('dayjs/plugin/customParseFormat')
dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(customParseFormat)

const TZ = 'Asia/Jerusalem'                  // your real zone
const ISO_NO_COLON = 'YYYY-MM-DDTHH:mmZZ'    // => 04:00+0300

module.exports = {
  site: 'freetv.tv',
  days: 2,

  url ({ channel, date }) {
    /* CHANGE #1  ─ use keepLocalTime=true so “2025-06-26” stays that day */
    const start = dayjs.tz(date).tz(TZ, true)   // true = don’t shift, just tag
                    .startOf('day')
                    .add(4, 'hour')          // API’s 04:00 window

    const since = start.format(ISO_NO_COLON)
    const till  = start.add(1, 'day').format(ISO_NO_COLON)

    const url = `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`

    /* log in CI so you can copy-paste and test */
    console.log('▶️  URL', url)
    return url
  },

  parser ({ content }) {
    let items
    try { items = JSON.parse(content) } catch { return [] }

    return items.flatMap(item => {
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

/* CHANGE #2 – parse without double-shift */
function parseDate (str) {
  return str ? dayjs.tz(str, TZ) : dayjs.invalid()
}

function getImageUrl (item) {
  const url = item?.images?.['16x9']?.[0]?.url
  return url ? `https:${url}` : null
}
