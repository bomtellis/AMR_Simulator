// Adapt the retained Analytics Dashboard template to category service reviews.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL, fileURLToPath} from 'node:url';

const require = createRequire(path.join(process.env.AMR_REPORT_NODE_MODULES, '..', 'amr-report-resolver.cjs'));
const {FileBlob, SpreadsheetFile} = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const [input, output, previewDir] = process.argv.slice(2);
const {review: r, common: c} = JSON.parse(await fs.readFile(input, 'utf8'));
const template = path.join(path.dirname(fileURLToPath(import.meta.url)), 'assets', 'department_review_template.xlsx');
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(template));
const dashboard = wb.worksheets.getItem('Dashboard');
const events = wb.worksheets.getItem('Data & Targets');
const helper = wb.worksheets.getItem('_Chart Helpers');
// Replace the template's example marketing data and charts with service data.
// Retain its workbook, sheet roles and navy/cyan dashboard visual language.
for (const s of [dashboard, events, helper]) {
  s.deleteAllDrawings();
  for (const t of [...s.tables.items]) t.delete();
  const used = s.getUsedRange();
  used.unmerge();
  used.conditionalFormats.deleteAll();
  used.clear({applyTo: 'all'});
}
const departments = wb.worksheets.add('Departments');
const rules = wb.worksheets.add('Generation rules');
const timetable = wb.worksheets.add('Timetable');
const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const navy = '#152A3C', blue = '#1B354C', cyan = '#159DBA';
const names = ['Dashboard', 'Data & Targets', '_Chart Helpers', 'Departments', 'Generation rules', 'Timetable'];
const col = n => {let text = ''; for (n++; n; n = Math.floor((n - 1) / 26)) text = String.fromCharCode(65 + (n - 1) % 26) + text; return text;};
const date = text => text ? new Date(text.replace(' ', 'T') + 'Z') : null;
const literal = v => typeof v === 'string' && v.startsWith('=') ? "'" + v : v;

function title(s, title, note, last = 'J') {
  s.showGridLines = false;
  s.getRange(`A1:${last}5`).format.font = {name: 'Arial', size: 10};
  s.getRange(`A2:${last}2`).merge();
  s.getRange('A2').values = [[title]];
  s.getRange('A2').format.font = {name: 'Arial', size: 14, bold: true, color: navy};
  s.getRange(`A3:${last}4`).merge();
  s.getRange('A3').values = [[note]];
  s.getRange(`A3:${last}4`).format.wrapText = true;
  s.getRange(`A3:${last}4`).format.rowHeight = 23;
  s.freezePanes.freezeRows(5);
  s.freezePanes.freezeColumns(2);
}
function table(s, headers, rows, widths, name, start = 5) {
  const last = col(headers.length - 1), end = start + Math.max(1, rows.length);
  s.getRange(`A${start}:${last}${end}`).values = [headers, ...(rows.length ? rows.map(row => row.map(literal)) : [headers.map((_, i) => i ? null : 'No records')])];
  const used = s.getRange(`A${start}:${last}${end}`);
  used.format.font = {name: 'Arial', size: 10, color: '#22384B'};
  used.format.rowHeight = 30;
  used.format.verticalAlignment = 'center';
  used.format.wrapText = true;
  s.getRange(`A${start + 1}:${last}${end}`).format.fill = '#FFFFFF';
  s.getRange(`A${start}:${last}${start}`).format = {fill: blue, font: {name: 'Arial', size: 10, bold: true, color: '#FFFFFF'}, rowHeight: 32};
  widths.forEach((w, i) => s.getRange(`${col(i)}${start}:${col(i)}${end}`).format.columnWidth = w);
  if (rows.length) s.tables.add(`A${start}:${last}${end}`, true, name);
  return end;
}
title(events, r.name + ' | Event detail', 'One row per generated task. In period = 1 means service completed within the reporting interval. Return tasks include empty-container deliveries. Filter Status and Service to review exceptions.', 'S');
const eventEnd = table(events,
  ['Task ID', 'Parent task', 'Department ID', 'Department', 'Level', 'Service', 'Trigger', 'Generated', 'Actual service time', 'Weekday', 'In period', 'Status', 'Payload', 'AMR origin', 'AMR destination', 'Final destination', 'Service time basis', 'AMR handover', 'Generation detail'],
  r.events.map(e => [e.task_id, e.parent_task, e.department_id, e.department, e.level, e.service, e.trigger, date(e.generated), date(e.actual), e.weekday, e.in_period ? 1 : 0, e.status, e.payload, e.origin, e.destination, e.final_destination, e.basis, date(e.amr_handover), e.details]),
  [43, 40, 15, 32, 9, 15, 22, 24, 24, 12, 12, 20, 24, 30, 30, 30, 32, 24, 80], 'ServiceEvents');
for (const column of ['H', 'I', 'R']) events.getRange(`${column}6:${column}${eventEnd}`).setNumberFormat('yyyy-mm-dd hh:mm:ss');
events.getRange(`A6:S${eventEnd}`).format.rowHeight = 42;

title(departments, r.name + ' | Configured departments', 'All departments in the supplied configuration. Category scope includes enabled rules or observed tasks. Category locations may also identify source departments.', 'J');
table(departments, ['Department ID', 'Department', 'Level', 'Enabled', 'Category scope', 'Operating hours', 'Active days', 'Beds', 'Category locations', 'Shared AMR zones'],
  r.departments.map(d => [d.id, d.name, d.level, d.enabled ? 'Yes' : 'No', d.in_scope ? 'Yes' : 'No', d.hours, d.days, d.beds, d.locations, d.zones]),
  [16, 37, 10, 12, 17, 20, 38, 10, 57, 43], 'DepartmentDirectory');
departments.getRange(`A6:J${Math.max(6, r.departments.length + 5)}`).format.rowHeight = 48;
title(rules, r.name + ' | Generation rules', 'Effective category, department-group and waste-stream settings. Schedule times are release/fill times. A threshold rule has no fixed collection time; see actual collections in Timetable.', 'O');
table(rules, ['Department ID', 'Department', 'Rule ID', 'Mode', 'Payload', 'Schedule times', 'Active days', 'Alternate weeks', 'Timeframe', 'Threshold (m3)', 'Frequency / day', 'AMR origin', 'AMR destination', 'Return enabled', 'Notes'],
  r.rules.map(v => [v.id, v.department, v.instance, v.mode, v.payload, v.schedule, v.days, v.fortnightly ? 'Yes' : 'No', v.window, v.threshold, v.frequency, v.origin, v.destination, v.returns ? 'Yes' : 'No', v.notes]),
  [16, 37, 46, 24, 27, 34, 37, 18, 20, 20, 18, 38, 40, 18, 55], 'GenerationRules');
rules.getRange(`A6:O${Math.max(6, r.rules.length + 5)}`).format.rowHeight = 48;

const grouped = new Map();
for (const e of r.timetable) {
  const day = e.time.slice(0, 10), key = [day, e.department_id, e.kind].join('|');
  if (!grouped.has(key)) grouped.set(key, {day, dept: `${e.department_id} - ${e.department}`, kind: e.kind, count: 0, hours: Array.from({length: 24}, () => [])});
  const group = grouped.get(key);
  group.hours[Number(e.time.slice(11, 13))].push(e.time.slice(11));
  group.count++;
}
const timelineRows = [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, g]) => [date(g.day + ' 00:00:00'), g.dept, g.kind, g.count, ...g.hours.map(a => a.join('\n'))]);
title(timetable, r.name + ' | Service timetable', 'Each hourly cell lists exact event times (HH:MM:SS); repeats are separate tasks. Orange = configuration schedule; blue = actual delivery; green = actual AMR collection. No categories are combined.', 'AB');
table(timetable, ['Date', 'Department', 'Event', 'Count', ...Array.from({length: 24}, (_, h) => `${String(h).padStart(2, '0')}:00`)], timelineRows, [16, 39, 25, 10, ...Array(24).fill(14)], 'ServiceTimetable');
const timelineEnd = Math.max(6, timelineRows.length + 5);
timetable.getRange(`A6:A${timelineEnd}`).setNumberFormat('yyyy-mm-dd ddd');
timelineRows.forEach((row, i) => {
  const line = i + 6, height = Math.max(28, ...row.slice(4).map(v => (v.split('\n').length) * 15 + 8));
  timetable.getRange(`A${line}:AB${line}`).format.rowHeight = height;
  row.slice(4).forEach((v, j) => {if (v) timetable.getRange(`${col(j + 4)}${line}`).format.fill = row[2].startsWith('Scheduled') ? '#FFF0D6' : row[2].includes('delivery') ? '#D7F2F8' : '#E2F0DF';});
});

// Dashboard: the template's KPI / chart / variance arrangement, adapted to
// the requested weekday table and department comparison inputs.
const summaryStart = 30, summaryEnd = summaryStart + Math.max(1, r.summary.length);
dashboard.showGridLines = false;
dashboard.getRange(`A1:N${summaryEnd + 22}`).format = {fill: navy, font: {name: 'Arial', size: 10, color: '#FFFFFF'}, rowHeight: 22};
dashboard.getRange('A2:N2').merge();
dashboard.getRange('A2').values = [[r.name + ' | Department service review']];
dashboard.getRange('A2').format.font = {name: 'Arial', size: 16, bold: true, color: '#FFFFFF'};
dashboard.getRange('A3:N3').merge();
dashboard.getRange('A3').values = [[`${c.start} to ${c.end} (end excluded) | ${r.owner}`]];
dashboard.getRange('A4:N4').merge();
dashboard.getRange('A4').values = [['SIMULATED SERVICE  |  Category files are separate. Current-service inputs are amber and initially blank.']];
const summaryRows = r.summary.map(s => [s.id, s.department, s.service, ...s.values, s.total, null, null, null]);
table(dashboard, ['Dept ID', 'Department', 'Service', ...days, 'Total', 'Current total', 'Difference', 'Owner comments'], summaryRows,
  [13, 35, 17, ...Array(7).fill(10), 12, 15, 14, 38], 'WeekdayReview', summaryStart);
// Formula-backed summary is traceable to the category event sheet.
const er = column => `'Data & Targets'!$${column}$6:$${column}$${eventEnd}`;
r.summary.forEach((s, index) => {
  const row = summaryStart + 1 + index;
  dashboard.getRange(`D${row}:J${row}`).formulas = [days.map((_, d) => `=COUNTIFS(${er('C')},A${row},${er('F')},C${row},${er('J')},${col(d + 3)}$${summaryStart},${er('K')},1)`)];
  dashboard.getRange(`K${row}`).formulas = [[`=SUM(D${row}:J${row})`]];
  dashboard.getRange(`M${row}`).formulas = [[`=IF(L${row}="","",K${row}-L${row})`]];
});
dashboard.getRange(`L${summaryStart + 1}:L${summaryEnd}`).format.fill = '#FFF0D6';
dashboard.getRange(`N${summaryStart + 1}:N${summaryEnd}`).format.fill = '#FFF0D6';
dashboard.getRange(`A${summaryStart + 1}:N${summaryEnd}`).format.rowHeight = 35;
const panels = [['A6:C6', 'A7:C8', 'DELIVERIES', `=SUMIF(C${summaryStart + 1}:C${summaryEnd},"Delivery",K${summaryStart + 1}:K${summaryEnd})`],
 ['D6:F6', 'D7:F8', 'COLLECTIONS', `=SUMIF(C${summaryStart + 1}:C${summaryEnd},"Collection",K${summaryStart + 1}:K${summaryEnd})`],
 ['G6:J6', 'G7:J8', 'DEPARTMENTS IN SCOPE', r.summary.length / 2],
 ['K6:N6', 'K7:N8', 'NOT COMPLETED', r.events.filter(e => e.status !== 'Completed').length]];
for (const [labelRange, valueRange, label, value] of panels) {
  dashboard.getRange(labelRange).merge(); dashboard.getRange(labelRange.split(':')[0]).values = [[label]];
  dashboard.getRange(valueRange).merge();
  const cell = dashboard.getRange(valueRange.split(':')[0]);
  if (typeof value === 'string') cell.formulas = [[value]]; else cell.values = [[value]];
  dashboard.getRange(valueRange).format = {fill: blue, font: {name: 'Arial', size: 24, bold: true, color: '#FFFFFF'}};
}
helper.getRange('A1:D8').values = [['Weekday', 'Deliveries', 'Collections', 'Coverage hours'], ...days.map(day => [day, null, null, c.coverage_hours[day] || 0])];
days.forEach((_, i) => helper.getRange(`B${i + 2}:C${i + 2}`).formulas = [[
  `=COUNTIFS(${er('F')},"Delivery",${er('J')},A${i + 2},${er('K')},1)`,
  `=COUNTIFS(${er('F')},"Collection",${er('J')},A${i + 2},${er('K')},1)`]]);
helper.getRange('A1:D8').format.columnWidth = 20;
const chart = dashboard.charts.add('line', helper.getRange('A1:C8'));
chart.title = 'Completed service by weekday';
chart.titleTextStyle.fontSize = 14;
chart.titleTextStyle.typeface = 'Arial';
chart.setPosition('A10', 'N25');
chart.series.items[0].fill = cyan;
chart.series.items[1].fill = '#4C956C';
chart.series.items[0].line = {fill: cyan, style: 'solid', width: 3};
chart.series.items[1].line = {fill: '#4C956C', style: 'dashed', width: 2};
chart.xAxis = {axisType: 'textAxis', textStyle: {typeface: 'Arial', fontSize: 11}};
chart.yAxis = {numberFormatCode: '0', numberFormatSourceLinked: false, textStyle: {typeface: 'Arial', fontSize: 10}};
chart.yAxis.title.text = 'Completed payload tasks';
dashboard.getRange('A26:N27').merge();
dashboard.getRange('A26').values = [['Weekday coverage: ' + days.map(d => `${d} ${c.coverage_hours[d] || 0} h`).join(' | ') + '. Totals are counts across this interval, not daily averages.']];
dashboard.getRange('A26:N27').format.wrapText = true;
dashboard.freezePanes.freezeRows(5);
dashboard.freezePanes.freezeColumns(2);
let noteRow = summaryEnd + 3;
for (const note of [...c.notes, `Source CSV: ${c.sources.csv || 'Test data'}`, `Configuration: ${c.sources.config || 'Test data'}`, `Configuration SHA-256: ${c.sources.config_sha256 || ''}`]) {
  dashboard.getRange(`A${noteRow}:N${noteRow + 1}`).merge();
  dashboard.getRange(`A${noteRow}`).values = [[note]];
  dashboard.getRange(`A${noteRow}:N${noteRow + 1}`).format.wrapText = true;
  noteRow += 2;
}
wb.recalculate();
// A failed calculation must fail the export, not silently disagree with PDF.
const got = [dashboard.getRange('A7').values[0][0], dashboard.getRange('D7').values[0][0]];
if (got[0] !== r.total_deliveries || got[1] !== r.total_collections) throw new Error(`Workbook totals ${got} do not reconcile with event totals ${r.total_deliveries},${r.total_collections}`);
console.log((await wb.inspect({kind: 'region', sheetId: 'Dashboard', range: 'A6:N8', maxChars: 1500, tableMaxRows: 3, tableMaxCols: 14})).ndjson);
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
if (previewDir) {
  await fs.mkdir(previewDir, {recursive: true});
  for (const name of names) {
    const preview = await wb.render({sheetName: name, range: name === 'Dashboard' ? 'A1:N37' : name === 'Timetable' ? 'A1:AB11' : name === '_Chart Helpers' ? 'A1:D8' : name === 'Data & Targets' ? 'A1:S11' : name === 'Generation rules' ? 'A1:O12' : 'A1:J12', scale: 1, format: 'png'});
    await fs.writeFile(path.join(previewDir, `${r.key}_${name.replace(/[^a-zA-Z]/g, '_')}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}
