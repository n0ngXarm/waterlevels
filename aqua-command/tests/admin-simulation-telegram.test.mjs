import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';
import { spawn } from 'node:child_process';

function openPort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const p = srv.address().port;
      srv.close(() => resolve(p));
    });
    srv.on('error', reject);
  });
}

const ADMIN_KEY = 'test-admin-secret-key-at-least-32-chars';
const VIEWER_KEY = 'test-viewer-read-key-at-least-32-chars';
const GW_PATAN_KEY = 'test-gw-patan-secret-at-least-32-chars';

test('Zone B: Admin Simulation, Mock Telegram, and Environment Isolation', { timeout: 20_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-admin-sim-test-'));

  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  const port = await openPort();
  const env = {
    ...process.env,
    APP_ENV: 'lab',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(port),
    STATION_REGISTRY_PATH: path.join(root, '..', 'config', 'station_registry.json'),
    ADMIN_API_KEY: ADMIN_KEY,
    VIEWER_API_KEY: VIEWER_KEY,
    GATEWAY_TOKEN_GW_CM01_PATAN: GW_PATAN_KEY,
    REQUIRE_AUTH_FOR_READ: 'true',
    TELEGRAM_BOT_TOKEN: '',
    TELEGRAM_CHAT_ID: '',
    TELEGRAM_MIN_GAP_MS: '50'
  };

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${port}`;

  async function api(p, { method = 'GET', body = null, key = null, cookie = null } = {}) {
    const headers = {};
    if (body) headers['Content-Type'] = 'application/json';
    if (key) headers['X-API-Key'] = key;
    if (cookie) headers['Cookie'] = cookie;
    const res = await fetch(`${base}${p}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined
    });
    const json = await res.json().catch(() => null);
    return { status: res.status, ok: res.ok, json, headers: res.headers };
  }

  try {
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died');
      try {
        const r = await fetch(`${base}/api/health`);
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    // 1. Ingest real telemetry from gateway to set baseline
    const ingestRes = await fetch(`${base}/api/v1/ingest/telemetry`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Gateway-Token': GW_PATAN_KEY
      },
      body: JSON.stringify({
        stationId: 'CM-01',
        collectorId: 'GW-CM01-PATAN',
        epoch: 'EP-01',
        sequenceNumber: 1,
        sourceTimestamp: new Date().toISOString(),
        points: { CM01_PT_01: { value: 2.85, quality: 'GOOD' } }
      })
    });
    assert.equal(ingestRes.status, 200);

    // 2. Viewer role simulation rejection (Must fail with 401 or 403)
    const viewerLogin = await api('/api/auth/login', { method: 'POST', body: { key: VIEWER_KEY } });
    assert.equal(viewerLogin.status, 200);
    assert.equal(viewerLogin.json.role, 'viewer');
    const viewerCookie = viewerLogin.headers.get('set-cookie')?.split(';')[0];
    assert.ok(viewerCookie);

    const viewerSim = await api('/api/demo/incident', {
      method: 'POST',
      cookie: viewerCookie,
      body: { stationId: 'CM-01', type: 'pressure-low' }
    });
    assert.equal(viewerSim.status, 403, 'Viewer must be rejected with 403 on simulation');

    // 3. Admin role simulation in APP_ENV=lab (Must succeed with 200)
    const adminLogin = await api('/api/auth/login', { method: 'POST', body: { key: ADMIN_KEY } });
    assert.equal(adminLogin.status, 200);
    assert.equal(adminLogin.json.role, 'admin');
    const adminCookie = adminLogin.headers.get('set-cookie')?.split(';')[0];
    assert.ok(adminCookie);

    const adminSim = await api('/api/demo/incident', {
      method: 'POST',
      cookie: adminCookie,
      body: { stationId: 'CM-01', type: 'pressure-low' }
    });
    assert.equal(adminSim.status, 200);
    assert.equal(adminSim.json.dataClassification, 'SIMULATED_LAB');

    // Verify snapshot reflects simulation and SIMULATED_LAB tags
    const stateRes = await api('/api/state', { cookie: adminCookie });
    assert.equal(stateRes.status, 200);
    const stationCm01 = stateRes.json.stations.find(s => s.id === 'CM-01');
    assert.equal(stationCm01.hasSimulatedLabIncident, true);
    assert.equal(stationCm01.pressureBar, 0.64);
    assert.equal(stationCm01.status, 'critical');

    const simAlert = stateRes.json.alerts.find(a => a.stationId === 'CM-01' && a.severity === 'critical');
    assert.ok(simAlert, 'Critical alert must be generated from simulation');
    assert.equal(simAlert.dataClassification, 'SIMULATED_LAB');
    assert.equal(simAlert.demo, true);

    // Mock Queue entry must have been created because Telegram is unconfigured in lab
    assert.ok(stateRes.json.queueStats.pending > 0 || stateRes.json.queueStats.mockSent > 0 || stateRes.json.queueStats.sent > 0);
    const mockJob = stateRes.json.queueRecent.find(q => q.mock && q.alertId === simAlert.id);
    assert.ok(mockJob, 'Job must be marked mock: true in lab without credentials');
    assert.match(mockJob.mockNotice, /MOCK \/ NOT ACTUALLY SENT/);

    // 4. Mock Telegram Test Endpoint
    const mockTestRes = await api('/api/test-telegram', {
      method: 'POST',
      cookie: adminCookie,
      body: { mode: 'mock', outcome: 'success' }
    });
    assert.equal(mockTestRes.status, 202);
    assert.equal(mockTestRes.json.mode, 'mock');

    const mockFailRes = await api('/api/test-telegram', {
      method: 'POST',
      cookie: adminCookie,
      body: { mode: 'mock', outcome: 'failure' }
    });
    assert.equal(mockFailRes.status, 202);

    let failedQueueItem = null;
    for (let i = 0; i < 30; i++) {
      const stateAfterQueue = await api('/api/state', { cookie: adminCookie });
      failedQueueItem = stateAfterQueue.json.queueRecent?.find(q => q.lastError);
      if (failedQueueItem) break;
      await new Promise(r => setTimeout(r, 150));
    }
    assert.ok(failedQueueItem, 'Mock failure must record simulated error');
    assert.match(failedQueueItem.lastError, /Simulated Telegram 500/);

    // Retry failed items
    const retryRes = await api('/api/queue/retry-failed', { method: 'POST', cookie: adminCookie });
    assert.equal(retryRes.status, 200);
    assert.ok(retryRes.json.retried >= 1);

    // 5. Real Telegram Test Confirmation Requirement
    const realNoConfirm = await api('/api/test-telegram', {
      method: 'POST',
      cookie: adminCookie,
      body: { mode: 'real' }
    });
    assert.equal(realNoConfirm.status, 400, 'Real send without confirmRealSend must return 400');

    const realWithConfirm = await api('/api/test-telegram', {
      method: 'POST',
      cookie: adminCookie,
      body: { mode: 'real', confirmRealSend: true }
    });
    assert.equal(realWithConfirm.status, 422, 'Real send without configured credentials must return 422');

    // 6. Reset only simulated data without wiping real gateway data
    const resetRes = await api('/api/demo/reset', { method: 'POST', cookie: adminCookie });
    assert.equal(resetRes.status, 200);
    assert.equal(resetRes.json.resetStations, 1);

    const stateAfterReset = await api('/api/state', { cookie: adminCookie });
    const stationAfterReset = stateAfterReset.json.stations.find(s => s.id === 'CM-01');
    assert.equal(stationAfterReset.hasSimulatedLabIncident, false);
    assert.equal(stationAfterReset.hasTelemetry, true);
    assert.equal(stationAfterReset.online, true);

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
