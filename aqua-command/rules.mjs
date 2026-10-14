// Example thresholds for the DEMO ONLY; local engineering teams must approve production rules.
export const RULES = [
  { id: 'pressure-low', field: 'pressureBar', title: 'แรงดันน้ำต่ำ', unit: 'bar', direction: 'low', warning: 1.5, critical: 0.9 },
  { id: 'pressure-high', field: 'pressureBar', title: 'แรงดันน้ำสูง', unit: 'bar', direction: 'high', warning: 5.0, critical: 5.8 },
  { id: 'tank-low', field: 'tankLevelPct', title: 'ระดับถังเก็บน้ำต่ำ', unit: '%', direction: 'low', warning: 35, critical: 20 },
  { id: 'turbidity-high', field: 'turbidityNtu', title: 'ความขุ่นสูง', unit: 'NTU', direction: 'high', warning: 1.0, critical: 4.0 },
  { id: 'chlorine-low', field: 'chlorineMgL', title: 'คลอรีนอิสระต่ำ', unit: 'mg/L', direction: 'low', warning: 0.2, critical: 0.1 },
  { id: 'station-offline', field: 'online', title: 'สถานีขาดการเชื่อมต่อ', unit: '', direction: 'offline', warning: 0, critical: 0 }
];

export function severityOf(rule, val) {
  if (rule.direction === 'offline') return val === false ? 'critical' : null;
  if (typeof val !== 'number' || !Number.isFinite(val)) return null;
  if (rule.direction === 'low') return val < rule.critical ? 'critical' : val < rule.warning ? 'warning' : null;
  return val > rule.critical ? 'critical' : val > rule.warning ? 'warning' : null;
}

export function evaluateTelemetry(station) {
  return RULES.map(rule => ({rule, severity: severityOf(rule, station[rule.field]), value: station[rule.field]}))
    .filter(result => result.severity !== null);
}

export function alertMessage(alert) {
  const icons = {critical: '🔴', warning: '🟠', resolved: '🟢', info: '🔵'};
  const isSimulated = Boolean(alert.demo || alert.dataClassification === 'SIMULATED_LAB' || alert.origin === 'ADMIN_SIMULATION');
  const tag = alert.origin === 'ADMIN_SIMULATION'
    ? '[SIMULATION_OVERLAY] '
    : (alert.dataClassification === 'SIMULATED_LAB' ? '[SIMULATED_LAB] ' : (alert.demo ? '[DEMO] ' : ''));
  const area = alert.region ? (alert.region.includes('เชียงใหม่') ? alert.region : `${alert.region}, เชียงใหม่`) : 'จังหวัดเชียงใหม่';
  let sourceLabel = 'ระบบตรวจวัด กปภ. เชียงใหม่';
  if (alert.origin === 'ADMIN_SIMULATION') {
    sourceLabel = 'จำลองเหตุการณ์ผู้ดูแลระบบ (ADMIN_SIMULATION OVERLAY)';
  } else if (alert.origin === 'GATEWAY_INGEST') {
    sourceLabel = alert.dataClassification === 'SIMULATED_LAB'
      ? 'ข้อมูลเกตเวย์ทดสอบห้องปฏิบัติการ (GATEWAY_INGEST / SIMULATED_LAB)'
      : 'ข้อมูลเกตเวย์ภาคสนาม (GATEWAY_INGEST)';
  } else if (isSimulated) {
    sourceLabel = alert.dataClassification === 'SIMULATED_LAB' ? 'ข้อมูลจำลองห้องปฏิบัติการ (SIMULATED_LAB)' : 'ข้อมูลจำลอง / DEMO';
  }
  return `${icons[alert.severity] || '🔔'} ${tag}AQUA COMMAND — CHIANG MAI (${alert.severity.toUpperCase()})\n` +
    `ระดับ: ${alert.severity.toUpperCase()}\n` +
    `เหตุการณ์: ${alert.title}\n` +
    `สถานี: ${alert.stationName}\n` +
    `พื้นที่: ${area}\n` +
    `รายละเอียด: ${alert.message}\n` +
    `เวลา: ${new Intl.DateTimeFormat('th-TH', {timeZone:'Asia/Bangkok', dateStyle:'medium', timeStyle:'medium'}).format(new Date(alert.createdAt))}\n` +
    `รหัสเหตุการณ์: ${alert.id}\n` +
    `แหล่งข้อมูล: ${sourceLabel}`;
}
