var SHEET_ID = '1y2Gk6UPAwkXdx0-AQi80Saeu0frZWtaPzjK9_ssIX9Q';
var SAVE_SHEET_NAME = 'Sheet2';
var SEARCH_SHEET_NAME = 'SearchedNumbers';
var SAVE_HEADERS = ['Found Number', 'Number total', 'Number Compound', 'prepaid / postpaid', 'Pricing', 'Availability', 'Status', 'Price'];
var SEARCH_HEADERS = ['Searched Number', 'Number total', 'Number Compound', 'Status'];
var READ_FIELDS = ['Found Number', 'Number total', 'Number Compound', 'prepaid / postpaid', 'Pricing', 'Availability', 'Status', 'Price'];
var SEARCH_READ_FIELDS = ['Searched Number', 'Number total', 'Number Compound', 'Status'];

function jsonResponse(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
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

function validateNumber(num) {
  var s = String(num).replace(/\D/g, '');
  if (s.length < 6) return { valid: false, reason: 'Too short: ' + s };
  
  // 1. Never save numbers with 2, 4, 8 in it
  if (/[248]/.test(s)) return { valid: false, reason: 'Contains 2/4/8: ' + s };
  
  // 2. Strict Check: Double zero 00 is forbidden
  if (s.indexOf('00') !== -1) return { valid: false, reason: 'Contains double zero 00' };
  
  // 3. Digit-triple check (triples are forbidden)
  var tripMatch = s.match(/(\d)\1\1/);
  if (tripMatch) return { valid: false, reason: 'Contains triple digit: ' + tripMatch[0] };
  
  // 4. Consecutive pairs check: every non-zero adjacent digit pair must strictly be in GOOD_PAIRS
  var GOOD_PAIRS = [
    '11', '13', '31', '15', '51', '17', '71', '19', '91',
    '33', '35', '53', '37', '73', '39', '93',
    '55', '57', '75', '59', '95', '79', '97', '99'
  ];
  // Relax starting fixed digits validation: start transition checks from index 3 (the 4th digit) onwards
  for (var i = 3; i < s.length - 1; i++) {
    var pair = s.substring(i, i + 2);
    if (pair.indexOf('0') !== -1) continue; // Allow pairs with zero (e.g. 90, 07 in 9071)
    if (GOOD_PAIRS.indexOf(pair) === -1) {
      // Check exceptions for digit 6:
      // Exception A: 96 at the end of the number
      if (pair === '96' && i === s.length - 2) {
        continue;
      }
      // Exception B: Part of a 969 sequence
      if (pair === '96' && s.substring(i, i + 3) === '969') {
        continue;
      }
      if (pair === '69' && i > 0 && s.substring(i - 1, i + 2) === '969') {
        continue;
      }
      return { valid: false, reason: 'Invalid digit transition pair: ' + pair };
    }
  }
  
  // 5. Max one 0 in first 4 digits - RELAXED/REMOVED for starting fixed operator digits
  // (We now permit any operator-fixed prefix configurations with good total and pairs)
  
  // 6. Check compound total and single total (must be 1, 3, 5, 6, and compound sum must not be 51)
  var compound = computeCompound(s);
  if (compound === 51) return { valid: false, reason: 'Compound total is 51' };
  
  var singleTotal = computeSingleTotal(compound);
  if ([1, 3, 5, 6].indexOf(singleTotal) === -1) {
    return { valid: false, reason: 'Single total is ' + singleTotal + ' (not in 1, 3, 5, 6)' };
  }
  
  return {
    valid: true,
    correctedTotal: singleTotal,
    correctedCompound: compound
  };
}

function getRowsFromSheet(sheet, fields) {
  var readFields = fields || READ_FIELDS;
  var data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];
  var headers = data[0].map(function(h) { return String(h).trim(); });
  var rows = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    if (row.every(function(c) { return c === '' || c === null; })) continue;
    var obj = {};
    readFields.forEach(function(field) {
      var idx = headers.indexOf(field);
      obj[field] = idx >= 0 ? row[idx] : '';
    });
    rows.push(obj);
  }
  return rows;
}

function doGet(e) {
  try {
    var doc = SpreadsheetApp.openById(SHEET_ID);
    
    // Check if a maintenance or autoheal action is requested
    var action = e && e.parameter && e.parameter.action ? String(e.parameter.action).toLowerCase() : '';
    if (action === 'maintenance' || action === 'autoheal') {
      var maintResult = performSheetMaintenance(doc);
      return jsonResponse(maintResult);
    }

    var sheetParam = e && e.parameter && e.parameter.sheet ? e.parameter.sheet : '';

    // ?sheet=searched → return only SearchedNumbers sheet
    if (sheetParam === 'searched') {
      var sh = doc.getSheetByName(SEARCH_SHEET_NAME);
      if (!sh) return jsonResponse({ status: 'success', data: [] });
      return jsonResponse({ status: 'success', data: getRowsFromSheet(sh, SEARCH_READ_FIELDS) });
    }

    // ?sheet=found → return only Sheet2 (found numbers)
    if (sheetParam === 'found') {
      var sh2 = doc.getSheetByName(SAVE_SHEET_NAME);
      if (!sh2) return jsonResponse({ status: 'success', data: [] });
      return jsonResponse({ status: 'success', data: getRowsFromSheet(sh2, READ_FIELDS) });
    }

    // ?sheet=<name> → specific named sheet
    if (sheetParam && sheetParam !== 'all') {
      var sh3 = doc.getSheetByName(sheetParam);
      if (!sh3) return jsonResponse({ status: 'error', message: sheetParam + ' not found in the document.' });
      return jsonResponse({ status: 'success', data: getRowsFromSheet(sh3) });
    }

    // default / ?sheet=all → all sheets combined
    var allRows = [];
    var sheets = doc.getSheets();
    for (var i = 0; i < sheets.length; i++) {
      var shName = sheets[i].getName();
      var fields = shName === SEARCH_SHEET_NAME ? SEARCH_READ_FIELDS : READ_FIELDS;
      allRows = allRows.concat(getRowsFromSheet(sheets[i], fields));
    }
    return jsonResponse({ status: 'success', data: allRows });
  } catch (error) {
    return jsonResponse({ status: 'error', message: error.toString() });
  }
}

function cleanDuplicatesInSheet(sheet, headers) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 3) return 0;
  var data = sheet.getRange(2, 1, lastRow - 1, headers.length).getValues();
  var seen = {};
  var rowsToDelete = [];
  for (var i = 0; i < data.length; i++) {
    var num = String(data[i][0] || '').replace(/\D/g, '');
    if (!num) continue;
    if (seen[num]) { rowsToDelete.push(i + 2); } else { seen[num] = true; }
  }
  for (var d = rowsToDelete.length - 1; d >= 0; d--) { sheet.deleteRow(rowsToDelete[d]); }
  return rowsToDelete.length;
}

function doPost(e) {
  try {
    var payload = parsePostPayload(e);
    var type = String(payload.type || 'found').toLowerCase();

    if (type === 'searched') {
      return handleSearchedNumbers(payload);
    }
    return handleFoundNumbers(payload);
  } catch (error) {
    return jsonResponse({ status: 'error', message: error.toString() });
  }
}

// ── Found Numbers (Sheet2) ──────────────────────────────────────────────────

function handleFoundNumbers(payload) {
  var inputRows = normalizeFoundRows(payload);
  if (inputRows.length === 0) return jsonResponse({ status: 'error', message: 'No valid rows received.' });

  var doc = SpreadsheetApp.openById(SHEET_ID);
  var sheet = getOrCreateSheet(doc, SAVE_SHEET_NAME, SAVE_HEADERS);
  var removedCount = cleanDuplicatesInSheet(sheet, SAVE_HEADERS);
  var existingNumbers = getExistingNumbers(sheet);
  var rowsToAppend = [];
  var skipped = 0;
  var rejected = [];

  inputRows.forEach(function(row) {
    var rawNum = String(row.foundNumber || '').replace(/\D/g, '');
    if (!rawNum) { skipped++; return; }
    if (existingNumbers.has(rawNum)) { skipped++; return; }
    var validation = validateNumber(rawNum);
    if (!validation.valid) { rejected.push({ number: rawNum, reason: validation.reason }); return; }
    existingNumbers.add(rawNum);
    rowsToAppend.push([rawNum, validation.correctedTotal, validation.correctedCompound, row.plan || '', row.pricing || '', row.availability || '', row.status || 'Available', row.price || '']);
  });

  if (rowsToAppend.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, rowsToAppend.length, SAVE_HEADERS.length).setValues(rowsToAppend);
  }

  return jsonResponse({
    status: 'success',
    type: 'found',
    inserted: rowsToAppend.length,
    skipped: skipped,
    rejected: rejected.length,
    rejectedDetails: rejected,
    duplicatesRemoved: removedCount
  });
}

// ── Searched Numbers (SearchedNumbers sheet) ────────────────────────────────

function handleSearchedNumbers(payload) {
  var inputRows = normalizeSearchedRows(payload);
  if (inputRows.length === 0) return jsonResponse({ status: 'error', message: 'No valid rows received.' });

  var doc = SpreadsheetApp.openById(SHEET_ID);
  var sheet = getOrCreateSheet(doc, SEARCH_SHEET_NAME, SEARCH_HEADERS);
  var rowsToAppend = [];
  var skipped = 0;

  inputRows.forEach(function(row) {
    var rawNum = String(row.searchedNumber || '').replace(/\D/g, '');
    if (!rawNum) { skipped++; return; }
    var compound = computeCompound(rawNum);
    var total = computeSingleTotal(compound);
    rowsToAppend.push([rawNum, total, compound, row.status || '']);
  });

  if (rowsToAppend.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, rowsToAppend.length, SEARCH_HEADERS.length).setValues(rowsToAppend);
  }

  return jsonResponse({
    status: 'success',
    type: 'searched',
    inserted: rowsToAppend.length,
    skipped: skipped
  });
}

// ── Shared helpers ──────────────────────────────────────────────────────────

function parsePostPayload(e) {
  if (!e || !e.postData || !e.postData.contents) return {};
  try { return JSON.parse(e.postData.contents); } catch (error) { return e.parameter || {}; }
}

function normalizeFoundRows(payload) {
  if (Array.isArray(payload)) return payload.map(normalizeFoundRow);
  if (Array.isArray(payload.rows)) return payload.rows.map(normalizeFoundRow);
  return [normalizeFoundRow(payload)];
}

function normalizeFoundRow(row) {
  return {
    foundNumber: row.foundNumber || row.number || row['Found Number'],
    plan: row.plan || row.type || row['prepaid / postpaid'],
    pricing: row.pricing || row['Pricing'] || '',
    availability: row.availability || row['Availability'] || '',
    status: row.status || row['Status'] || 'Available',
    price: row.price || row['Price'] || ''
  };
}

function normalizeSearchedRows(payload) {
  if (Array.isArray(payload.rows)) return payload.rows.map(normalizeSearchedRow);
  if (Array.isArray(payload)) return payload.map(normalizeSearchedRow);
  return [normalizeSearchedRow(payload)];
}

function normalizeSearchedRow(row) {
  return {
    searchedNumber: row.searchedNumber || row.number || row['Searched Number'],
    status: row.status || row['Status'] || ''
  };
}

function getOrCreateSheet(doc, name, headers) {
  var sheet = doc.getSheetByName(name);
  if (!sheet) { sheet = doc.insertSheet(name); }
  ensureHeaders(sheet, headers);
  if (name === SAVE_SHEET_NAME) { applyStatusValidation(sheet); }
  return sheet;
}

function ensureHeaders(sheet, headers) {
  var current = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  var needs = headers.some(function(h, i) { return current[i] !== h; });
  if (needs) { sheet.getRange(1, 1, 1, headers.length).setValues([headers]); }
}

function applyStatusValidation(sheet) {
  var lastRow = Math.max(sheet.getLastRow(), 2);
  var rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['Available', 'Blocked', 'Sold'], true)
    .setAllowInvalid(false)
    .setHelpText('Choose: Available, Blocked, or Sold')
    .build();
  sheet.getRange(2, 7, lastRow - 1, 1).setDataValidation(rule);
}

function getExistingNumbers(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return new Set();
  return new Set(
    sheet.getRange(2, 1, lastRow - 1, 1).getValues()
      .map(function(r) { return String(r[0] || '').replace(/\D/g, ''); })
      .filter(Boolean)
  );
}

// ── Google Sheets Custom Menu UI ────────────────────────────────────────────

function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('🤖 VI SearchBot')
    .addItem('⚙ Run Sheet Auto-Heal & Maintenance', 'runMaintenanceManual')
    .addToUi();
}

function runMaintenanceManual() {
  var doc = SpreadsheetApp.getActiveSpreadsheet();
  var result = performSheetMaintenance(doc);
  var ui = SpreadsheetApp.getUi();
  ui.alert(
    '⚙ Maintenance Completed Successfully!\n\n' +
    '• Valid rows updated/repaired: ' + result.updatedRows + '\n' +
    '• Invalid rows deleted: ' + result.removedRows + '\n' +
    '• Duplicate entries removed: ' + result.duplicatesRemoved
  );
}

// ── Sheet Auto-Heal Maintenance Core ───────────────────────────────────────

function performSheetMaintenance(doc) {
  var sheet = doc.getSheetByName(SAVE_SHEET_NAME);
  if (!sheet) return { status: 'error', message: 'Sheet2 not found' };
  
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return { status: 'success', message: 'No rows to maintain', updatedRows: 0, removedRows: 0, duplicatesRemoved: 0 };
  
  var range = sheet.getRange(2, 1, lastRow - 1, SAVE_HEADERS.length);
  var values = range.getValues();
  
  var newValues = [];
  var updatedCount = 0;
  var removedCount = 0;
  
  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var num = String(row[0] || '').replace(/\D/g, '');
    if (!num) continue;
    
    // 1. Validate the number under the new strict rules (good pairs, total 1/3/5/6, no 2/4/8, no 51, no triples, etc.)
    var valStatus = validateNumber(num);
    if (!valStatus.valid) {
      removedCount++;
      continue; // Delete this number automatically
    }
    
    var rowChanged = false;
    
    // 2. Ensure Availability and Status are properly set (not Blocked, default to Available)
    if (row[5] === '' || row[5] === null || row[5] === 'Blocked') {
      row[5] = 'Available';
      rowChanged = true;
    }
    if (row[6] === '' || row[6] === null || row[6] === 'Blocked') {
      row[6] = 'Available';
      rowChanged = true;
    }
    
    // 3. Number total (index 1)
    if (row[1] === '' || row[1] === null || row[1] !== valStatus.correctedTotal) {
      row[1] = valStatus.correctedTotal;
      rowChanged = true;
    }
    
    // 4. Number Compound (index 2)
    if (row[2] === '' || row[2] === null || row[2] !== valStatus.correctedCompound) {
      row[2] = valStatus.correctedCompound;
      rowChanged = true;
    }
    
    // 5. prepaid / postpaid (index 3)
    if (row[3] === '' || row[3] === null) {
      row[3] = 'prepaid';
      rowChanged = true;
    }
    
    // 6. Pricing (index 4)
    if (row[4] === '' || row[4] === null) {
      row[4] = generateAppscriptPricing();
      rowChanged = true;
    }
    
    // 7. Price (index 7)
    if (row[7] === '' || row[7] === null || row[7] !== row[4]) {
      row[7] = row[4]; // Match Pricing
      rowChanged = true;
    }
    
    if (rowChanged) {
      updatedCount++;
    }
    
    newValues.push(row);
  }
  
  // If anything changed or rows were deleted, write back
  if (removedCount > 0 || updatedCount > 0) {
    // Clear old data range
    range.clearContent();
    if (newValues.length > 0) {
      sheet.getRange(2, 1, newValues.length, SAVE_HEADERS.length).setValues(newValues);
    }
  }
  
  // Clean duplicates in the sheet
  var duplicatesRemoved = cleanDuplicatesInSheet(sheet, SAVE_HEADERS);
  
  return {
    status: 'success',
    updatedRows: updatedCount,
    removedRows: removedCount,
    duplicatesRemoved: duplicatesRemoved
  };
}

function generateAppscriptPricing() {
  while (true) {
    // Generate random price between 2399 and 5099
    var price = Math.floor(Math.random() * (5099 - 2399 + 1)) + 2399;
    var total = String(price).split('').reduce(function(a, b) { return a + Number(b); }, 0);
    var singleTotal = computeSingleTotal(total);
    if (singleTotal === 3 || singleTotal === 5) {
      return price;
    }
  }
}
