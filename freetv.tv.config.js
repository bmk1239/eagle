import { addExtra }       from 'puppeteer-extra';
import puppeteerCore      from 'puppeteer-core';
import StealthPlugin      from 'puppeteer-extra-plugin-stealth';
import fs                 from 'node:fs/promises';

const puppeteer = addExtra(puppeteerCore);
puppeteer.use(StealthPlugin());

const sleep = ms => new Promise(r => setTimeout(r, ms));

export async function harvest({
  chromePath,
  proxy,                // e.g. http://user:pass@il-proxy:3128
  envFile = '.env.ftv'  // file to dump cookie to
}) {
  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--ignore-certificate-errors',
      `--proxy-server=${proxy}`
    ]
  });

  const page = await browser.newPage();
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
    'AppleWebKit/537.36 (KHTML, like Gecko) '   +
    'Chrome/137.0.0.0 Safari/537.36'
  );

  await page.goto('https://web.freetv.tv/', { waitUntil: 'domcontentloaded' });

  // Poll cookies for up to 40 s
  const client = await page.target().createCDPSession();
  let jar = '';
  for (let i = 0; i < 20; i++) {
    const { cookies } = await client.send('Network.getAllCookies');
    jar = cookies
      .filter(c => c.domain.endsWith('freetv.tv'))
      .map(c => `${c.name}=${c.value}`)
      .join('; ');
    if (jar.includes('cf_clearance')) break;
    await sleep(2000);
  }

  if (!jar.includes('cf_clearance'))
    throw new Error('Cloudflare challenge not solved (no cf_clearance)');

  console.log('✅ harvested cookie (masked)');
  await fs.writeFile(envFile, `FREETV_COOKIE=${jar}\n`);
  await browser.close();
}

// If you run the file directly: `node tools/harvest-ftv-cookie.mjs`
if (import.meta.url === `file://${process.argv[1]}`) {
  const chrome = process.env.CHROME_BIN || process.argv[2];
  const proxy  = process.env.IL_PROXY    || process.argv[3];
  if (!chrome || !proxy) {
    console.error('Usage: node harvest-ftv-cookie.mjs <chromePath> <proxy>');
    process.exit(1);
  }
  harvest({ chromePath: chrome, proxy })
    .catch(e => { console.error(e); process.exit(1); });
}
