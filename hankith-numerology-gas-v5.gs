// ══════════════════════════════════════════════════════════════════════
// HANKITH NUMEROLOGY - GOOGLE APPS SCRIPT v5.1.0
// Complete Backend: Numbers, Customers, Suggestions, Design, Visitors,
// Compatibility, Reports, Sharing, Free/Paid, Transactions, Auto-Cleanup
//
// FIXED v5.1.0: doGet addNumber/addNumbersBatch appendRow column order
//   to match HEADERS_NUMBERS (Row,Number,Root,Compound,Plan,Source,
//   Price,Status,Found,Last Updated,Notes,Hash)
// ══════════════════════════════════════════════════════════════════════

// ─── CONFIGURATION ──────────────────────────────────────────────────

const SPREADSHEET_ID = "1DC6U1DoyFt_LHlbE-Hww9f1rBjLLnEeg0g1Pjp3Y57E";

const SHEET_NUMBERS = "Numbers";
const SHEET_FREE_NUMBERS = "FreeNumbers";
const SHEET_PAID_NUMBERS = "PaidNumbers";
const SHEET_CUSTOMERS = "Customers";
const SHEET_REPORTS = "Reports";
const SHEET_TRANSACTIONS = "Transactions";
const SHEET_LOGS = "Logs";
const SHEET_HEALTH = "Health";
const SHEET_WEBSITE_VISITORS = "WebsiteVisitors";

const HEADERS_NUMBERS = [
  "Row", "Number", "Root", "Compound", "Plan", "Source",
  "Price", "Status", "Found", "Last Updated", "Notes", "Hash"
];

const HEADERS_FREE = [
  "Row", "Number", "Root", "Compound", "Plan", "Source",
  "Price", "Status", "Found", "Last Updated", "Notes", "Hash", "Expiry Date"
];

const HEADERS_PAID = [
  "Row", "Number", "Root", "Compound", "Plan", "Source",
  "Price", "Status", "Found", "Last Updated", "Notes", "Hash", "Expiry Date"
];

const HEADERS_CUSTOMERS = [
  "ID", "Name", "Gender", "DOB", "Day", "Month", "Year",
  "Pincode", "WhatsApp", "Created At", "Status", "Notes",
  "Last Contacted", "Follow-Up Count", "Follow-Up Stage", "Follow-Up Date"
];

const HEADERS_REPORTS = [
  "ID", "Customer ID", "Customer Name", "Mobile Number", "Report Type",
  "Overall Score", "Grade", "Generated At", "Shared At", "Report Data"
];

const HEADERS_TRANSACTIONS = [
  "ID", "Order ID", "Payment ID", "Customer Name", "Customer Email",
  "Customer Phone", "Amount", "Currency", "Status", "Service Type",
  "Service Details", "Created At", "Verified At", "Notes"
];

const HEADERS_HEALTH = ["Timestamp", "Action", "Status", "Details", "LatencyMs"];

const HEADERS_WEBSITE_VISITORS = [
  "ID", "Timestamp", "Name", "DOB", "Mobile", "Email", "Gender",
  "Source", "Page", "Service", "IP Address", "User Agent", "Status"
];

// ─── FOLLOW-UP STAGES ───────────────────────────────────────────────

const FOLLOW_UP_STAGES = {
  FRESH: { name: "fresh", days: 0, label: "Fresh (0-2 days)" },
  STAGE_2: { name: "2-day", days: 2, label: "Follow-Up 2 Days" },
  STAGE_5: { name: "5-day", days: 5, label: "Follow-Up 5 Days" },
  STAGE_7: { name: "7-day", days: 7, label: "Follow-Up 7 Days" },
  STAGE_14: { name: "14-day", days: 14, label: "Follow-Up 14 Days" },
};

// ─── NUMEROLOGY CONSTANTS ───────────────────────────────────────────

const PLANET_MAP = {
  1: "Sun", 2: "Moon", 3: "Jupiter", 4: "Rahu",
  5: "Mercury", 6: "Venus", 7: "Ketu", 8: "Saturn", 9: "Mars",
};

const LUCKY_ROOTS = [1, 3, 5, 6];

const FRIENDLY = {
  1: [3, 5, 6, 9], 2: [1, 3, 5, 9], 3: [1, 2, 5, 6, 9],
  4: [1, 5, 9], 5: [1, 3, 6, 9], 6: [1, 3, 5],
  7: [1, 3, 5], 8: [1, 3, 5], 9: [1, 3, 5],
};

const GOOD_PAIRS = [
  "11","13","31","15","51","17","71","19","91",
  "33","35","53","37","73","39","93",
  "55","57","75","59","95","77","79","97","99",
];

const HIGHLIGHT_PAIRS = ["77", "99"];

const AVOID_PAIRS = [
  "14","41","16","61","18","81","23","32","26","62",
  "27","72","28","82","34","43","45","54","46","64",
  "48","84","67","76","68","86","69","96","89","98",
];

const GOOD_COMPOUNDS = {
  1: [46, 64, 37, 55],
  3: [66, 39, 30],
  5: [41, 32, 50, 59],
  6: [42, 24, 33, 60],
};

const CHALDEAN_MAP = {
  A:1,B:2,C:3,D:4,E:5,F:8,G:3,H:5,I:1,J:1,
  K:2,L:3,M:4,N:5,O:7,P:8,Q:1,R:2,S:3,T:4,
  U:6,V:6,W:6,X:5,Y:1,Z:7,
};

const LUCKY_MAP = {
  1: [1, 3, 5, 9], 2: [2, 4, 6, 8], 3: [3, 6, 9],
  4: [4, 8], 5: [5, 1, 3], 6: [6, 3, 9],
  7: [7, 1, 2], 8: [8, 4, 6], 9: [9, 3, 6]
};

const UNLUCKY_MAP = {
  1: [8, 6], 2: [5, 7], 3: [5, 6],
  4: [5, 6], 5: [6, 8], 6: [5, 8],
  7: [5, 8], 8: [5, 1], 9: [5, 8]
};

// ─── NUMBER NORMALIZATION ───────────────────────────────────────────

function normalizePhone(input) {
  if (!input) return "";
  let digits = String(input).replace(/\D/g, "");
  if (digits.length > 10) {
    if (digits.startsWith("91") && digits.length === 12) digits = digits.slice(2);
    else if (digits.startsWith("0") && digits.length === 11) digits = digits.slice(1);
  }
  if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
  if (digits.length !== 10) return "";
  if (digits[0] === "0" || digits[0] === "1") return "";
  return digits;
}

function getDedupKey(normalized) {
  return normalized.length >= 6 ? normalized.slice(-6) : normalized;
}

function getHash(normalized) {
  let hash = 0;
  for (let i = 0; i < normalized.length; i++) {
    hash = ((hash << 5) - hash + normalized.charCodeAt(i)) | 0;
  }
  return "h_" + Math.abs(hash).toString(36);
}

function computeRoot(digits) {
  let sum = 0;
  for (const d of digits) sum += parseInt(d, 10);
  while (sum > 9) {
    sum = String(sum).split("").reduce((s, d) => s + parseInt(d, 10), 0);
  }
  return sum;
}

function computeCompound(digits) {
  return digits.split("").reduce((s, d) => s + parseInt(d, 10), 0);
}

function computeSingleTotal(n) {
  var sum = n;
  while (sum > 9) {
    sum = String(sum).split('').reduce(function(a, b) { return a + Number(b); }, 0);
  }
  return sum;
}

function getRandomPricing(totalStr) {
  var total = parseInt(totalStr, 10);
  var price = Math.floor(Math.random() * (5099 - 2399 + 1)) + 2399;
  var priceStr = String(price);
  var priceTotal = 0;
  for (var i = 0; i < priceStr.length; i++) {
    priceTotal += parseInt(priceStr[i], 10);
  }
  var singleTotal = computeSingleTotal(priceTotal);
  if (singleTotal === 3 || singleTotal === 5) {
    return price;
  }
  return 2399;
}

function getMobileRoot(numStr) {
  const digits = numStr.replace(/\D/g, "").split("").map(Number);
  const last10 = digits.length > 10 ? digits.slice(-10) : digits;
  const sum = last10.reduce((s, d) => s + d, 0);
  return reduceToSingle(sum);
}

function getMobileTotal(numStr) {
  const digits = numStr.replace(/\D/g, "").split("").map(Number);
  const last10 = digits.length > 10 ? digits.slice(-10) : digits;
  return last10.reduce((s, d) => s + d, 0);
}

function computeChaldean(name) {
  let total = 0;
  const upper = name.toUpperCase();
  for (let i = 0; i < upper.length; i++) {
    const ch = upper[i];
    if (CHALDEAN_MAP[ch] !== undefined) total += CHALDEAN_MAP[ch];
  }
  let single = total;
  while (single > 9) {
    single = String(single).split("").reduce((s, d) => s + parseInt(d, 10), 0);
  }
  return { total, single };
}

function reduceToSingle(n) {
  while (n > 9 && n !== 11 && n !== 22 && n !== 33 && n !== 44) {
    n = Math.floor(n / 10) + (n % 10);
  }
  return n;
}

// ─── FREE/PAID NUMBER CLASSIFICATION ────────────────────────────────

function isFreeNumber(number) {
  const normalized = normalizePhone(number);
  if (!normalized) return false;
  if (normalized.includes("0")) return true;
  if (normalized.startsWith("7090")) return true;
  const last6 = normalized.slice(-6);
  if (last6.includes("0")) return true;
  return false;
}

function getNumberClassification(number) {
  const normalized = normalizePhone(number);
  if (!normalized) return { isFree: false, reason: "invalid" };
  if (normalized.includes("0")) {
    return { isFree: true, reason: "contains_zero" };
  }
  if (normalized.startsWith("7090")) {
    return { isFree: true, reason: "blocked_prefix_7090" };
  }
  const last6 = normalized.slice(-6);
  if (last6.includes("0")) {
    return { isFree: true, reason: "zero_in_last_6" };
  }
  return { isFree: false, reason: "paid" };
}

// ─── SHEET HELPERS ──────────────────────────────────────────────────

function getSheet(name) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    if (name === SHEET_NUMBERS) {
      sheet.getRange(1, 1, 1, HEADERS_NUMBERS.length).setValues([HEADERS_NUMBERS]);
      sheet.setFrozenRows(1);
    } else if (name === SHEET_FREE_NUMBERS) {
      sheet.getRange(1, 1, 1, HEADERS_FREE.length).setValues([HEADERS_FREE]);
      sheet.setFrozenRows(1);
    } else if (name === SHEET_PAID_NUMBERS) {
      sheet.getRange(1, 1, 1, HEADERS_PAID.length).setValues([HEADERS_PAID]);
      sheet.setFrozenRows(1);
    } else if (name === SHEET_CUSTOMERS) {
      sheet.getRange(1, 1, 1, HEADERS_CUSTOMERS.length).setValues([HEADERS_CUSTOMERS]);
      sheet.setFrozenRows(1);
    } else if (name === SHEET_REPORTS) {
      sheet.getRange(1, 1, 1, HEADERS_REPORTS.length).setValues([HEADERS_REPORTS]);
      sheet.setFrozenRows(1);
    } else if (name === SHEET_TRANSACTIONS) {
      sheet.getRange(1, 1, 1, HEADERS_TRANSACTIONS.length).setValues([HEADERS_TRANSACTIONS]);
      sheet.setFrozenRows(1);
    } else if (name === SHEET_HEALTH) {
      sheet.getRange(1, 1, 1, HEADERS_HEALTH.length).setValues([HEADERS_HEALTH]);
      sheet.setFrozenRows(1);
    } else if (name === SHEET_WEBSITE_VISITORS) {
      sheet.getRange(1, 1, 1, HEADERS_WEBSITE_VISITORS.length).setValues([HEADERS_WEBSITE_VISITORS]);
      sheet.setFrozenRows(1);
    }
  }
  return sheet;
}

function logHealth(action, status, details, latencyMs) {
  try {
    const sheet = getSheet(SHEET_HEALTH);
    sheet.appendRow([new Date().toISOString(), action, status, details, latencyMs || 0]);
  } catch (e) {}
}

// ─── NUMBER CACHE ───────────────────────────────────────────────────

function getExistingNumbers() {
  const cache = CacheService.getScriptCache();
  const countStr = cache.get("existing_numbers_v5_count");
  if (countStr) {
    try {
      const count = parseInt(countStr);
      const CHUNK_SIZE = 500;
      const numChunks = Math.ceil(count / CHUNK_SIZE);
      const all = [];
      for (let c = 0; c < numChunks; c++) {
        const chunkStr = cache.get("existing_numbers_v5_" + c);
        if (!chunkStr) return null;
        all.push(...JSON.parse(chunkStr));
      }
      if (all.length === count) return all;
    } catch (e) {}
  }

  const sheet = getSheet(SHEET_NUMBERS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return [];

  const data = sheet.getRange(2, 2, lastRow - 1, 2).getValues();
  const existing = data.map((row, i) => ({
    number: String(row[0]),
    normalized: normalizePhone(row[0]),
    dedupKey: getDedupKey(normalizePhone(row[0])),
    hash: row[1] || "",
    row: i + 2,
  }));

  try {
    const CHUNK_SIZE = 500;
    for (let i = 0; i < existing.length; i += CHUNK_SIZE) {
      const chunk = existing.slice(i, i + CHUNK_SIZE);
      cache.put("existing_numbers_v5_" + (i / CHUNK_SIZE), JSON.stringify(chunk), 60);
    }
    cache.put("existing_numbers_v5_count", String(existing.length), 60);
  } catch (e) {}
  return existing;
}

function clearNumberCache() {
  const cache = CacheService.getScriptCache();
  cache.remove("existing_numbers_v5_count");
  for (let i = 0; i < 20; i++) {
    cache.remove("existing_numbers_v5_" + i);
  }
}

// ─── NUMBER STATISTICS ──────────────────────────────────────────────

function getNumberStatistics() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get("number_stats");
  if (cached) {
    try { return JSON.parse(cached); } catch (e) {}
  }

  const mainSheet = getSheet(SHEET_NUMBERS);
  const totalNumbers = Math.max(0, mainSheet.getLastRow() - 1);
  let freeNumbers = 0;
  let paidNumbers = 0;
  let lastUpdated = "never";

  if (totalNumbers > 0) {
    const numData = mainSheet.getRange(2, 1, totalNumbers, HEADERS_NUMBERS.length).getValues();
    for (let i = 0; i < numData.length; i++) {
      const numStr = String(numData[i][1] || "").trim();
      if (!numStr) continue;
      const cls = getNumberClassification(numStr);
      if (cls.isFree) freeNumbers++;
      else paidNumbers++;
    }
    const lastRow = mainSheet.getLastRow();
    if (lastRow > 1) {
      const lastUpdatedCell = mainSheet.getRange(lastRow, 10).getValue();
      if (lastUpdatedCell) {
        lastUpdated = new Date(lastUpdatedCell).toLocaleString();
      }
    }
  }

  const stats = {
    totalNumbers,
    freeNumbers,
    paidNumbers,
    lastUpdated,
    timestamp: new Date().toISOString()
  };

  try {
    cache.put("number_stats", JSON.stringify(stats), 60);
  } catch (e) {}
  return stats;
}

// ─── CUSTOMER OPERATIONS ────────────────────────────────────────────

function getCustomerById(customerId) {
  const sheet = getSheet(SHEET_CUSTOMERS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return null;
  const data = sheet.getRange(2, 1, lastRow - 1, HEADERS_CUSTOMERS.length).getValues();
  for (let i = 0; i < data.length; i++) {
    if (String(data[i][0]) === customerId) {
      return {
        id: data[i][0],
        name: data[i][1],
        gender: data[i][2],
        dob: data[i][3],
        day: Number(data[i][4]),
        month: Number(data[i][5]),
        year: Number(data[i][6]),
        pincode: data[i][7],
        whatsapp: data[i][8],
        createdAt: data[i][9],
        status: data[i][10],
        notes: data[i][11],
        lastContacted: data[i][12],
        followUpCount: Number(data[i][13]) || 0,
        followUpStage: data[i][14] || "fresh",
        followUpDate: data[i][15] || "",
      };
    }
  }
  return null;
}

function updateCustomer(customerId, updates) {
  const sheet = getSheet(SHEET_CUSTOMERS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return null;
  const data = sheet.getRange(2, 1, lastRow - 1, HEADERS_CUSTOMERS.length).getValues();
  for (let i = 0; i < data.length; i++) {
    if (String(data[i][0]) === customerId) {
      const rowNum = i + 2;
      if (updates.name !== undefined) sheet.getRange(rowNum, 2, 1, 1).setValue(updates.name);
      if (updates.gender !== undefined) sheet.getRange(rowNum, 3, 1, 1).setValue(updates.gender);
      if (updates.dob !== undefined) sheet.getRange(rowNum, 4, 1, 1).setValue(updates.dob);
      if (updates.day !== undefined) sheet.getRange(rowNum, 5, 1, 1).setValue(updates.day);
      if (updates.month !== undefined) sheet.getRange(rowNum, 6, 1, 1).setValue(updates.month);
      if (updates.year !== undefined) sheet.getRange(rowNum, 7, 1, 1).setValue(updates.year);
      if (updates.pincode !== undefined) sheet.getRange(rowNum, 8, 1, 1).setValue(updates.pincode);
      if (updates.whatsapp !== undefined) sheet.getRange(rowNum, 9, 1, 1).setValue(updates.whatsapp);
      if (updates.status !== undefined) sheet.getRange(rowNum, 11, 1, 1).setValue(updates.status);
      if (updates.notes !== undefined) sheet.getRange(rowNum, 12, 1, 1).setValue(updates.notes);
      if (updates.lastContacted !== undefined) sheet.getRange(rowNum, 13, 1, 1).setValue(updates.lastContacted);
      if (updates.followUpCount !== undefined) sheet.getRange(rowNum, 14, 1, 1).setValue(updates.followUpCount);
      if (updates.followUpStage !== undefined) sheet.getRange(rowNum, 15, 1, 1).setValue(updates.followUpStage);
      if (updates.followUpDate !== undefined) sheet.getRange(rowNum, 16, 1, 1).setValue(updates.followUpDate);
      return getCustomerById(customerId);
    }
  }
  return null;
}

function deleteCustomer(customerId) {
  const sheet = getSheet(SHEET_CUSTOMERS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return false;
  const data = sheet.getRange(2, 1, lastRow - 1, HEADERS_CUSTOMERS.length).getValues();
  for (let i = 0; i < data.length; i++) {
    if (String(data[i][0]) === customerId) {
      sheet.deleteRow(i + 2);
      return true;
    }
  }
  return false;
}

// ─── NUMBER OPERATIONS ──────────────────────────────────────────────

function deleteNumber(sheetName, rowNumber) {
  const sheet = getSheet(sheetName);
  const lastRow = sheet.getLastRow();
  if (rowNumber >= 2 && rowNumber <= lastRow) {
    sheet.deleteRow(rowNumber);
    clearNumberCache();
    return true;
  }
  return false;
}

function deleteNumberByValue(numberValue) {
  const normalized = normalizePhone(numberValue);
  const mainSheet = getSheet(SHEET_NUMBERS);
  let lastRow = mainSheet.getLastRow();
  if (lastRow > 1) {
    const data = mainSheet.getRange(2, 2, lastRow - 1, 1).getValues();
    for (let i = 0; i < data.length; i++) {
      if (normalizePhone(String(data[i][0])) === normalized) {
        mainSheet.deleteRow(i + 2);
        clearNumberCache();
        return { deleted: true, sheet: SHEET_NUMBERS };
      }
    }
  }
  const freeSheet = getSheet(SHEET_FREE_NUMBERS);
  lastRow = freeSheet.getLastRow();
  if (lastRow > 1) {
    const data = freeSheet.getRange(2, 2, lastRow - 1, 1).getValues();
    for (let i = 0; i < data.length; i++) {
      if (normalizePhone(String(data[i][0])) === normalized) {
        freeSheet.deleteRow(i + 2);
        clearNumberCache();
        return { deleted: true, sheet: SHEET_FREE_NUMBERS };
      }
    }
  }
  const paidSheet = getSheet(SHEET_PAID_NUMBERS);
  lastRow = paidSheet.getLastRow();
  if (lastRow > 1) {
    const data = paidSheet.getRange(2, 2, lastRow - 1, 1).getValues();
    for (let i = 0; i < data.length; i++) {
      if (normalizePhone(String(data[i][0])) === normalized) {
        paidSheet.deleteRow(i + 2);
        clearNumberCache();
        return { deleted: true, sheet: SHEET_PAID_NUMBERS };
      }
    }
  }
  return { deleted: false, sheet: null };
}

// ─── AUTO-CLEANUP SYSTEM ────────────────────────────────────────────

function autoCleanupNumbers() {
  const now = new Date();
  let totalDeleted = 0;
  const cleanupIntervals = [7, 14, 21];
  for (const days of cleanupIntervals) {
    const cutoffDate = new Date(now);
    cutoffDate.setDate(cutoffDate.getDate() - days);
    totalDeleted += cleanupSheet(SHEET_NUMBERS, cutoffDate);
    totalDeleted += cleanupSheet(SHEET_FREE_NUMBERS, cutoffDate);
    totalDeleted += cleanupSheet(SHEET_PAID_NUMBERS, cutoffDate);
  }
  clearNumberCache();
  logHealth("auto_cleanup", "ok", `Deleted ${totalDeleted} numbers older than 21 days`);
  return { deleted: totalDeleted, timestamp: now.toISOString() };
}

function cleanupSheet(sheetName, cutoffDate) {
  const sheet = getSheet(sheetName);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return 0;
  const dates = sheet.getRange(2, 9, lastRow - 1, 1).getValues();
  let deletedCount = 0;
  for (let i = dates.length - 1; i >= 0; i--) {
    const dateValue = dates[i][0];
    if (dateValue) {
      const date = new Date(dateValue);
      if (date < cutoffDate) {
        sheet.deleteRow(i + 2);
        deletedCount++;
      }
    }
  }
  return deletedCount;
}

// ─── VALIDATION-BASED CLEANUP ───────────────────────────────────────

function validateAndCleanupNumbers() {
  const sheet = getSheet(SHEET_NUMBERS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return { deleted: 0, reason: "No numbers" };
  const numbers = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
  let deletedCount = 0;
  const blocked6Pairs = ["16", "26", "36", "46", "56", "76", "86"];
  for (let i = numbers.length - 1; i >= 0; i--) {
    const num = String(numbers[i][0] || "").trim();
    if (!num || num.length !== 10) { sheet.deleteRow(i + 2); deletedCount++; continue; }
    let shouldDelete = false;
    let reason = "";
    if (num.indexOf("7090") !== -1) { shouldDelete = true; reason = "Contains 7090"; }
    if (!shouldDelete) { const last6 = num.slice(-6); if (last6.indexOf("0") !== -1) { shouldDelete = true; reason = "Zero in last 6 digits"; } }
    if (!shouldDelete) {
      for (let pi = 0; pi <= num.length - 2; pi++) {
        const pair = num.slice(pi, pi + 2);
        if (blocked6Pairs.indexOf(pair) !== -1) {
          if (pair === "96" && pi === num.length - 2) continue;
          if (pair === "96" && pi + 2 < num.length && num[pi + 2] === "9") continue;
          if (pair === "69" && pi > 0 && num[pi - 1] === "9") continue;
          shouldDelete = true; reason = "Blocked pair " + pair; break;
        }
      }
    }
    if (!shouldDelete) { const root = computeRoot(num); if ([1, 3, 5, 6].indexOf(root) === -1) { shouldDelete = true; reason = "Total " + root + " not in [1,3,5,6]"; } }
    if (!shouldDelete) { if (num.indexOf("2") !== -1 || num.indexOf("4") !== -1 || num.indexOf("8") !== -1) { shouldDelete = true; reason = "Contains 2/4/8"; } }
    if (!shouldDelete) { if (num.indexOf("00") !== -1) { shouldDelete = true; reason = "Contains 00"; } }
    if (shouldDelete) { sheet.deleteRow(i + 2); deletedCount++; }
  }
  clearNumberCache();
  logHealth("validate_cleanup", "ok", "Removed " + deletedCount + " invalid numbers");
  return { deleted: deletedCount, timestamp: new Date().toISOString() };
}

// ─── FOLLOW-UP SYSTEM ───────────────────────────────────────────────

function calculateFollowUpStage(createdAt) {
  const created = new Date(createdAt);
  const now = new Date();
  const diffMs = now - created;
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  if (diffDays < 2) return FOLLOW_UP_STAGES.FRESH;
  if (diffDays < 5) return FOLLOW_UP_STAGES.STAGE_2;
  if (diffDays < 7) return FOLLOW_UP_STAGES.STAGE_5;
  if (diffDays < 14) return FOLLOW_UP_STAGES.STAGE_7;
  return FOLLOW_UP_STAGES.STAGE_14;
}

function calculateFollowUpDate(createdAt) {
  const created = new Date(createdAt);
  const stage = calculateFollowUpStage(createdAt);
  const nextFollowUp = new Date(created);
  nextFollowUp.setDate(nextFollowUp.getDate() + stage.days);
  return nextFollowUp.toISOString();
}

// ─── TRANSACTION OPERATIONS ─────────────────────────────────────────

function saveTransaction(data) {
  const sheet = getSheet(SHEET_TRANSACTIONS);
  const id = "TXN_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  const now = new Date().toISOString();
  sheet.appendRow([
    id, data.orderId || "", data.paymentId || "",
    data.customerName || "", data.customerEmail || "", data.customerPhone || "",
    data.amount || 0, data.currency || "INR", data.status || "pending",
    data.serviceType || "", data.serviceDetails || "", now, "", data.notes || ""
  ]);
  return id;
}

function verifyTransaction(paymentId) {
  const sheet = getSheet(SHEET_TRANSACTIONS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return false;
  const data = sheet.getRange(2, 1, lastRow - 1, HEADERS_TRANSACTIONS.length).getValues();
  for (let i = 0; i < data.length; i++) {
    if (String(data[i][2]) === paymentId) {
      sheet.getRange(i + 2, 9, 1, 1).setValue("verified");
      sheet.getRange(i + 2, 13, 1, 1).setValue(new Date().toISOString());
      return true;
    }
  }
  return false;
}

function getTransactions() {
  const sheet = getSheet(SHEET_TRANSACTIONS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return [];
  const data = sheet.getRange(2, 1, lastRow - 1, HEADERS_TRANSACTIONS.length).getValues();
  return data.map(row => ({
    id: row[0], orderId: row[1], paymentId: row[2], customerName: row[3],
    customerEmail: row[4], customerPhone: row[5], amount: row[6],
    currency: row[7], status: row[8], serviceType: row[9],
    serviceDetails: row[10], createdAt: row[11], verifiedAt: row[12], notes: row[13]
  }));
}

// ─── NUMBER DESIGN ENGINE ───────────────────────────────────────────

function designNumberLastDigits(day, month, year) {
  const moolankh = reduceToSingle(day);
  const bhagyank = reduceToSingle(
    String(day).padStart(2, "0").split("").reduce((s, d) => s + parseInt(d, 10), 0) +
    String(month).padStart(2, "0").split("").reduce((s, d) => s + parseInt(d, 10), 0) +
    String(year).split("").reduce((s, d) => s + parseInt(d, 10), 0)
  );
  const luckyInfo = LUCKY_MAP[moolankh] || [1, 3, 5];
  const unluckyInfo = UNLUCKY_MAP[moolankh] || [6, 8];
  const dobFreq = {};
  for (let i = 1; i <= 9; i++) dobFreq[i] = 0;
  for (const ch of (String(day).padStart(2, "0") + String(month).padStart(2, "0") + String(year))) {
    const d = parseInt(ch);
    if (d >= 1 && d <= 9) dobFreq[d]++;
  }
  const sortedFreq = Object.keys(dobFreq).map(Number).filter(k => k >= 1).sort((a, b) => {
    if (dobFreq[b] !== dobFreq[a]) return dobFreq[b] - dobFreq[a];
    return b - a;
  });
  const king = sortedFreq[0] || moolankh;
  const queen = sortedFreq[1] || bhagyank;
  const lastDigits = [];
  for (const lucky of luckyInfo) { if (lastDigits.length < 4) lastDigits.push(lucky); }
  const friendlyNumbers = FRIENDLY[moolankh] || [1, 3, 5];
  for (const friendly of friendlyNumbers) { if (!lastDigits.includes(friendly) && lastDigits.length < 4) lastDigits.push(friendly); }
  if (!lastDigits.includes(king) && lastDigits.length < 4) lastDigits.push(king);
  if (!lastDigits.includes(queen) && lastDigits.length < 4) lastDigits.push(queen);
  while (lastDigits.length < 4) {
    for (let d = 1; d <= 9; d++) {
      if (!lastDigits.includes(d) && !unluckyInfo.includes(d)) { lastDigits.push(d); break; }
    }
  }
  const combinations = [];
  combinations.push({ digits: lastDigits.slice(0, 4), type: "lucky", score: calculateCombinationScore(lastDigits.slice(0, 4), moolankh, bhagyank, king, queen) });
  const kingQueenDigits = [king, queen, ...luckyInfo.slice(0, 2)];
  combinations.push({ digits: kingQueenDigits.slice(0, 4), type: "king-queen", score: calculateCombinationScore(kingQueenDigits.slice(0, 4), moolankh, bhagyank, king, queen) });
  const balancedDigits = [moolankh, bhagyank, ...luckyInfo.slice(0, 2)];
  combinations.push({ digits: balancedDigits.slice(0, 4), type: "balanced", score: calculateCombinationScore(balancedDigits.slice(0, 4), moolankh, bhagyank, king, queen) });
  combinations.sort((a, b) => b.score - a.score);
  return {
    moolankh, bhagyank, king, queen,
    luckyNumbers: luckyInfo, unluckyNumbers: unluckyInfo,
    recommendedLast4: combinations[0].digits.join(""),
    combinations: combinations, digits: combinations[0].digits
  };
}

function calculateCombinationScore(digits, moolankh, bhagyank, king, queen) {
  let score = 0;
  for (const d of digits) {
    if (LUCKY_ROOTS.includes(d)) score += 10;
    if (d === moolankh) score += 15;
    if (d === bhagyank) score += 12;
    if (d === king) score += 10;
    if (d === queen) score += 8;
  }
  for (let i = 0; i < digits.length - 1; i++) {
    const pair = String(digits[i]) + String(digits[i + 1]);
    if (AVOID_PAIRS.includes(pair)) score -= 20;
    if (GOOD_PAIRS.includes(pair)) score += 10;
    if (HIGHLIGHT_PAIRS.includes(pair)) score += 15;
  }
  const total = digits.reduce((a, b) => a + b, 0);
  const single = reduceToSingle(total);
  if (LUCKY_ROOTS.includes(single)) score += 15;
  if (single === moolankh) score += 20;
  return score;
}

// ─── COMPATIBILITY ENGINE ───────────────────────────────────────────

function generateMobileDobCompatibilityReport(dobInput, mobileNumber) {
  const { day, month, year } = dobInput;
  const digits = mobileNumber.replace(/\D/g, "").split("").map(Number);
  const moolankh = reduceToSingle(day);
  const bhagyank = reduceToSingle(
    String(day).padStart(2, "0").split("").reduce((s, d) => s + parseInt(d, 10), 0) +
    String(month).padStart(2, "0").split("").reduce((s, d) => s + parseInt(d, 10), 0) +
    String(year).split("").reduce((s, d) => s + parseInt(d, 10), 0)
  );
  const luckyInfo = LUCKY_MAP[moolankh] || [1, 3, 5];
  const unluckyInfo = UNLUCKY_MAP[moolankh] || [6, 8];
  const luckyNumbers = [...new Set([...luckyInfo, ...(LUCKY_MAP[bhagyank] || [])])];
  const unluckyNumbers = [...new Set([...unluckyInfo, ...(UNLUCKY_MAP[bhagyank] || [])])];
  const mobileTotal = digits.reduce((a, b) => a + b, 0);
  const mobileSingle = reduceToSingle(mobileTotal);
  const lastFour = mobileNumber.slice(-4);
  const lastFourDigits = lastFour.split("").map(Number);
  const lastFourTotal = lastFourDigits.reduce((a, b) => a + b, 0);
  const lastFourSingle = reduceToSingle(lastFourTotal);
  const scores = { mobileStrength: 0, communicationEnergy: 0, financialSupport: 0, careerSupport: 0, relationshipSupport: 0, healthEnergy: 0, stability: 0, successPotential: 0, planetaryHarmony: 0, luckyAlignment: 0 };
  // Score calculations...
  if (mobileSingle === moolankh) scores.mobileStrength = 95;
  else if (luckyNumbers.includes(mobileSingle)) scores.mobileStrength = 85;
  else if (unluckyNumbers.includes(mobileSingle)) scores.mobileStrength = 25;
  else scores.mobileStrength = 50;
  if ([5, 3, 6].includes(mobileSingle)) scores.communicationEnergy = 85;
  else if ([1, 9].includes(mobileSingle)) scores.communicationEnergy = 70;
  else scores.communicationEnergy = 50;
  if ([5, 6, 8, 9].includes(mobileSingle)) scores.financialSupport = 85;
  else if ([1, 3].includes(mobileSingle)) scores.financialSupport = 70;
  else scores.financialSupport = 50;
  if ([1, 4, 5, 8, 9].includes(mobileSingle)) scores.careerSupport = 80;
  else if ([3, 6].includes(mobileSingle)) scores.careerSupport = 65;
  else scores.careerSupport = 50;
  if ([2, 3, 5, 6, 9].includes(mobileSingle)) scores.relationshipSupport = 80;
  else if ([1, 7].includes(mobileSingle)) scores.relationshipSupport = 60;
  else scores.relationshipSupport = 50;
  if ([1, 3, 5, 9].includes(mobileSingle)) scores.healthEnergy = 75;
  else if ([4, 8].includes(mobileSingle)) scores.healthEnergy = 55;
  else scores.healthEnergy = 60;
  if (mobileSingle === moolankh && mobileSingle === bhagyank) scores.stability = 95;
  else if (mobileSingle === moolankh) scores.stability = 80;
  else scores.stability = 60;
  if (luckyNumbers.includes(mobileSingle)) scores.successPotential = 85;
  else if (mobileSingle === moolankh) scores.successPotential = 80;
  else scores.successPotential = 50;
  if (mobileSingle === moolankh) scores.planetaryHarmony = 90;
  else if (luckyNumbers.includes(mobileSingle)) scores.planetaryHarmony = 75;
  else scores.planetaryHarmony = 50;
  if (luckyNumbers.includes(mobileSingle)) scores.luckyAlignment = 90;
  else if (unluckyNumbers.includes(mobileSingle)) scores.luckyAlignment = 20;
  else scores.luckyAlignment = 50;
  const weights = [0.15, 0.12, 0.12, 0.12, 0.10, 0.10, 0.10, 0.10, 0.09, 0.10];
  const scoreValues = Object.values(scores);
  let overallScore = 0;
  for (let i = 0; i < weights.length; i++) overallScore += scoreValues[i] * weights[i];
  overallScore = Math.round(overallScore);
  let overallGrade = "Poor";
  if (overallScore >= 85) overallGrade = "Excellent";
  else if (overallScore >= 75) overallGrade = "Very Good";
  else if (overallScore >= 65) overallGrade = "Good";
  else if (overallScore >= 50) overallGrade = "Average";
  else if (overallScore >= 35) overallGrade = "Needs Improvement";
  const analysis = {
    luckyNumberAlignment: `Mobile Total ${mobileTotal} → Single ${mobileSingle}. ${luckyNumbers.includes(mobileSingle) ? `Matches your lucky number — excellent support!` : unluckyNumbers.includes(mobileSingle) ? `Matches your unlucky number — needs attention.` : `Neutral alignment with your profile.`}`,
    unluckyDetection: unluckyNumbers.includes(mobileSingle) ? `ALERT: Mobile vibration ${mobileSingle} is unlucky for your profile.` : `Good — no unlucky number conflicts detected.`,
    lastFourDigits: `Last 4 digits: ${lastFour} (Total: ${lastFourTotal}, Single: ${lastFourSingle}) — ${luckyNumbers.includes(lastFourSingle) ? 'Lucky last four!' : 'Standard energy.'}`
  };
  const recommendations = {
    keepCurrentNumber: overallScore >= 65,
    lastFourDigitQuality: (luckyNumbers.includes(lastFourSingle) ? "Excellent" : lastFourSingle === moolankh ? "Good" : unluckyNumbers.includes(lastFourSingle) ? "Weak" : "Average"),
    expertOpinion: '', suggestions: []
  };
  if (overallScore >= 80) { recommendations.expertOpinion = `EXCELLENT MATCH: This mobile number ${mobileNumber} is highly compatible with your DOB. The vibration ${mobileSingle} aligns perfectly with your Driver ${moolankh} and supports your destiny path.`; recommendations.suggestions.push('Your mobile number is well-aligned — keep it!'); }
  else if (overallScore >= 65) { recommendations.expertOpinion = `GOOD MATCH: This mobile number has solid compatibility with your DOB. The vibration ${mobileSingle} works well with your profile.`; }
  else if (overallScore >= 50) { recommendations.expertOpinion = `AVERAGE MATCH: This mobile number has moderate compatibility. The vibration ${mobileSingle} has some conflicts with your DOB profile.`; recommendations.suggestions.push('Consider getting a secondary number with vibration closer to your lucky numbers'); }
  else { recommendations.expertOpinion = `NEEDS IMPROVEMENT: This mobile number ${mobileNumber} has weak compatibility with your DOB.`; recommendations.suggestions.push('Consider changing to a number with vibration closer to your lucky numbers'); }
  return {
    dob: dobInput, mobileNumber,
    dobAnalysis: { driverNumber: moolankh, destinyNumber: bhagyank, luckyNumbers, unluckyNumbers },
    mobileAnalysis: { total: mobileTotal, singleDigit: mobileSingle, presentDigits: [...new Set(digits)], missingDigits: [1,2,3,4,5,6,7,8,9].filter(d => !digits.includes(d)) },
    overallScore, overallGrade, scores, analysis, recommendations
  };
}

// ─── REPORT OPERATIONS ──────────────────────────────────────────────

function saveReport(customerId, customerName, mobileNumber, reportType, overallScore, grade, reportData) {
  const sheet = getSheet(SHEET_REPORTS);
  const id = "RPT_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  const now = new Date().toISOString();
  sheet.appendRow([id, customerId, customerName, mobileNumber, reportType, overallScore, grade, now, "", JSON.stringify(reportData)]);
  return id;
}

function markReportShared(reportId) {
  const sheet = getSheet(SHEET_REPORTS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return false;
  const data = sheet.getRange(2, 1, lastRow - 1, HEADERS_REPORTS.length).getValues();
  for (let i = 0; i < data.length; i++) {
    if (String(data[i][0]) === reportId) { sheet.getRange(i + 2, 9, 1, 1).setValue(new Date().toISOString()); return true; }
  }
  return false;
}

// ─── SHARE OPERATIONS ───────────────────────────────────────────────

function generateReportShareUrl(customer, report, mobileNumber) {
  const greeting = `🌟 *HANKITH NUMEROLOGY* 🌟\n\n`;
  const hello = `Dear *${customer.name}*,\n\n`;
  const message = `✨ Your Mobile + DOB Compatibility Report is ready!\n\n` +
    `📱 *Mobile Number:* ${mobileNumber}\n` +
    `📅 *Date of Birth:* ${customer.dob}\n` +
    `⭐ *Compatibility Score:* ${report.overallScore}/100 (${report.overallGrade})\n\n` +
    `🔮 *Key Findings:*\n` +
    `• Driver Number: ${report.dobAnalysis.driverNumber} (${PLANET_MAP[report.dobAnalysis.driverNumber]})\n` +
    `• Destiny Number: ${report.dobAnalysis.destinyNumber} (${PLANET_MAP[report.dobAnalysis.destinyNumber]})\n` +
    `• Mobile Vibration: ${report.mobileAnalysis.singleDigit} (${PLANET_MAP[report.mobileAnalysis.singleDigit]})\n\n` +
    `💡 *Expert Opinion:*\n${report.recommendations.expertOpinion}\n\n` +
    `📞 *Contact us for detailed analysis and personalized recommendations.*\n\n` +
    `---\n*Hankith Numerology*\n*Unlock Your Destiny Through Numbers*`;
  const whatsappUrl = `https://wa.me/91${customer.whatsapp}?text=${encodeURIComponent(greeting + hello + message)}`;
  return { whatsappUrl, message: greeting + hello + message };
}

function generatePincodeShareUrl(customer, agentPhone) {
  const message = `*HANKITH NUMEROLOGY - SIM Delivery Check*\n\n` +
    `Pincode: *${customer.pincode}*\nCustomer ID: ${customer.id}\n\n` +
    `Please check SIM delivery availability for this pincode.\nOr suggest nearby pincodes if not available.\n\n---\nHANKITH NUMEROLOGY`;
  const whatsappUrl = `https://wa.me/91${agentPhone}?text=${encodeURIComponent(message)}`;
  return { whatsappUrl, message };
}

// ─── SUGGESTION ENGINE ──────────────────────────────────────────────

function suggestNumbersForCustomer(customer, poolNumbers) {
  var day = customer.day, month = customer.month, year = customer.year, customerName = customer.name || "";
  var moolankh = reduceToSingle(day);
  var bhagyank = reduceToSingle(
    String(day).padStart(2, "0").split("").reduce(function(s, d) { return s + parseInt(d, 10); }, 0) +
    String(month).padStart(2, "0").split("").reduce(function(s, d) { return s + parseInt(d, 10); }, 0) +
    String(year).split("").reduce(function(s, d) { return s + parseInt(d, 10); }, 0)
  );
  var dobFreq = {}; for (var i = 1; i <= 9; i++) dobFreq[i] = 0;
  for (var ch of (String(day).padStart(2, "0") + String(month).padStart(2, "0") + String(year))) { var d = parseInt(ch); if (d >= 1 && d <= 9) dobFreq[d]++; }
  var missingFromDob = [1,2,3,4,5,6,7,8,9].filter(function(d) { return dobFreq[d] === 0; });
  var firstNameChaldean = { total: 0, single: 0 };
  if (customerName.trim()) { var parts = customerName.trim().split(/\s+/); firstNameChaldean = computeChaldean(parts[0] || ""); }
  var sortedFreq = Object.keys(dobFreq).map(Number).filter(function(k) { return k >= 1; }).sort(function(a, b) { if (dobFreq[b] !== dobFreq[a]) return dobFreq[b] - dobFreq[a]; return b - a; });
  var king = sortedFreq[0] || moolankh, queen = sortedFreq[1] || bhagyank;
  var prohibitedRoots = [];
  if (king === 8 || queen === 8 || moolankh === 8 || bhagyank === 8) prohibitedRoots.push(1);
  if (king === 6 || queen === 6 || moolankh === 6 || bhagyank === 6) prohibitedRoots.push(3);
  if (king === 3 || queen === 3 || moolankh === 3 || bhagyank === 3) prohibitedRoots.push(6);
  var luckyNumbers = LUCKY_MAP[moolankh] || [1, 3, 5, 9], unluckyNumbers = UNLUCKY_MAP[moolankh] || [6, 8];
  var vedicPositions = [[4,9,2],[3,5,7],[8,1,6]];
  var dobAllDigits = (String(day).padStart(2, "0") + String(month).padStart(2, "0") + String(year)).split("").map(Number).filter(function(d) { return d >= 1 && d <= 9; });
  var vedicGrid = [[null,null,null],[null,null,null],[null,null,null]];
  for (var gi = 0; gi < 3; gi++) { for (var gj = 0; gj < 3; gj++) { var posNum = vedicPositions[gi][gj]; var cnt = dobAllDigits.filter(function(d) { return d === posNum; }).length; vedicGrid[gi][gj] = cnt > 0 ? cnt : null; } }
  function gridDisplayString(grid, positions) { var result = []; for (var gi2 = 0; gi2 < 3; gi2++) { for (var gj2 = 0; gj2 < 3; gj2++) { var num = positions[gi2][gj2]; var cnt = grid[gi2][gj2] || 0; if (cnt > 0) { var str = ""; for (var k = 0; k < cnt; k++) str += String(num); result.push({ number: num, count: cnt, display: str }); } } } return result; }
  var vedicGridDisplay = gridDisplayString(vedicGrid, vedicPositions);
  var scored = [];
  for (var idx = 0; idx < poolNumbers.length; idx++) {
    var entry = poolNumbers[idx], numStr = String(entry.number), root = getMobileRoot(numStr), total = getMobileTotal(numStr);
    var digits = numStr.replace(/\D/g, "").split("").map(Number);
    var mobileSet = {}; digits.forEach(function(dd) { if (dd >= 1 && dd <= 9) mobileSet[dd] = true; });
    var score = 0, reasons = [], warnings = [], matchLabel = "";
    if (prohibitedRoots.indexOf(root) !== -1) { warnings.push("Root " + root + " (" + PLANET_MAP[root] + ") — BLOCKED by K/Q rule"); score -= 100; }
    if (root === 2 || root === 4 || root === 8) { score -= 40; warnings.push("Root " + root + " (" + PLANET_MAP[root] + ") — AVOID"); }
    var last6 = digits.length >= 6 ? digits.slice(-6) : digits;
    if (last6.indexOf(0) !== -1) { score -= 100; warnings.push("Zero in last 6 digits — BLOCKED"); }
    if (root === moolankh) { score += 35; reasons.push("Root " + root + " (" + PLANET_MAP[root] + ") matches Moolankh"); matchLabel = "Perfect Moolankh"; }
    if (root === bhagyank && bhagyank !== moolankh) { score += 30; reasons.push("Root " + root + " matches Bhagyank " + bhagyank); if (!matchLabel) matchLabel = "Bhagyank Match"; }
    if (root !== moolankh && FRIENDLY[moolankh] && FRIENDLY[moolankh].indexOf(root) !== -1) { score += 20; reasons.push(PLANET_MAP[root] + " friendly to Moolankh"); if (!matchLabel) matchLabel = "Friendly Root"; }
    var filledCount = 0; [1,2,3,4,5,6,7,8,9].forEach(function(dd) { if (dobFreq[dd] === 0 && mobileSet[dd]) filledCount++; });
    if (filledCount > 0) { score += filledCount * 5; reasons.push("Fills " + filledCount + " missing DOB digit(s)"); }
    if (mobileSet[moolankh]) { score += 8; reasons.push("Contains " + moolankh + " (" + PLANET_MAP[moolankh] + ") — King"); }
    if (mobileSet[bhagyank] && bhagyank !== moolankh) { score += 8; reasons.push("Contains " + bhagyank + " (" + PLANET_MAP[bhagyank] + ") — Queen"); }
    if (!matchLabel) matchLabel = score >= 50 ? "Good Match" : score >= 20 ? "Moderate" : "Weak Match";
    if (reasons.length === 0) reasons.push("Available in number pool");
    scored.push({ number: numStr, root: root, compound: total, plan: entry.plan || "---", score: Math.max(0, Math.min(100, score)), matchLabel: matchLabel, reasons: reasons, warnings: warnings });
  }
  var filtered = scored.filter(function(s) { return prohibitedRoots.indexOf(s.root) === -1; });
  filtered.sort(function(a, b) { return b.score - a.score; });
  return {
    customer: { id: customer.id, name: customer.name, dob: customer.dob, day: day, month: month, year: year },
    numerology: { moolankh: moolankh, moolankhPlanet: PLANET_MAP[moolankh], bhagyank: bhagyank, bhagyankPlanet: PLANET_MAP[bhagyank], king: king, kingPlanet: PLANET_MAP[king], queen: queen, queenPlanet: PLANET_MAP[queen], friendlyRoots: FRIENDLY[moolankh] || [], missingFromDob: missingFromDob, vedicGrid: vedicGridDisplay },
    suggestions: { all: filtered },
    totalPool: poolNumbers.length, filteredCount: filtered.length
  };
}

// ══════════════════════════════════════════════════════════════════════
// HANDLERS - doGet
// ══════════════════════════════════════════════════════════════════════

function doGet(e) {
  const lock = LockService.getScriptLock();
  const start = new Date().getTime();
  try {
    lock.tryLock(5000);
    const action = (e.parameter.action || "").toLowerCase();
    const target = e.parameter.target || "numbers";

    if (action === "health" || action === "healthCheck") {
      const stats = getNumberStatistics(); logHealth("health_check", "ok", "Healthy", new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, status: "healthy", version: "5.1.0", stats, uptime: new Date().toISOString() })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "heartbeat") {
      return ContentService.createTextOutput(JSON.stringify({ status: "alive", timestamp: new Date().toISOString() })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "stats") {
      const stats = getNumberStatistics(); logHealth("stats_check", "ok", "Stats retrieved", new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, ...stats })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "check_free") {
      const number = e.parameter.number;
      if (!number) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "number is required" })).setMimeType(ContentService.MimeType.JSON);
      return ContentService.createTextOutput(JSON.stringify({ success: true, classification: getNumberClassification(number) })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "cleanup") {
      const result = autoCleanupNumbers();
      return ContentService.createTextOutput(JSON.stringify({ success: true, ...result })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "validate_cleanup") {
      const result = validateAndCleanupNumbers();
      return ContentService.createTextOutput(JSON.stringify({ success: true, ...result })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "delete_customer") {
      var delId = e.parameter.id; if (!delId) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "id required" })).setMimeType(ContentService.MimeType.JSON);
      var delSheet = getSheet(SHEET_CUSTOMERS); var delLastRow = delSheet.getLastRow();
      if (delLastRow > 1) { var delData = delSheet.getRange(2, 1, delLastRow - 1, 1).getValues(); for (var di = 0; di < delData.length; di++) { if (String(delData[di][0]) === String(delId)) { delSheet.deleteRow(di + 2); logHealth("delete_customer", "ok", "Customer: " + delId, new Date().getTime() - start); return ContentService.createTextOutput(JSON.stringify({ success: true })).setMimeType(ContentService.MimeType.JSON); } } }
      return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "update_customer") {
      var updId = e.parameter.id; if (!updId) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "id required" })).setMimeType(ContentService.MimeType.JSON);
      var updSheet = getSheet(SHEET_CUSTOMERS); var updLastRow = updSheet.getLastRow();
      if (updLastRow > 1) { var updData = updSheet.getRange(2, 1, updLastRow - 1, HEADERS_CUSTOMERS.length).getValues(); for (var ui = 0; ui < updData.length; ui++) { if (String(updData[ui][0]) === String(updId)) { var rowNum = ui + 2; if (e.parameter.status) updSheet.getRange(rowNum, 11).setValue(e.parameter.status); if (e.parameter.lastContactedAt) updSheet.getRange(rowNum, 13).setValue(e.parameter.lastContactedAt); if (e.parameter.followUpCount) updSheet.getRange(rowNum, 14).setValue(parseInt(e.parameter.followUpCount)); if (e.parameter.notes) updSheet.getRange(rowNum, 12).setValue(e.parameter.notes); logHealth("update_customer", "ok", "Customer: " + updId, new Date().getTime() - start); return ContentService.createTextOutput(JSON.stringify({ success: true })).setMimeType(ContentService.MimeType.JSON); } } }
      return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "cleanup_customers") {
      const custSheet = getSheet(SHEET_CUSTOMERS); const custLastRow = custSheet.getLastRow();
      if (custLastRow <= 1) return ContentService.createTextOutput(JSON.stringify({ success: true, deleted: 0, reason: "No customers" })).setMimeType(ContentService.MimeType.JSON);
      const custData = custSheet.getRange(2, 1, custLastRow - 1, HEADERS_CUSTOMERS.length).getValues();
      let deletedCount = 0; const seenPhones = {};
      for (let ci = custData.length - 1; ci >= 0; ci--) { const row = custData[ci]; const cid = String(row[0] || "").trim(); const phone = String(row[8] || "").trim(); if (!cid) { custSheet.deleteRow(ci + 2); deletedCount++; continue; } if (phone) { if (seenPhones[phone] !== undefined) { custSheet.deleteRow(ci + 2); deletedCount++; } else { seenPhones[phone] = true; } } }
      logHealth("cleanup_customers", "ok", "Deleted " + deletedCount + " rows", new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, deleted: deletedCount })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "add_customer") {
      var sheet = getSheet(SHEET_CUSTOMERS); var custId = "CUST_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); var now = new Date().toISOString();
      var name = e.parameter.name || "", gender = e.parameter.gender || "", dob = e.parameter.dob || "", day = parseInt(e.parameter.day) || 0, month = parseInt(e.parameter.month) || 0, year = parseInt(e.parameter.year) || 0, pincode = e.parameter.pincode || "", whatsapp = e.parameter.whatsapp || "", notes = e.parameter.notes || "";
      if (!name || !dob || !whatsapp) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "name, dob, whatsapp required" })).setMimeType(ContentService.MimeType.JSON);
      sheet.appendRow([custId, name, gender, dob, day, month, year, pincode, whatsapp, now, "pending", notes, "", 0, "fresh", calculateFollowUpDate(now)]);
      logHealth("add_customer", "ok", "Customer: " + custId, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, id: custId })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "get_transactions") {
      return ContentService.createTextOutput(JSON.stringify({ success: true, transactions: getTransactions() })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "suggest") {
      var customerId = e.parameter.customer_id; if (!customerId) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "customer_id required" })).setMimeType(ContentService.MimeType.JSON);
      var customer = getCustomerById(customerId); if (!customer) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      var numSheet = getSheet(SHEET_NUMBERS); var numLastRow = numSheet.getLastRow(); var poolNumbers = [];
      if (numLastRow > 1) { var numData = numSheet.getRange(2, 1, numLastRow - 1, HEADERS_NUMBERS.length).getValues(); for (var ni = 0; ni < numData.length; ni++) { var numVal = String(numData[ni][1] || "").trim(); if (numVal && numVal.length >= 10) poolNumbers.push({ number: numVal, plan: String(numData[ni][4] || "---") }); } }
      if (poolNumbers.length === 0) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "No numbers in pool" })).setMimeType(ContentService.MimeType.JSON);
      var result = suggestNumbersForCustomer(customer, poolNumbers); logHealth("suggest_numbers", "ok", "Customer: " + customerId, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, result: result })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "design_number") {
      var customerId = e.parameter.customer_id; if (!customerId) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "customer_id required" })).setMimeType(ContentService.MimeType.JSON);
      var customer = getCustomerById(customerId); if (!customer) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      var design = designNumberLastDigits(customer.day, customer.month, customer.year); logHealth("design_number", "ok", "Customer: " + customerId, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, design: design })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "generate_report") {
      var customerId = e.parameter.customer_id, mobileNumber = e.parameter.mobile_number;
      if (!customerId || !mobileNumber) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "customer_id and mobile_number required" })).setMimeType(ContentService.MimeType.JSON);
      var customer = getCustomerById(customerId); if (!customer) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      var report = generateMobileDobCompatibilityReport({ day: customer.day, month: customer.month, year: customer.year }, mobileNumber);
      var reportId = saveReport(customerId, customer.name, mobileNumber, "mobile-dob", report.overallScore, report.overallGrade, report);
      logHealth("generate_report", "ok", "Customer: " + customerId, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, reportId: reportId, report: report })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "share_report") {
      var customerId = e.parameter.customer_id, mobileNumber = e.parameter.mobile_number, reportId = e.parameter.report_id;
      if (!customerId || !mobileNumber) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "customer_id and mobile_number required" })).setMimeType(ContentService.MimeType.JSON);
      var customer = getCustomerById(customerId); if (!customer) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      var report = generateMobileDobCompatibilityReport({ day: customer.day, month: customer.month, year: customer.year }, mobileNumber);
      var shareData = generateReportShareUrl(customer, report, mobileNumber);
      if (reportId) markReportShared(reportId);
      logHealth("share_report", "ok", "Customer: " + customerId, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, whatsappUrl: shareData.whatsappUrl, message: shareData.message })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "share_pincode") {
      var customerId = e.parameter.customer_id, agentPhone = e.parameter.agent_phone;
      if (!customerId || !agentPhone) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "customer_id and agent_phone required" })).setMimeType(ContentService.MimeType.JSON);
      var customer = getCustomerById(customerId); if (!customer) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      var shareData = generatePincodeShareUrl(customer, agentPhone);
      logHealth("share_pincode", "ok", "Customer: " + customerId, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, whatsappUrl: shareData.whatsappUrl, message: shareData.message })).setMimeType(ContentService.MimeType.JSON);
    }

    // ══════════════════════════════════════════════════════════════════
    // FIXED v5.1.0: ADD NUMBER via GET (for HF scraper)
    // Column order now matches HEADERS_NUMBERS:
    //   Row, Number, Root, Compound, Plan, Source,
    //   Price, Status, Found, Last Updated, Notes, Hash
    // ══════════════════════════════════════════════════════════════════
    if (action === "addnumber") {
      const num = String(e.parameter.number || "").trim();
      const normalized = normalizePhone(num);
      if (!normalized || normalized.length !== 10) {
        return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Invalid number format" })).setMimeType(ContentService.MimeType.JSON);
      }
      if (normalized.indexOf("7090") !== -1) {
        return ContentService.createTextOutput(JSON.stringify({ success: true, skipped: true, reason: "Contains 7090" })).setMimeType(ContentService.MimeType.JSON);
      }
      const last6 = normalized.slice(-6);
      if (last6.indexOf("0") !== -1) {
        return ContentService.createTextOutput(JSON.stringify({ success: true, skipped: true, reason: "Zero in last 6 digits" })).setMimeType(ContentService.MimeType.JSON);
      }
      const blocked6Pairs = ["16","26","36","46","56","76","86"];
      for (let pi = 0; pi <= normalized.length - 2; pi++) {
        const pair = normalized.slice(pi, pi + 2);
        if (blocked6Pairs.indexOf(pair) !== -1) {
          if (pair === "96" && pi === normalized.length - 2) continue;
          if (pair === "96" && pi + 2 < normalized.length && normalized[pi + 2] === "9") continue;
          if (pair === "69" && pi > 0 && normalized[pi - 1] === "9") continue;
          return ContentService.createTextOutput(JSON.stringify({ success: true, skipped: true, reason: "Blocked pair " + pair })).setMimeType(ContentService.MimeType.JSON);
        }
      }
      const root = parseInt(e.parameter.root) || computeRoot(normalized);
      const compound = parseInt(e.parameter.compound) || computeCompound(normalized);
      if ([1, 3, 5, 6].indexOf(root) === -1) {
        return ContentService.createTextOutput(JSON.stringify({ success: true, skipped: true, reason: "Total " + root + " not in [1,3,5,6]" })).setMimeType(ContentService.MimeType.JSON);
      }
      const existing = getExistingNumbers();
      const dedupKey = getDedupKey(normalized);
      if (existing.some(e => e.normalized === normalized || e.dedupKey === dedupKey)) {
        return ContentService.createTextOutput(JSON.stringify({ success: true, skipped: true, reason: "Duplicate" })).setMimeType(ContentService.MimeType.JSON);
      }
      const source = e.parameter.source || "scraper";
      const plan = e.parameter.plan || "---";
      const now = new Date().toISOString();
      const hash = getHash(normalized);
      const pricing = getRandomPricing(String(root));
      const mainSheet = getSheet(SHEET_NUMBERS);

      // ═══ FIXED: Correct column order matching HEADERS_NUMBERS ═══
      mainSheet.appendRow([
        mainSheet.getLastRow() + 1,  // Row
        normalized,                   // Number
        root,                         // Root
        compound,                     // Compound
        plan,                         // Plan
        source,                       // Source
        pricing,                      // Price
        "available",                  // Status
        now,                          // Found
        now,                          // Last Updated
        "",                           // Notes
        hash                          // Hash
      ]);

      logHealth("addNumber_get", "ok", "Number: " + normalized, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, added: true, number: normalized })).setMimeType(ContentService.MimeType.JSON);
    }

    // ══════════════════════════════════════════════════════════════════
    // FIXED v5.1.0: ADD NUMBERS BATCH via GET (for HF scraper)
    // Column order now matches HEADERS_NUMBERS
    // ══════════════════════════════════════════════════════════════════
    if (action === "addnumbersbatch") {
      var numbersJson = e.parameter.numbers || "[]";
      var numbers;
      try { numbers = JSON.parse(numbersJson); } catch(ex) { return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Invalid JSON" })).setMimeType(ContentService.MimeType.JSON); }
      var existing = getExistingNumbers();
      var mainSheet = getSheet(SHEET_NUMBERS);
      var added = [], skipped = [];
      var blocked6Pairs = ["16","26","36","46","56","76","86"];

      for (var bi = 0; bi < numbers.length; bi++) {
        var entry = numbers[bi], bnum = String(entry.number || "").trim(), bnorm = normalizePhone(bnum);
        if (!bnorm || bnorm.length !== 10) { skipped.push({ number: bnum, reason: "Invalid format" }); continue; }
        if (bnorm.indexOf("7090") !== -1) { skipped.push({ number: bnorm, reason: "Contains 7090" }); continue; }
        var blast6 = bnorm.slice(-6);
        if (blast6.indexOf("0") !== -1) { skipped.push({ number: bnorm, reason: "Zero in last 6 digits" }); continue; }
        var hasBlockedPair = false;
        for (var pi = 0; pi <= bnorm.length - 2; pi++) { var pair = bnorm.slice(pi, pi + 2); if (blocked6Pairs.indexOf(pair) !== -1) { if (pair === "96" && pi === bnorm.length - 2) continue; if (pair === "96" && pi + 2 < bnorm.length && bnorm[pi + 2] === "9") continue; if (pair === "69" && pi > 0 && bnorm[pi - 1] === "9") continue; hasBlockedPair = true; break; } }
        if (hasBlockedPair) { skipped.push({ number: bnorm, reason: "Blocked pair" }); continue; }
        var broot = entry.root || computeRoot(bnorm);
        if ([1, 3, 5, 6].indexOf(broot) === -1) { skipped.push({ number: bnorm, reason: "Total " + broot + " not in [1,3,5,6]" }); continue; }
        var bdedup = getDedupKey(bnorm);
        if (existing.some(function(e2) { return e2.normalized === bnorm || e2.dedupKey === bdedup; })) { skipped.push({ number: bnorm, reason: "Duplicate" }); continue; }
        var bcompound = entry.compound || computeCompound(bnorm), bsource = entry.source || "scraper", bplan = entry.plan || "---", bnow = new Date().toISOString(), bhash = getHash(bnorm), bpricing = getRandomPricing(String(broot));

        // ═══ FIXED: Correct column order matching HEADERS_NUMBERS ═══
        mainSheet.appendRow([
          mainSheet.getLastRow() + 1,  // Row
          bnorm,                        // Number
          broot,                        // Root
          bcompound,                    // Compound
          bplan,                        // Plan
          bsource,                      // Source
          bpricing,                     // Price
          "available",                  // Status
          bnow,                         // Found
          bnow,                         // Last Updated
          "",                           // Notes
          bhash                         // Hash
        ]);

        existing.push({ normalized: bnorm, dedupKey: bdedup });
        added.push(bnorm);
      }
      logHealth("addNumbersBatch_get", "ok", "Added: " + added.length + ", Skipped: " + skipped.length, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, added: added.length, skipped: skipped.length, addedNumbers: added, skippedDetails: skipped })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── SAVE WEBSITE VISITOR ──────────────────────────────────────
    if (action === "save_website_visitor") {
      const wsSheet = getSheet(SHEET_WEBSITE_VISITORS);
      const id = "VIS_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
      const now = new Date().toISOString();
      wsSheet.appendRow([id, now, e.parameter.name || "", e.parameter.dob || "", e.parameter.mobile || "", e.parameter.email || "", e.parameter.gender || "", e.parameter.source || "landing_page", e.parameter.page || "/", e.parameter.service || "", e.parameter.ipAddress || "", e.parameter.userAgent || "", "new"]);
      logHealth("save_website_visitor", "ok", "Visitor: " + id, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, id: id })).setMimeType(ContentService.MimeType.JSON);
    }

    // Default: get numbers
    if (target === "numbers" || target === "all") {
      const existing = getExistingNumbers();
      let filtered = existing;
      let statusMap = null;
      if (e.parameter.status || e.parameter.available === "true") {
        const sheet = getSheet(SHEET_NUMBERS); const lastRow = sheet.getLastRow();
        if (lastRow > 1) { const statusData = sheet.getRange(2, 8, lastRow - 1, 1).getValues(); statusMap = {}; for (let i = 0; i < statusData.length; i++) statusMap[i + 2] = String(statusData[i][0] || ""); }
      }
      if (e.parameter.number) { const n = normalizePhone(e.parameter.number); filtered = filtered.filter(row => row.normalized === n); }
      if (e.parameter.status && statusMap) filtered = filtered.filter(row => statusMap[row.row] === e.parameter.status);
      if (e.parameter.available === "true" && statusMap) filtered = filtered.filter(row => { const s = statusMap[row.row]; return s === "available" || s === ""; });
      const limit = parseInt(e.parameter.limit) || filtered.length;
      filtered = filtered.slice(0, limit);
      const sheet = getSheet(SHEET_NUMBERS);
      let numbers;
      if (filtered.length > 0 && filtered.length === existing.length && !e.parameter.status && !e.parameter.available && !e.parameter.number) {
        const allData = sheet.getRange(2, 1, sheet.getLastRow() - 1, HEADERS_NUMBERS.length).getValues();
        numbers = allData.map((data, i) => ({ row: data[0], number: String(data[1]), root: data[2], compound: data[3], plan: data[4], source: data[5], price: data[6], status: data[7], found: data[8], lastUpdated: data[9], notes: data[10] }));
      } else {
        const rows = filtered.map(r => r.row); const minRow = Math.min(...rows); const maxRow = Math.max(...rows);
        const allData = sheet.getRange(minRow, 1, maxRow - minRow + 1, HEADERS_NUMBERS.length).getValues();
        const dataByRow = {}; for (let i = 0; i < allData.length; i++) dataByRow[minRow + i] = allData[i];
        numbers = filtered.map(row => { const data = dataByRow[row.row] || []; return { row: data[0], number: String(data[1]), root: data[2], compound: data[3], plan: data[4], source: data[5], price: data[6], status: data[7], found: data[8], lastUpdated: data[9], notes: data[10] }; });
      }
      logHealth("get_numbers", "ok", numbers.length + " numbers retrieved", new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, numbers: numbers, total: numbers.length })).setMimeType(ContentService.MimeType.JSON);
    }

    if (target === "customers") {
      const sheet = getSheet(SHEET_CUSTOMERS); const lastRow = sheet.getLastRow();
      if (lastRow <= 1) return ContentService.createTextOutput(JSON.stringify({ success: true, customers: [], total: 0 })).setMimeType(ContentService.MimeType.JSON);
      const data = sheet.getRange(2, 1, lastRow - 1, HEADERS_CUSTOMERS.length).getValues();
      const customers = data.map((row, i) => ({ id: row[0], name: row[1], gender: row[2], dob: row[3], day: row[4], month: row[5], year: row[6], pincode: row[7], whatsapp: row[8], createdAt: row[9], status: row[10], notes: row[11], lastContacted: row[12], followUpCount: row[13], followUpStage: row[14] || "fresh", followUpDate: row[15] || "" }));
      return ContentService.createTextOutput(JSON.stringify({ success: true, customers, total: customers.length })).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Unknown target" })).setMimeType(ContentService.MimeType.JSON);
  } finally { lock.releaseLock(); }
}

// ══════════════════════════════════════════════════════════════════════
// HANDLERS - doPost
// ══════════════════════════════════════════════════════════════════════

function doPost(e) {
  const lock = LockService.getScriptLock();
  const start = new Date().getTime();
  try {
    lock.tryLock(10000);
    const body = JSON.parse(e.postData.contents);
    const action = body.action || "add";

    // ─── ADD NUMBERS (Vercel app format) ───────────────────────────
    if (action === "add" || body.numbers) {
      const numbersToAdd = body.numbers || [body];
      const mainSheet = getSheet(SHEET_NUMBERS);
      const freeSheet = getSheet(SHEET_FREE_NUMBERS);
      const paidSheet = getSheet(SHEET_PAID_NUMBERS);
      const existing = getExistingNumbers();
      const added = [], skipped = [], skippedDetails = [];
      let freeAdded = 0, paidAdded = 0;

      for (const entry of numbersToAdd) {
        const num = String(entry.number || entry.Number || "").trim();
        const normalized = normalizePhone(num);
        if (!normalized || normalized.length !== 10) { skipped.push(num); skippedDetails.push({ number: num, reason: "Invalid format" }); continue; }
        const dedupKey = getDedupKey(normalized);
        const hash = getHash(normalized);
        if (existing.some(e => e.normalized === normalized || e.dedupKey === dedupKey)) { skipped.push(num); skippedDetails.push({ number: num, reason: "Duplicate" }); continue; }
        const root = computeRoot(normalized), compound = computeCompound(normalized), now = new Date().toISOString();
        const plan = entry.plan || entry.Plan || "---", source = entry.source || entry.Source || "api";
        const expiryDate = new Date(); expiryDate.setDate(expiryDate.getDate() + 21);
        mainSheet.appendRow([mainSheet.getLastRow() + 1, normalized, root, compound, plan, source, 0, "available", now, now, "", hash]);
        const classification = getNumberClassification(normalized);
        if (classification.isFree) { freeSheet.appendRow([freeSheet.getLastRow() + 1, normalized, root, compound, plan, source, 0, "available", now, now, "", hash, expiryDate.toISOString()]); freeAdded++; }
        else { paidSheet.appendRow([paidSheet.getLastRow() + 1, normalized, root, compound, plan, source, 0, "available", now, now, "", hash, expiryDate.toISOString()]); paidAdded++; }
        added.push(normalized);
        existing.push({ number: normalized, normalized, dedupKey, hash, row: mainSheet.getLastRow() });
      }
      clearNumberCache();
      logHealth("post_numbers", "ok", "Added: " + added.length + ", Free: " + freeAdded + ", Paid: " + paidAdded + ", Skipped: " + skipped.length, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, added: added.length, skipped: skipped.length, addedNumbers: added, skippedDetails: skippedDetails, freeAdded: freeAdded, paidAdded: paidAdded, total: mainSheet.getLastRow() - 1 })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── ADD NUMBER (single) ────────────────────────────────────────
    if (action === "addNumber") {
      const entry = body.data || body;
      const num = String(entry.number || "").trim(), normalized = normalizePhone(num);
      if (!normalized || normalized.length !== 10) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Invalid number format" })).setMimeType(ContentService.MimeType.JSON);
      const existing = getExistingNumbers(), dedupKey = getDedupKey(normalized);
      if (existing.some(e => e.normalized === normalized || e.dedupKey === dedupKey)) return ContentService.createTextOutput(JSON.stringify({ success: true, skipped: true, reason: "Duplicate" })).setMimeType(ContentService.MimeType.JSON);
      const root = entry.root || computeRoot(normalized), compound = entry.compound || computeCompound(normalized), now = new Date().toISOString(), source = entry.source || "scraper", hash = getHash(normalized);
      const mainSheet = getSheet(SHEET_NUMBERS);
      mainSheet.appendRow([mainSheet.getLastRow() + 1, normalized, root, compound, entry.plan || "---", source, 0, "available", now, now, "", hash]);
      const cls = getNumberClassification(normalized); const expiry = new Date(); expiry.setDate(expiry.getDate() + 21);
      if (cls.isFree) getSheet(SHEET_FREE_NUMBERS).appendRow([getSheet(SHEET_FREE_NUMBERS).getLastRow() + 1, normalized, root, compound, entry.plan || "---", source, 0, "available", now, now, "", hash, expiry.toISOString()]);
      else getSheet(SHEET_PAID_NUMBERS).appendRow([getSheet(SHEET_PAID_NUMBERS).getLastRow() + 1, normalized, root, compound, entry.plan || "---", source, 0, "available", now, now, "", hash, expiry.toISOString()]);
      clearNumberCache(); logHealth("addNumber_scraper", "ok", "Number: " + normalized, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, added: normalized })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── ADD NUMBERS BATCH ─────────────────────────────────────────
    if (action === "addNumbersBatch") {
      const entries = body.data || body.numbers || [];
      const mainSheet = getSheet(SHEET_NUMBERS), freeSheet = getSheet(SHEET_FREE_NUMBERS), paidSheet = getSheet(SHEET_PAID_NUMBERS);
      const existing = getExistingNumbers(); const added = [], skipped = []; let freeAdded = 0, paidAdded = 0;
      for (const entry of entries) {
        const num = String(entry.number || "").trim(), normalized = normalizePhone(num);
        if (!normalized || normalized.length !== 10) { skipped.push(num); continue; }
        const dedupKey = getDedupKey(normalized);
        if (existing.some(e => e.normalized === normalized || e.dedupKey === dedupKey)) { skipped.push(num); continue; }
        const root = entry.root || computeRoot(normalized), compound = entry.compound || computeCompound(normalized), now = new Date().toISOString(), source = entry.source || "scraper", hash = getHash(normalized);
        mainSheet.appendRow([mainSheet.getLastRow() + 1, normalized, root, compound, entry.plan || "---", source, 0, "available", now, now, "", hash]);
        const cls = getNumberClassification(normalized); const expiry = new Date(); expiry.setDate(expiry.getDate() + 21);
        if (cls.isFree) { freeSheet.appendRow([freeSheet.getLastRow() + 1, normalized, root, compound, entry.plan || "---", source, 0, "available", now, now, "", hash, expiry.toISOString()]); freeAdded++; }
        else { paidSheet.appendRow([paidSheet.getLastRow() + 1, normalized, root, compound, entry.plan || "---", source, 0, "available", now, now, "", hash, expiry.toISOString()]); paidAdded++; }
        added.push(normalized); existing.push({ number: normalized, normalized, dedupKey, hash, row: mainSheet.getLastRow() });
      }
      clearNumberCache(); logHealth("addNumbersBatch_scraper", "ok", "Added: " + added.length + ", Skipped: " + skipped.length, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, added: added.length, skipped: skipped.length, freeAdded, paidAdded, total: mainSheet.getLastRow() - 1 })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── DELETE NUMBER ────────────────────────────────────────────
    if (action === "delete") {
      const result = deleteNumberByValue(body.number);
      if (!result.deleted) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Number not found" })).setMimeType(ContentService.MimeType.JSON);
      logHealth("delete_number", "ok", "Number: " + body.number, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, deleted: true, sheet: result.sheet })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── ADD CUSTOMER ─────────────────────────────────────────────
    if (action === "add_customer") {
      const sheet = getSheet(SHEET_CUSTOMERS);
      const id = "CUST_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
      const now = new Date().toISOString();
      sheet.appendRow([id, body.name || "", body.gender || "", body.dob || "", body.day || "", body.month || "", body.year || "", body.pincode || "", body.whatsapp || "", now, "pending", body.notes || "", "", 0, "fresh", calculateFollowUpDate(now)]);
      logHealth("add_customer", "ok", "Customer: " + id, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, id })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── UPDATE CUSTOMER ──────────────────────────────────────────
    if (action === "update_customer") {
      if (!body.id) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer ID required" })).setMimeType(ContentService.MimeType.JSON);
      const updated = updateCustomer(body.id, body);
      if (!updated) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      logHealth("update_customer", "ok", "Customer: " + body.id, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, customer: updated })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── DELETE CUSTOMER ──────────────────────────────────────────
    if (action === "delete_customer") {
      if (!body.id) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer ID required" })).setMimeType(ContentService.MimeType.JSON);
      if (!deleteCustomer(body.id)) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      logHealth("delete_customer", "ok", "Customer: " + body.id, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── SHARE REPORT / PINCODE ────────────────────────────────────
    if (action === "share_report") {
      if (!body.customer_id || !body.mobile_number) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "customer_id and mobile_number required" })).setMimeType(ContentService.MimeType.JSON);
      var customer = getCustomerById(body.customer_id); if (!customer) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      var report = generateMobileDobCompatibilityReport({ day: customer.day, month: customer.month, year: customer.year }, body.mobile_number);
      var shareData = generateReportShareUrl(customer, report, body.mobile_number);
      logHealth("share_report", "ok", "Customer: " + body.customer_id, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, whatsappUrl: shareData.whatsappUrl, message: shareData.message })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "share_pincode") {
      if (!body.customer_id || !body.agent_phone) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "customer_id and agent_phone required" })).setMimeType(ContentService.MimeType.JSON);
      var customer = getCustomerById(body.customer_id); if (!customer) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Customer not found" })).setMimeType(ContentService.MimeType.JSON);
      var shareData = generatePincodeShareUrl(customer, body.agent_phone);
      logHealth("share_pincode", "ok", "Customer: " + body.customer_id, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, whatsappUrl: shareData.whatsappUrl, message: shareData.message })).setMimeType(ContentService.MimeType.JSON);
    }

    // ─── TRANSACTIONS ─────────────────────────────────────────────
    if (action === "save_transaction") {
      const id = saveTransaction(body); logHealth("save_transaction", "ok", "Transaction: " + id, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, id })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "verify_transaction") {
      if (!body.payment_id) return ContentService.createTextOutput(JSON.stringify({ success: false, error: "payment_id required" })).setMimeType(ContentService.MimeType.JSON);
      const verified = verifyTransaction(body.payment_id); logHealth("verify_transaction", "ok", "Payment: " + body.payment_id, new Date().getTime() - start);
      return ContentService.createTextOutput(JSON.stringify({ success: true, verified })).setMimeType(ContentService.MimeType.JSON);
    }
    if (action === "cleanup") {
      const result = autoCleanupNumbers();
      return ContentService.createTextOutput(JSON.stringify({ success: true, ...result })).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({ success: false, error: "Unknown action" })).setMimeType(ContentService.MimeType.JSON);
  } finally { lock.releaseLock(); }
}

// ─── TRIGGERS ───────────────────────────────────────────────────────

function onOpen() {
  SpreadsheetApp.getUi().createMenu("Hankith Tools")
    .addItem("Show Health", "showHealth")
    .addItem("Clear Cache", "clearNumberCache")
    .addItem("Run Diagnostics", "runDiagnostics")
    .addItem("Auto Cleanup Numbers", "autoCleanupNumbers")
    .addItem("Show Statistics", "showStatistics")
    .addToUi();
}

function showHealth() {
  const stats = getNumberStatistics();
  SpreadsheetApp.getUi().alert("Health Status\n\nTotal Numbers: " + stats.totalNumbers + "\nFree Numbers: " + stats.freeNumbers + "\nPaid Numbers: " + stats.paidNumbers + "\nLast Updated: " + stats.lastUpdated + "\nVersion: 5.1.0");
}

function showStatistics() {
  const stats = getNumberStatistics();
  SpreadsheetApp.getUi().alert("Number Statistics\n\nTotal Numbers: " + stats.totalNumbers + "\nFree Numbers: " + stats.freeNumbers + "\nPaid Numbers: " + stats.paidNumbers + "\nLast Updated: " + stats.lastUpdated);
}

function runDiagnostics() {
  const sheet = getSheet(SHEET_NUMBERS);
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) { SpreadsheetApp.getUi().alert("No numbers to diagnose."); return; }
  const data = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
  const normalized = data.map(r => normalizePhone(String(r[0])));
  const duplicates = normalized.filter((n, i) => normalized.indexOf(n) !== i);
  const invalid = normalized.filter(n => n.length !== 10);
  const freeNumbers = normalized.filter(n => isFreeNumber(n));
  const paidNumbers = normalized.filter(n => !isFreeNumber(n));
  SpreadsheetApp.getUi().alert("Diagnostics\n\nTotal rows: " + (lastRow - 1) + "\nValid: " + normalized.filter(n => n.length === 10).length + "\nInvalid: " + invalid.length + "\nDuplicates: " + duplicates.length + "\nFree Numbers: " + freeNumbers.length + "\nPaid Numbers: " + paidNumbers.length);
}
