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

test('Zone B Ingestion API: Priority 3 End-to-End Verification', { timeout: 25_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-field-e2e-'));

  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  // 1. Setup Mock Telegram Server to test alert dispatch & queue retry
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

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
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

    // --- Test Scenario 1: Unauthorized Access Protection ---
    // Unauthenticated read to /api/state when REQUIRE_AUTH_FOR_READ is true
    const unauthRead = await getState(null);
    assert.equal(unauthRead.status, 401, 'Unauthenticated /api/state must return HTTP 401');

    // Authenticated read succeeds
    const authRead = await getState(VIEWER_KEY);
    assert.equal(authRead.status, 200);
    assert.equal(authRead.json.mode, 'live-ingest');

    // Ingestion without gateway token must return HTTP 401
    const unauthIngest = await postIngest({ stationId: 'CM-01' }, null);
    assert.equal(unauthIngest.status, 401, 'Ingestion without gateway token must return HTTP 401');

    // Ingestion with wrong token must return HTTP 401
    const badTokenIngest = await postIngest({ stationId: 'CM-01' }, 'wrong-token-value-too-short');
    assert.equal(badTokenIngest.status, 401, 'Ingestion with wrong token must return HTTP 401');

    // --- Test Scenario 2: Invalid Telemetry Validation (HTTP 422 & 404) ---
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

    // Out of bounds: pressure exceeding 15 bar
    inv = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: 99.5, quality: 'GOOD' } }
    });
    assert.equal(inv.status, 422, 'Out of bounds excessive pressure returns 422');

    // Non-numeric point value
    inv = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: 'NaN', quality: 'GOOD' } }
    });
    assert.equal(inv.status, 422, 'Non-numeric point value returns 422');

    // --- Test Scenario 3: Connected & Normal Telemetry Ingestion ---
    const t0 = new Date().toISOString();
    const normalPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sequenceNumber: 1,
      sourceTimestamp: t0,
      points: {
        CM01_PT_01: { value: 2.80, quality: 'GOOD', unit: 'bar' },
        CM01_LT_01: { value: 75.0, quality: 'GOOD', unit: '%' },
        CM01_FT_01: { value: 2800.0, quality: 'GOOD', unit: 'm3/h' },
        CM01_AT_01: { value: 0.45, quality: 'GOOD', unit: 'NTU' },
        CM01_AT_02: { value: 0.52, quality: 'GOOD', unit: 'mg/L' }
      }
    };
    const resNormal = await postIngest(normalPayload);
    assert.equal(resNormal.status, 200);
    const resBody = await resNormal.json();
    assert.equal(resBody.ok, true);
    assert.equal(resBody.dataClassification, 'AUTHORIZED_FIELD_TELEMETRY');
    assert.equal(resBody.isHistoricalReplay, false);

    // Verify state reflects telemetry
    let st = (await getState(VIEWER_KEY)).json;
    const st01 = st.stations.find(s => s.id === 'CM-01');
    assert.equal(st01.pressureBar, 2.80);
    assert.equal(st01.tankLevelPct, 75.0);
    assert.equal(st01.online, true);
    assert.equal(st01.dataClassification, 'AUTHORIZED_FIELD_TELEMETRY');
    assert.equal(st.alerts.length, 0, 'Nominal reading creates no alerts');

    // --- Test Scenario 4: Warning & Critical Alert Escalation ---
    // Inject low pressure (0.6 bar = CRITICAL for pressureBar < 0.8)
    const critPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sequenceNumber: 2,
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

    // Wait for Telegram dispatch
    await new Promise(r => setTimeout(r, 1100));
    assert.ok(telegramRequests.length >= 1, 'Telegram notification should be sent for critical alert');
    assert.match(telegramRequests[0].body.text, /วิกฤต/);

    // --- Test Scenario 5: Duplicate Telemetry Deduplication ---
    // Send identical critical telemetry packet again
    assert.equal((await postIngest(critPayload)).status, 200);
    st = (await getState(VIEWER_KEY)).json;
    assert.equal(st.alerts.length, 1, 'Duplicate telemetry packet MUST NOT create duplicate alert');

    // --- Test Scenario 6: Escalation Transition to Warning ---
    const warnPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sequenceNumber: 3,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_PT_01: { value: 1.20, quality: 'GOOD' } // 1.20 is warning threshold (< 1.5)
      }
    };
    assert.equal((await postIngest(warnPayload)).status, 200);
    st = (await getState(VIEWER_KEY)).json;
    assert.equal(st.alerts[0].severity, 'warning');
    assert.ok(st.alerts[1].supersededAt, 'Previous critical alert must be superseded');

    // --- Test Scenario 7: Alert Resolution Transition ---
    const resolvedPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sequenceNumber: 4,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_PT_01: { value: 2.75, quality: 'GOOD' } // nominal
      }
    };
    assert.equal((await postIngest(resolvedPayload)).status, 200);
    st = (await getState(VIEWER_KEY)).json;
    assert.equal(st.metrics.activeAlertCount, 0);
    assert.equal(st.alerts[0].severity, 'resolved');
    assert.ok(st.alerts[0].resolvedAt);

    // --- Test Scenario 8: Historical Buffer Replay Safeguard ---
    // Simulate replaying an old packet from 10 minutes ago
    const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    const replayPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sequenceNumber: 100,
      sourceTimestamp: tenMinAgo,
      points: {
        CM01_PT_01: { value: 0.50, quality: 'GOOD' } // Old low pressure that occurred during outage
      }
    };
    const replayRes = await postIngest(replayPayload);
    assert.equal(replayRes.status, 200);
    const replayJson = await replayRes.json();
    assert.equal(replayJson.isHistoricalReplay, true, 'Old telemetry must be tagged isHistoricalReplay=true');

    // Ensure it did NOT trigger a false alarm storm on current state
    st = (await getState(VIEWER_KEY)).json;
    assert.equal(st.metrics.activeAlertCount, 0, 'Replayed historical telemetry must not trigger active alert storm');

    // --- Test Scenario 9: Telegram Queue Failure & Exponential Backoff Retry ---
    telegramFailNext = 99; // force any subsequent Telegram dispatch to fail with HTTP 500

    // Trigger a new warning on tank level (e.g. 20% < 30%)
    const tankWarnPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sequenceNumber: 5,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_LT_01: { value: 20.0, quality: 'GOOD' }
      }
    };
    assert.equal((await postIngest(tankWarnPayload)).status, 200);

    // Poll until a job experiences a failure and records lastError
    let failedJob = null;
    for (let i = 0; i < 40; i++) {
      st = (await getState(VIEWER_KEY)).json;
      failedJob = st.queueRecent?.find(q => q.lastError && q.attempt > 0);
      if (failedJob) break;
      await new Promise(r => setTimeout(r, 200));
    }

    assert.ok(failedJob, 'A queued job must encounter the simulated HTTP 500 error');
    assert.match(failedJob.lastError, /500/);
    assert.equal(failedJob.status, 'pending', 'Job must remain pending for exponential backoff retry');

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
