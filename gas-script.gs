/**
 * ═══════════════════════════════════════════════════════════════════════════════
 * VI NUMBER SCRAPER — Google Apps Script v5.1
 * ═══════════════════════════════════════════════════════════════════════════════
 * 
 * ACTIONS (via doGet):
 *   ?action=getNumbers        →  Returns ALL numbers from the sheet
 *   ?action=addNumber         →  Add a single number (params: number, root, compound, source, plan)
 *   ?action=addNumbersBatch   →  Batch add (params: numbers=[{number,root,compound,source,plan},...])
 *   ?action=healthCheck       →  Returns health/stats
 *   ?action=deleteNumber      →  Remove a number (params: number)
 *   ?action=repair            →  Rebuild sheet index, fix inconsistencies, remove bad data
 * 
 * SHEET STRUCTURE (Sheet2):
 *   Col A: Found Number (phone number)
 *   Col B: Root (1-9 numerology root)
 *   Col C: Compound (sum of digits)
 *   Col D: Plan (prepaid/postpaid)
 *   Col E: Source (scraper/manual)
 *   Col F: Price
 *   Col G: Status (available/blocked/sold)
 *   Col H: Found Timestamp
 *   Col I: Last Updated
 *   Col J: Notes
 * ═══════════════════════════════════════════════════════════════════════════════
 */

var SHEET_ID = '1y2Gk6UPAwkXdx0-AQi80Saeu0frZWtaPzjK9_ssIX9Q';
var SHEET_NAME = 'Sheet2';

// ── Helpers ───────────────────────────────────────────────────────────────────

function json(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function getSheet() {
  var doc = SpreadsheetApp.openById(SHEET_ID);
  var sheet = doc.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = doc.insertSheet(SHEET_NAME);
    sheet.getRange(1, 1, 1, 10).setValues([[
      'Found Number', 'Root', 'Compound', 'Plan', 'Source',
      'Price', 'Status', 'Found', 'Last Updated', 'Notes'
    ]]);
  }
  return sheet;
}

/**
 * Read ALL rows from the sheet and return as an array of objects.
 * This is the SINGLE source of truth — used by both getNumbers AND duplicate checks.
 */
function readAllRows() {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  
  var data = sheet.getRange(1, 1, lastRow, 10).getValues();
  var headers = data[0].map(function(h) { return String(h).trim().toLowerCase(); });
  
  var rows = [];
  for (var i = 1; i < data.length; i++) {
    var r = data[i];
    var num = String(r[0] || '').replace(/\D/g, '');
    if (!num) continue; // Skip empty rows
    
    rows.push({
      row: i + 1,
      number: num,
      root: Number(r[1]) || 0,
      compound: Number(r[2]) || 0,
      plan: String(r[3] || 'prepaid'),
      source: String(r[4] || 'scraper'),
      price: Number(r[5]) || 0,
      status: String(r[6] || 'available'),
      found: r[7] ? String(r[7]) : new Date().toISOString(),
      lastUpdated: r[8] ? String(r[8]) : new Date().toISOString(),
      notes: String(r[9] || ''),
    });
  }
  return rows;
}

/**
 * Build a number→rowIndex map from the sheet (for O(1) duplicate lookups).
 * Uses readAllRows internally so it's always consistent with getNumbers.
 */
function buildNumberMap() {
  var rows = readAllRows();
  var map = {};
  for (var i = 0; i < rows.length; i++) {
    map[rows[i].number] = rows[i].row;
  }
  return map;
}

function computeCompound(num) {
  return String(num).split('').reduce(function(acc, d) { return acc + Number(d); }, 0);
}

function computeSingleTotal(n) {
  var sum = n;
  while (sum > 9) {
    sum = String(sum).split('').reduce(function(a, b) { return a + Number(b); }, 0);
  }
  return sum;
}

// ── Numerology Validation ────────────────────────────────────────────────────

function validateNumber(num) {
  var s = String(num).replace(/\D/g, '');
  if (s.length < 10) return { valid: false, reason: 'Invalid length: ' + s.length };
  
  // 1. Never save numbers with 2, 4, 8 in it
  if (/[248]/.test(s)) return { valid: false, reason: 'Contains 2/4/8' };
  
  // 2. Double zero 00 is forbidden
  if (s.indexOf('00') !== -1) return { valid: false, reason: 'Contains double zero 00' };
  
  // 3. Digit-triple check (triples are forbidden)
  var tripMatch = s.match(/(\d)\1\1/);
  if (tripMatch) return { valid: false, reason: 'Contains triple digit: ' + tripMatch[0] };
  
  // 4. Consecutive pairs check (from 4th digit onward)
  var GOOD_PAIRS = [
    '11','13','31','15','51','17','71','19','91',
    '33','35','53','37','73','39','93',
    '55','57','75','59','95','79','97','99'
  ];
  for (var i = 3; i < s.length - 1; i++) {
    var pair = s.substring(i, i + 2);
    if (pair.indexOf('0') !== -1) continue;
    if (GOOD_PAIRS.indexOf(pair) === -1) {
      if (pair === '96' && i === s.length - 2) continue;
      if (pair === '96' && s.substring(i, i + 3) === '969') continue;
      if (pair === '69' && i > 0 && s.substring(i - 1, i + 2) === '969') continue;
      return { valid: false, reason: 'Invalid pair: ' + pair };
    }
  }
  
  // 5. Check compound and root
  var compound = computeCompound(s);
  if (compound === 51) return { valid: false, reason: 'Compound is 51' };
  
  var root = computeSingleTotal(compound);
  if ([1, 3, 5, 6].indexOf(root) === -1) {
    return { valid: false, reason: 'Root ' + root + ' not in 1,3,5,6' };
  }
  
  return { valid: true, root: root, compound: compound };
}

// ── doGet — Master Router ────────────────────────────────────────────────────

function doGet(e) {
  try {
    var action = e && e.parameter && e.parameter.action
      ? String(e.parameter.action).toLowerCase()
      : '';
    
    switch (action) {
      case 'getnumbers':
        return handleGetNumbers();
      case 'addnumber':
        return handleAddNumber(e.parameter);
      case 'addnumbersbatch':
        return handleAddNumbersBatch(e.parameter);
      case 'healthcheck':
        return handleHealthCheck();
      case 'deletenumber':
        return handleDeleteNumber(e.parameter);
      case 'repair':
        return handleRepair();
      default:
        // Default: return all numbers (backward compatible)
        return handleGetNumbers();
    }
  } catch (error) {
    return json({ success: false, error: error.toString() });
  }
}

// ── Action: getNumbers ───────────────────────────────────────────────────────

function handleGetNumbers() {
  var rows = readAllRows();
  return json({
    success: true,
    numbers: rows,
  });
}

// ── Action: addNumber ────────────────────────────────────────────────────────

function handleAddNumber(params) {
  if (!params || !params.number) {
    return json({ success: false, error: 'Missing number parameter' });
  }
  
  var num = String(params.number).replace(/\D/g, '');
  var existing = buildNumberMap();
  
  // Check duplicate (uses same readAllRows as getNumbers — always consistent)
  if (existing[num]) {
    return json({ success: true, skipped: true, reason: 'Duplicate' });
  }
  
  // Validate
  var validation = validateNumber(num);
  if (!validation.valid) {
    return json({ success: true, skipped: true, reason: validation.reason });
  }
  
  // Append to sheet
  var sheet = getSheet();
  var now = new Date().toISOString();
  sheet.appendRow([
    num,
    params.root ? Number(params.root) : validation.root,
    params.compound ? Number(params.compound) : validation.compound,
    params.plan || 'prepaid',
    params.source || 'scraper',
    params.price ? Number(params.price) : 1499,
    params.status || 'available',
    params.found || now,
    now,
    params.notes || '',
  ]);
  
  return json({ success: true, added: true, number: num, root: validation.root });
}

// ── Action: addNumbersBatch ──────────────────────────────────────────────────

function handleAddNumbersBatch(params) {
  if (!params || !params.numbers) {
    return json({ success: false, error: 'Missing numbers parameter' });
  }
  
  var batchData;
  try {
    batchData = JSON.parse(params.numbers);
  } catch (e) {
    return json({ success: false, error: 'Invalid JSON in numbers parameter: ' + e.toString() });
  }
  
  if (!Array.isArray(batchData) || batchData.length === 0) {
    return json({ success: false, error: 'numbers must be a non-empty array' });
  }
  
  var existing = buildNumberMap(); // Uses same readAllRows as getNumbers — always consistent
  var sheet = getSheet();
  var now = new Date().toISOString();
  
  var added = 0;
  var skipped = 0;
  var addedNumbers = [];
  var skippedDetails = [];
  
  for (var i = 0; i < batchData.length; i++) {
    var item = batchData[i];
    var num = String(item.number || '').replace(/\D/g, '');
    if (!num) { skipped++; skippedDetails.push({ number: item.number || '', reason: 'Empty number' }); continue; }
    
    // Check duplicate
    if (existing[num]) {
      skipped++;
      skippedDetails.push({ number: num, reason: 'Duplicate' });
      continue;
    }
    
    // Validate
    var validation = validateNumber(num);
    if (!validation.valid) {
      skipped++;
      skippedDetails.push({ number: num, reason: validation.reason });
      continue;
    }
    
    // Append to sheet
    sheet.appendRow([
      num,
      item.root ? Number(item.root) : validation.root,
      item.compound ? Number(item.compound) : validation.compound,
      item.plan || 'prepaid',
      item.source || 'scraper',
      item.price ? Number(item.price) : 1499,
      item.status || 'available',
      item.found || now,
      now,
      item.notes || '',
    ]);
    
    added++;
    addedNumbers.push(num);
    existing[num] = true; // Prevent duplicate in same batch
  }
  
  return json({
    success: true,
    added: added,
    skipped: skipped,
    addedNumbers: addedNumbers,
    skippedDetails: skippedDetails,
  });
}

// ── Action: healthCheck ──────────────────────────────────────────────────────

function handleHealthCheck() {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  var totalNumbers = lastRow > 1 ? lastRow - 1 : 0;
  
  // Count by status
  var freeCount = 0;
  var paidCount = 0;
  if (lastRow > 1) {
    var statuses = sheet.getRange(2, 7, lastRow - 1, 1).getValues();
    for (var i = 0; i < statuses.length; i++) {
      var s = String(statuses[i][0] || '').toLowerCase();
      if (s === 'available' || s === '') freeCount++;
      else paidCount++;
    }
  }
  
  return json({
    success: true,
    status: 'healthy',
    version: '5.1.0',
    stats: {
      totalNumbers: totalNumbers,
      freeNumbers: freeCount,
      paidNumbers: paidCount,
      timestamp: new Date().toISOString(),
    },
  });
}

// ── Action: deleteNumber ─────────────────────────────────────────────────────

function handleDeleteNumber(params) {
  if (!params || !params.number) {
    return json({ success: false, error: 'Missing number parameter' });
  }
  
  var num = String(params.number).replace(/\D/g, '');
  var rows = readAllRows();
  
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].number === num) {
      var sheet = getSheet();
      sheet.deleteRow(rows[i].row);
      return json({ success: true, deleted: true, number: num });
    }
  }
  
  return json({ success: true, deleted: false, number: num, reason: 'Not found' });
}

// ── Action: repair — Fix Inconsistencies ────────────────────────────────────

function handleRepair() {
  var sheet = getSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return json({ success: true, message: 'No data to repair', repaired: 0 });
  
  var data = sheet.getRange(1, 1, lastRow, 10).getValues();
  var headers = data[0];
  var validRows = [headers];
  var seen = {};
  var removedInvalid = 0;
  var removedDuplicates = 0;
  var repaired = 0;
  
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    var num = String(row[0] || '').replace(/\D/g, '');
    if (!num) { removedInvalid++; continue; }
    
    // Duplicate check
    if (seen[num]) { removedDuplicates++; continue; }
    seen[num] = true;
    
    // Validate and repair
    var validation = validateNumber(num);
    if (!validation.valid) { removedInvalid++; continue; }
    
    // Fix root/compound if wrong
    if (Number(row[1]) !== validation.root || Number(row[2]) !== validation.compound) {
      row[1] = validation.root;
      row[2] = validation.compound;
      repaired++;
    }
    
    // Fix empty fields
    if (!row[3]) row[3] = 'prepaid';
    if (!row[4]) row[4] = 'scraper';
    if (!row[5]) row[5] = 1499;
    if (!row[6]) row[6] = 'available';
    if (!row[7]) row[7] = new Date().toISOString();
    if (!row[8]) row[8] = new Date().toISOString();
    if (!row[9]) row[9] = '';
    
    validRows.push(row);
  }
  
  // Rewrite sheet
  sheet.clear();
  if (validRows.length > 0) {
    sheet.getRange(1, 1, validRows.length, 10).setValues(validRows);
  }
  
  return json({
    success: true,
    message: 'Sheet repaired',
    totalBefore: lastRow - 1,
    totalAfter: validRows.length - 1,
    removedInvalid: removedInvalid,
    removedDuplicates: removedDuplicates,
    repaired: repaired,
  });
}
