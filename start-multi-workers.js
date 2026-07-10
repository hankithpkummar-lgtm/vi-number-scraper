const { fork } = require('child_process');
const os = require('os');
const path = require('path');

const BOT_FILE = path.join(__dirname, 'vi-number-bot-one-worker.js');

// Calculate ideal worker count based on system specs
const cpus = os.cpus().length;
const totalMemGB = os.totalmem() / (1024 ** 3);

// Keep minimum 3 workers, cap at maximum 5 workers (best to avoid overwhelming target site/IP bans)
const MIN_WORKERS = 3;
const MAX_WORKERS = 5;

// Allocate 1 worker per CPU core, within the designated bounds
let idealWorkers = Math.max(MIN_WORKERS, Math.min(MAX_WORKERS, cpus));

// Also verify system RAM: each worker needs at least 0.8 GB of memory to run comfortably
const maxByRAM = Math.floor(totalMemGB / 0.8);
if (idealWorkers > maxByRAM) {
  idealWorkers = Math.max(MIN_WORKERS, maxByRAM);
}

console.log(`[Manager] System Resources: ${cpus} vCPUs, ${totalMemGB.toFixed(2)} GB RAM`);
console.log(`[Manager] Dynamically assigned ${idealWorkers} workers (Range: ${MIN_WORKERS} - ${MAX_WORKERS})`);

const workers = new Map();

function spawnWorker(workerId) {
  const args = [
    `--worker-id=${workerId}`,
    `--worker-count=${idealWorkers}`,
    '--headless'
  ];
  
  // Inherit active-minutes / idle-minutes from manager argv if passed
  const activeMins = process.argv.find(arg => arg.startsWith('--active-minutes='));
  const idleMins = process.argv.find(arg => arg.startsWith('--idle-minutes='));
  if (activeMins) args.push(activeMins);
  if (idleMins) args.push(idleMins);

  console.log(`[Manager] Spawning Worker ${workerId}/${idealWorkers}...`);
  
  // silent: false ensures all worker stdout/stderr is cleanly piped to our console logs
  const child = fork(BOT_FILE, args, { silent: false });
  
  workers.set(workerId, child);

  child.on('exit', (code, sig) => {
    console.log(`[Manager] Worker ${workerId} exited with code ${code} and signal ${sig}`);
    workers.delete(workerId);
    
    // Automatically restart to keep 24/7 system active
    console.log(`[Manager] Restarting Worker ${workerId} in 5 seconds...`);
    setTimeout(() => spawnWorker(workerId), 5000);
  });
}

// Start all workers with a staggered, randomized delay to break synchronized signatures
console.log(`[Manager] Initiating staggered worker startup sequence...`);
for (let i = 1; i <= idealWorkers; i++) {
  const startupDelay = (i - 1) * Math.floor(Math.random() * (75000 - 40000 + 1) + 40000); // 40-75s staggered delay
  if (startupDelay === 0) {
    spawnWorker(i);
  } else {
    console.log(`[Manager] Worker ${i} scheduled to launch in ${(startupDelay/1000).toFixed(1)} seconds...`);
    setTimeout(() => spawnWorker(i), startupDelay);
  }
}

// Graceful shutdown handling
process.on('SIGINT', () => {
  console.log('[Manager] Shutdown signal received. Terminating all workers...');
  for (const [id, child] of workers.entries()) {
    try { child.kill('SIGINT'); } catch (_) {}
  }
  process.exit(0);
});
process.on('SIGTERM', () => {
  console.log('[Manager] Termination signal received. Shutting down workers...');
  for (const [id, child] of workers.entries()) {
    try { child.kill('SIGTERM'); } catch (_) {}
  }
  process.exit(0);
});
