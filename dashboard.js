const express = require('express');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { fork, exec } = require('child_process');
const ExcelJS = require('exceljs');
const xlsx = require('xlsx');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());
const PORT = process.env.PORT || 7860;

const defaultBot = process.env.VI_BOT_FILE || 'vi-number-bot-one-worker.js';
let botPath = path.join(__dirname, defaultBot);
if (!fs.existsSync(botPath)) {
  const fallback = path.join(__dirname, 'vi-number-bot-one-worker.js');
  if (fs.existsSync(fallback)) botPath = fallback;
}
const BOT_FILE = botPath;
const MASTER_XLSX = path.join(__dirname, 'outputs', 'Vi_Master_Outputs.xlsx');
const NUMBERS_JSON = path.join(__dirname, 'outputs', 'found_numbers.json');
const CONFIG_FILE = path.join(__dirname, 'bot-config.json');

// ── Config ──────────────────────────────────────────────────────────────────
let headlessMode = false;
let autoRamEnabled = false;
let maxWorkers = 12;
let fullname = 'Hankith';
let mobile = '9071977078';
let pincode = '560100';

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      const c = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
      headlessMode = !!c.headless;
      autoRamEnabled = !!c.autoRam;
      maxWorkers = c.maxWorkers || 12;
      if (c.fullname) fullname = c.fullname;
      if (c.mobile) mobile = c.mobile;
      if (c.pincode) pincode = c.pincode;
    }
  } catch (_) {}

  if (process.platform === 'linux' && !process.env.DISPLAY) {
    headlessMode = true;
  }
}

function saveConfig() {
  try {
    fs.writeFileSync(CONFIG_FILE, JSON.stringify({
      headless: headlessMode,
      autoRam: autoRamEnabled,
      maxWorkers,
      fullname,
      mobile,
      pincode
    }, null, 2));
  } catch (_) {}
}

loadConfig();

// Container-aware memory detection for optimal Cgroups/Hugging Face support
function getContainerMemory() {
  var totalMemBytes = os.totalmem();
  var freeMemBytes = os.freemem();

  try {
    // Check Cgroups v2 (modern Linux / Docker)
    if (fs.existsSync('/sys/fs/cgroup/memory.max')) {
      var maxStr = fs.readFileSync('/sys/fs/cgroup/memory.max', 'utf8').trim();
      if (maxStr && maxStr !== 'max') {
        var limit = parseInt(maxStr, 10);
        if (!isNaN(limit) && limit > 0) {
          totalMemBytes = limit;
          if (fs.existsSync('/sys/fs/cgroup/memory.current')) {
            var currentStr = fs.readFileSync('/sys/fs/cgroup/memory.current', 'utf8').trim();
            var current = parseInt(currentStr, 10);
            if (!isNaN(current) && current > 0) {
              freeMemBytes = Math.max(0, totalMemBytes - current);
            }
          }
        }
      }
    } 
    // Fallback to Cgroups v1
    else if (fs.existsSync('/sys/fs/cgroup/memory/memory.limit_in_bytes')) {
      var limitStr = fs.readFileSync('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'utf8').trim();
      var limit = parseInt(limitStr, 10);
      if (!isNaN(limit) && limit > 0 && limit < 1e15) { // very large numbers mean unlimited
        totalMemBytes = limit;
        if (fs.existsSync('/sys/fs/cgroup/memory/memory.usage_in_bytes')) {
          var usageStr = fs.readFileSync('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf8').trim();
          var usage = parseInt(usageStr, 10);
          if (!isNaN(usage) && usage > 0) {
            freeMemBytes = Math.max(0, totalMemBytes - usage);
          }
        }
      }
    }
  } catch (e) {
    // Ignore and fallback to standard os limits
  }

  return {
    totalGB: totalMemBytes / (1024 ** 3),
    freeGB: freeMemBytes / (1024 ** 3)
  };
}

// ── State ───────────────────────────────────────────────────────────────────
let botProcesses = [];
let logBuffer = [];
const MAX_BUFFER = 2000;
const clients = new Set();
const patternHistory = []; // { pattern, timestamp, workerId }
let botStarted = true; // Tracks if the bot is supposed to be running (defaults to true since it auto-starts)

// ── Ensure dirs/files ────────────────────────────────────────────────────────
if (!fs.existsSync(path.dirname(MASTER_XLSX))) fs.mkdirSync(path.dirname(MASTER_XLSX), { recursive: true });
if (!fs.existsSync(NUMBERS_JSON)) fs.writeFileSync(NUMBERS_JSON, JSON.stringify([], null, 2));

// ── SSE helpers ──────────────────────────────────────────────────────────────
function sendEvent(type, payload) {
  const msg = `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`;
  for (const res of clients) res.write(msg);
}

function pushLog(line) {
  const entry = { time: new Date().toISOString(), line };
  logBuffer.push(entry);
  if (logBuffer.length > MAX_BUFFER) logBuffer.shift();
  sendEvent('log', entry);
  console.log(line); // Stream directly to system console to ensure Hugging Face logs show live scraper activity
}

function sendStatusUpdate() {
  botProcesses = botProcesses.filter(p => !p.killed && p.exitCode === null);
  const running = botProcesses.length > 0;
  const pids = botProcesses.map(p => p.pid).filter(Boolean);
  const mem = getContainerMemory();
  const freeGB = mem.freeGB.toFixed(2);
  const totalGB = mem.totalGB.toFixed(2);
  sendEvent('status', {
    running,
    pids,
    botPath: BOT_FILE,
    freeMemGB: freeGB,
    totalMemGB: totalGB,
    headless: headlessMode,
    autoRam: autoRamEnabled,
    maxWorkers,
    fullname,
    mobile,
    pincode
  });
}

setInterval(sendStatusUpdate, 3000);

// ── Worker management ────────────────────────────────────────────────────────
const RAM_PER_WORKER_HEADED   = 1.2;  // GB per headed worker
const RAM_PER_WORKER_HEADLESS = 0.55; // GB per headless worker
const RAM_TO_HEADLESS_GB      = 1.2;  // switch headless when free RAM drops below
const RAM_TO_HEADED_GB        = 2.8;  // switch back headed when free RAM recovers above
const RAM_KILL_WORKER_GB      = 0.8;  // emergency: kill a worker

// macOS process names never to touch
const SYSTEM_PROCS = [
  'kernel_task','launchd','WindowServer','loginwindow','Dock','SystemUIServer',
  'coreaudiod','mds','mdworker','hidd','opendirectoryd','configd','node',
  'bash','zsh','sh','python','ruby'
];

let lastHogReport = 0; // throttle hog SSE events (ms)

function getMemHogs(callback) {
  if (process.platform !== 'darwin') return callback([]);
  exec('ps aux -m', (err, stdout) => {
    if (err) return callback([]);
    const selfPid = process.pid;
    const hogs = [];
    const lines = stdout.trim().split('\n').slice(1);
    for (const line of lines) {
      const parts = line.trim().split(/\s+/);
      if (parts.length < 11) continue;
      const pid = parseInt(parts[1]);
      const memPct = parseFloat(parts[3]);
      const rssKB  = parseInt(parts[5]);
      const name   = path.basename(parts[10]);
      if (pid === selfPid || memPct < 1.0) continue;
      if (SYSTEM_PROCS.some(s => name.toLowerCase().includes(s.toLowerCase()))) continue;
      if (name.startsWith('com.apple') || name.startsWith('com.') || name === '(sd)') continue;
      hogs.push({ pid, name, memPct, ramGB: (rssKB / (1024 * 1024)).toFixed(2) });
      if (hogs.length >= 8) break;
    }
    callback(hogs);
  });
}

function computeIdealWorkers() {
  const mem = getContainerMemory();
  const freeGB = mem.freeGB;
  const perWorker = headlessMode ? RAM_PER_WORKER_HEADLESS : RAM_PER_WORKER_HEADED;
  return Math.max(1, Math.min(maxWorkers, Math.floor(freeGB / perWorker)));
}

function getNextWorkerId() {
  const activeIds = new Set(botProcesses.map(p => p.workerId).filter(Boolean));
  let id = 1;
  while (activeIds.has(id)) id++;
  return id;
}

function spawnWorker(workerId, totalWorkers) {
  const args = ['--child', `--worker-id=${workerId}`, `--worker-count=${totalWorkers}`];
  if (headlessMode) args.push('--headless');

  const child = fork(BOT_FILE, args, {
    silent: true,
    env: {
      ...process.env,
      FULLNAME: fullname,
      MOBILE: mobile,
      PINCODE: pincode
    }
  });
  child.workerId = workerId;
  child.intentionallyKilled = false;
  child.spawnTime = Date.now();
  child.lastActiveTime = Date.now();

  child.stdout.on('data', d => {
    child.lastActiveTime = Date.now();
    const text = d.toString().trim();
    const patMatch = text.match(/Searching pattern:\s*(\S+)/);
    if (patMatch) {
      const entry = { pattern: patMatch[1], timestamp: new Date().toISOString(), workerId };
      patternHistory.push(entry);
      if (patternHistory.length > 500) patternHistory.shift();
      sendEvent('pattern', entry);
    }
    pushLog(`[W${workerId}] ${text}`);
  });

  child.stderr.on('data', d => {
    child.lastActiveTime = Date.now();
    pushLog(`[W${workerId} ERR] ${d.toString().trim()}`);
  });

  child.on('exit', (code, sig) => {
    pushLog(`Worker ${workerId} exited code=${code} signal=${sig}`);
    botProcesses = botProcesses.filter(p => p !== child);
    sendStatusUpdate();

    if (botStarted && !child.intentionallyKilled) {
      const reason = child.rotationReason || 'exited unexpectedly';
      pushLog(`⚠ Worker ${workerId} (${reason}). Auto-restarting in 5 seconds...`);
      setTimeout(() => {
        if (botStarted) {
          botProcesses = botProcesses.filter(p => !p.killed && p.exitCode === null);
          const currentCount = botProcesses.length;
          const targetCount = autoRamEnabled ? computeIdealWorkers() : maxWorkers;
          if (currentCount < targetCount) {
            const nextId = getNextWorkerId();
            botProcesses.push(spawnWorker(nextId, targetCount));
            sendStatusUpdate();
          }
        }
      }, 5000);
    }
  });

  pushLog(`▶ Worker ${workerId}/${totalWorkers} PID=${child.pid} headless=${headlessMode}`);
  return child;
}

function restartAllWorkers(count) {
  const n = count || botProcesses.filter(p => !p.killed && p.exitCode === null).length || 1;
  botProcesses.forEach(p => {
    p.intentionallyKilled = true;
    try { p.kill('SIGINT'); } catch (_) {}
  });
  botProcesses = [];
  pushLog(`🔄 Restarting ${n} worker(s) (headless=${headlessMode})…`);
  setTimeout(() => {
    for (let i = 1; i <= n; i++) botProcesses.push(spawnWorker(i, n));
    sendStatusUpdate();
  }, 1800);
}

function cleanupOrphanedBrowsers() {
  const isLinux = process.platform === 'linux';
  const isDarwin = process.platform === 'darwin';
  if (isLinux || isDarwin) {
    const cmd = isLinux ? 'pkill -f "chrome|chromium"' : 'pkill -f "Chromium|Chrome"';
    exec(cmd, (err) => {
      if (!err) {
        pushLog('🧹 Cleaned up lingering Chromium/Chrome browser processes.');
      }
    });
  }
}


// ── Auto-RAM loop ─────────────────────────────────────────────────────────────
setInterval(() => {
  if (!autoRamEnabled) return;

  const mem = getContainerMemory();
  const freeGB = mem.freeGB;
  botProcesses = botProcesses.filter(p => !p.killed && p.exitCode === null);
  const current = botProcesses.length;

  // ── headed → headless: RAM dropped below threshold ──
  if (!headlessMode && freeGB < RAM_TO_HEADLESS_GB && current > 0) {
    headlessMode = true;
    saveConfig();
    pushLog(`🌙 AutoRAM: ${freeGB.toFixed(2)}GB free — switching Chromium to headless`);
    sendEvent('ramAlert', { level: 'warning', freeGB: freeGB.toFixed(2), action: 'switched_headless' });
    restartAllWorkers(current);
    return;
  }

  // ── headless → headed: RAM recovered above threshold ──
  const isHeadedSupported = process.platform !== 'linux' || !!process.env.DISPLAY;
  if (isHeadedSupported && headlessMode && freeGB > RAM_TO_HEADED_GB && current > 0) {
    headlessMode = false;
    saveConfig();
    pushLog(`☀ AutoRAM: ${freeGB.toFixed(2)}GB free — switching Chromium back to headed`);
    sendEvent('ramAlert', { level: 'info', freeGB: freeGB.toFixed(2), action: 'switched_headed' });
    restartAllWorkers(current);
    return;
  }

  // ── emergency: kill a worker + report background hogs ──
  if (freeGB < RAM_KILL_WORKER_GB) {
    sendEvent('ramAlert', { level: 'critical', freeGB: freeGB.toFixed(2) });
    if (current > 1) {
      const last = botProcesses.pop();
      last.intentionallyKilled = true;
      try { last.kill('SIGINT'); } catch (_) {}
      pushLog(`⚠ AutoRAM: killed 1 worker — critical RAM (${freeGB.toFixed(2)}GB free)`);
    }
    if (Date.now() - lastHogReport > 30000) {
      lastHogReport = Date.now();
      getMemHogs(hogs => {
        if (hogs.length > 0) {
          pushLog(`⚠ AutoRAM: background hogs using RAM — check dashboard`);
          sendEvent('ramHogs', { freeGB: freeGB.toFixed(2), hogs });
        }
      });
    }
    return;
  }

  if (freeGB < 1.5) sendEvent('ramAlert', { level: 'warning', freeGB: freeGB.toFixed(2) });

  if (current === 0) return;

  const ideal = computeIdealWorkers();
  if (current > ideal) {
    const last = botProcesses.pop();
    last.intentionallyKilled = true;
    try { last.kill('SIGINT'); } catch (_) {}
    pushLog(`⚡ AutoRAM: ${current} → ${current - 1} workers (${freeGB.toFixed(2)}GB free)`);
  } else if (current < ideal) {
    const nextId = getNextWorkerId();
    botProcesses.push(spawnWorker(nextId, ideal));
    pushLog(`⚡ AutoRAM: ${current} → ${current + 1} workers (${freeGB.toFixed(2)}GB free)`);
  }

  sendStatusUpdate();
}, 12000);

// ── Watchdog self-healing loop ───────────────────────────────────────────────
setInterval(() => {
  const now = Date.now();
  
  // Clean up exited references
  botProcesses = botProcesses.filter(p => !p.killed && p.exitCode === null);
  
  if (botProcesses.length === 0) {
    cleanupOrphanedBrowsers();
  }
  
  botProcesses.forEach(p => {
    // 1. Stuck/Hung Watchdog: Silent/no prints for > 8 minutes
    const inactiveDuration = now - p.lastActiveTime;
    if (inactiveDuration > 8 * 60 * 1000) {
      pushLog(`[Self-Heal] Worker ${p.workerId} HUNG (silent for ${(inactiveDuration / 60000).toFixed(1)}m). Force restarting...`);
      p.rotationReason = 'stuck watchdog action';
      p.intentionallyKilled = false; // Trigger standard auto-restart
      try {
        p.kill('SIGKILL');
      } catch (err) {
        pushLog(`[Self-Heal] Error killing hung worker ${p.workerId}: ${err.message}`);
      }
    }
    // 2. Proactive Memory Rotation: Active for > 4 hours to clean cumulative browser leak
    else if (now - p.spawnTime > 4 * 60 * 60 * 1000) {
      pushLog(`[Self-Heal] Worker ${p.workerId} running >4 hours. Proactively rotating to clear memory leaks...`);
      p.rotationReason = 'proactive memory rotation';
      p.intentionallyKilled = false; // Trigger standard auto-restart
      try {
        p.kill('SIGINT');
      } catch (_) {}
    }
  });
}, 60000);

// ── Auto-start on launch ──────────────────────────────────────────────────────
if (fs.existsSync(BOT_FILE)) {
  setTimeout(() => {
    botStarted = true;
    const ideal = computeIdealWorkers();
    const count = autoRamEnabled ? ideal : 1;
    for (let i = 1; i <= count; i++) botProcesses.push(spawnWorker(i, count));
    pushLog(`▶ Auto-started ${count} worker(s) on launch (headless=${headlessMode})`);
    sendStatusUpdate();
  }, 2500);
}

// ── Routes ────────────────────────────────────────────────────────────────────
app.get('/health', (req, res) => {
  const mem = getContainerMemory();
  return res.json({
    status: 'ok',
    uptime: process.uptime(),
    workers: botProcesses.length,
    freeMemGB: mem.freeGB.toFixed(2),
    totalMemGB: mem.totalGB.toFixed(2)
  });
});

app.get('/', (req, res) => res.sendFile(path.join(__dirname, 'public', 'dashboard.html')));

app.get('/events', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();
  sendStatusUpdate();
  sendEvent('logs', { logs: logBuffer.slice(-100) });
  clients.add(res);
  req.on('close', () => clients.delete(res));
});

app.post('/start', (req, res) => {
  if (!fs.existsSync(BOT_FILE)) return res.json({ ok: false, error: 'Bot file not found' });

  const requested = Number(req.body && req.body.workers) || 1;
  maxWorkers = requested;
  saveConfig();

  botStarted = true;

  botProcesses = botProcesses.filter(p => !p.killed && p.exitCode === null);
  const current = botProcesses.length;

  if (current >= requested) return res.json({ ok: false, msg: `Already ${current} workers running`, pids: botProcesses.map(p => p.pid) });

  for (let i = current + 1; i <= requested; i++) {
    const nextId = getNextWorkerId();
    botProcesses.push(spawnWorker(nextId, requested));
  }
  sendStatusUpdate();
  return res.json({ ok: true, workers: requested, pids: botProcesses.map(p => p.pid) });
});

app.post('/stop', (req, res) => {
  botStarted = false;
  const pids = botProcesses.map(p => p.pid);
  botProcesses.forEach(p => {
    p.intentionallyKilled = true;
    try { p.kill('SIGINT'); } catch (_) {}
  });
  botProcesses = [];
  exec(`pkill -f "node.*${path.basename(BOT_FILE)}"`, () => {
    setTimeout(() => {
      cleanupOrphanedBrowsers();
    }, 1000);
  });
  pushLog(`■ Stopped all workers (PIDs: ${pids.join(', ')})`);
  sendStatusUpdate();
  return res.json({ ok: true, pids });
});

app.post('/headless', (req, res) => {
  if (process.platform === 'linux' && !process.env.DISPLAY) {
    pushLog(`⚠ Headless mode toggle ignored: Headed browser is not supported in this environment (missing X11 DISPLAY).`);
    return res.json({ ok: false, error: 'Headed browser not supported in this environment', headless: true });
  }
  headlessMode = !headlessMode;
  saveConfig();
  pushLog(`⚙ Headless mode: ${headlessMode}`);
  botProcesses = botProcesses.filter(p => !p.killed && p.exitCode === null);
  if (botProcesses.length > 0) restartAllWorkers(botProcesses.length);
  else sendStatusUpdate();
  return res.json({ ok: true, headless: headlessMode });
});

app.post('/autoram', (req, res) => {
  autoRamEnabled = req.body && req.body.enabled !== undefined ? !!req.body.enabled : !autoRamEnabled;
  saveConfig();
  pushLog(`⚙ AutoRAM: ${autoRamEnabled}`);
  sendStatusUpdate();
  return res.json({ ok: true, autoRam: autoRamEnabled });
});

app.get('/ram', (req, res) => {
  const mem = getContainerMemory();
  const freeGB = mem.freeGB.toFixed(2);
  const totalGB = mem.totalGB.toFixed(2);
  const idealWorkers = computeIdealWorkers();
  return res.json({ freeGB, totalGB, idealWorkers, headless: headlessMode, autoRam: autoRamEnabled });
});

app.get('/patterns', (req, res) => res.json({ patterns: patternHistory.slice(-100) }));

app.post('/clearLogs', (req, res) => {
  logBuffer = [];
  pushLog('Logs cleared');
  return res.json({ ok: true });
});

app.get('/status', (req, res) => {
  botProcesses = botProcesses.filter(p => !p.killed && p.exitCode === null);
  const mem = getContainerMemory();
  return res.json({
    running: botProcesses.length > 0,
    pids: botProcesses.map(p => p.pid).filter(Boolean),
    botPath: BOT_FILE,
    freeMemGB: mem.freeGB.toFixed(2),
    totalMemGB: mem.totalGB.toFixed(2),
    headless: headlessMode,
    autoRam: autoRamEnabled,
    maxWorkers,
    fullname,
    mobile,
    pincode
  });
});

app.post('/config', (req, res) => {
  const { name: reqName, mobile: reqMobile, pincode: reqPincode } = req.body || {};
  if (reqName !== undefined) fullname = String(reqName).trim() || 'Hankith';
  if (reqMobile !== undefined) mobile = String(reqMobile).trim() || '9071977078';
  if (reqPincode !== undefined) pincode = String(reqPincode).trim() || '560100';
  saveConfig();
  pushLog(`⚙ Settings updated: fullname="${fullname}", mobile="${mobile}", pincode="${pincode}"`);
  sendStatusUpdate();
  return res.json({ ok: true, fullname, mobile, pincode });
});

app.get('/numbers.csv', async (req, res) => {
  if (!fs.existsSync(MASTER_XLSX)) return res.status(200).send('sheet,number,row\n');
  try {
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.readFile(MASTER_XLSX);
    let out = 'sheet,number,row\n';
    wb.eachSheet(sheet => {
      sheet.eachRow((row, n) => {
        if (n === 1) return;
        const num = row.getCell(2).value;
        if (num) out += `${sheet.name},${num},${n}\n`;
      });
    });
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', 'attachment; filename="numbers.csv"');
    return res.send(out);
  } catch (e) {
    return res.status(500).json({ ok: false, error: e.message });
  }
});

app.get('/logs', (req, res) => res.json({ logs: logBuffer }));

function getSingleTotal(numStr) {
  const clean = String(numStr).replace(/\D/g, '');
  let sum = clean.split('').reduce((acc, d) => acc + Number(d), 0);
  while (sum > 9) {
    sum = String(sum).split('').reduce((a, b) => a + Number(b), 0);
  }
  return sum;
}

app.get('/numbers', async (req, res) => {
  if (!fs.existsSync(MASTER_XLSX)) return res.json({ ok: true, groups: { 1: [], 3: [], 5: [], 6: [] } });
  try {
    const wb = xlsx.readFile(MASTER_XLSX);
    const seen = new Set();
    const allNumbers = [];

    wb.SheetNames.forEach(sheetName => {
      xlsx.utils.sheet_to_json(wb.Sheets[sheetName], { defval: '' }).forEach(rowData => {
        const rawNum = rowData.number || rowData.Number || rowData.mobile || rowData.Phone || rowData['Found Number'];
        if (!rawNum) return;
        const numStr = String(rawNum).replace(/\D/g, '');
        if (!numStr || seen.has(numStr)) return;
        seen.add(numStr);

        const singleTotal = rowData.numberTotal || rowData['Number total'] || rowData.Total || getSingleTotal(numStr);
        const compound = rowData.compoundTotal || rowData['Number Compound'] || rowData.Compound || numStr.split('').reduce((acc, d) => acc + Number(d), 0);
        const plan = rowData.plan || rowData['prepaid / postpaid'] || '';
        const timestamp = rowData.timestamp || rowData.Timestamp || new Date().toISOString();

        allNumbers.push({
          number: numStr,
          singleTotal: Number(singleTotal),
          compoundTotal: Number(compound),
          plan: plan,
          timestamp: timestamp
        });
      });
    });

    allNumbers.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

    const groups = { 1: [], 3: [], 5: [], 6: [] };
    allNumbers.forEach(n => {
      if (groups[n.singleTotal]) {
        groups[n.singleTotal].push(n);
      }
    });

    return res.json({ ok: true, groups });
  } catch (e) {
    return res.json({ ok: false, error: e.message });
  }
});

// ── RAM hog detection & quit ──────────────────────────────────────────────────
app.get('/ram/hogs', (req, res) => {
  getMemHogs(hogs => res.json({ ok: true, hogs }));
});

app.post('/ram/quit', (req, res) => {
  const { appName, pid } = req.body || {};
  if (!appName && !pid) return res.json({ ok: false, error: 'Need appName or pid' });

  if (appName && process.platform === 'darwin') {
    exec(`osascript -e 'tell application "${appName}" to quit'`, err => {
      if (!err) {
        pushLog(`🗑 Quit "${appName}" to free RAM`);
        return res.json({ ok: true, method: 'quit', appName });
      }
      // graceful quit failed → force kill by PID
      if (pid) {
        exec(`kill ${parseInt(pid)}`, () => {
          pushLog(`🗑 Force-killed PID ${pid} (${appName}) to free RAM`);
          res.json({ ok: true, method: 'kill', pid });
        });
      } else {
        res.json({ ok: false, error: err.message });
      }
    });
  } else if (pid) {
    exec(`kill ${parseInt(pid)}`, err => {
      pushLog(`🗑 Killed PID ${pid} to free RAM`);
      res.json({ ok: !err, pid });
    });
  } else {
    res.json({ ok: false, error: 'Platform not supported for graceful quit' });
  }
});

// macOS terminal launch (kept for compatibility)
app.post('/terminal/start', (req, res) => {
  if (process.platform !== 'darwin') return res.json({ ok: false, error: 'macOS only' });
  exec(`osascript -e 'tell application "Terminal" to do script "cd ${__dirname} && node ${path.basename(BOT_FILE)} --child"'`, err => {
    if (err) return res.json({ ok: false, error: err.message });
    return res.json({ ok: true });
  });
});

app.post('/terminal/stop', (req, res) => {
  exec(`pkill -f "node .*${path.basename(BOT_FILE)}"`, err => {
    return res.json({ ok: !err });
  });
});

app.use('/static', express.static(path.join(__dirname, 'public')));

app.listen(PORT, () => {
  console.log(`Dashboard → http://localhost:${PORT}  headless=${headlessMode} autoRam=${autoRamEnabled}`);
  pushLog(`Dashboard started on port ${PORT}`);
});
