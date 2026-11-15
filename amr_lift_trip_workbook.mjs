// All recorded lift trips, with the existing third-party fields at the right.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

const require = createRequire(path.join(process.env.AMR_REPORT_NODE_MODULES, '..', 'amr-report-resolver.cjs'));
const {Workbook, SpreadsheetFile} = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const [input, output, previewDir] = process.argv.slice(2);
const data = JSON.parse(await fs.readFile(input, 'utf8'));
// Five context rows plus the header must fit inside Excel's worksheet limit.
if (data.rows.length > 1048570) throw new Error('Too many trips for one Excel table (maximum 1,048,570).');
const wb = Workbook.create();
const sheet = wb.worksheets.add('Lift trips');
sheet.showGridLines = false;
sheet.tabColor = '#1F4E78';
const column = n => {let s = ''; for (n++; n; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + (n - 1) % 26) + s; return s;};
const last = column(data.headers.length - 1), start = 5, end = Math.max(start + 1, start + data.rows.length);
const literal = v => typeof v === 'string' && v.startsWith('=') ? "'" + v : v;
sheet.getRange('A2').values = [['Lift trips']];
sheet.getRange('A2').format.font = {name: 'Arial', size: 14, bold: true, color: '#1F4E78'};
sheet.getRange('A3').values = [['All recorded transfer and empty reposition trips. Origin and Destination Number = simulator floor + 1.']];
sheet.getRange('A3').format.font = {name: 'Arial', size: 10, italic: true, color: '#44546A'};
sheet.getRange(`A${start}:${last}${start}`).values = [data.headers];
if (data.rows.length) {
  // Leave the last column for live Excel formulas, not saved concatenated text.
  const dataLast = column(data.headers.length - 2);
  sheet.getRange(`A${start + 1}:${dataLast}${end}`).values = data.rows.map(row => row.map((value, i) =>
    data.time_kind === 'datetime' && [5, 6].includes(i) && value ? new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z') : literal(value)));
  const importStart = data.headers.indexOf('Start Seconds');
  const fields = Array.from({length: 7}, (_, i) => column(importStart + i));
  const formula = row => '=' + fields.map((c, i) => i === 5 ? `${c}${row}` : `TEXT(${c}${row},"0")`).join('&","&');
  sheet.getRange(`${last}${start + 1}`).formulas = [[formula(start + 1)]];
  if (data.rows.length > 1) sheet.getRange(`${last}${start + 1}:${last}${end}`).fillDown();
}
const table = sheet.tables.add(`A${start}:${last}${end}`, true, 'LiftTrips');
table.showFilterButton = true;
table.style = 'TableStyleMedium2';
const used = sheet.getRange(`A${start}:${last}${end}`);
used.format.font = {name: 'Arial', size: 10, color: '#243746'};
used.format.rowHeight = 24;
used.format.verticalAlignment = 'center';
const widths = [14, 22, 23, 24, 35, 27, 27, 18, 19, 17, 19, 21, 21, 16, 16, 29, 23, 22, 24, 29, 25, 28, 18, 19, 22, 18, 21, 20, 22, 57];
widths.forEach((width, i) => sheet.getRange(`${column(i)}${start}:${column(i)}${end}`).format.columnWidth = width);
for (const c of ['A', 'J', 'M', 'Q', 'R']) sheet.getRange(`${c}${start + 1}:${c}${end}`).setNumberFormat(c === 'A' ? '0' : '0.###');
sheet.getRange(`W${start + 1}:AA${end}`).setNumberFormat('0');
sheet.getRange(`AC${start + 1}:AC${end}`).setNumberFormat('0');
sheet.getRange(`AB${start + 1}:AB${end}`).setNumberFormat('@');
sheet.getRange(`F${start + 1}:G${end}`).setNumberFormat(data.time_kind === 'datetime' ? 'dd/mm/yyyy hh:mm:ss.000' : '0.###" s"');
sheet.getRange(`A${start}:${last}${start}`).format = {
  fill: '#1F4E78', font: {name: 'Arial', size: 10, bold: true, color: '#FFFFFF'},
  rowHeight: 34, horizontalAlignment: 'center', verticalAlignment: 'center', wrapText: true,
};
sheet.freezePanes.freezeRows(start);
sheet.freezePanes.freezeColumns(2);

// Keep unused lifts visible without inventing trip rows in the movement table.
const lifts = wb.worksheets.add('Lifts');
lifts.showGridLines = false;
lifts.getRange('A2').values = [['Configured lifts']];
lifts.getRange('A2').format.font = {name: 'Arial', size: 14, bold: true, color: '#1F4E78'};
lifts.getRange('A3').values = [['Source: ' + data.source]];
lifts.getRange('A3').format.font = {name: 'Arial', size: 10, color: '#44546A'};
lifts.getRange('A4').values = [['Event SHA-256: ' + data.source_sha256]];
const liftEnd = 5 + data.lifts.length;
lifts.getRange(`A5:B${liftEnd}`).values = [['Lift ID', 'Trips'], ...data.lifts.map(l => [literal(l.lift_id), l.trips])];
lifts.tables.add(`A5:B${liftEnd}`, true, 'ConfiguredLifts').style = 'TableStyleMedium2';
lifts.getRange(`A5:B${liftEnd}`).format.font = {name: 'Arial', size: 10, color: '#243746'};
lifts.getRange(`A5:B${liftEnd}`).format.rowHeight = 24;
lifts.getRange('A5:B5').format = {fill: '#1F4E78', font: {name: 'Arial', size: 10, bold: true, color: '#FFFFFF'}};
lifts.getRange(`A5:A${liftEnd}`).format.columnWidth = Math.max(28, ...data.lifts.map(l => Math.min(80, l.lift_id.length + 4)));
lifts.getRange(`B5:B${liftEnd}`).format.columnWidth = 14;
lifts.getRange(`B6:B${liftEnd}`).setNumberFormat('0');
lifts.freezePanes.freezeRows(5);
wb.recalculate();
if (data.rows.length) {
  const actual = sheet.getRange(`${last}6:${last}${end}`).values;
  const importStart = data.headers.indexOf('Start Seconds');
  for (let i = 0; i < data.rows.length; i++) {
    const expected = data.rows[i].slice(importStart).join(',');
    if (actual[i][0] !== expected) throw new Error(`Concatenation mismatch on trip ${i + 1}`);
  }
}
if (previewDir) {
  // Exercise edit-driven recalculation, then restore the source data for export.
  if (data.rows.length) {
    const original = sheet.getRange('W6').values[0][0];
    const before = sheet.getRange('AD6').values[0][0];
    sheet.getRange('W6').values = [[original + 7]];
    wb.recalculate();
    const after = sheet.getRange('AD6').values[0][0];
    if (after === before || after.split(',')[0] !== String(original + 7)) throw new Error('Concatenation did not recalculate after an edit.');
    sheet.getRange('W6').values = [[original]];
    wb.recalculate();
    if (sheet.getRange('AD6').values[0][0] !== before) throw new Error('Failed to restore the original trip.');
  }
  await fs.mkdir(previewDir, {recursive: true});
  for (const [name, range, filename] of [['Lift trips', `A2:J${Math.min(end, 12)}`, 'trip-details.png'],
    ['Lift trips', `W5:AD${Math.min(end, 12)}`, 'third-party-formulas.png'], ['Lifts', `A2:H${Math.min(liftEnd, 15)}`, 'lifts.png']]) {
    const blob = await wb.render({sheetName: name, range, scale: 1.5, format: 'png'});
    await fs.writeFile(path.join(previewDir, filename), new Uint8Array(await blob.arrayBuffer()));
  }
  console.log((await wb.inspect({kind: 'table', range: 'Lift trips!W5:AD8', include: 'values,formulas', maxChars: 2500, tableMaxRows: 4, tableMaxCols: 8})).ndjson);
  console.log((await wb.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!', options: {useRegex: true, maxResults: 10}, maxChars: 1000})).ndjson);
}
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
