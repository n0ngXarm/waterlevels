import test from 'node:test';
import assert from 'node:assert/strict';
import {RULES, severityOf, evaluateTelemetry, alertMessage} from '../rules.mjs';
const rule=id=>RULES.find(x=>x.id===id);
test('low-pressure thresholds are strict and ordered',()=>{
  assert.equal(severityOf(rule('pressure-low'),.89),'critical');
  assert.equal(severityOf(rule('pressure-low'),.9),'warning');
  assert.equal(severityOf(rule('pressure-low'),1.49),'warning');
  assert.equal(severityOf(rule('pressure-low'),1.5),null);
  assert.equal(severityOf(rule('pressure-low'),null),null);
});
test('high-turbidity and offline rules',()=>{
  assert.equal(severityOf(rule('turbidity-high'),4.01),'critical');
  assert.equal(severityOf(rule('turbidity-high'),4.0),'warning');
  assert.equal(severityOf(rule('station-offline'),false),'critical');
  assert.equal(severityOf(rule('station-offline'),true),null);
});
test('evaluator returns only violated known metrics',()=>{
  const a=evaluateTelemetry({pressureBar:0.7,tankLevelPct:70,turbidityNtu:0.5,chlorineMgL:.5,online:true});
  assert.deepEqual(a.map(x=>x.rule.id),['pressure-low']);
});
test('telegram messages include identifiable event and DEMO label',()=>{
  const msg=alertMessage({id:'AL-T100',severity:'critical',demo:true,title:'แรงดันต่ำ',stationName:'เชียงใหม่',region:'ภาคเหนือ',message:'0.6 bar',createdAt:'2026-10-14T02:00:00.000Z'});
  assert.match(msg,/\[DEMO\]/);assert.match(msg,/AL-T100/);assert.match(msg,/เชียงใหม่/);
});
