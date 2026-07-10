const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const TARGET_URL = 'https://www.myvi.in/new-connection/choose-your-fancy-mobile-numbers-online';
let PINCODE = process.env.PINCODE || '560100';
let MOBILE = process.env.MOBILE || '9071977078';
let FULLNAME = process.env.FULLNAME || 'Hankith';

try {
  const configPath = path.join(__dirname, 'bot-config.json');
  if (fs.existsSync(configPath)) {
    const cfg = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (cfg.pincode) PINCODE = String(cfg.pincode);
    if (cfg.mobile) MOBILE = String(cfg.mobile);
    if (cfg.fullname) FULLNAME = String(cfg.fullname);
  }
} catch (_) {}

const argWorkerId = process.argv.find(arg => arg.startsWith('--worker-id='));
const argWorkerCount = process.argv.find(arg => arg.startsWith('--worker-count='));
const argMaxCycles = process.argv.find(arg => arg.startsWith('--max-cycles='));

const WORKER_ID = argWorkerId ? Number(argWorkerId.split('=')[1]) : 1;
const WORKER_COUNT = argWorkerCount ? Number(argWorkerCount.split('=')[1]) : 1;
const MAX_CYCLES = argMaxCycles ? Number(argMaxCycles.split('=')[1]) : Infinity;
let HEADLESS = process.argv.includes('--headless');
if (process.platform === 'linux' && !process.env.DISPLAY) HEADLESS = true;

// Pattern cooldown: don't repeat same pattern within 2 hours (reduced from 5)
const patternCooldown = new Map();
function isPatternAvailable(pat) {
  const last = patternCooldown.get(pat);
  return !last || (Date.now() - last > 2 * 60 * 60 * 1000);
}
function markPatternUsed(pat) {
  patternCooldown.set(pat, Date.now());
  const cutoff = Date.now() - 3 * 60 * 60 * 1000;
  for (const [p, t] of patternCooldown) if (t < cutoff) patternCooldown.delete(p);
}

function workerLog(message) {
  console.log(`[Worker ${WORKER_ID}/${WORKER_COUNT}] ${message}`);
}

const PATTERN_DIGITS = ['1','3','5','7','9'];
const GOOD_PAIRS = [
  '11', '13', '31', '15', '51', '17', '71', '19', '91',
  '33', '35', '53', '37', '73', '39', '93',
  '55', '57', '75', '59', '95', '79', '97', '99'
];
const VALID_TOTALS = [1,3,5,6];
const PRIORITIES = ['13','15','171','373','969','96','75','95','91','31','313','319','159'];

const USER_AGENTS = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
];

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function rand(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }

// Pre-generate 10 randomized 5-digit combinations
const SEARCH_COMBINATIONS = [];
function initSearchCombinations() {
  while (SEARCH_COMBINATIONS.length < 10) {
    let s = '';
    while (s.length < 5) {
      const digit = PATTERN_DIGITS[rand(0, PATTERN_DIGITS.length - 1)];
      const temp = s + digit;
      if (temp.length > 1) {
        const pair = temp.slice(-2);
        if (pair === '77' || !GOOD_PAIRS.includes(pair)) continue;
      }
      if (temp.length > 2 && temp.slice(-3) === digit + digit + digit) continue;
      s = temp;
    }
    if (!SEARCH_COMBINATIONS.includes(s)) SEARCH_COMBINATIONS.push(s);
  }
  workerLog(`Pre-generated ${SEARCH_COMBINATIONS.length} search combinations: ${SEARCH_COMBINATIONS.join(', ')}`);
}
initSearchCombinations();

function genPattern(totalSearches) {
  return SEARCH_COMBINATIONS[totalSearches % SEARCH_COMBINATIONS.length];
}

function getSingleTotal(num) {
  let sum = num;
  while (sum > 9) sum = String(sum).split('').reduce((a, b) => a + Number(b), 0);
  return sum;
}

function normalize(num) { return String(num).replace(/\D/g, ''); }
function sumDigits(num) { return String(num).split('').reduce((a, ch) => a + Number(ch), 0); }

function validateNumber(num) {
  const s = String(num).replace(/\D/g, '');
  if (s.length < 6) return { valid: false, reason: 'Too short' };
  if (/[248]/.test(s)) return { valid: false, reason: 'Contains 2/4/8' };
  if (s.indexOf('00') !== -1) return { valid: false, reason: 'Double zero' };
  const tripMatch = s.match(/(\d)\1\1/);
  if (tripMatch) return { valid: false, reason: 'Triple digit' };
  for (let i = 3; i < s.length - 1; i++) {
    const pair = s.substring(i, i + 2);
    if (pair.indexOf('0') !== -1) continue;
    if (!GOOD_PAIRS.includes(pair)) {
      if (pair === '96' && i === s.length - 2) continue;
      if (pair === '96' && s.substring(i, i + 3) === '969') continue;
      if (pair === '69' && i > 0 && s.substring(i - 1, i + 2) === '969') continue;
      return { valid: false, reason: 'Invalid pair: ' + pair };
    }
  }
  const compound = sumDigits(s);
  if (compound === 51) return { valid: false, reason: 'Compound 51' };
  const singleTotal = getSingleTotal(compound);
  if (!VALID_TOTALS.includes(singleTotal)) return { valid: false, reason: 'Total ' + singleTotal };
  return { valid: true, correctedTotal: singleTotal, correctedCompound: compound };
}

let activeBrowser = null;

async function runBot() {
  workerLog('=== Starting browser session ===');
  const browser = await chromium.launch({
    headless: HEADLESS,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--disable-extensions',
      '--disable-background-networking',
      '--disable-default-apps',
      '--disable-sync',
      '--disable-translate',
      '--metrics-recording-only',
      '--mute-audio',
      '--no-first-run'
    ]
  });
  activeBrowser = browser;
  const runStart = Date.now();
  // Active for 60 minutes (increased from 40)
  const sessionActiveMinutes = 60 + rand(-10, 10);

  try {
    const selectedUA = USER_AGENTS[rand(0, USER_AGENTS.length - 1)];
    const context = await browser.newContext({
      viewport: { width: rand(1280, 1440), height: rand(800, 900) },
      userAgent: selectedUA,
      extraHTTPHeaders: { 'Accept-Language': 'en-IN,en;q=0.9' }
    });
    const page = await context.newPage();

    // Block unnecessary resources for speed
    await page.route('**/*.{png,jpg,jpeg,gif,svg,webp,ico,woff,woff2,ttf}', route => route.abort());
    await page.route('**/analytics**', route => route.abort());
    await page.route('**/tracking**', route => route.abort());
    await page.route('**/ads**', route => route.abort());
    await page.route('**/doubleclick**', route => route.abort());
    await page.route('**/googletagmanager**', route => route.abort());
    await page.route('**/google-analytics**', route => route.abort());
    await page.route('**/clarity**', route => route.abort());
    await page.route('**/facebook**', route => route.abort());
    await page.route('**/tiktok**', route => route.abort());

    workerLog('Opening target site...');
    try {
      await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    } catch (e) {
      workerLog(`Navigation warning: ${e.message}`);
    }
    // Reduced wait: 2s instead of 7s
    await sleep(2000);
    try {
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    } catch (_) {}
    await sleep(1000);

    workerLog('Entering pincode');
    await page.fill('input#pinCode', PINCODE).catch(() => {});
    await sleep(500);

    // Close popup if present
    try {
      const popup = page.locator('img.close-icon, img[alt="store modal close"]');
      if (await popup.count() > 0) await popup.first().click({ timeout: 2000 });
    } catch (_) {}

    workerLog('Entering mobile & fullname');
    await page.fill('input#moNumber', MOBILE).catch(() => {});
    await sleep(300);
    await page.fill('input#fullname', FULLNAME).catch(() => {});
    await sleep(300);

    // Select free search tab
    await page.click('a#freeNumber-tab').catch(() => {});
    await sleep(500);

    workerLog(`Starting search loop`);

    let totalSearches = 0;
    while (totalSearches < MAX_CYCLES) {
      let pattern = genPattern(totalSearches);
      let coolTries = 0;
      while (!isPatternAvailable(pattern) && coolTries < 50) {
        totalSearches++;
        coolTries++;
        pattern = genPattern(totalSearches);
      }
      markPatternUsed(pattern);
      totalSearches++;

      // Stagger delay between workers (reduced: 500ms-1.5s + worker offset)
      const stagger = rand(500, 1500) + (WORKER_ID * rand(300, 800));
      await sleep(stagger);

      // Type pattern and search
      await page.fill('input#cynNumber', pattern).catch(() => {});
      await sleep(200);
      await page.click('button#SearchBtnCYN').catch(() => {});
      await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
      await sleep(800);

      // Extract numbers from results
      const found = await page.$$eval('div.num-inner-wrap', nodes =>
        nodes.map(node => {
          const numEl = node.querySelector('span.mo-no');
          const typeEl = node.querySelector('span.type');
          return { num: numEl ? numEl.innerText.replace(/\D/g, '') : '', type: typeEl ? typeEl.innerText.trim() : '' };
        })
      ).catch(() => []);

      const rows = [];
      for (const item of found) {
        const num = normalize(item.num);
        const validation = validateNumber(num);
        if (!validation.valid) continue;

        const planMode = /postpaid/i.test(item.type) ? 'postpaid' : 'prepaid';
        const isPreferredPrefix = num.startsWith('7353') || num.startsWith('9071') || num.startsWith('9739');
        const isPriority = isPreferredPrefix || PRIORITIES.some(pk => num.includes(pk));

        rows.push({
          number: num,
          type: validation.correctedTotal,
          compound: validation.correctedCompound,
          plan: planMode,
          priority: isPriority,
          pricing: rand(2399, 5099),
          pattern: pattern,
          found: new Date().toISOString(),
        });
      }

      if (rows.length > 0) {
        for (const row of rows) {
          process.send({ type: 'found', ...row });
          workerLog(`✅ FOUND: ${row.number} (total=${row.compound}, type=${row.type})`);
        }
      }

      // Navigate to next page if available
      await page.click('span.next').catch(() => {});
      await sleep(300);

      // Refresh page every 30 searches (reduced from 50)
      if (totalSearches % 30 === 0) {
        workerLog('Refreshing page...');
        try {
          await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
          await sleep(1500);
          await page.fill('input#pinCode', PINCODE).catch(() => {});
          await sleep(300);
          try {
            const popup = page.locator('img.close-icon, img[alt="store modal close"]');
            if (await popup.count() > 0) await popup.first().click({ timeout: 2000 });
          } catch (_) {}
          await page.fill('input#moNumber', MOBILE).catch(() => {});
          await sleep(200);
          await page.fill('input#fullname', FULLNAME).catch(() => {});
          await sleep(200);
          await page.click('a#freeNumber-tab').catch(() => {});
          await sleep(300);
        } catch (_) {}
      }

      // Check session timeout
      if (Date.now() - runStart > sessionActiveMinutes * 60 * 1000) {
        workerLog(`Session timeout (${sessionActiveMinutes}m). Restarting...`);
        break;
      }
    }
  } finally {
    workerLog('Closing browser');
    await browser.close().catch(() => {});
    activeBrowser = null;
  }
}

// Main loop: run bot, cool down, repeat
(async () => {
  workerLog('=== Worker starting ===');

  while (true) {
    try {
      await runBot();
      if (MAX_CYCLES !== Infinity) {
        workerLog('MAX_CYCLES reached. Exiting.');
        process.exit(0);
      }
      // Idle cooldown: 10 minutes (reduced from 20)
      const idleMins = 10 + rand(-3, 3);
      workerLog(`Cooling down for ${idleMins} minutes...`);
      await sleep(idleMins * 60 * 1000);
      workerLog('Waking up. Starting next session...');
    } catch (e) {
      workerLog(`Session error: ${e.message}`);
      await sleep(5000);
    }
  }
})();

async function cleanupAndExit(signal) {
  workerLog(`Received ${signal}. Cleaning up...`);
  if (activeBrowser) {
    try { await activeBrowser.close(); } catch (_) {}
  }
  process.exit(0);
}
process.on('SIGINT', () => cleanupAndExit('SIGINT'));
process.on('SIGTERM', () => cleanupAndExit('SIGTERM'));
