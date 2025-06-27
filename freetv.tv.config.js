// epg/sites/freetv.tv/freetv.tv.config.js
// ---------------------------------------------------------------------------
// Grab FreeTV programme listings and convert them into a Day.js-friendly
// structure for your EPG pipeline.
// ---------------------------------------------------------------------------

const dayjs = require('dayjs');
const utc   = require('dayjs/plugin/utc');
const tz    = require('dayjs/plugin/timezone');
dayjs.extend(utc);
dayjs.extend(tz);

const TZ  = 'Asia/Jerusalem';
const ISO = 'YYYY-MM-DDTHH:mmZZ';

/* -------------------------------------------------------------------------
 * Hard-coded session cookie captured from DevTools (“Copy as fetch”)
 * NOTE: renew this string whenever FreeTV rotates the AWSALB token
 * ---------------------------------------------------------------------- */
const SESSION_COOKIE =
  'AWSALB=MP190m8HtEDvXuwbvRwZNC8f7O8vg94OyVHKK6A1UopgfiBXQeg585/YG359GoiAcND/YAf5LP/nvTf+sa+O1jEXNgfCTiKuBQI6WC17rN7auKAzkz4Du4B2EDD+; ' +
  'AWSALBCORS=MP190m8HtEDvXuwbvRwZNC8f7O8vg94OyVHKK6A1UopgfiBXQeg585/YG359GoiAcND/YAf5LP/nvTf+sa+O1jEXNgfCTiKuBQI6WC17rN7auKAzkz4Du4B2EDD+';

module.exports = {
  site : 'freetv.tv',
  days : 2,

  delay      : 1200,   // 1 request every 1.2 s (stay under Cloudflare radar)
  concurrency: 1,      // serial requests only

  /* ------------ HTTP settings ------------------------------------------ */
  request: {
    headers : buildHeaders(),
    timeout : 20000     // 20 s per request
  },

  /* ------------ Build the API URL ------------------------------------- */
  url({ channel, date }) {
    const start = dayjs(date).tz(TZ).startOf('day').add(4, 'hour'); // 04:00 local
    const since = start.format(ISO);
    const till  = start.add(1, 'day').format(ISO);

    const url =
      `https://web.freetv.tv/api/products/lives/programmes` +
      `?liveId[]=${channel.site_id}` +
      `&since=${encodeURIComponent(since)}` +
      `&till=${encodeURIComponent(till)}` +
      `&lang=HEB&platform=BROWSER`;

    console.debug('[freetv.tv] →', url);
    return url;
  },

  /* ------------ Parse the JSON response ------------------------------- */
  parser({ content }) {
    let raw;
    try {
      raw = Buffer.isBuffer(content)
        ? content.toString()
        : typeof content === 'string'
        ? content
        : JSON.stringify(content);

      if (raw.trim().startsWith('<')) {
        console.warn('[freetv.tv] ⚠ Got HTML instead of JSON:', raw.slice(0, 400));
        return [];
      }

      const data = JSON.parse(raw);
      return data.flatMap(item => {
        const start = parse(item.since);
        const stop  = parse(item.till);
        if (!start?.isValid() || !stop?.isValid()) return [];
        return {
          title      : item.title,
          description: item.description || item.lead || '',
          image      : img(item),
          icon       : img(item),
          start,
          stop
        };
      });
    } catch (err) {
      console.error('[freetv.tv] JSON parse failed:', err);
      return [];
    }
  }
};

/* ---------------- Helper functions ------------------------------------- */
function buildHeaders() {
  return {
    'User-Agent':
      'Mozilla/5.0 (compatible; EPGGrabber/1.0; +https://github.com/yourrepo)',
    // This single line forces the API to return JSON instead of an HTML shell
    'Accept' : 'application/json',
    'Origin' : 'https://web.freetv.tv',
    'Referer': 'https://web.freetv.tv/',
    'Cookie' : SESSION_COOKIE
  };
}

function parse(s) { return s ? dayjs.utc(s).tz(TZ) : null; }
function img(o)   {
  const u = o?.images?.['16x9']?.[0]?.url;
  return u ? `https:${u}` : null;
}
// ---------------------------------------------------------------------------
