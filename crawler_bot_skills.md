# Crawler Bot Agent Skill Runbook & Knowledge Base

This file serves as a persistent **Skill File** for future AI agents and developers working on the `vi-searchbot` repository. It documents known environment constraints, architectural components, and self-healing fixes implemented for past runtime errors to ensure automatic, intelligent maintenance.

---

## 🧭 Core Architecture & Files

* **`dashboard.js`**: The Express-based control panel and process manager. It manages worker processes, Cgroups memory detection, the Auto-RAM worker balancer, the self-healing watchdog loops, and exposes `/health` and CSV logs. Defaults to port `7860`.
* **`vi-number-bot-one-worker.js`**: The actual crawler worker that launches Playwright (Chromium) to search fancy mobile numbers on Vodafone-Idea (Vi). It handles intelligent patterns, AppScript API synchronization, and cooldowns.
* **`google-appscript-sheet2.gs`**: The Google Apps Script code coordinating remote Google Sheets integration, number filtering, and remote auto-heal/maintenance requests.
* **`Dockerfile`**: Docker container structure exposing port `7860` and executing the Express dashboard.

---

## 🛠️ Environment Constraints (Hugging Face Spaces vs Local macOS)

| Aspect | Hugging Face Space (Docker Container) | Local macOS Desktop |
| :--- | :--- | :--- |
| **OS Platform** | Linux (`linux`) | macOS (`darwin`) |
| **Display Server** | Headless (No X11 / no `$DISPLAY` environment) | Headed (Natively supported) |
| **Default Port** | Must bind strictly to `7860` | Flexible (typically `3000` or `7860`) |
| **Memory Detection** | Host `os.freemem()` is inaccurate due to Cgroups. Must read `/sys/fs/cgroup/` parameters. | Can safely use standard Node `os.freemem()`. |

---

## 🧠 Solved Problems & Self-Healing Runbook

Use this knowledge base to automatically recognize, diagnose, and resolve runtime failures:

### 1. Headed Browser Launch Crash on Linux
* **Problem**: 
  `Session error: browserType.launch: Target page, context or browser has been closed. Looks like you launched a headed browser without having a XServer running.`
* **Root Cause**: 
  The Auto-RAM loop in `dashboard.js` detected high free RAM (e.g., >15GB free on Hugging Face host) and toggled `headlessMode = false` to run headed Chromium. Without an XServer (DISPLAY) in the Docker container, Playwright immediately crashed.
* **How it is Fixed & Avoided**:
  * **Dashboard Check**: Added `const isHeadedSupported = process.platform !== 'linux' || !!process.env.DISPLAY` check in the Auto-RAM loop to block `headlessMode -> false` transitions.
  * **API Toggle Guard**: Blocked `/headless` API toggle endpoint if `!isHeadedSupported`.
  * **Worker Double-Lock**: Added a fallback in `vi-number-bot-one-worker.js`:
    ```javascript
    let HEADLESS = process.argv.includes('--headless');
    if (process.platform === 'linux' && !process.env.DISPLAY) {
      HEADLESS = true;
    }
    ```
  * *Rule for future agents*: Never allow `headlessMode = false` under Linux unless `$DISPLAY` is explicitly set in the environment.

### 2. Hugging Face Space Launch Timeout ("Workload Not Healthy")
* **Problem**: 
  `Launch timed out, workload was not healthy after 30 min`
* **Root Cause**: 
  Hugging Face Space expects a web service to bind to and respond on port `7860`. If the container runs `vi-number-bot-one-worker.js` directly as its entrypoint, there is no HTTP server listening on the port, triggering a health-check failure.
* **How it is Fixed & Avoided**:
  * Expose port `7860` in the `Dockerfile`.
  * Run the `dashboard.js` Express web app as the container `CMD`.
  * Provide a fast `/health` API endpoint responding with `{ status: "ok" }`.

### 3. Log Invisibility / Frozen Container Logs
* **Problem**: 
  Container logs are completely frozen at startup (`Dashboard started on port 7860`), making it appear as if the bot is stuck or inactive.
* **Root Cause**: 
  Child workers were spawned silently (`{ silent: true }`) with stdout/stderr piped only to the dashboard's internal buffer for the SSE stream, preventing standard output from reaching the Docker runtime logs.
* **How it is Fixed & Avoided**:
  * Modified `pushLog()` in `dashboard.js` to mirror all worker logging to `console.log`:
    ```javascript
    function pushLog(line) {
      // ...
      console.log(line); // Stream to system stdout/stderr
    }
    ```

### 4. False-Positive Watchdog Termination During Idle Cooling
* **Problem**: 
  Manager watchdog kills active crawler bot because it hasn't printed logs for several minutes, thinking it is hung.
* **Root Cause**: 
  The worker enters an `idleSleep` phase (cooling down for 20-30 minutes to bypass rate-limits). During this time, it printed nothing, causing the watchdog to falsely trigger a restart.
* **How it is Fixed & Avoided**:
  * Implemented log heartbeats during cooling sleep. The worker prints a status log every 2 minutes while sleeping, proving it is active to the watchdog guardian.

### 5. Cumulative Browser Memory Leaks
* **Problem**: 
  Scraper processes gradually grow in memory usage, eventually crashing due to out-of-memory errors.
* **Root Cause**: 
  Playwright/Chromium accumulates memory and cache over long operational periods.
* **How it is Fixed & Avoided**:
  * **Proactive Rotation**: The dashboard's watchdog automatically terminates and restarts worker processes after 4 hours of continuous runtime.
  * **Orphan Cleanup**: Spawning/stopping runs `cleanupOrphanedBrowsers()` using `pkill -f` to sweep leftover Chromium processes from the system.
  * **Container RAM Tracking**:
    ```javascript
    // Reads modern Cgroups limits instead of host limits
    if (fs.existsSync('/sys/fs/cgroup/memory.max')) { ... }
    ```

---

## 📈 Auto-Update Procedure for Future Fixes

Whenever a new runtime error is fixed:
1. **Identify the exact error log** and locate the file/function responsible.
2. **Document the root cause** (e.g. environment variable missing, logic constraint, library version mismatch).
3. **Draft the self-healing solution** ensuring it does not break local macOS desktop support.
4. **Append the new entry** to this `crawler_bot_skills.md` file under the "Solved Problems" section.
5. **Commit the changes** and push to Hugging Face to ensure the persistent documentation matches the code.
