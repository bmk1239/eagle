// epg/sites/freetv.tv/freetv.tv.config.js  ----------------------------------
const dayjs = require('dayjs');
const utc   = require('dayjs/plugin/utc');
const tz    = require('dayjs/plugin/timezone');
dayjs.extend(utc);
dayjs.extend(tz);

const TZ  = 'Asia/Jerusalem';
const ISO = 'YYYY-MM-DDTHH:mmZZ';

module.exports = {
  site : 'freetv.tv',
  days : 2,

  delay      : 1200,   // 1 request every 1.2 s
  concurrency: 1,      // serial requests only

  /* ------------ Cloudflare + auth headers -------------------------------- */
  request: {
    headers: buildHeaders(),
    timeout: 20000      // 20 s per request
  },

  /* ------------ Build the API URL --------------------------------------- */
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

  /* ------------ Parse the JSON response --------------------------------- */
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

/* ---------------- Helper functions --------------------------------------- */
function buildHeaders() {
  const base = {
    'User-Agent':
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    Origin : 'https://web.freetv.tv',
    Referer: 'https://web.freetv.tv/'
  };

  /* ---- OPTION A: reuse browser session cookie -------------------------- */
  if (process.env.FREETV_COOKIE) {
    base.Cookie = process.env.FREETV_COOKIE;
  }

  /* ---- OPTION B: HTTP basic-auth (if the API supports it) -------------- */
  if (process.env.FREETV_USERNAME && process.env.FREETV_PASSWORD) {
    const token = Buffer.from(
      `${process.env.FREETV_USERNAME}:${process.env.FREETV_PASSWORD}`
    ).toString('base64');
    base.Authorization = `Basic ${token}`;
  }

  return base;
}

function parse(s)   { return s ? dayjs.utc(s).tz(TZ) : null; }
function img(o)     {
  const u = o?.images?.['16x9']?.[0]?.url;
  return u ? `https:${u}` : null;
}
// ---------------------------------------------------------------------------
