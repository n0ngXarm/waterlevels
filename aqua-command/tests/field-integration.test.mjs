import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';
import http from 'node:http';
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
const GATEWAY_KEY = 'test-gateway-token-secret-at-least-32-chars';
const VIEWER_KEY = 'test-viewer-read-key-at-least-32-chars';

test('Zone B Ingestion API: Phase 1 Remediation & End-to-End Verification', { timeout: 30_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-field-e2e-'));

  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  // 1. Setup Mock Telegram Server to test alert dispatch & queue retry (Zero real requests sent)
  const telegramRequests = [];
  let telegramFailNext = 0; // if > 0, return HTTP 500
  const mockTelegramPort = await openPort();
  const mockTelegramServer = http.createServer((req, res) => {
    let chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      const body = Buffer.concat(chunks).toString('utf8');
      telegramRequests.push({ url: req.url, body: JSON.parse(body || '{}') });
      if (telegramFailNext > 0) {
        telegramFailNext--;
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, description: 'Internal Telegram Gateway Error' }));
      } else {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, result: { message_id: 9999 } }));
      }
    });
  });
  await new Promise(r => mockTelegramServer.listen(mockTelegramPort, '127.0.0.1', r));

  const serverPort = await openPort();
  const env = {
    ...process.env,
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(serverPort),
    STATION_REGISTRY_PATH: path.join(root, '..', 'config', 'station_registry.json'),
    ADMIN_API_KEY: ADMIN_KEY,
    GATEWAY_INGEST_KEY: GATEWAY_KEY,
    VIEWER_API_KEY: VIEWER_KEY,
    REQUIRE_AUTH_FOR_READ: 'true',
    TELEGRAM_BOT_TOKEN: 'mock_test_bot_token_123',
    TELEGRAM_CHAT_ID: '12345678',
    TELEGRAM_API_BASE: `http://127.0.0.1:${mockTelegramPort}`,
    TELEGRAM_MIN_GAP_MS: '50',
    STALE_AFTER_SECONDS: '30'
  };

  let child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${serverPort}`;

  async function postIngest(payload, token = GATEWAY_KEY) {
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['X-Gateway-Token'] = token;
    return fetch(`${base}/api/v1/ingest/telemetry`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload)
    });
  }

  async function getState(token = VIEWER_KEY) {
    const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
    const res = await fetch(`${base}/api/state`, { headers });
    return { status: res.status, json: res.ok ? await res.json() : null };
  }

  try {
    // Wait for server health
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died unexpectedly');
      try {
        const r = await fetch(`${base}/api/health`);
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    // --- Test Requirement 4: Role-Separated Authentication & URL Credential Rejection ---
    // 4.1 Unauthenticated read returns 401
    const unauthRead = await getState(null);
    assert.equal(unauthRead.status, 401, 'Unauthenticated /api/state must return HTTP 401');

    // 4.2 Authenticated read with VIEWER_KEY succeeds
    const authRead = await getState(VIEWER_KEY);
    assert.equal(authRead.status, 200);
    assert.equal(authRead.json.mode, 'live-ingest');

    // 4.3 GATEWAY_KEY CANNOT access read-only state (Role Separation)
    const gatewayRead = await getState(GATEWAY_KEY);
    assert.equal(gatewayRead.status, 401, 'Gateway key MUST NOT have Viewer permissions on /api/state');

    // 4.4 VIEWER_KEY CANNOT ingest telemetry (Role Separation)
    const viewerIngest = await postIngest({ stationId: 'CM-01' }, VIEWER_KEY);
    assert.equal(viewerIngest.status, 401, 'Viewer key MUST NOT have Gateway Ingestion permissions');

    // 4.5 Passing token via URL query parameter is STRICTLY REJECTED (No URL credentials)
    const urlTokenRes = await fetch(`${base}/api/state?token=${VIEWER_KEY}`);
    assert.equal(urlTokenRes.status, 401, 'Credentials sent via URL query parameters must be rejected');

    // 4.6 Gateway key CANNOT access Admin export endpoint
    const gatewayExport = await fetch(`${base}/api/export/alerts`, { headers: { 'X-Gateway-Token': GATEWAY_KEY } });
    assert.equal(gatewayExport.status, 401, 'Gateway key MUST NOT have Admin export permissions');

    // 4.7 Admin key CAN access Admin export endpoint
    const adminExport = await fetch(`${base}/api/export/alerts`, { headers: { 'Authorization': `Bearer ${ADMIN_KEY}` } });
    assert.equal(adminExport.status, 200, 'Admin key must access Admin export endpoint');

    // --- Test Requirement 2: Invalid Telemetry Validation (HTTP 422 & 404) ---
    // Missing station ID
    let inv = await postIngest({ collectorId: 'GW-01', sourceTimestamp: new Date().toISOString(), points: {} });
    assert.equal(inv.status, 422, 'Missing stationId returns 422');

    // Nonexistent station ID
    inv = await postIngest({ stationId: 'UNKNOWN_99', collectorId: 'GW-01', sourceTimestamp: new Date().toISOString(), points: { PT: { value: 2.5 } } });
    assert.equal(inv.status, 404, 'Unknown station returns 404');

    // Out of bounds: negative pressure
    inv = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: -2.0, quality: 'GOOD' } }
    });
    assert.equal(inv.status, 422, 'Out of bounds negative pressure returns 422');

    // Non-numeric point value
    inv = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: 'NaN', quality: 'GOOD' } }
    });
    assert.equal(inv.status, 422, 'Non-numeric point value returns 422');

    // --- Test Requirement 1: Server-enforced Source Classification ---
    // Lab simulator gateway claims "AUTHORIZED_FIELD_TELEMETRY" -> Server must OVERRIDE to "SIMULATED_LAB"
    const t0 = new Date().toISOString();
    const labSimulatorPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN', // Registered as LAB in station_registry.json
      epoch: 'EP-TEST01',
      sequenceNumber: 1,
      sourceTimestamp: t0,
      dataClassification: 'AUTHORIZED_FIELD_TELEMETRY', // Untrusted client claim
      points: {
        CM01_PT_01: { value: 2.80, quality: 'GOOD', unit: 'bar' },
        CM01_LT_01: { value: 75.0, quality: 'GOOD', unit: '%' },
        CM01_FT_01: { value: 2800.0, quality: 'GOOD', unit: 'm3/h' },
        CM01_AT_01: { value: 0.45, quality: 'GOOD', unit: 'NTU' },
        CM01_AT_02: { value: 0.52, quality: 'GOOD', unit: 'mg/L' }
      }
    };
    const resLab = await postIngest(labSimulatorPayload);
    assert.equal(resLab.status, 200);
    const labJson = await resLab.json();
    assert.equal(labJson.ok, true);
    assert.equal(labJson.dataClassification, 'SIMULATED_LAB', 'Server must enforce SIMULATED_LAB for lab gateway');

    let st = (await getState(VIEWER_KEY)).json;
    const st01 = st.stations.find(s => s.id === 'CM-01');
    assert.equal(st01.dataClassification, 'SIMULATED_LAB');
    assert.equal(st01.pressureBar, 2.80);
    assert.equal(st01.online, true);

    // Production gateway (GW-CM01-FIELD-PROD) is enforced as AUTHORIZED_FIELD_TELEMETRY
    const prodPayload = {
      ...labSimulatorPayload,
      collectorId: 'GW-CM01-FIELD-PROD',
      sequenceNumber: 2,
      sourceTimestamp: new Date().toISOString()
    };
    const resProd = await postIngest(prodPayload);
    assert.equal(resProd.status, 200);
    assert.equal((await resProd.json()).dataClassification, 'AUTHORIZED_FIELD_TELEMETRY');

    // --- Test Requirement 3: Idempotency & Deduplication Check ---
    // Sending the exact same packet again returns duplicate=true without re-evaluating rules
    const resDup = await postIngest(prodPayload);
    assert.equal(resDup.status, 200);
    const dupJson = await resDup.json();
    assert.equal(dupJson.duplicate, true, 'Identical packet signature must be recognized as duplicate');

    // --- Test Requirement 2: Warning, Critical & Resolved Escalation ---
    // Inject low pressure (0.6 bar = CRITICAL for pressureBar < 0.8)
    const critPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      epoch: 'EP-TEST01',
      sequenceNumber: 10,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_PT_01: { value: 0.60, quality: 'GOOD' }
      }
    };
    assert.equal((await postIngest(critPayload)).status, 200);

    st = (await getState(VIEWER_KEY)).json;
    assert.equal(st.metrics.critical, 1);
    assert.equal(st.alerts.length, 1);
    assert.equal(st.alerts[0].severity, 'critical');

    // Escalation Transition to Warning (1.2 bar)
    const warnPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      epoch: 'EP-TEST01',
      sequenceNumber: 11,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_PT_01: { value: 1.20, quality: 'GOOD' }
      }
    };
    assert.equal((await postIngest(warnPayload)).status, 200);
    st = (await getState(VIEWER_KEY)).json;
    assert.equal(st.alerts[0].severity, 'warning');
    assert.ok(st.alerts[1].supersededAt);

    // Alert Resolution Transition (2.75 bar nominal)
    const resolvedPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      epoch: 'EP-TEST01',
      sequenceNumber: 12,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_PT_01: { value: 2.75, quality: 'GOOD' }
      }
    };
    assert.equal((await postIngest(resolvedPayload)).status, 200);
    st = (await getState(VIEWER_KEY)).json;
    assert.equal(st.metrics.activeAlertCount, 0);
    assert.equal(st.alerts[0].severity, 'resolved');

    // --- Test Requirement 2: Historical Buffer Replay & Packet Ordering Safeguard ---
    // Telemetry from 10 minutes ago
    const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    const replayPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      epoch: 'EP-TEST01',
      sequenceNumber: 50,
      sourceTimestamp: tenMinAgo,
      points: {
        CM01_PT_01: { value: 0.40, quality: 'GOOD' } // Old low pressure
      }
    };
    const replayRes = await postIngest(replayPayload);
    assert.equal(replayRes.status, 200);
    const replayJson = await replayRes.json();
    assert.equal(replayJson.isHistoricalReplay, true, 'Old telemetry must be tagged isHistoricalReplay=true');

    // Current live state must NOT have been overwritten by historical replay
    st = (await getState(VIEWER_KEY)).json;
    assert.equal(st.stations.find(s => s.id === 'CM-01').pressureBar, 2.75, 'Live pressure must not be overwritten by replay');
    assert.equal(st.metrics.activeAlertCount, 0, 'Historical replay must not trigger active alert storm');

    // --- Test Requirement 8: Telegram Mock Queue Failure & Exponential Backoff ---
    telegramFailNext = 99; // Mock telegram returns HTTP 500
    const tankWarnPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      epoch: 'EP-TEST01',
      sequenceNumber: 15,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_LT_01: { value: 20.0, quality: 'GOOD' }
      }
    };
    assert.equal((await postIngest(tankWarnPayload)).status, 200);

    let failedJob = null;
    for (let i = 0; i < 40; i++) {
      st = (await getState(VIEWER_KEY)).json;
      failedJob = st.queueRecent?.find(q => q.lastError && q.attempt > 0);
      if (failedJob) break;
      await new Promise(r => setTimeout(r, 200));
    }
    assert.ok(failedJob, 'A queued job must encounter simulated HTTP 500 error');
    assert.match(failedJob.lastError, /500/);
    assert.equal(failedJob.status, 'pending', 'Job must remain pending for exponential backoff retry');

    // --- Test Requirement 5: Durable Telemetry Storage Across Server Restart ---
    // Kill the running server process
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });

    // Spawn a brand new server process pointing to the same persistent storage directory
    child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Restarted server died unexpectedly');
      try {
        const r = await fetch(`${base}/api/health`);
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    // Verify state after restart retains telemetry
    const restartedState = (await getState(VIEWER_KEY)).json;
    const restartedStation = restartedState.stations.find(s => s.id === 'CM-01');
    assert.equal(restartedStation.pressureBar, 2.75, 'Station pressure must be preserved across server restarts');
    assert.equal(restartedStation.tankLevelPct, 20.0, 'Station tank level must be preserved across server restarts');
    assert.equal(restartedStation.hasTelemetry, true, 'Station hasTelemetry flag must remain true after restart');
    assert.equal(restartedStation.dataClassification, 'SIMULATED_LAB', 'Data classification must persist across restart');

  } finally {
    mockTelegramServer.close();
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
