# Google Apps Script Agent Skill & Sheet Monitoring Runbook

This specialized **Skill File** provides persistent documentation, code backups, and a sheet modifications monitoring system for the Google Apps Script integration (`google-appscript-sheet2.gs`). It governs how the remote Google Sheet coordinates number filtering, validations, remote maintenance, and automatic duplicate cleanups.

---

## 🛠️ Google Apps Script Overview & API Specs

The Apps Script resides at the Google Sheets Macro level, bound to the Spreadsheet ID:
`1y2Gk6UPAwkXdx0-AQi80Saeu0frZWtaPzjK9_ssIX9Q`

It exposes a **Web App URL** that processes GET and POST requests:

### 1. HTTP GET API (`doGet`)
* **`?action=maintenance` or `?action=autoheal`**: Triggers a remote database clean-up and auto-heal loop, verifying all rows, correcting sum errors, validating digit pairs, assigning missing pricing, and deleting invalid entries.
* **`?sheet=found`**: Returns JSON data for found numbers in `Sheet2`.
* **`?sheet=searched`**: Returns JSON data for searched numbers in `SearchedNumbers`.
* **`?sheet=all` / Default**: Returns combined data from all sheets.

### 2. HTTP POST API (`doPost`)
* **Found Number Entry** (`type: 'found'`): Appends new fancy mobile numbers, automatically validating them, calculating totals, assigning pricing, and rejecting non-compliant numbers.
* **Searched Number Entry** (`type: 'searched'`): Appends numbers searched by workers to prevent redundant lookup overhead.

---

## 🎛️ Number Validation Rules & Filters Reference

Every number processed by the bot or sheet must pass the strict validation pipeline (`validateNumber`):

1. **Length Requirement**: Must be at least `6` digits.
2. **Digit Exclusion**: Numbers containing **`2`, `4`, or `8`** are strictly forbidden and rejected.
3. **Double Zero Guard**: Double zero (`00`) sequences are strictly forbidden.
4. **Digit-Triple Guard**: Triple digits (e.g., `777`, `999`) are strictly forbidden.
5. **Single Total & Compound Total Rules**:
   - **Compound Sum**: Cannot equal `51`.
   - **Single Total (Reduced Sum)**: Must be strictly in `[1, 3, 5, 6]`.
6. **Zero Count Rule (RELAXED)**: The limit of maximum one `0` in the first 4 digits has been relaxed/removed since the starting digits are fixed operator prefixes.
7. **Adjacent Digit Pair Constraints (RELAXED)**:
   - Non-zero adjacent digit transitions must reside in the approved list:
     `'13', '31', '15', '51', '17', '71', '19', '91', '33', '35', '53', '37', '73', '39', '93', '55', '57', '75', '59', '95', '79', '97', '99'`
   - This rule is relaxed for the starting fixed operator digits (the transition loop starts at index `3`, checking transitions from the 4th/5th digits onwards).
   - **Digit 6 Exceptions**:
     * **Exception A**: `96` is allowed if it is located at the **very end** of the number.
     * **Exception B**: Sequence `969` is allowed anywhere in the number (exempting consecutive transitions `96` and `69`).

---

## 📝 Sheet Modifications & Filter Evolution Log

Use this section to log and monitor changes to the validation criteria, sheet headers, or database schema.

| Date | Type | Description | Changed Rules / Code Block |
| :--- | :--- | :--- | :--- |
| **2026-05-22** | **Filter Update** | Relaxed operator starting fixed digits validation | Starts adjacent transition checks at index 3, and removed first-4 zero restriction. |
| **2026-05-22** | **Filter Update** | Permitted Ending `96` and Sequence `969` | Added digit `6` transition exceptions in adjacent pair validator check. |
| **2026-05-22** | **Schema Update** | Added Price Validation & Generation | Automated pricing assignments (2399–5099 with reduced sums of 3 or 5). |
| **2026-05-22** | **Maintenance** | Integrated Duplicate Eliminator | Automatically checks and deletes exact duplicate numbers on entry and run. |

---

## 🚀 Guidelines for Modifying Apps Script Code

When user requests require editing Google Apps Script logic:

1. **Keep Parity with Crawler**: Any changes made to digit validators in `google-appscript-sheet2.gs` (e.g., changing good pairs, adding exceptions) must be mirrored exactly in `vi-number-bot-one-worker.js` to ensure the bot doesn't waste bandwidth scraping numbers that the Google Sheet will subsequently reject.
2. **Validate Apps Script ES5/ES6 compatibility**: Apps Script runs in V8 but uses old-school JavaScript patterns. Standard imports/requires are not supported; use standard functions and global variables.
3. **Always Run Auto-Heal**: After changing validation rules, it is recommended to request a remote auto-heal cycle (`?action=autoheal`) so the spreadsheet database automatically cleanses, upgrades, or deletes older entries based on the new rules.

---

## 📂 Source Code Backup (`google-appscript-sheet2.gs`)

In case the Apps Script macro is lost, corrupted, or overwritten on Google Sheets, here is the full, clean source backup:

```javascript
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
  
  if (/[248]/.test(s)) return { valid: false, reason: 'Contains 2/4/8: ' + s };
  if (s.indexOf('00') !== -1) return { valid: false, reason: 'Contains double zero 00' };
  
  var tripMatch = s.match(/(\d)\1\1/);
  if (tripMatch) return { valid: false, reason: 'Contains triple digit: ' + tripMatch[0] };
  
  var GOOD_PAIRS = [
    '11', '13', '31', '15', '51', '17', '71', '19', '91',
    '33', '35', '53', '37', '73', '39', '93',
    '55', '57', '75', '59', '95', '79', '97', '99'
  ];
  // Relax starting fixed digits validation: start transition checks from index 3 (the 4th digit) onwards
  for (var i = 3; i < s.length - 1; i++) {
    var pair = s.substring(i, i + 2);
    if (pair.indexOf('0') !== -1) continue;
    if (GOOD_PAIRS.indexOf(pair) === -1) {
      if (pair === '96' && i === s.length - 2) {
        continue;
      }
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
    var action = e && e.parameter && e.parameter.action ? String(e.parameter.action).toLowerCase() : '';
    if (action === 'maintenance' || action === 'autoheal') {
      var maintResult = performSheetMaintenance(doc);
      return jsonResponse(maintResult);
    }

    var sheetParam = e && e.parameter && e.parameter.sheet ? e.parameter.sheet : '';
    if (sheetParam === 'searched') {
      var sh = doc.getSheetByName(SEARCH_SHEET_NAME);
      if (!sh) return jsonResponse({ status: 'success', data: [] });
      return jsonResponse({ status: 'success', data: getRowsFromSheet(sh, SEARCH_READ_FIELDS) });
    }
    if (sheetParam === 'found') {
      var sh2 = doc.getSheetByName(SAVE_SHEET_NAME);
      if (!sh2) return jsonResponse({ status: 'success', data: [] });
      return jsonResponse({ status: 'success', data: getRowsFromSheet(sh2, READ_FIELDS) });
    }
    if (sheetParam && sheetParam !== 'all') {
      var sh3 = doc.getSheetByName(sheetParam);
      if (!sh3) return jsonResponse({ status: 'error', message: sheetParam + ' not found in the document.' });
      return jsonResponse({ status: 'success', data: getRowsFromSheet(sh3) });
    }

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
    
    var valStatus = validateNumber(num);
    if (!valStatus.valid) {
      removedCount++;
      continue;
    }
    
    var rowChanged = false;
    
    if (row[5] === '' || row[5] === null || row[5] === 'Blocked') {
      row[5] = 'Available';
      rowChanged = true;
    }
    if (row[6] === '' || row[6] === null || row[6] === 'Blocked') {
      row[6] = 'Available';
      rowChanged = true;
    }
    if (row[1] === '' || row[1] === null || row[1] !== valStatus.correctedTotal) {
      row[1] = valStatus.correctedTotal;
      rowChanged = true;
    }
    if (row[2] === '' || row[2] === null || row[2] !== valStatus.correctedCompound) {
      row[2] = valStatus.correctedCompound;
      rowChanged = true;
    }
    if (row[3] === '' || row[3] === null) {
      row[3] = 'prepaid';
      rowChanged = true;
    }
    if (row[4] === '' || row[4] === null) {
      row[4] = generateAppscriptPricing();
      rowChanged = true;
    }
    if (row[7] === '' || row[7] === null || row[7] !== row[4]) {
      row[7] = row[4];
      rowChanged = true;
    }
    
    if (rowChanged) {
      updatedCount++;
    }
    
    newValues.push(row);
  }
  
  if (removedCount > 0 || updatedCount > 0) {
    range.clearContent();
    if (newValues.length > 0) {
      sheet.getRange(2, 1, newValues.length, SAVE_HEADERS.length).setValues(newValues);
    }
  }
  
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
    var price = Math.floor(Math.random() * (5099 - 2399 + 1)) + 2399;
    var total = String(price).split('').reduce(function(a, b) { return a + Number(b); }, 0);
    var singleTotal = computeSingleTotal(total);
    if (singleTotal === 3 || singleTotal === 5) {
      return price;
    }
  }
}
```
