const cloudscraper = require('cloudscraper');

(async () => {
  const url =
    'https://web.freetv.tv/api/products/lives/programmes' +
    '?liveId[]=3359448' +
    `&since=${encodeURIComponent(process.argv[2])}` +
    `&till=${encodeURIComponent(process.argv[3])}` +
    '&lang=HEB&platform=BROWSER';

  const body = await cloudscraper.get({
    url,
    headers: {
      'Origin' : 'https://web.freetv.tv',
      'Referer': 'https://web.freetv.tv/'
    },
    proxy: process.env.IL_PROXY
  });
  console.log(body);       // JSON text
})();
