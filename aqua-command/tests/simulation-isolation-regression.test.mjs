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
const GW_PROD_KEY = 'test-gw-prod-secret-at-least-32-chars';

function createTestEnv(tmp, root, envOverrides = {}) {
  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'), { recursive: true });

  return {
    ...process.env,
    APP_ENV: 'lab',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    STATION_REGISTRY_PATH: path.join(root, '..', 'config', 'station_registry.json'),
    ADMIN_API_KEY: ADMIN_KEY,
    VIEWER_API_KEY: VIEWER_KEY,
    GATEWAY_TOKEN_GW_CM01_PATAN: GW_PATAN_KEY,
    GATEWAY_TOKEN_GW_CM01_FIELD_PROD: GW_PROD_KEY,
    REQUIRE_AUTH_FOR_READ: 'true',
    TELEGRAM_BOT_TOKEN: '',
    TELEGRAM_CHAT_ID: '',
    TELEGRAM_MIN_GAP_MS: '50',
    ...envOverrides
  };
}

async function waitForServer(base, child, maxRetries = 50) {
  for (let i = 0; i < maxRetries; i++) {
    if (child.exitCode !== null) throw Error(`Server died unexpectedly with code ${child.exitCode}`);
    try {
      const r = await fetch(`${base}/api/health`);
      if (r.ok) return;
    } catch {}
    await new Promise(r => setTimeout(r, 100));
  }
  throw Error('Server startup timed out');
}

test('Regression Suite: Scenario A & B — Simulation Overlay Pattern, Restore & Concurrent Gateway Ingest', { timeout: 25_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-reg-ab-'));
  const port = await openPort();
  const env = createTestEnv(tmp, root, { PORT: String(port) });

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${port}`;

  async function postIngest(payload, token = GW_PATAN_KEY) {
    return fetch(`${base}/api/v1/ingest/telemetry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Gateway-Token': token },
      body: JSON.stringify(payload)
    });
  }

  async function api(p, { method = 'GET', body = null, key = null, cookie = null } = {}) {
    const headers = {};
    if (body) headers['Content-Type'] = 'application/json';
    if (key) headers['X-API-Key'] = key;
    if (cookie) headers['Cookie'] = cookie;
    const res = await fetch(`${base}${p}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const json = await res.json().catch(() => null);
    return { status: res.status, ok: res.ok, json, headers: res.headers };
  }

  try {
    await waitForServer(base, child);

    // Login admin
    const loginRes = await api('/api/auth/login', { method: 'POST', body: { key: ADMIN_KEY } });
    assert.equal(loginRes.status, 200);
    const adminCookie = loginRes.headers.get('set-cookie')?.split(';')[0];
    assert.ok(adminCookie);

    // === SCENARIO A: SIM RESTORE (Gateway 2.85 -> Sim 0.64 -> Reset -> 2.85 NOT 2.65) ===
    const t0 = new Date().toISOString();
    const ingestA = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      epoch: 'EP-01',
      sequenceNumber: 101,
      sourceTimestamp: t0,
      points: { CM01_PT_01: { value: 2.85, quality: 'GOOD' } }
    });
    assert.equal(ingestA.status, 200);

    // Verify baseline state
    let state = (await api('/api/state', { cookie: adminCookie })).json;
    let cm01 = state.stations.find(s => s.id === 'CM-01');
    assert.equal(cm01.pressureBar, 2.85);
    assert.equal(cm01.status, 'normal');
    assert.equal(cm01.origin, 'GATEWAY_INGEST');

    // Trigger Admin Simulation: pressure-low (0.64 bar)
    const simA = await api('/api/demo/incident', {
      method: 'POST',
      cookie: adminCookie,
      body: { stationId: 'CM-01', type: 'pressure-low' }
    });
    assert.equal(simA.status, 200);
    assert.equal(simA.json.origin, 'ADMIN_SIMULATION');

    // Verify simulation overlay is active while raw gateway telemetry is preserved
    state = (await api('/api/state', { cookie: adminCookie })).json;
    cm01 = state.stations.find(s => s.id === 'CM-01');
    assert.equal(cm01.pressureBar, 0.64, 'Live station reading must reflect simulation overlay');
    assert.equal(cm01.status, 'critical');
    assert.equal(cm01.hasSimulatedLabIncident, true);
    assert.equal(cm01.origin, 'ADMIN_SIMULATION');
    assert.equal(cm01.gatewayTelemetry.pressureBar, 2.85, 'Preserved raw gateway telemetry must remain 2.85');

    // Reset simulation
    const resetA = await api('/api/demo/reset', { method: 'POST', cookie: adminCookie });
    assert.equal(resetA.status, 200);

    // Verify station restores to actual gateway telemetry 2.85, NOT hardcoded 2.65
    state = (await api('/api/state', { cookie: adminCookie })).json;
    cm01 = state.stations.find(s => s.id === 'CM-01');
    assert.notEqual(cm01.pressureBar, 2.65, 'Must NOT restore to hardcoded 2.65 bar');
    assert.equal(cm01.pressureBar, 2.85, 'Must restore precisely to latest gateway telemetry (2.85 bar)');
    assert.equal(cm01.status, 'normal');
    assert.equal(cm01.hasSimulatedLabIncident, false);
    assert.equal(cm01.origin, 'GATEWAY_INGEST');

    // === SCENARIO B: CONCURRENT UPDATE (Gateway 2.85 -> Sim 0.64 -> Gateway 2.75 during Sim -> Reset -> 2.75 with seq 202) ===
    // Trigger simulation overlay again
    await api('/api/demo/incident', {
      method: 'POST',
      cookie: adminCookie,
      body: { stationId: 'CM-01', type: 'pressure-low' }
    });

    state = (await api('/api/state', { cookie: adminCookie })).json;
    cm01 = state.stations.find(s => s.id === 'CM-01');
    assert.equal(cm01.pressureBar, 0.64);

    // While simulation is active, gateway sends a new packet (2.75 bar, seq 202)
    const tConcurrent = new Date(Date.now() + 1000).toISOString();
    const ingestB = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      epoch: 'EP-01',
      sequenceNumber: 202,
      sourceTimestamp: tConcurrent,
      points: { CM01_PT_01: { value: 2.75, quality: 'GOOD' } }
    });
    assert.equal(ingestB.status, 200, 'Ingest during active simulation must be accepted with 200');

    // View during simulation: live display shows 0.64 bar overlay, but gatewayTelemetry received 2.75
    state = (await api('/api/state', { cookie: adminCookie })).json;
    cm01 = state.stations.find(s => s.id === 'CM-01');
    assert.equal(cm01.pressureBar, 0.64, 'Live display must keep active overlay during simulation');
    assert.equal(cm01.gatewayTelemetry.pressureBar, 2.75, 'Gateway telemetry buffer must record new 2.75 update');
    assert.equal(cm01.gatewayTelemetry.sequenceNumber, 202);

    // Reset simulation
    const resetB = await api('/api/demo/reset', { method: 'POST', cookie: adminCookie });
    assert.equal(resetB.status, 200);

    // Verify station restores to the concurrent update (2.75 bar, seq 202, timestamp tConcurrent)
    state = (await api('/api/state', { cookie: adminCookie })).json;
    cm01 = state.stations.find(s => s.id === 'CM-01');
    assert.equal(cm01.pressureBar, 2.75, 'Must reflect concurrent gateway update of 2.75 bar');
    assert.equal(cm01.sequenceNumber, 202, 'Must reflect sequence 202 from concurrent gateway update');
    assert.equal(cm01.sourceTimestamp, tConcurrent, 'Must reflect latest timestamp from concurrent update');
    assert.equal(cm01.status, 'normal');

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('Regression Suite: Scenario C — Alert Provenance & Reset Isolation', { timeout: 20_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-reg-c-'));
  const port = await openPort();
  const env = createTestEnv(tmp, root, { PORT: String(port) });

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${port}`;

  async function postIngest(payload, token = GW_PATAN_KEY) {
    return fetch(`${base}/api/v1/ingest/telemetry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Gateway-Token': token },
      body: JSON.stringify(payload)
    });
  }

  async function api(p, { method = 'GET', body = null, key = null, cookie = null } = {}) {
    const headers = {};
    if (body) headers['Content-Type'] = 'application/json';
    if (key) headers['X-API-Key'] = key;
    if (cookie) headers['Cookie'] = cookie;
    const res = await fetch(`${base}${p}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const json = await res.json().catch(() => null);
    return { status: res.status, ok: res.ok, json, headers: res.headers };
  }

  try {
    await waitForServer(base, child);

    const loginRes = await api('/api/auth/login', { method: 'POST', body: { key: ADMIN_KEY } });
    assert.equal(loginRes.status, 200);
    const adminCookie = loginRes.headers.get('set-cookie')?.split(';')[0];
    assert.ok(adminCookie);

    // 1. Gateway sends high turbidity -> generates real gateway alert (GATEWAY_INGEST)
    const ingestRes = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      epoch: 'EP-01',
      sequenceNumber: 301,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_PT_01: { value: 2.80, quality: 'GOOD' },
        CM01_AT_01: { value: 5.50, quality: 'GOOD' } // Turbidity critical > 4.0
      }
    });
    assert.equal(ingestRes.status, 200);

    let state = (await api('/api/state', { cookie: adminCookie })).json;
    const gatewayAlert = state.alerts.find(a => a.stationId === 'CM-01' && a.ruleId === 'turbidity-high');
    assert.ok(gatewayAlert, 'Gateway turbidity alert must be created');
    assert.equal(gatewayAlert.origin, 'GATEWAY_INGEST');
    assert.equal(gatewayAlert.resolvedAt, null);

    // 2. Admin simulates pressure-low -> generates simulation alert (ADMIN_SIMULATION)
    const simRes = await api('/api/demo/incident', {
      method: 'POST',
      cookie: adminCookie,
      body: { stationId: 'CM-01', type: 'pressure-low' }
    });
    assert.equal(simRes.status, 200);

    state = (await api('/api/state', { cookie: adminCookie })).json;
    const simAlert = state.alerts.find(a => a.stationId === 'CM-01' && a.ruleId === 'pressure-low');
    assert.ok(simAlert, 'Simulation alert must be created');
    assert.equal(simAlert.origin, 'ADMIN_SIMULATION');
    assert.equal(simAlert.resolvedAt, null);

    // Both alerts are active
    assert.ok(state.alerts.filter(a => !a.resolvedAt).length >= 2);

    // 3. Admin resets simulation
    const resetRes = await api('/api/demo/reset', { method: 'POST', cookie: adminCookie });
    assert.equal(resetRes.status, 200);

    // Verify ONLY simulation alert is resolved; Gateway alert MUST REMAIN ACTIVE!
    state = (await api('/api/state', { cookie: adminCookie })).json;
    const simAlertAfterReset = state.alerts.find(a => a.id === simAlert.id);
    const gatewayAlertAfterReset = state.alerts.find(a => a.id === gatewayAlert.id);

    assert.ok(simAlertAfterReset.resolvedAt !== null, 'Simulation alert MUST be resolved');
    assert.equal(gatewayAlertAfterReset.resolvedAt, null, 'Gateway alert MUST REMAIN UNRESOLVED (active)');

    // 4. Repeat reset call (Idempotency test)
    const resetIdempotent = await api('/api/demo/reset', { method: 'POST', cookie: adminCookie });
    assert.equal(resetIdempotent.status, 200);
    assert.equal(resetIdempotent.json.resetStations, 0, 'Repeat reset on already clean state resets 0 stations');

    state = (await api('/api/state', { cookie: adminCookie })).json;
    const gatewayAlertStillActive = state.alerts.find(a => a.id === gatewayAlert.id);
    assert.equal(gatewayAlertStillActive.resolvedAt, null, 'Gateway alert must stay active on repeat resets');

  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('Regression Suite: Scenario D — Security Isolation, Environment Guards & Fail-Closed Startup', { timeout: 25_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');

  // Subtest D1: Startup fail-closed on invalid APP_ENV
  for (const badEnv of ['staging', 'unknown', 'development', 'test', 'local']) {
    const tmpBad = fs.mkdtempSync(path.join(os.tmpdir(), `aqua-reg-d-bad-${badEnv}-`));
    const badPort = await openPort();
    const envBad = createTestEnv(tmpBad, root, { APP_ENV: badEnv, PORT: String(badPort) });

    const badChild = spawn(process.execPath, [path.join(tmpBad, 'server.mjs')], { cwd: tmpBad, env: envBad, stdio: 'pipe' });
    let stderr = '';
    badChild.stderr.on('data', d => { stderr += d.toString(); });

    const exitCode = await new Promise(resolve => badChild.once('exit', resolve));
    assert.notEqual(exitCode, 0, `Server with APP_ENV="${badEnv}" must exit with non-zero exit code`);
    assert.match(stderr, /FATAL: Unsupported or invalid APP_ENV/, `Stderr must contain fatal error message for ${badEnv}`);
    fs.rmSync(tmpBad, { recursive: true, force: true });
  }

  // Subtest D2: APP_ENV=prod and APP_ENV=production reject simulation with 403
  for (const prodEnv of ['prod', 'production']) {
    const tmpProd = fs.mkdtempSync(path.join(os.tmpdir(), `aqua-reg-d-${prodEnv}-`));
    const prodPort = await openPort();
    const envProd = createTestEnv(tmpProd, root, { APP_ENV: prodEnv, PORT: String(prodPort) });

    const prodChild = spawn(process.execPath, [path.join(tmpProd, 'server.mjs')], { cwd: tmpProd, env: envProd, stdio: 'pipe' });
    const prodBase = `http://127.0.0.1:${prodPort}`;

    try {
      await waitForServer(prodBase, prodChild);

      // In prod/production, login admin
      const loginRes = await fetch(`${prodBase}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: ADMIN_KEY })
      });
      assert.equal(loginRes.status, 200);
      const prodCookie = loginRes.headers.get('set-cookie')?.split(';')[0];

      // Simulation incident must be rejected with 403
      const simRes = await fetch(`${prodBase}/api/demo/incident`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Cookie': prodCookie },
        body: JSON.stringify({ stationId: 'CM-01', type: 'pressure-low' })
      });
      assert.equal(simRes.status, 403, `Simulation must be rejected with 403 in ${prodEnv}`);

      // Simulation reset must be rejected with 403
      const resetRes = await fetch(`${prodBase}/api/demo/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Cookie': prodCookie }
      });
      assert.equal(resetRes.status, 403, `Simulation reset must be rejected with 403 in ${prodEnv}`);

      // In prod/production, LAB gateway must be rejected with 403
      const labGwRes = await fetch(`${prodBase}/api/v1/ingest/telemetry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Gateway-Token': GW_PATAN_KEY },
        body: JSON.stringify({
          stationId: 'CM-01',
          collectorId: 'GW-CM01-PATAN',
          epoch: 'EP-01',
          sequenceNumber: 1,
          sourceTimestamp: new Date().toISOString(),
          points: { CM01_PT_01: { value: 2.80, quality: 'GOOD' } }
        })
      });
      assert.equal(labGwRes.status, 403, `LAB gateway must be rejected in ${prodEnv}`);

      // PROD gateway in prod/production must succeed with 200 and AUTHORIZED_FIELD_TELEMETRY
      const prodGwRes = await fetch(`${prodBase}/api/v1/ingest/telemetry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Gateway-Token': GW_PROD_KEY },
        body: JSON.stringify({
          stationId: 'CM-01',
          collectorId: 'GW-CM01-FIELD-PROD',
          epoch: 'EP-01',
          sequenceNumber: 1,
          sourceTimestamp: new Date().toISOString(),
          points: { CM01_PT_01: { value: 2.80, quality: 'GOOD' } }
        })
      });
      assert.equal(prodGwRes.status, 200, `PROD gateway must succeed in ${prodEnv}`);
      const prodGwJson = await prodGwRes.json();
      assert.equal(prodGwJson.dataClassification, 'AUTHORIZED_FIELD_TELEMETRY');

    } finally {
      prodChild.kill('SIGTERM');
      await new Promise(resolve => {
        if (prodChild.exitCode !== null || prodChild.signalCode) resolve();
        else prodChild.once('exit', resolve);
      });
      fs.rmSync(tmpProd, { recursive: true, force: true });
    }
  }

  // Subtest D3: In APP_ENV=lab, Viewer is rejected with 403, Admin succeeds with 200, PROD gateway rejected
  const tmpLab = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-reg-d-lab-'));
  const labPort = await openPort();
  const envLab = createTestEnv(tmpLab, root, { APP_ENV: 'lab', PORT: String(labPort) });

  const labChild = spawn(process.execPath, [path.join(tmpLab, 'server.mjs')], { cwd: tmpLab, env: envLab, stdio: 'pipe' });
  const labBase = `http://127.0.0.1:${labPort}`;

  try {
    await waitForServer(labBase, labChild);

    // Viewer login
    const vLogin = await fetch(`${labBase}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: VIEWER_KEY })
    });
    assert.equal(vLogin.status, 200);
    const viewerCookie = vLogin.headers.get('set-cookie')?.split(';')[0];

    // Viewer simulation must fail with 403
    const vSim = await fetch(`${labBase}/api/demo/incident`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Cookie': viewerCookie },
      body: JSON.stringify({ stationId: 'CM-01', type: 'pressure-low' })
    });
    assert.equal(vSim.status, 403, 'Viewer simulation must be rejected with 403');

    // Admin login
    const aLogin = await fetch(`${labBase}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: ADMIN_KEY })
    });
    assert.equal(aLogin.status, 200);
    const adminCookie = aLogin.headers.get('set-cookie')?.split(';')[0];

    // Admin simulation must succeed with 200
    const aSim = await fetch(`${labBase}/api/demo/incident`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Cookie': adminCookie },
      body: JSON.stringify({ stationId: 'CM-01', type: 'pressure-low' })
    });
    assert.equal(aSim.status, 200, 'Admin simulation must succeed in lab with 200');

    // In lab, PROD gateway must be rejected with 403
    const prodInLab = await fetch(`${labBase}/api/v1/ingest/telemetry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Gateway-Token': GW_PROD_KEY },
      body: JSON.stringify({
        stationId: 'CM-01',
        collectorId: 'GW-CM01-FIELD-PROD',
        epoch: 'EP-01',
        sequenceNumber: 1,
        sourceTimestamp: new Date().toISOString(),
        points: { CM01_PT_01: { value: 2.80, quality: 'GOOD' } }
      })
    });
    assert.equal(prodInLab.status, 403, 'PROD gateway must be rejected in lab environment');

  } finally {
    labChild.kill('SIGTERM');
    await new Promise(resolve => {
      if (labChild.exitCode !== null || labChild.signalCode) resolve();
      else labChild.once('exit', resolve);
    });
    fs.rmSync(tmpLab, { recursive: true, force: true });
  }
});
