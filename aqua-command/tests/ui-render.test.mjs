import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createContext,runInContext} from 'node:vm';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const station={id:'CM-01',name:'เชียงใหม่',region:'ภาคเหนือ',zone:'เหนือ',x:30,y:24,pressureBar:2.4,tankLevelPct:78,flowM3h:1860,turbidityNtu:.3,chlorineMgL:.5,online:true,hasTelemetry:true,status:'normal'};
const alert={id:'AL-001',createdAt:new Date().toISOString(),severity:'warning',stationId:station.id,stationName:station.name,title:'ตัวอย่าง',message:'แรงดันน้ำต่ำ',region:station.region,demo:true,ruleId:'pressure-low'};
const fixture={mode:'demo',serverTime:new Date().toISOString(),stations:[station],alerts:[alert],history:Array.from({length:12},(_,i)=>({time:new Date(Date.now()-(12-i)*900_000).toISOString(),pressure:2.2+i/20,flow:12+i/3,tank:65+i/10})),metrics:{online:1,total:1,normal:1,warning:0,critical:0,activeStations:0,pressure:2.4,tank:78,flow:1860,turbidity:.3,activeAlertCount:1},telegram:{configured:false,demoForwarding:false,reminderMinutes:30},queueStats:{sent:0,pending:0,failed:0},queueRecent:[],rules:[{id:'pressure-low',title:'แรงดันน้ำต่ำ',direction:'low',warning:1.5,critical:.9,unit:'bar'}]};
test('all five dashboard views render with mock telemetry',async()=>{
 const app={innerHTML:''};
 const doc={activeElement:null,querySelector:s=>s==='#app'?app:null,addEventListener(){},body:{classList:{toggle(){}}}};
 const ctx=createContext({console,document:doc,window:{scrollTo(){}},setInterval(){},setTimeout(){},clearTimeout(){},fetch:async()=>({ok:true,json:async()=>fixture}),EventSource:class{},Intl,Date,Math,Number,JSON,String,Array,Object,Set,Promise,URL});
 runInContext(readFileSync(path.join(root,'public','app.js'),'utf8'),ctx);
 await new Promise(resolve=>setTimeout(resolve,10));
 for(const page of ['overview','stations','alerts','analytics','settings']){
  runInContext(`state.view='${page}';render()`,ctx);
  assert.match(app.innerHTML,/<main class="content">/);
  assert.match(app.innerHTML,/<h1>/);
  assert.doesNotMatch(app.innerHTML,/ReferenceError|TypeError|Cannot read properties/);
 }
});
