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
const VIEWER_KEY = 'test-viewer-read-key-at-least-32-chars';
const GW_PATAN_KEY = 'test-gw-patan-secret-at-least-32-chars';
const GW_NONGSERVER_KEY = 'test-gw-nongserver-secret-at-least-32-chars';
const GW_PROD_KEY = 'test-gw-prod-secret-at-least-32-chars';

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
    APP_ENV: 'lab',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(serverPort),
    STATION_REGISTRY_PATH: path.join(root, '..', 'config', 'station_registry.json'),
    ADMIN_API_KEY: ADMIN_KEY,
    GATEWAY_TOKEN_GW_CM01_PATAN: GW_PATAN_KEY,
    GATEWAY_TOKEN_GW_CM01_NONGSERVER: GW_NONGSERVER_KEY,
    GATEWAY_TOKEN_GW_CM01_FIELD_PROD: GW_PROD_KEY,
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

  async function postIngest(payload, token = GW_PATAN_KEY) {
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
    const gatewayRead = await getState(GW_PATAN_KEY);
    assert.equal(gatewayRead.status, 401, 'Gateway key MUST NOT have Viewer permissions on /api/state');

    // 4.4 VIEWER_KEY CANNOT ingest telemetry (Role Separation)
    const viewerIngest = await postIngest({ stationId: 'CM-01', collectorId: 'GW-CM01-PATAN' }, VIEWER_KEY);
    assert.equal(viewerIngest.status, 401, 'Viewer key MUST NOT have Gateway Ingestion permissions');

    // 4.5 ADMIN_KEY CANNOT ingest telemetry (Strict Separation of Gateway vs Admin)
    const adminIngest = await postIngest({ stationId: 'CM-01', collectorId: 'GW-CM01-PATAN' }, ADMIN_KEY);
    assert.equal(adminIngest.status, 401, 'Admin key MUST NOT be accepted on gateway ingestion endpoint');

    // 4.6 Passing token via URL query parameter is STRICTLY REJECTED (No URL credentials)
    const urlTokenRes = await fetch(`${base}/api/state?token=${VIEWER_KEY}`);
    assert.equal(urlTokenRes.status, 401, 'Credentials sent via URL query parameters must be rejected');

    // 4.7 Gateway key CANNOT access Admin export endpoint
    const gatewayExport = await fetch(`${base}/api/export/alerts`, { headers: { 'X-Gateway-Token': GW_PATAN_KEY } });
    assert.equal(gatewayExport.status, 401, 'Gateway key MUST NOT have Admin export permissions');

    // 4.8 Viewer key CANNOT access Admin export endpoint
    const viewerExport = await fetch(`${base}/api/export/alerts`, { headers: { 'Authorization': `Bearer ${VIEWER_KEY}` } });
    assert.equal(viewerExport.status, 401, 'Viewer key MUST NOT have Admin export permissions');

    // 4.9 Admin key CAN access Admin export endpoint
    const adminExport = await fetch(`${base}/api/export/alerts`, { headers: { 'Authorization': `Bearer ${ADMIN_KEY}` } });
    assert.equal(adminExport.status, 200, 'Admin key must access Admin export endpoint');

    // --- Phase 2A & 2C Negative Security Tests: Gateway Binding, Spoofing & Isolation ---
    // 4.10 Unregistered Gateway ID returns HTTP 403 Forbidden
    const unregGw = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-UNREGISTERED-FAKE',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: 2.5, quality: 'GOOD' } }
    }, GW_PATAN_KEY);
    assert.equal(unregGw.status, 403, 'Unregistered Gateway ID must return HTTP 403');

    // 4.11 Cross-Station Injection: Gateway GW-CM01-PATAN is bound to CM-01; sending for CM-02 returns 403
    const crossStation = await postIngest({
      stationId: 'CM-02',
      collectorId: 'GW-CM01-PATAN',
      sourceTimestamp: new Date().toISOString(),
      points: { CM02_PT_01: { value: 2.5, quality: 'GOOD' } }
    }, GW_PATAN_KEY);
    assert.equal(crossStation.status, 403, 'Cross-station injection attempt must return HTTP 403');

    // 4.12 Gateway Spoofing: Invalid token for registered gateway returns HTTP 401 Unauthorized
    const spoofToken = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: 2.5, quality: 'GOOD' } }
    }, 'invalid-spoofed-gateway-token-32ch');
    assert.equal(spoofToken.status, 401, 'Invalid token for registered gateway must return HTTP 401');

    // 4.12.1 Cross-Gateway Token Spoofing: GW-CM01-PATAN using GW-CM01-NONGSERVER's token returns HTTP 401
    const crossGwToken = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: 2.5, quality: 'GOOD' } }
    }, GW_NONGSERVER_KEY);
    assert.equal(crossGwToken.status, 401, 'Using another gateway token must be rejected with HTTP 401');

    // 4.12.2 Production Gateway Impersonation in Lab: GW-CM01-FIELD-PROD is partitioned off in LAB mode
    const prodInLab = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01-FIELD-PROD',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: 2.5, quality: 'GOOD' } }
    }, GW_PROD_KEY);
    assert.equal(prodInLab.status, 403, 'Production gateway claimed in LAB environment must return HTTP 403');

    // 4.12.3 Origin / CSRF Protection: State-changing requests with external Origin header rejected
    const csrfBlocked = await fetch(`${base}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Origin': 'http://evil-attacker.website'
      },
      body: JSON.stringify({ key: VIEWER_KEY })
    });
    assert.equal(csrfBlocked.status, 403, 'Cross-origin state-changing request must return HTTP 403');

    // 4.12.4 Dynamic HTTPS Cookie: Request with X-Forwarded-Proto: https emits Secure cookie
    const httpsLogin = await fetch(`${base}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Forwarded-Proto': 'https'
      },
      body: JSON.stringify({ key: VIEWER_KEY })
    });
    assert.equal(httpsLogin.status, 200);
    const httpsCookie = httpsLogin.headers.get('set-cookie');
    assert.match(httpsCookie, /;\s*Secure/i, 'Session cookie must include Secure attribute when proxied via HTTPS');

    // 4.12.5 Brute-Force Rate Limiting: 5 failed attempts per IP allowed, 6th attempt returns HTTP 429
    for (let i = 0; i < 5; i++) {
      const badAttempt = await fetch(`${base}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Forwarded-For': '198.51.100.42'
        },
        body: JSON.stringify({ key: `wrong-credential-attempt-${i}-padding-extra` })
      });
      assert.equal(badAttempt.status, 401);
    }
    const rateLimited = await fetch(`${base}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Forwarded-For': '198.51.100.42'
      },
      body: JSON.stringify({ key: 'wrong-credential-rate-limited-attempt-padding' })
    });
    assert.equal(rateLimited.status, 429, 'Excessive failed login attempts must return HTTP 429');

    // --- Phase 2A Frontend Session Cookie Authentication Architecture ---
    // 4.13 Invalid credentials to /api/auth/login return 401
    const badLogin = await fetch(`${base}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'wrong-passphrase-at-least-24-chars-long' })
    });
    assert.equal(badLogin.status, 401);

    // 4.14 Viewer login to /api/auth/login returns 200 and sets HttpOnly aqua_session cookie
    const viewerLogin = await fetch(`${base}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: VIEWER_KEY })
    });
    assert.equal(viewerLogin.status, 200);
    const setCookieHeader = viewerLogin.headers.get('set-cookie');
    assert.ok(setCookieHeader, 'Login must issue Set-Cookie header');
    assert.match(setCookieHeader, /aqua_session=[a-f0-9]{64}/);
    assert.match(setCookieHeader, /HttpOnly/i);
    assert.match(setCookieHeader, /SameSite=Lax/i);

    const sessionMatch = setCookieHeader.match(/aqua_session=([a-f0-9]+)/);
    const sessionCookie = `aqua_session=${sessionMatch[1]}`;

    // 4.14.1 Viewer Session RBAC Negative Checks: Viewer cookie CANNOT ingest or administer
    const viewerCookieIngest = await fetch(`${base}/api/v1/ingest/telemetry`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': sessionCookie
      },
      body: JSON.stringify({ stationId: 'CM-01', collectorId: 'GW-CM01-PATAN' })
    });
    assert.equal(viewerCookieIngest.status, 401, 'Viewer session cookie cannot ingest telemetry');

    const viewerCookieIncident = await fetch(`${base}/api/incidents`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': sessionCookie
      },
      body: JSON.stringify({ title: 'Unauthorized Incident' })
    });
    assert.equal(viewerCookieIncident.status, 401, 'Viewer session cookie cannot create incidents');

    const viewerCookieExport = await fetch(`${base}/api/export/alerts`, {
      headers: { 'Cookie': sessionCookie }
    });
    assert.equal(viewerCookieExport.status, 401, 'Viewer session cookie cannot export alerts');

    // 4.15 Session cookie can access /api/auth/status
    const authStatus = await (await fetch(`${base}/api/auth/status`, {
      headers: { 'Cookie': sessionCookie }
    })).json();
    assert.equal(authStatus.authenticated, true);
    assert.equal(authStatus.role, 'viewer');

    // 4.16 Session cookie can access /api/state WITHOUT any Authorization header
    const cookieStateRes = await fetch(`${base}/api/state`, {
      headers: { 'Cookie': sessionCookie }
    });
    assert.equal(cookieStateRes.status, 200, 'Session cookie must authorize /api/state access');

    // 4.17 Session cookie can connect to SSE /api/stream
    const cookieStreamRes = await fetch(`${base}/api/stream`, {
      headers: { 'Cookie': sessionCookie }
    });
    assert.equal(cookieStreamRes.status, 200, 'Session cookie must authorize SSE stream');
    assert.match(cookieStreamRes.headers.get('content-type'), /text\/event-stream/);
    cookieStreamRes.body?.cancel();

    // 4.18 Logout clears the session cookie
    const logoutRes = await fetch(`${base}/api/auth/logout`, {
      method: 'POST',
      headers: { 'Cookie': sessionCookie }
    });
    assert.equal(logoutRes.status, 200);
    const clearedCookie = logoutRes.headers.get('set-cookie');
    assert.match(clearedCookie, /Max-Age=0/);

    // 4.19 After logout, former session cookie is rejected on /api/state
    const postLogoutState = await fetch(`${base}/api/state`, {
      headers: { 'Cookie': sessionCookie }
    });
    assert.equal(postLogoutState.status, 401, 'Logged out session cookie must be rejected');

    // --- Test Requirement 2: Invalid Telemetry Validation (HTTP 422 & 404) ---
    // Missing station ID
    let inv = await postIngest({ collectorId: 'GW-CM01-PATAN', sourceTimestamp: new Date().toISOString(), points: {} });
    assert.equal(inv.status, 422, 'Missing stationId returns 422');

    // Nonexistent station ID
    inv = await postIngest({ stationId: 'UNKNOWN_99', collectorId: 'GW-CM01-PATAN', sourceTimestamp: new Date().toISOString(), points: { PT: { value: 2.5 } } });
    assert.equal(inv.status, 404, 'Unknown station returns 404');

    // Out of bounds: negative pressure
    inv = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
      sourceTimestamp: new Date().toISOString(),
      points: { CM01_PT_01: { value: -2.0, quality: 'GOOD' } }
    });
    assert.equal(inv.status, 422, 'Out of bounds negative pressure returns 422');

    // Non-numeric point value
    inv = await postIngest({
      stationId: 'CM-01',
      collectorId: 'GW-CM01-PATAN',
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
    const resLab = await postIngest(labSimulatorPayload, GW_PATAN_KEY);
    assert.equal(resLab.status, 200);
    const labJson = await resLab.json();
    assert.equal(labJson.ok, true);
    assert.equal(labJson.dataClassification, 'SIMULATED_LAB', 'Server must enforce SIMULATED_LAB for lab gateway');

    let st = (await getState(VIEWER_KEY)).json;
    const st01 = st.stations.find(s => s.id === 'CM-01');
    assert.equal(st01.dataClassification, 'SIMULATED_LAB');
    assert.equal(st01.pressureBar, 2.80);
    assert.equal(st01.online, true);

    // nongserver lab gateway (GW-CM01-NONGSERVER) is also enforced as SIMULATED_LAB
    const nongPayload = {
      ...labSimulatorPayload,
      collectorId: 'GW-CM01-NONGSERVER',
      sequenceNumber: 2,
      sourceTimestamp: new Date().toISOString()
    };
    const resNong = await postIngest(nongPayload, GW_NONGSERVER_KEY);
    assert.equal(resNong.status, 200);
    assert.equal((await resNong.json()).dataClassification, 'SIMULATED_LAB');

    // --- Test Requirement 3: Idempotency & Deduplication Check ---
    // Sending the exact same packet again returns duplicate=true without re-evaluating rules
    const resDup = await postIngest(nongPayload, GW_NONGSERVER_KEY);
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

test('Zone B Ingestion API: Production Mode Gateway Verification', { timeout: 15_000 }, async () => {
  const root = path.resolve(import.meta.dirname, '..');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aqua-prod-e2e-'));

  for (const file of ['server.mjs', 'rules.mjs']) {
    fs.copyFileSync(path.join(root, file), path.join(tmp, file));
  }
  fs.cpSync(path.join(root, 'public'), path.join(tmp, 'public'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'storage'));

  const serverPort = await openPort();
  const env = {
    ...process.env,
    APP_ENV: 'prod',
    DEMO_MODE: 'false',
    HOST: '127.0.0.1',
    PORT: String(serverPort),
    STATION_REGISTRY_PATH: path.join(root, '..', 'config', 'station_registry.json'),
    ADMIN_API_KEY: ADMIN_KEY,
    GATEWAY_TOKEN_GW_CM01_FIELD_PROD: GW_PROD_KEY,
    VIEWER_API_KEY: VIEWER_KEY,
    REQUIRE_AUTH_FOR_READ: 'true',
    TELEGRAM_BOT_TOKEN: '',
    TELEGRAM_CHAT_ID: ''
  };

  const child = spawn(process.execPath, [path.join(tmp, 'server.mjs')], { cwd: tmp, env, stdio: 'pipe' });
  const base = `http://127.0.0.1:${serverPort}`;

  try {
    for (let i = 0; i < 50; i++) {
      if (child.exitCode !== null) throw Error('Server died unexpectedly');
      try {
        const r = await fetch(`${base}/api/health`);
        if (r.ok) break;
      } catch {}
      await new Promise(r => setTimeout(r, 100));
    }

    const prodPayload = {
      stationId: 'CM-01',
      collectorId: 'GW-CM01-FIELD-PROD',
      epoch: 'EP-PROD01',
      sequenceNumber: 1,
      sourceTimestamp: new Date().toISOString(),
      points: {
        CM01_PT_01: { value: 2.82, quality: 'GOOD', unit: 'bar' }
      }
    };

    const res = await fetch(`${base}/api/v1/ingest/telemetry`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Gateway-Token': GW_PROD_KEY
      },
      body: JSON.stringify(prodPayload)
    });

    assert.equal(res.status, 200);
    const json = await res.json();
    assert.equal(json.ok, true);
    assert.equal(json.dataClassification, 'AUTHORIZED_FIELD_TELEMETRY', 'PROD gateway in prod environment must receive AUTHORIZED_FIELD_TELEMETRY');
  } finally {
    child.kill('SIGTERM');
    await new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode) resolve();
      else child.once('exit', resolve);
    });
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

