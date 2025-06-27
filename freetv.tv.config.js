// epg/sites/freetv.tv/freetv.tv.config.js
// ---------------------------------------------------------------------------
// FreeTV – programme guide grabber
// Works from GitHub Actions behind an IL proxy (Fortinet MITM cert) and
// avoids Cloudflare’s 403 by:
//   • sending *exactly* the same header set the browser uses
//   • shipping the AWSALB / AWSALBCORS cookie you pasted
//   • falling back to env-vars so you can rotate the cookie without a commit
//
// If you still see 403, run the built-in “DEBUG=epg:* npm run grab:ftv” task
// once – it prints the full response and first 400 bytes of the body.
// ---------------------------------------------------------------------------

const dayjs  = require('dayjs');
const utc    = require('dayjs/plugin/utc');
const tz     = require('dayjs/plugin/timezone');
dayjs.extend(utc);
dayjs.extend(tz);

const TZ   = 'Asia/Jerusalem';
const ISO  = 'YYYY-MM-DDTHH:mmZZ';

// ────────────────────────────────────────────────────────────────────────────
// 1.  Session cookie – keep it *fresh*!  FreeTV rotates the pair ~weekly.
//    • Set FREETV_COOKIE in GitHub Secrets to override the hard-coded value.
//    • The string must include BOTH cookies exactly as copied in DevTools.
// ────────────────────────────────────────────────────────────────────────────
const SESSION_COOKIE = process.env.FREETV_COOKIE || (
  'AWSALB=MP190m8HtEDvXuwbvRwZNC8f7O8vg94OyVHKK6A1UopgfiBXQeg585/' +
  'YG359GoiAcND/YAf5LP/nvTf+sa+O1jEXNgfCTiKuBQI6WC17rN7auKAzkz4Du4B2EDD+; ' +
  'AWSALBCORS=MP190m8HtEDvXuwbvRwZNC8f7O8vg94OyVHKK6A1UopgfiBXQeg585/' +
  'YG359GoiAcND/YAf5LP/nvTf+sa+O1jEXNgfCTiKuBQI6WC17rN7auKAzkz4Du4B2EDD+'
);

module.exports = {
  site : 'freetv.tv',
  days : 2,

  // Cloudflare rate-limit  ⚠️  1 request / 1.5 s is the sweet spot
  delay      : 1500,
  concurrency: 1,

  // GitHub runner calls us via “grab.ts … --proxy $IL_PROXY”
  request: {
    headers : buildHeaders(),
    timeout : 20_000      // 20 s
  },

  /* ─────────── Build the API URL ─────────── */
  url({ channel, date }) {
    const start = dayjs(date).tz(TZ).startOf('day').add(4, 'hour'); // 04:00 local
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

  /* ─────────── Parse the JSON response ─────────── */
  parser({ content }) {
    const raw = Buffer.isBuffer(content)
      ? content.toString()
      : typeof content === 'string'
      ? content
      : JSON.stringify(content);

    if (raw.trim().startsWith('<')) {
      console.warn('[freetv.tv] ⚠  HTML instead of JSON – body starts:',
        raw.slice(0, 400));
      return [];
    }

    let data;
    try { data = JSON.parse(raw); }
    catch (e) {
      console.error('[freetv.tv] JSON parse failed:', e);
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

/* ─────────── Helpers ─────────── */
function buildHeaders() {
  return {
    // full Chrome UA – Cloudflare “browser integrity check” likes it
    'User-Agent':
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',

    // use *exactly* what DevTools shows (yes, HTML types first!)
    'Accept':
      'text/html,application/xhtml+xml,application/xml;q=0.9,' +
      'image/avif,image/webp,image/apng,*/*;q=0.8,' +
      'application/signed-exchange;v=b3;q=0.7',

    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control'  : 'no-cache',
    'Pragma'         : 'no-cache',

    // Chrome’s client-hints (optional but quietens some WAF rules)
    'Sec-CH-UA':
      '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    'Sec-CH-UA-Mobile': '?0',
    'Sec-CH-UA-Platform': '"Windows"',

    // CORS
    'Origin' : 'https://web.freetv.tv',
    'Referer': 'https://web.freetv.tv/',

    // **Auth / Stickiness**
    Cookie: SESSION_COOKIE
  };
}

function parse(s) { return s ? dayjs.utc(s).tz(TZ) : null; }
function img(o)   { return o?.images?.['16x9']?.[0]?.url
                        ? `https:${o.images['16x9'][0].url}` : null; }
