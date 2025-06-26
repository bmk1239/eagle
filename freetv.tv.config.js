const dayjs = require('dayjs')
const utc = require('dayjs/plugin/utc')
const timezone = require('dayjs/plugin/timezone')
const customParseFormat = require('dayjs/plugin/customParseFormat')
dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(customParseFormat)

const TZ = 'Asia/Jerusalem'                  // your real zone
const ISO_NO_COLON = 'YYYY-MM-DDTHH:mmZZ'    // => 04:00+0300

// ▶️  all the new bits are marked with  ▲ …

module.exports = {
  site: 'freetv.tv',
  days: 2,

  /* ▲ 1)  Tell epg-grabber to send browser-like headers on *every* request   */
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

  /* ▲ 2)  Add a small pause so the runner never bursts faster than 4 r/s   */
  delay: 400,        // milliseconds between requests (tweak if you wish)

  url ({ channel, date }) {
    /* keepLocalTime=true → instance .tz() instead of dayjs.tz(..., true)  */
    const start = dayjs(date).tz(TZ, true).startOf('day').add(4, 'hour')

    const since = start.format(ISO_NO_COLON)
    const till  = start.add(1, 'day').format(ISO_NO_COLON)

    const url = `https://web.freetv.tv/api/products/lives/programmes?liveId[]=${
      channel.site_id
    }&since=${encodeURIComponent(since)}&till=${encodeURIComponent(till)}&lang=HEB&platform=BROWSER`

    console.log('▶️  URL', url)   // still handy for debugging
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

function parseDate (str) {
  return str ? dayjs.tz(str, TZ) : dayjs.invalid()
}

function getImageUrl (item) {
  const url = item?.images?.['16x9']?.[0]?.url
  return url ? `https:${url}` : null
}
