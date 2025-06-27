// epg/sites/freetv.tv/freetv.tv.config.js
// ---------------------------------------------------------------------------
// FreeTV EPG grabber – June 2025 version
//   * works behind a Fortinet MITM proxy (GitHub Actions “IL_PROXY”)
//   * passes Cloudflare WAF rules 1-4 (see README)
//   * cookie can be rotated via FREETV_COOKIE secret
// ---------------------------------------------------------------------------

const dayjs  = require('dayjs');
const utc    = require('dayjs/plugin/utc');
const tz     = require('dayjs/plugin/timezone');
dayjs.extend(utc);
dayjs.extend(tz);

const TZ  = 'Asia/Jerusalem';
const ISO = 'YYYY-MM-DDTHH:mmZZ';

/*───────────────────────────────────────────────────────────────────────────*/
/*  Cookie – override in GitHub Secrets to avoid committing new values      */
/*───────────────────────────────────────────────────────────────────────────*/
const SESSION_COOKIE = process.env.FREETV_COOKIE || (
  'AWSALB=MP190m8HtEDvXuwbvRwZNC8f7O8vg94OyVHKK6A1UopgfiBXQeg585/' +
  'YG359GoiAcND/YAf5LP/nvTf+sa+O1jEXNgfCTiKuBQI6WC17rN7auKAzkz4Du4B2EDD+; ' +
  'AWSALBCORS=MP190m8HtEDvXuwbvRwZNC8f7O8vg94OyVHKK6A1UopgfiBXQeg585/' +
  'YG359GoiAcND/YAf5LP/nvTf+sa+O1jEXNgfCTiKuBQI6WC17rN7auKAzkz4Du4B2EDD+'
);

module.exports = {
  site : 'freetv.tv',
  days : 2,

  delay      : 1500,   // 1 req / 1.5 s keeps us under CF’s rate-limit
  concurrency: 1,

  request: {
    headers : buildHeaders(),
    timeout : 20_000
  },

  url ({ channel, date }) {
    const start = dayjs(date).tz(TZ).startOf('day').add(4, 'hour'); // 04:00
    const since = start.format(ISO);
    const till  = start.add(1, 'day').format(ISO);
    return (
      'https://web.freetv.tv/api/products/lives/programmes' +
      `?liveId[]=${channel.site_id}` +
      `&since=${encodeURIComponent(since)}` +
      `&till=${encodeURIComponent(till)}` +
      '&lang=HEB&platform=BROWSER'
    );
  },

  parser ({ content }) {
    const raw = Buffer.isBuffer(content)
      ? content.toString()
      : typeof content === 'string'
      ? content
      : JSON.stringify(content);

    if (raw.trim().startsWith('<')) {
      console.warn('[freetv.tv] ⚠ HTML instead of JSON:', raw.slice(0, 200));
      return [];
    }

    let data;
    try { data = JSON.parse(raw); } catch (e) {
      console.error('[freetv.tv] JSON parse error:', e);
      return [];
    }

    return data.flatMap(item => {
      const start = parse(item.since);
      const stop  = parse(item.till);
      if (!start?.isValid() || !stop?.isValid()) return [];

      const pic = img(item);
      return {
        title      : item.title,
        description: item.description || item.lead || '',
        image      : pic,
        icon       : pic,
        start, stop
      };
    });
  }
};

/*───────────────────────── Helpers ─────────────────────────*/
function buildHeaders () {
  return {
    // Browser UA so CF “Browser Integrity Check” passes
    'User-Agent':
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',

    // RULE #3 – *must* ask for JSON
    'Accept': 'application/json, text/plain, */*',

    // RULE #1 – these three + X-Requested-With mimic fetch() exactly
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'X-Requested-With': 'XMLHttpRequest',

    // CORS
    'Origin' : 'https://web.freetv.tv',
    'Referer': 'https://web.freetv.tv/',

    // Sticky-session & auth
    'Cookie': SESSION_COOKIE
  };
}

const parse = s => (s ? dayjs.utc(s).tz(TZ) : null);
const img   = o => o?.images?.['16x9']?.[0]?.url
                 ? `https:${o.images['16x9'][0].url}` : null;
