// Editable, range-backed stacked charts. Uses the same runtime as other AMR Excel exports.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(path.join(process.env.AMR_REPORT_NODE_MODULES,'..','amr-report-resolver.cjs'));
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const [input,output,previewDir]=process.argv.slice(2);
const data=JSON.parse(await fs.readFile(input,'utf8'));
if(data.counts.length>1048565)throw new Error('Too many movement cohorts for one workbook. Export a shorter run.');
const wb=Workbook.create();
const navy='#243B53', muted='#526777', body='#243746';
const col=n=>{let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
const literal=v=>typeof v==='string'&&v.startsWith('=')?"'"+v:v;
const quote=v=>'"'+String(v).replaceAll('"','""')+'"';
const dayValue=key=>data.day_mode==='calendar'?new Date(key+'T00:00:00Z'):Number(key.slice(4));
const dayFormat=data.day_mode==='calendar'?'yyyy-mm-dd':'"Day "0';
const names=new Set(['movement counts']);
const sheets=data.lifts.map(identity=>{
 let base=identity.replace(/[\[\]:*?/\\]/g,'_').replace(/^'+|'+$/g,'').slice(0,31)||'Lift';
 if(base.toLowerCase()==='history')base='Lift History';
 let name=base,n=1;while(names.has(name.toLowerCase())){const suffix=' ('+(++n)+')';name=base.slice(0,31-suffix.length)+suffix;}
 names.add(name.toLowerCase());return {identity,sheet:wb.worksheets.add(name)};
});
const source=wb.worksheets.add('Movement counts');
source.showGridLines=false;
for(let row=2;row<=6;row++)source.getRange(`A${row}:F${row}`).merge();
source.getRange('A2').values=[['Lift movement counts']];
source.getRange('A2').format.font={name:'Arial',size:14,bold:true,color:navy};
source.getRange('A3').values=[['Source: '+data.source]];
source.getRange('A4').values=[['Recorded movements: '+data.movements]];
source.getRange('A5').values=[['Counts use movement starts. Each mixed-purpose movement is counted once.']];
source.getRange('A6').values=[['Event SHA-256: '+data.source_sha256]];
source.getRange('A3:F6').format.font={name:'Arial',size:10,color:muted};
const rows=data.counts.map(r=>[literal(r.lift_id),dayValue(r.day),literal(r.purpose),literal(data.purposes.find(p=>p.id===r.purpose).label),r.minute/1440,r.count]);
const sourceEnd=Math.max(10,9+rows.length);
source.getRange('A9:F9').values=[['Lift ID','Day','Purpose code','Trip purpose','Time of day','Movements']];
if(rows.length)source.getRange(`A10:F${sourceEnd}`).values=rows;
source.getRange(`A9:F${sourceEnd}`).format.font={name:'Arial',size:10,color:body};
source.getRange(`A9:F${sourceEnd}`).format.rowHeight=21;
const table=source.tables.add(`A9:F${sourceEnd}`,true,'LiftMovementCounts');
table.style='TableStyleMedium2';table.showFilterButton=true;
source.getRange(`B10:B${sourceEnd}`).setNumberFormat(dayFormat);
source.getRange(`E10:E${sourceEnd}`).setNumberFormat('hh:mm');
source.getRange(`F10:F${sourceEnd}`).setNumberFormat('0');
[24,18,27,29,19,18].forEach((w,i)=>source.getRange(`${col(i)}9:${col(i)}${sourceEnd}`).format.columnWidth=w);
source.getRange('A9:F9').format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:28};
source.freezePanes.freezeRows(9);
const purposes=data.purposes.length?data.purposes:[{id:'unknown',label:'Unclassified',colour:'#A7A7A7'}];
const last=col(purposes.length),totalCol=col(purposes.length+1);
const slots=Array.from({length:1440/data.interval_minutes},(_,i)=>i*data.interval_minutes);
const end=32+slots.length;
for(const {identity,sheet} of sheets){
 sheet.showGridLines=false;sheet.tabColor=navy;
 sheet.getRange(`A2:L${end}`).format.font={name:'Arial',size:10,color:body};
 sheet.getRange(`A2:L${end}`).format.rowHeight=20;
 sheet.getRange(`A2:L${end}`).format.columnWidth=11;
 sheet.getRange('A2').format.rowHeight=8;
 sheet.getRange('A3').values=[['Lift ID']];sheet.getRange('B3').values=[[literal(identity)]];
 sheet.getRange('A4').values=[['Day']];
 sheet.getRange('B4').values=[[data.initial_day==='All days'?'All days':dayValue(data.initial_day)]];
 sheet.getRange('B4').setNumberFormat(dayFormat);
 sheet.getRange('D4').values=[['Empty repositioning']];
 sheet.getRange('F4').values=[[data.include_reposition?'Yes':'No']];
 sheet.getRange('B4').format={fill:'#FFF2CC',font:{name:'Arial',size:10,color:'#245A81'},borders:{preset:'outside',style:'thin',color:'#9AA9B7'}};
 sheet.getRange('F4').format={fill:'#FFF2CC',font:{name:'Arial',size:10,color:'#245A81'},borders:{preset:'outside',style:'thin',color:'#9AA9B7'}};
 sheet.getRange('B4').format.columnWidth=19;
 sheet.getRange('A5').format.rowHeight=8;
 sheet.getRange('A6').format.font={name:'Arial',size:10,color:muted};
 sheet.getRange('A6:L6').merge();
 sheet.getRange('A7:L7').merge();
 sheet.getRange('A7').values=[['Purpose colours follow recorded service categories. Outbound and return trips share their purpose.']];
 sheet.getRange('A7').format.font={name:'Arial',size:10,color:muted};
 sheet.getRange('P2').values=[['Available days']];
 sheet.getRange(`P3:P${3+data.days.length}`).values=[['All days'],...data.days.map(day=>[dayValue(day)])];
 sheet.getRange(`P4:P${Math.max(4,3+data.days.length)}`).setNumberFormat(dayFormat);
 sheet.getRange('P2:P'+(3+data.days.length)).format.columnWidth=19;
 sheet.getRange('B4').dataValidation={rule:{type:'list',formula1:`$P$3:$P$${3+data.days.length}`},errorAlert:{style:'stop',title:'Choose an available day',message:'Use All days or a day from the list.'}};
 sheet.getRange('F4').dataValidation={list:{inCellDropDown:true,source:['Yes','No']}};
 sheet.getRange(`A32:${totalCol}32`).values=[['Time',...purposes.map(p=>literal(p.label)),'Total']];
 sheet.getRange(`A33:A${end}`).values=slots.map(m=>[m/1440]);
 sheet.getRange(`A33:A${end}`).setNumberFormat('hh:mm');
 const formulas=slots.map((m,i)=>purposes.map(p=>{
  const common=`'Movement counts'!$F$10:$F$${sourceEnd},'Movement counts'!$A$10:$A$${sourceEnd},$B$3,'Movement counts'!$C$10:$C$${sourceEnd},${quote(p.id)},'Movement counts'!$E$10:$E$${sourceEnd},$A${33+i}`;
  const filtered=`IF($B$4="All days",SUMIFS(${common}),SUMIFS(${common},'Movement counts'!$B$10:$B$${sourceEnd},$B$4))`;
  return '='+ (p.id==='empty_lift_reposition'?`IF($F$4="Yes",${filtered},0)`:filtered);
 }));
 sheet.getRange(`B33:${last}${end}`).formulas=formulas;
 sheet.getRange(`${totalCol}33`).formulas=[[`=SUM(B33:${last}33)`]];
 sheet.getRange(`${totalCol}33:${totalCol}${end}`).fillDown();
 sheet.getRange(`B33:${totalCol}${end}`).setNumberFormat('0');
 sheet.getRange(`A32:${totalCol}32`).format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:36,wrapText:true,verticalAlignment:'center'};
 sheet.getRange('A6').formulas=[[`=IF(SUM(${totalCol}33:${totalCol}${end})=0,"No recorded movements for this selection.","All days sums counts by ${data.day_mode==='calendar'?'clock time':'time within each simulation day'}. The vertical scale stays fixed for day comparisons.")`]];
 const chart=sheet.charts.add('bar',sheet.getRange(`A32:${last}${end}`));
 chart.barOptions.direction='column';chart.barOptions.grouping='stacked';chart.barOptions.overlap=100;chart.barOptions.gapWidth=35;
 chart.title=identity+' - Movements by purpose';chart.titleTextStyle.fontSize=15;chart.titleTextStyle.typeface='Arial';
 chart.legend={position:'top',textStyle:{typeface:'Arial',fontSize:11}};
 chart.xAxis={axisType:'textAxis',numberFormatCode:'hh:mm',numberFormatSourceLinked:false,tickLabelInterval:Math.max(1,120/data.interval_minutes),majorGridlines:{fill:'#FFFFFF',style:'solid',width:.1},textStyle:{typeface:'Arial',fontSize:10}};
 const allDayTotals=new Map();for(const r of data.counts)if(r.lift_id===identity)allDayTotals.set(r.minute,(allDayTotals.get(r.minute)||0)+r.count);
 const wholeRunPeak=Math.max(0,...allDayTotals.values());
 const rawStep=Math.max(1,wholeRunPeak/6),factor=10**Math.floor(Math.log10(rawStep));
 const niceStep=[1,2,5,10].find(n=>n*factor>=rawStep)*factor;
 chart.yAxis={min:0,max:6*niceStep,numberFormatCode:'0',numberFormatSourceLinked:false,majorGridlines:{fill:'#E3E9EF',style:'solid',width:.5},textStyle:{typeface:'Arial',fontSize:10}};
 chart.yAxis.title.text='Movements per '+data.interval_minutes+' minutes';chart.xAxis.title.text=data.day_mode==='calendar'?'Time of day':'Time within simulation day';
 chart.dataLabels={showValue:false};chart.setPosition('A8','L30');
 chart.series.items.forEach((s,i)=>{s.fill=purposes[i].colour;});
 sheet.freezePanes.freezeRows(7);
}
wb.recalculate();
const verify=(entry,day,include)=>{
 const wanted=new Map();for(const r of data.counts)if(r.lift_id===entry.identity&&(day==='All days'||r.day===day))wanted.set(r.minute+'|'+r.purpose,(wanted.get(r.minute+'|'+r.purpose)||0)+r.count);
 const actual=entry.sheet.getRange(`B33:${last}${end}`).values;
 for(let i=0;i<slots.length;i++)for(let j=0;j<purposes.length;j++){
  const expected=!include&&purposes[j].id==='empty_lift_reposition'?0:wanted.get(slots[i]+'|'+purposes[j].id)||0;
  if(actual[i][j]!==expected)throw new Error(`Chart count mismatch: ${entry.identity}, ${day}, ${slots[i]}, ${purposes[j].id}: ${actual[i][j]} != ${expected}`);
 }
};
for(const entry of sheets)verify(entry,data.initial_day,data.include_reposition);
if(previewDir){
 await fs.mkdir(previewDir,{recursive:true});
 for(let i=0;i<sheets.length;i++){
  const entry=sheets[i];
  if(data.days.length){entry.sheet.getRange('B4').values=[[dayValue(data.days[data.days.length-1])]];entry.sheet.getRange('F4').values=[['No']];wb.recalculate();verify(entry,data.days[data.days.length-1],false);}
  entry.sheet.getRange('B4').values=[[data.initial_day==='All days'?'All days':dayValue(data.initial_day)]];entry.sheet.getRange('F4').values=[[data.include_reposition?'Yes':'No']];wb.recalculate();verify(entry,data.initial_day,data.include_reposition);
  const blob=await wb.render({sheetName:entry.sheet.name,range:'A2:L30',scale:1.25,format:'png'});
  await fs.writeFile(path.join(previewDir,`lift-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
 }
 const blob=await wb.render({sheetName:'Movement counts',range:'A2:F'+Math.min(sourceEnd,20),scale:1.25,format:'png'});
 await fs.writeFile(path.join(previewDir,'counts.png'),new Uint8Array(await blob.arrayBuffer()));
 console.log((await wb.inspect({kind:'drawing',maxChars:1800})).ndjson);
}
await(await SpreadsheetFile.exportXlsx(wb)).save(output);
console.log(JSON.stringify({lifts:sheets.length,movements:data.movements,days:data.days.length}));
