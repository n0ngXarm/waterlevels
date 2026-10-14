const $ = x => document.querySelector(x);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, d = 0) => Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const thaiTime = iso => new Intl.DateTimeFormat('th-TH', { timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
const thaiDate = iso => new Intl.DateTimeFormat('th-TH', { timeZone: 'Asia/Bangkok', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(iso));
const relative = iso => {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีที่แล้ว` : m < 1440 ? `${Math.floor(m / 60)} ชม.ที่แล้ว` : thaiDate(iso);
};

const I = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  map: '<path d="M3 6.5 9 3l6 4 6-3v13.5l-6 3-6-4-6 3V6.5Z"/><path d="M9 3v13.5M15 7v13.5"/>',
  tank: '<rect x="5" y="3" width="14" height="18" rx="3"/><path d="M5 12c3-2 5 2 7 0s4-2 7 0M9 7h6"/>',
  chart: '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 2 5-7"/>',
  sliders: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  warning: '<path d="M10.3 3.2 2 18a2 2 0 0 0 1.8 3h16.4a2 2 0 0 0 1.8-3L13.7 3.2a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4m0 4h.01"/>',
  search: '<circle cx="10.8" cy="10.8" r="7"/><path d="m16 16 5 5"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  drops: '<path d="M12 2C8 7 5 11 5 15a7 7 0 0 0 14 0c0-4-3-8-7-13Z"/><path d="M9 17a3 3 0 0 0 3 3"/>',
  gauge: '<path d="M12 14l4-5M3 16a9 9 0 1 1 18 0M5 20h14M12 7v1"/><circle cx="12" cy="14" r="2"/>',
  activity: '<path d="M2 12h4l3-8 6 16 3-8h4"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  send: '<path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.5-4L3 10m0-5v5h5M4 13a8 8 0 0 0 14.5 4L21 14m0 5v-5h-5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  radio: '<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19 5a10 10 0 0 1 0 14M5 19A10 10 0 0 1 5 5"/>',
  server: '<rect x="3" y="3" width="18" height="8" rx="2"/><rect x="3" y="13" width="18" height="8" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  filter: '<path d="M3 4h18l-7 8v6l-4 2v-8L3 4Z"/>'
};

function icon(name, cls = '') {
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[name] || I.info}</svg>`;
}

let state = {
  data: null,
  view: 'overview',
  mapFilter: 'all',
  selectedDistrict: '',
  selected: null,
  modal: null,
  menu: false,
  query: '',
  filter: 'all',
  range: '24h',
  adminKey: '',
  demoStation: 'CM-01',
  demoType: 'pressure-low',
  toast: null,
  streamOnline: false,
  districts: []
};

let toastTimeout;

// 5 Main Sidebar Menus
const menu = [
  ['overview', 'grid', 'ภาพรวม'],
  ['map', 'map', 'แผนที่จังหวัดเชียงใหม่'],
  ['stations', 'tank', 'สถานีและแหล่งน้ำ'],
  ['analytics', 'chart', 'รายงาน'],
  ['settings', 'sliders', 'ตั้งค่าระบบ']
];

function actionButton(action, label, variant = '', attrs = '') {
  return `<button type="button" data-action="${action}" ${attrs} class="button ${variant}">${label}</button>`;
}

function render() {
  const active = document.activeElement;
  const focusId = active?.getAttribute?.('data-focus');
  const start = active?.selectionStart, end = active?.selectionEnd;
  const data = state.data;

  if (!data) {
    const appEl = $('#app');
    if (appEl) appEl.innerHTML = `<div class="boot"><div class="loader"></div><p>กำลังเชื่อมต่อศูนย์ควบคุมประปา เชียงใหม่...</p></div>`;
    return;
  }

  const live = state.streamOnline;
  const alertN = data.alerts.filter(a => !a.resolvedAt && !a.supersededAt && ['warning', 'critical'].includes(a.severity)).length;
  const viewTitles = {
    overview: 'ภาพรวมระบบประปา จังหวัดเชียงใหม่',
    map: 'แผนที่โครงข่ายน้ำ จังหวัดเชียงใหม่',
    stations: 'สถานีและแหล่งน้ำ จังหวัดเชียงใหม่',
    alerts: 'ศูนย์จัดการแจ้งเตือนเหตุการณ์',
    analytics: 'รายงานและวิเคราะห์เชิงลึก',
    settings: 'ตั้งค่าระบบและ Telegram Gateway'
  };

  const appEl = $('#app');
  if (!appEl) return;

  appEl.innerHTML = `<div class="app-shell">
    <aside class="sidebar ${state.menu ? 'open' : ''}" aria-label="เมนูหลัก">
      <div class="brand">
        <div class="brandmark">${icon('drops')}</div>
        <div>
          <div class="brandtitle">AQUA <b>COMMAND</b></div>
          <div class="branddesc">CHIANG MAI <span class="region-tag">กปภ.</span></div>
        </div>
      </div>
      <div class="nav-caption">CONTROL CENTER</div>
      <nav class="nav">
        ${menu.map(([id, ic, name]) => `
          <button class="nav-btn ${state.view === id ? 'selected' : ''}" data-view="${id}" type="button" aria-current="${state.view === id ? 'page' : 'false'}">
            ${icon(ic, 'nav-icon')}
            <span>${name}</span>
            ${id === 'overview' && alertN ? `<span class="nav-counter">${alertN}</span>` : ''}
          </button>
        `).join('')}
      </nav>
      <div class="nav-caption">SYSTEM HEALTH</div>
      <nav class="nav">
        <button class="nav-btn" data-view="settings" type="button">
          ${icon('radio', 'nav-icon')}
          <span>Telegram Gateway</span>
          <span class="status-pill ${data.telegram.configured ? '' : 'warning'}" style="margin-left:auto;padding:2px 7px;font-size:9px">
            ${data.telegram.configured ? 'ON' : 'OFF'}
          </span>
        </button>
        <button class="nav-btn" data-view="stations" type="button">
          ${icon('server', 'nav-icon')}
          <span>สถานีที่เชื่อมต่อ</span>
          <span style="margin-left:auto;color:var(--primary);font-size:10px;font-weight:700">
            ${data.metrics.online}/${data.metrics.total}
          </span>
        </button>
      </nav>
      <div class="side-spacer"></div>
      <div class="side-quick-box">
        <div class="side-quick-title">${icon('activity')} CHIANG MAI OPS</div>
        <p class="side-quick-desc">เฝ้าระวังแรงดันน้ำและระดับน้ำ 12 สถานี 25 อำเภอในจังหวัดเชียงใหม่</p>
        ${actionButton('openDemo', icon('plus') + ' จำลองเหตุการณ์', 'button-tiny button-primary', 'style="width:100%"')}
      </div>
      <div class="side-foot">
        <div class="avatar">CM</div>
        <div>
          <div class="user-name">Chiang Mai Ops</div>
          <div class="user-role">Water Command Center</div>
        </div>
        <span class="pulse-dot" style="margin-left:auto"></span>
      </div>
    </aside>
    <main class="content">
      <header class="topbar">
        <div style="display:flex;gap:12px;align-items:center">
          <button class="icon-btn mobile-topmenu" data-action="menu" aria-label="เปิดเมนู">${icon('menu')}</button>
          <div class="breadcrumb">
            AQUA COMMAND <span style="margin:0 4px">/</span>
            <strong>${viewTitles[state.view] || 'ศูนย์บัญชาการ'}</strong>
            <span class="breadcrumb-badge">เชียงใหม่</span>
          </div>
        </div>
        <div class="top-actions">
          <span class="status-pill ${live ? '' : 'warning'}">
            <span class="pulse-dot" style="${live ? '' : 'background:var(--warning)'}"></span>
            ${live ? 'CONNECTED' : 'RECONNECTING'}
          </span>
          <div class="divider-vertical"></div>
          <div class="header-time">
            <div class="clock" id="clock">${new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date())} ICT</div>
            <div class="date">${thaiDate(new Date())}</div>
          </div>
          <button class="icon-btn" data-view="alerts" aria-label="เปิดการแจ้งเตือน" title="ศูนย์แจ้งเตือนเหตุการณ์">
            ${icon('bell')}
            ${alertN ? '<span class="notification-dot"></span>' : ''}
          </button>
          <button class="icon-btn" data-view="settings" aria-label="ตั้งค่าระบบ" title="ตั้งค่าระบบ">
            ${icon('sliders')}
          </button>
        </div>
      </header>
      ${
        state.view === 'overview' ? overview() :
        state.view === 'map' ? mapPage() :
        state.view === 'stations' ? stationsPage() :
        state.view === 'alerts' ? alertsPage() :
        state.view === 'analytics' ? analyticsPage() :
        settingsPage()
      }
      <footer class="footbar">
        <span>© 2026 AQUA COMMAND · ระบบศูนย์ควบคุมและเฝ้าระวังระบบประปา จังหวัดเชียงใหม่</span>
        <span>REGIONAL TELEMETRY INTEGRATION · CHIANG MAI PROVINCE (UTC+7)</span>
      </footer>
    </main>
  </div>
  ${state.selected ? drawer() : ''}
  ${state.modal ? modal() : ''}
  ${state.toast ? `<div role="status" class="toast ${state.toast.error ? 'error' : ''}">${esc(state.toast.message)}</div>` : ''}`;

  document.body.classList.toggle('no-scroll', !!state.selected || !!state.modal);
  if (focusId) {
    const replacement = document.querySelector(`[data-focus="${focusId}"]`);
    if (replacement) {
      replacement.focus();
      if (typeof start === 'number' && replacement.setSelectionRange) {
        try { replacement.setSelectionRange(start, end); } catch {}
      }
    }
  }
}

function heading(kicker, title, desc, buttons = '') {
  return `<div class="page-heading">
    <div>
      <div class="eyebrow">${kicker} <span class="demo-flag">${state.data.mode === 'demo' ? 'DEMO DATA' : 'LIVE INGEST'}</span></div>
      <h1>${title}</h1>
      <p class="subheading">${desc}</p>
    </div>
    <div class="page-heading-actions">${buttons}</div>
  </div>`;
}

function kpiCard(label, val, unit, sub, badgeText, badgeType, ic, extraClass = '') {
  return `<div class="kpi ${extraClass}">
    <div class="kpi-top">
      <span class="kpi-label">${label}</span>
      <div class="kpi-icon">${icon(ic)}</div>
    </div>
    <div class="kpi-value">${val}<span class="unit">${unit}</span></div>
    <div class="kpi-bottom">
      <span class="kpi-sub">${sub}</span>
      ${badgeText ? `<span class="kpi-badge ${badgeType}">${badgeText}</span>` : ''}
    </div>
  </div>`;
}

function severityName(v) {
  return { critical: 'วิกฤต', warning: 'เฝ้าระวัง', normal: 'ปกติ', resolved: 'กลับสู่ปกติ', info: 'ข้อมูล', unknown: 'รอข้อมูล' }[v] || v;
}

// ---------------- 1. OVERVIEW PAGE ----------------
function overview() {
  const d = state.data;
  const m = d.metrics;
  const reservoirs = d.reservoirs || [
    { name: 'เขื่อนแม่งัดสมบูรณ์ชล', storagePct: 80.2, storageMcm: 212.5, capacityMcm: 265.0 },
    { name: 'เขื่อนแม่กวงอุดมธารา', storagePct: 72.0, storageMcm: 189.4, capacityMcm: 263.0 }
  ];
  const maeNgat = reservoirs.find(r => r.name.includes('แม่งัด')) || reservoirs[0];
  const maeKuang = reservoirs.find(r => r.name.includes('แม่กวง')) || reservoirs[1];

  return `
    ${heading(
      'PROVINCIAL WATER OPERATIONS COMMAND CENTER',
      'ภาพรวมระบบประปา จังหวัดเชียงใหม่',
      'ศูนย์ควบคุมและเฝ้าระวังระบบประปาระดับจังหวัด ติดตามแรงดัน ระดับน้ำ และเหตุผิดปกติแบบ Real-time',
      `${actionButton('reset', icon('refresh') + ' รีเซ็ตการจำลอง', 'button-ghost')}
       ${actionButton('openDemo', icon('plus') + ' จำลองเหตุการณ์', 'button-primary')}`
    )}

    <!-- 4 KPI Cards -->
    <section class="kpi-grid" aria-label="ตัวชี้วัดหลัก จังหวัดเชียงใหม่">
      ${kpiCard(
        'สถานีประปา',
        fmt(m.online) + '/' + fmt(m.total),
        'สถานี',
        `ปกติ ${m.normal} • เตือน ${m.warning} • วิกฤต ${m.critical}`,
        m.critical > 0 ? 'พบวิกฤต' : m.warning > 0 ? 'มีเตือน' : 'พร้อมใช้งาน',
        m.critical > 0 ? 'critical' : m.warning > 0 ? 'warning' : 'success',
        'server',
        m.critical > 0 ? 'kpi-alert' : m.warning > 0 ? 'kpi-warning' : ''
      )}
      ${kpiCard(
        'แรงดันน้ำเฉลี่ย',
        fmt(m.pressure, 2),
        'bar',
        'เกณฑ์มาตรฐาน 1.5 - 4.5 bar',
        m.pressure < 1.5 ? 'ต่ำกว่าเกณฑ์' : 'ระดับปกติ',
        m.pressure < 1.5 ? 'warning' : 'success',
        'gauge'
      )}
      ${kpiCard(
        'ระดับน้ำในแหล่งน้ำ',
        fmt(m.reservoirAvgPct || 76.1, 1),
        '%',
        `แม่งัด ${fmt(maeNgat?.storagePct || 80.2, 1)}% • แม่กวง ${fmt(maeKuang?.storagePct || 72.0, 1)}%`,
        'ปริมาณน้ำเพียงพอ',
        'success',
        'drops'
      )}
      ${kpiCard(
        'เหตุการณ์ที่ต้องติดตาม',
        fmt(m.activeAlertCount),
        'รายการ',
        'แจ้งเตือนผ่าน Telegram แล้ว',
        m.activeAlertCount > 0 ? 'ต้องตรวจสอบ' : 'ไม่มีเหตุวิกฤต',
        m.activeAlertCount > 0 ? 'critical' : 'success',
        'warning',
        m.activeAlertCount > 0 ? 'kpi-alert' : ''
      )}
    </section>

    <!-- Main Overview Layout: Left Chiang Mai Map, Right 3 Panels -->
    <section class="overview-grid" aria-label="แผนที่และสถานะภาพรวม">
      ${cmMapPanel()}
      <div class="right-stack">
        ${statusPanel()}
        ${reservoirPanel()}
        ${recentAlertsPanel()}
      </div>
    </section>

    <!-- Lower Section: Trend Analytics & Water Quality Sensors -->
    <section class="lower-grid" aria-label="แนวโน้มและคุณภาพน้ำ">
      ${chartPanel()}
      ${qualityPanel()}
    </section>
  `;
}

// ---------------- CHIANG MAI MAP PANEL ----------------
function cmMapPanel() {
  const s = state.data.stations;
  const filtered = s.filter(st => {
    if (state.mapFilter === 'all') return true;
    if (state.mapFilter === 'offline') return !st.online;
    return st.status === state.mapFilter;
  });

  // SVG dimensions
  const W = 620, H = 540;

  // Render District Polygons from loaded GeoJSON paths if available
  let districtPaths = '';
  if (state.districts && state.districts.length) {
    districtPaths = state.districts.map(d => {
      const isSel = state.selectedDistrict === d.name;
      return `<path class="cm-district-path ${isSel ? 'highlighted' : ''}" d="${d.dPath}" data-district="${esc(d.name)}">
        <title>อำเภอ${esc(d.name)}</title>
      </path>`;
    }).join('');
  } else {
    // Stylized Geographic Contour Fallback for Chiang Mai Province
    districtPaths = `
      <path class="cm-district-path" d="M 370 40 L 450 60 L 480 120 L 440 180 L 410 240 L 430 270 L 390 320 L 350 380 L 260 460 L 210 490 L 190 440 L 210 360 L 240 300 L 320 250 L 330 180 L 350 100 Z"/>
    `;
  }

  // Key Water Reservoirs plotted on Map
  const reservoirs = [
    { name: 'เขื่อนแม่งัดสมบูรณ์ชล', px: 388.7, py: 189.8, type: 'dam' },
    { name: 'เขื่อนแม่กวงอุดมธารา', px: 420.6, py: 232.8, type: 'dam' },
    { name: 'จุดสูบน้ำดิบแม่น้ำปิง', px: 371.4, py: 248.6, type: 'river' }
  ];

  const resSvg = reservoirs.map(r => `
    <g class="cm-reservoir-node" transform="translate(${r.px}, ${r.py})">
      <circle class="res-shape" r="6"/>
      <path d="M -3 -1 L 0 -4 L 3 -1 L 0 2 Z" fill="#00D4E8"/>
      <text class="cm-reservoir-label" x="8" y="3">${r.name}</text>
    </g>
  `).join('');

  // Station Nodes
  const stationNodes = filtered.map(st => {
    const px = st.px || (35 + (st.x || 30) * 5.5);
    const py = st.py || (7 + (st.y || 24) * 3.09);
    const right = px > 430;
    const high = py < 80;

    return `
      <g class="cm-station-node ${st.status} ${!st.online ? 'offline' : ''}" 
         data-station="${esc(st.id)}" 
         tabindex="0" 
         role="button" 
         aria-label="สถานี ${esc(st.name)} สถานะ ${st.status}">
        <circle class="halo" cx="${px}" cy="${py}" r="11"/>
        <circle class="core" cx="${px}" cy="${py}" r="4.2"/>
        <text class="cm-station-label" 
              x="${px + (right ? -12 : 12)}" 
              y="${py + (high ? 14 : -6)}" 
              text-anchor="${right ? 'end' : 'start'}">
          ${esc(st.name)}
        </text>
      </g>
    `;
  }).join('');

  return `
    <div class="panel cm-map-panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">
            ${icon('map')} แผนที่โครงข่ายประปา จังหวัดเชียงใหม่
          </div>
          <div class="panel-caption">แสดงสถานะแรงดันและคุณภาพน้ำ 12 สถานีตามพิกัดจริง ครอบคลุม 25 อำเภอ</div>
        </div>
        <div class="panel-extra">
          <span class="pulse-dot"></span> &nbsp;${filtered.length}/${s.length} STATIONS
        </div>
      </div>

      <div class="map-toolbar">
        <div class="filter-chips">
          ${[
            ['all', 'ทั้งหมด'],
            ['normal', 'ปกติ'],
            ['warning', 'เฝ้าระวัง'],
            ['critical', 'วิกฤต'],
            ['offline', 'ออฟไลน์']
          ].map(([k, t]) => `
            <button class="filter-chip ${state.mapFilter === k ? 'active' : ''}" data-action="setMapFilter" data-filter-val="${k}">
              ${t}
            </button>
          `).join('')}
        </div>
        <div>
          <select class="field" style="padding:4px 8px;font-size:10px;width:auto" data-action="selectDistrict">
            <option value="">ทุกอำเภอ (เชียงใหม่)</option>
            ${(state.districts || []).map(d => `
              <option value="${esc(d.name)}" ${state.selectedDistrict === d.name ? 'selected' : ''}>
                อำเภอ${esc(d.name)}
              </option>
            `).join('')}
          </select>
        </div>
      </div>

      <div class="cm-map-canvas-wrap">
        <svg class="cm-svg-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="แผนที่โครงข่ายระบบประปา จังหวัดเชียงใหม่">
          <defs>
            <pattern id="cmGrid" width="30" height="30" patternUnits="userSpaceOnUse">
              <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#16314D" stroke-width="0.6" opacity="0.6"/>
            </pattern>
            <radialGradient id="cmMapGlow">
              <stop offset="0%" stop-color="#00D4E8" stop-opacity="0.08"/>
              <stop offset="100%" stop-color="#071526" stop-opacity="0"/>
            </radialGradient>
          </defs>
          <rect width="${W}" height="${H}" fill="url(#cmGrid)"/>
          <circle cx="360" cy="250" r="240" fill="url(#cmMapGlow)"/>

          <!-- District Boundaries -->
          <g class="districts-layer">
            ${districtPaths}
          </g>

          <!-- Reservoirs -->
          <g class="reservoirs-layer">
            ${resSvg}
          </g>

          <!-- Water Stations -->
          <g class="stations-layer">
            ${stationNodes}
          </g>
        </svg>

        <div class="map-compass">N↑</div>

        <div class="map-legend">
          <span class="legend-item"><span class="legend-dot success"></span> ปกติ</span>
          <span class="legend-item"><span class="legend-dot warning"></span> เฝ้าระวัง</span>
          <span class="legend-item"><span class="legend-dot critical"></span> วิกฤต</span>
          <span class="legend-item"><span class="legend-dot offline"></span> ขาดการเชื่อมต่อ</span>
        </div>
      </div>

      <div class="map-footer">
        <span><strong>หมายเหตุ:</strong> ตำแหน่งสถานีและขอบเขตอำเภออ้างอิงฐานข้อมูล GIS จังหวัดเชียงใหม่</span>
        <span>UPDATED ${thaiTime(state.data.serverTime)} ICT</span>
      </div>
    </div>
  `;
}

// ---------------- RIGHT PANEL 1: STATUS DONUT ----------------
function statusPanel() {
  const d = state.data;
  const s = d.stations;
  const normal = s.filter(x => x.online && x.status === 'normal').length;
  const warning = s.filter(x => x.status === 'warning').length;
  const critical = s.filter(x => x.status === 'critical').length;
  const offline = s.filter(x => !x.online).length;
  const total = s.length || 1;

  // Donut SVG circumference calculation
  const r = 48;
  const c = 2 * Math.PI * r;
  const pNorm = (normal / total) * c;
  const pWarn = (warning / total) * c;
  const pCrit = (critical / total) * c;
  const pOff = (offline / total) * c;

  const offNorm = 0;
  const offWarn = -pNorm;
  const offCrit = -(pNorm + pWarn);
  const offOff = -(pNorm + pWarn + pCrit);

  const healthyPct = Math.round((normal / total) * 100);

  return `
    <div class="panel status-panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">${icon('activity')} สถานะระบบประปาเชียงใหม่</div>
          <div class="panel-caption">สัดส่วนความพร้อมจ่ายน้ำและจุดผิดปกติ</div>
        </div>
        <span class="status-pill" style="font-size:9px">MONITORING</span>
      </div>

      <div class="status-body">
        <div class="donut-wrap">
          <svg viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="${r}" fill="none" stroke="#091C30" stroke-width="12"/>
            <circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--success)" stroke-width="12"
                    stroke-dasharray="${pNorm} ${c}" stroke-dashoffset="${offNorm}"/>
            <circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--warning)" stroke-width="12"
                    stroke-dasharray="${pWarn} ${c}" stroke-dashoffset="${offWarn}"/>
            <circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--critical)" stroke-width="12"
                    stroke-dasharray="${pCrit} ${c}" stroke-dashoffset="${offCrit}"/>
            <circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--offline)" stroke-width="12"
                    stroke-dasharray="${pOff} ${c}" stroke-dashoffset="${offOff}"/>
          </svg>
          <div class="donut-center">
            <strong>${healthyPct}%</strong>
            <small>ปกติ</small>
          </div>
        </div>

        <div class="status-breakdown">
          <div class="status-row">
            <span class="status-row-label">
              <span class="legend-dot success"></span> สถานีปกติ
            </span>
            <span class="status-row-val" style="color:var(--success)">${normal} สถานี</span>
          </div>
          <div class="status-row">
            <span class="status-row-label">
              <span class="legend-dot warning"></span> เฝ้าระวัง
            </span>
            <span class="status-row-val" style="color:var(--warning)">${warning} สถานี</span>
          </div>
          <div class="status-row">
            <span class="status-row-label">
              <span class="legend-dot critical"></span> วิกฤต
            </span>
            <span class="status-row-val" style="color:var(--critical)">${critical} สถานี</span>
          </div>
          <div class="status-row">
            <span class="status-row-label">
              <span class="legend-dot offline"></span> ขาดการเชื่อมต่อ
            </span>
            <span class="status-row-val" style="color:var(--offline)">${offline} สถานี</span>
          </div>
        </div>
      </div>
    </div>
  `;
}

// ---------------- RIGHT PANEL 2: RESERVOIRS ----------------
function reservoirPanel() {
  const d = state.data;
  const reservoirs = d.reservoirs || [
    { name: 'เขื่อนแม่งัดสมบูรณ์ชล', storagePct: 80.2, storageMcm: 212.5, capacityMcm: 265.0, statusText: 'ปกติ (80.2%)' },
    { name: 'เขื่อนแม่กวงอุดมธารา', storagePct: 72.0, storageMcm: 189.4, capacityMcm: 263.0, statusText: 'ปกติ (72.0%)' },
    { name: 'จุดสูบน้ำดิบแม่น้ำปิง (ป่าตัน)', storagePct: 93.2, waterLevelM: 3.45, statusText: 'ระดับน้ำปกติ (3.45 ม.รทก.)' }
  ];

  return `
    <div class="panel reservoir-panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">${icon('drops')} ระดับน้ำในแหล่งน้ำที่ติดตาม</div>
          <div class="panel-caption">เขื่อนและแหล่งน้ำดิบหลักสำหรับผลิตน้ำประปาเชียงใหม่</div>
        </div>
      </div>

      <div class="reservoir-list">
        ${reservoirs.map(r => {
          const pct = Math.min(100, Math.max(0, r.storagePct || 70));
          const stateCls = pct < 30 ? 'critical' : pct < 50 ? 'warning' : '';
          return `
            <div class="reservoir-item">
              <div class="reservoir-header">
                <span class="reservoir-name">${esc(r.name)}</span>
                <span class="reservoir-capacity">${r.capacityMcm ? `${r.storageMcm} / ${r.capacityMcm} MCM` : `${r.waterLevelM} ม.รทก.`}</span>
              </div>
              <div class="progress-rail">
                <div class="progress-fill ${stateCls}" style="width:${pct}%"></div>
              </div>
              <div class="reservoir-sub">
                <span>ความจุ ${fmt(pct, 1)}%</span>
                <span>${esc(r.statusText || 'ปกติ')}</span>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

// ---------------- RIGHT PANEL 3: RECENT ALERTS ----------------
function recentAlertsPanel() {
  const recent = state.data.alerts.slice(0, 3);
  return `
    <div class="panel recent-alerts-panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">${icon('warning')} เหตุการณ์ล่าสุด</div>
          <div class="panel-caption">ตรวจจับเหตุผิดปกติพร้อมสถานะส่ง Telegram</div>
        </div>
        <button class="button button-tiny button-ghost" data-view="alerts">
          ดูทั้งหมด ${icon('arrow')}
        </button>
      </div>

      <div class="alerts-list">
        ${recent.length ? recent.map(alertRow).join('') : `<div class="blank-state">ไม่มีเหตุการณ์ผิดปกติในขณะนี้</div>`}
      </div>
    </div>
  `;
}

function alertRow(a) {
  return `
    <div class="alert-item ${a.severity}" data-station="${esc(a.stationId || '')}" role="button" tabindex="0">
      <div class="alert-icon">
        ${icon(a.severity === 'resolved' ? 'check' : a.severity === 'info' ? 'info' : 'warning')}
      </div>
      <div class="alert-copy">
        <h4>
          <span>${esc(a.title)}${a.demo ? ' <small style="color:var(--warning)">[DEMO]</small>' : ''}</span>
          <span>${relative(a.createdAt)}</span>
        </h4>
        <p>${esc(a.stationName)} · ${esc(a.message)}</p>
        <div class="alert-actions-row">
          <span class="telegram-tag">${icon('send')} Telegram Alerted</span>
          ${a.acknowledgedAt ? 
            `<small style="color:var(--success)">${icon('check')} รับทราบแล้ว</small>` : 
            `<button class="button button-tiny" data-ack="${esc(a.id)}">รับทราบ</button>`}
        </div>
      </div>
    </div>
  `;
}

// ---------------- CHARTS & WATER QUALITY ----------------
function chartPanel() {
  return `
    <div class="panel chart-panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">${icon('chart')} แนวโน้มแรงดันและอัตราการไหล (เชียงใหม่)</div>
          <div class="panel-caption">ค่าเฉลี่ยตรวจวัดจากทุกสถานีในโครงข่ายจังหวัดเชียงใหม่</div>
        </div>
        <div class="mini-toggle">
          ${[['1h', '1 ชม.'], ['24h', '24 ชม.'], ['7d', 'ภาพรวม']].map(([v, t]) => `
            <button class="${state.range === v ? 'active' : ''}" data-range="${v}">${t}</button>
          `).join('')}
        </div>
      </div>
      <div class="graph">${chartSvg(subset(), ['pressure', 'flow'])}</div>
      <div class="graph-note">
        <div class="chart-keys">
          <span class="chart-key"><span class="chart-dot"></span> แรงดันน้ำ (bar)</span>
          <span class="chart-key"><span class="chart-dot alt"></span> อัตราการไหล (× 1,000 m³/h)</span>
        </div>
        <span>● Telemetry Ingest</span>
      </div>
    </div>
  `;
}

function subset() {
  const h = state.data.history || [];
  return h.slice(-({ '1h': 4, '24h': 96, '7d': 96 }[state.range] || 96));
}

function chartSvg(list, keys, colors = ['#00D4E8', '#26B6FF']) {
  if (!list.length) return '<div class="blank-state">ยังไม่มีข้อมูล Telemetry สำหรับสร้างกราฟ</div>';
  const W = 740, H = 200, left = 36, right = 14, top = 16, bottom = 24;
  const pw = W - left - right, ph = H - top - bottom;
  const sampled = list.filter((_, i) => i % Math.max(1, Math.floor(list.length / 35)) === 0);

  const curves = keys.map((key, k) => {
    const values = sampled.map(p => Number(p[key] || 0));
    const min = Math.min(...values), max = Math.max(...values);
    const padding = Math.max(0.4, (max - min) * 0.22);
    const lo = Math.max(0, min - padding), hi = max + padding;
    const pts = values.map((v, i) => [left + (i / (values.length - 1 || 1)) * pw, top + ph - ((v - lo) / (hi - lo || 1)) * ph]);
    return {
      key, pts,
      curve: pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' '),
      lo, hi, color: colors[k]
    };
  });

  return `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="กราฟค่าแรงดันน้ำและอัตราการไหล">
      <defs>
        <linearGradient id="cmGraphFill" x1="0" x2="0" y1="0" y2="1">
          <stop stop-color="#00D4E8" stop-opacity="0.22"/>
          <stop offset="1" stop-color="#00D4E8" stop-opacity="0"/>
        </linearGradient>
      </defs>
      ${[0, 0.25, 0.5, 0.75, 1].map(i => `<line class="chart-gridline" x1="${left}" y1="${top + i * ph}" x2="${W - right}" y2="${top + i * ph}"/>`).join('')}
      ${curves.map((c, k) => `
        ${k === 0 ? `<path d="${c.curve} L${c.pts.at(-1)[0]} ${top + ph} L${left} ${top + ph} Z" fill="url(#cmGraphFill)"/>` : ''}
        <path d="${c.curve}" stroke="${c.color}" stroke-width="${k === 0 ? 3 : 2.2}" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      `).join('')}
      ${[0, 0.25, 0.5, 0.75, 1].map(i => `
        <text class="chart-axis" x="${left - 8}" y="${top + i * ph + 3}" text-anchor="end">
          ${fmt(curves[0].hi - i * (curves[0].hi - curves[0].lo), 1)}
        </text>
      `).join('')}
      ${[0, 0.25, 0.5, 0.75, 1].map(i => {
        const item = sampled[Math.min(sampled.length - 1, Math.round(i * (sampled.length - 1)))];
        return `<text class="chart-axis" x="${left + i * pw}" y="${H - 6}" text-anchor="middle">${item?.time ? thaiTime(item.time) : ''}</text>`;
      }).join('')}
    </svg>
  `;
}

function qualityPanel() {
  const m = state.data.metrics;
  const chlorine = m.chlorine || (state.data.stations.reduce((sum, s) => sum + (s.chlorineMgL || 0), 0) / (state.data.stations.length || 1));

  return `
    <div class="panel quality-panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">${icon('drops')} ดัชนีคุณภาพน้ำ (Chiang Mai WTPs)</div>
          <div class="panel-caption">ค่าตรวจวัดเฉลี่ยจากสถานีผลิตน้ำประปาเชียงใหม่</div>
        </div>
        <span class="status-pill" style="font-size:9px">RTU SENSORS</span>
      </div>

      <div class="quality-grid">
        <div class="quality-card">
          <div class="quality-title">ความขุ่นเฉลี่ย (Turbidity)</div>
          <div class="quality-num">${fmt(m.turbidity, 2)} <small>NTU</small></div>
          <div class="quality-bar"><span style="width:${Math.min(100, (m.turbidity / 5) * 100)}%"></span></div>
          <div class="quality-help">เกณฑ์มาตรฐาน ≤ 1.0 NTU</div>
        </div>
        <div class="quality-card">
          <div class="quality-title">คลอรีนคงเหลือ (Free Cl)</div>
          <div class="quality-num">${fmt(chlorine, 2)} <small>mg/L</small></div>
          <div class="quality-bar"><span style="width:${Math.min(100, chlorine * 100)}%"></span></div>
          <div class="quality-help">เกณฑ์มาตรฐาน 0.2 - 2.0 mg/L</div>
        </div>
        <div class="quality-card">
          <div class="quality-title">อัตราจ่ายน้ำรวม (Flow)</div>
          <div class="quality-num">${fmt(m.flow)} <small>m³/h</small></div>
          <div class="quality-bar"><span style="width:${Math.min(100, (m.flow / 25000) * 100)}%"></span></div>
          <div class="quality-help">ปริมาณน้ำจ่ายรวมทุกสถานี</div>
        </div>
      </div>
    </div>
  `;
}

// ---------------- 2. MAP PAGE ----------------
function mapPage() {
  return `
    ${heading(
      'GEOGRAPHIC INFORMATION SYSTEM',
      'แผนที่จังหวัดเชียงใหม่ (GIS)',
      'สำรวจตำแหน่งสถานีผลิตน้ำ แหล่งน้ำดิบ และพื้นที่บริการประปา 25 อำเภอในจังหวัดเชียงใหม่',
      actionButton('openDemo', icon('plus') + ' จำลองเหตุการณ์', 'button-primary')
    )}
    ${cmMapPanel()}
  `;
}

// ---------------- 3. STATIONS & SOURCES PAGE ----------------
function stationsPage() {
  const d = state.data;
  const filtered = d.stations.filter(s =>
    (s.name + s.id + (s.district || '') + (s.region || '') + (s.pwaBranch || '')).toLowerCase().includes(state.query.toLowerCase())
  );

  return `
    ${heading(
      'WATER ASSETS & PRODUCTION PLANTS',
      'สถานีและแหล่งน้ำ จังหวัดเชียงใหม่',
      'รายการสถานีผลิตน้ำประปา สถานีจ่ายน้ำ และเขื่อนกักเก็บน้ำในเขตจังหวัดเชียงใหม่',
      actionButton('openDemo', icon('plus') + ' จำลองเหตุการณ์', 'button-primary')
    )}

    <div class="page-toolbar">
      <div class="searchbox">
        ${icon('search')}
        <input data-focus="station-search" aria-label="ค้นหาสถานี" placeholder="ค้นหาชื่อสถานี, อำเภอ หรือ สาขา กปภ..." value="${esc(state.query)}"/>
      </div>
      <div class="status-pill">${d.metrics.online}/${d.metrics.total} พร้อมให้บริการ</div>
    </div>

    <div class="panel table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>สถานี / รหัส</th>
            <th>อำเภอ</th>
            <th>สาขา กปภ.</th>
            <th>แรงดัน (bar)</th>
            <th>ถังเก็บ (%)</th>
            <th>อัตราไหล (m³/h)</th>
            <th>ความขุ่น (NTU)</th>
            <th>คลอรีน (mg/L)</th>
            <th>สถานะ</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${filtered.map(s => `
            <tr class="table-row-click" data-station="${esc(s.id)}">
              <td>
                <b style="color:var(--foreground)">${esc(s.name)}</b><br>
                <small class="muted">${esc(s.id)}</small>
              </td>
              <td>${esc(s.district || s.region)}</td>
              <td><small>${esc(s.pwaBranch || 'กปภ.เชียงใหม่')}</small></td>
              <td>${s.pressureBar !== null ? fmt(s.pressureBar, 2) : '-'}</td>
              <td>${s.tankLevelPct !== null ? fmt(s.tankLevelPct, 1) + '%' : '-'}</td>
              <td>${s.flowM3h !== null ? fmt(s.flowM3h) : '-'}</td>
              <td>${s.turbidityNtu !== null ? fmt(s.turbidityNtu, 2) : '-'}</td>
              <td>${s.chlorineMgL !== null ? fmt(s.chlorineMgL, 2) : '-'}</td>
              <td><span class="state-tag ${s.status}">${s.status === 'normal' ? 'ปกติ' : severityName(s.status)}</span></td>
              <td>${icon('chevron')}</td>
            </tr>
          `).join('') || `<tr><td colspan="10"><div class="blank-state">ไม่พบสถานีที่ตรงกับคำค้นหา</div></td></tr>`}
        </tbody>
      </table>
    </div>

    <div class="notice-box" style="margin-top:16px">
      ${icon('info')} ระบบเชื่อมต่อเซนเซอร์ตรวจวัดคุณภาพน้ำ RTU และข้อมูลหยุดจ่ายน้ำของการประปาส่วนภูมิภาค เขต 9 (เชียงใหม่) พร้อมรองรับการ Ingest ผ่าน <code>POST /api/telemetry</code>
    </div>
  `;
}

// ---------------- 4. ALERTS CENTER PAGE ----------------
function alertsPage() {
  const a = state.data.alerts
    .filter(x => state.filter === 'all' || x.severity === state.filter)
    .filter(x => (x.title + x.stationName + x.message).toLowerCase().includes(state.query.toLowerCase()));

  return `
    ${heading(
      'INCIDENT DETECTION & DISPATCH',
      'ศูนย์จัดการแจ้งเตือนเหตุการณ์',
      'บันทึกเหตุการณ์น้ำประปาผิดปกติ การตอบรับเหตุ (Acknowledgement) และประวัติการส่ง Telegram',
      `${actionButton('csv', icon('download') + ' Export CSV', 'button-ghost')}
       ${actionButton('test', icon('send') + ' ทดสอบ Telegram', 'button-primary')}`
    )}

    <div class="page-toolbar">
      <div class="searchbox">
        ${icon('search')}
        <input data-focus="alert-search" placeholder="ค้นหาเหตุการณ์ หรือชื่อสถานี..." value="${esc(state.query)}"/>
      </div>
      <div class="mini-toggle">
        ${[['all', 'ทั้งหมด'], ['critical', 'วิกฤต'], ['warning', 'เฝ้าระวัง'], ['resolved', 'แก้ไขแล้ว']].map(([v, t]) => `
          <button class="${state.filter === v ? 'active' : ''}" data-filter="${v}">${t}</button>
        `).join('')}
      </div>
    </div>

    <div class="panel table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>เวลา</th>
            <th>ระดับ</th>
            <th>เหตุการณ์</th>
            <th>สถานี</th>
            <th>รายละเอียด</th>
            <th>การรับทราบ</th>
            <th>จัดการ</th>
          </tr>
        </thead>
        <tbody>
          ${a.map(x => `
            <tr>
              <td>
                ${thaiDate(x.createdAt)}<br>
                <small class="muted">${thaiTime(x.createdAt)}</small>
              </td>
              <td><span class="state-tag ${x.severity}">${severityName(x.severity)}</span></td>
              <td style="white-space:normal;min-width:140px">
                <b>${esc(x.title)}</b> ${x.demo ? '<small style="color:var(--warning)">[DEMO]</small>' : ''}
              </td>
              <td>${esc(x.stationName)}</td>
              <td style="white-space:normal;min-width:220px;max-width:360px">${esc(x.message)}</td>
              <td>${x.acknowledgedAt ? `<span style="color:var(--success)">${icon('check')} รับทราบแล้ว</span>` : 'ยังไม่ได้รับทราบ'}</td>
              <td>
                ${x.acknowledgedAt ? '-' : `<button class="button button-tiny" data-ack="${esc(x.id)}">รับทราบเหตุ</button>`}
              </td>
            </tr>
          `).join('') || `<tr><td colspan="7"><div class="blank-state">ไม่มีเหตุการณ์ในเงื่อนไขที่เลือก</div></td></tr>`}
        </tbody>
      </table>
    </div>

    <div class="notice-box" style="margin-top:16px">
      ${icon('info')} ระบบจะส่งการแจ้งเตือน Telegram โดยอัตโนมัติเมื่อเกิดเหตุใหม่ หรือเปลี่ยนระดับความรุนแรง พร้อมกลไก Deduplication และ Retry แบบ Exponential Backoff
    </div>
  `;
}

// ---------------- 5. ANALYTICS & REPORTS PAGE ----------------
function analyticsPage() {
  const d = state.data;
  return `
    ${heading(
      'ADVANCED SYSTEM INSIGHTS',
      'รายงานและวิเคราะห์ข้อมูลระบบ',
      'สถิติการจ่ายน้ำ แนวโน้มแรงดันย้อนหลัง และบันทึก Audit Log ของศูนย์ควบคุมเชียงใหม่',
      actionButton('csv', icon('download') + ' Export Alerts CSV', 'button-ghost')
    )}

    <div class="kpi-grid">
      ${kpiCard('อัตราจ่ายน้ำรวม', fmt(d.metrics.flow), 'm³/h', 'TOTAL NETWORK FLOW', 'REAL-TIME', 'success', 'drops')}
      ${kpiCard('แรงดันเฉลี่ย', fmt(d.metrics.pressure, 2), 'bar', 'PROVINCIAL AVERAGE', 'STANDARD', 'success', 'gauge')}
      ${kpiCard('ความขุ่นเฉลี่ย', fmt(d.metrics.turbidity, 2), 'NTU', 'TURBIDITY INDEX', 'SAFE', 'success', 'activity')}
      ${kpiCard('เหตุการณ์ที่บันทึก', fmt(d.alerts.length), 'รายการ', 'INCIDENT AUDIT LOG', 'TOTAL', 'warning', 'warning', 'kpi-warning')}
    </div>

    <div class="overview-grid">
      ${chartPanel()}
      ${qualityPanel()}
    </div>
  `;
}

// ---------------- 6. SETTINGS & TELEGRAM GATEWAY PAGE ----------------
function settingsPage() {
  const d = state.data;
  return `
    ${heading(
      'GATEWAY CONFIGURATION & SECURITY',
      'ตั้งค่าระบบและ Telegram Gateway',
      'ตรวจสอบสถานะการเชื่อมต่อ Bot แจ้งเตือน คิวส่งข้อความ และเกณฑ์แจ้งเตือนของระบบ',
      actionButton('test', icon('send') + ' ส่งข้อความทดสอบจริง', 'button-primary')
    )}

    <div class="overview-grid">
      <div class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">${icon('send')} Telegram Notification Gateway</div>
            <div class="panel-caption">ระบบส่งข้อความแจ้งเตือนอัตโนมัติผ่าน Telegram Bot API</div>
          </div>
          <span class="status-pill ${d.telegram.configured ? '' : 'warning'}">
            ${d.telegram.configured ? 'CONFIGURED' : 'NOT CONFIGURED'}
          </span>
        </div>

        <div style="padding:18px">
          <p style="font-size:11.5px;color:#ABC4D8;margin-bottom:12px">
            กำหนดค่าในไฟล์ <code>.env</code> ฝั่งเซิร์ฟเวอร์เพื่อให้ระบบส่งข้อความแจ้งเตือนไปยังกลุ่มปฏิบัติการ:
          </p>
          <div style="background:#071526;border:1px solid var(--border);border-radius:8px;padding:12px;font-family:monospace;font-size:11px;color:#7DE8F5;margin-bottom:14px;line-height:1.7">
TELEGRAM_BOT_TOKEN=your_bot_token<br>
TELEGRAM_CHAT_ID=your_chat_id<br>
ADMIN_API_KEY=your_secret_admin_key<br>
SEND_DEMO_ALERTS=false
          </div>

          <label class="field-label" for="admin-key">Admin API Key (สำหรับเรียก API ป้องกันความปลอดภัย)</label>
          <input id="admin-key" type="password" class="field" data-focus="admin-key" placeholder="กรอก ADMIN_API_KEY จาก .env" value="${esc(state.adminKey)}"/>

          <div style="margin-top:16px;display:flex;gap:8px">
            ${actionButton('test', icon('send') + ' ส่งข้อความทดสอบ Telegram', 'button-primary')}
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">${icon('server')} สถานะคิวและอัตราการส่ง (Queue Stats)</div>
            <div class="panel-caption">Telegram Delivery Queue & Rate Limiter</div>
          </div>
        </div>

        <div style="padding:18px">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
            <div class="notice-box">
              <div style="font-size:10px;color:var(--muted)">ส่งสำเร็จ</div>
              <div style="font-size:24px;font-weight:800;color:var(--success);margin:4px 0">${d.queueStats.sent}</div>
              <div style="font-size:9.5px;color:var(--muted)">DELIVERED</div>
            </div>
            <div class="notice-box">
              <div style="font-size:10px;color:var(--muted)">กำลังรอส่ง</div>
              <div style="font-size:24px;font-weight:800;color:var(--primary);margin:4px 0">${d.queueStats.pending}</div>
              <div style="font-size:9.5px;color:var(--muted)">PENDING / RETRY</div>
            </div>
            <div class="notice-box">
              <div style="font-size:10px;color:var(--muted)">ล้มเหลว</div>
              <div style="font-size:24px;font-weight:800;color:var(--critical);margin:4px 0">${d.queueStats.failed}</div>
              <div style="font-size:9.5px;color:var(--muted)">FAILED</div>
            </div>
            <div class="notice-box">
              <div style="font-size:10px;color:var(--muted)">ส่งเตือนซ้ำ</div>
              <div style="font-size:24px;font-weight:800;color:var(--warning);margin:4px 0">${d.telegram.reminderMinutes} <small style="font-size:11px">นาที</small></div>
              <div style="font-size:9.5px;color:var(--muted)">COOLDOWN</div>
            </div>
          </div>

          ${actionButton('retry', icon('refresh') + ' Retry Failed Messages', 'button-ghost')}
        </div>
      </div>
    </div>

    <!-- Threshold Rules Table -->
    <div class="panel" style="margin-top:16px">
      <div class="panel-head">
        <div>
          <div class="panel-title">${icon('sliders')} เกณฑ์การแจ้งเตือนแรงดันและคุณภาพน้ำ (Alert Threshold Rules)</div>
          <div class="panel-caption">เกณฑ์ที่ศูนย์ควบคุมใช้ประเมินและแจ้งเตือนไปยัง Telegram</div>
        </div>
      </div>

      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>ตัวชี้วัด</th>
              <th>ทิศทาง</th>
              <th>เกณฑ์เฝ้าระวัง (Warning)</th>
              <th>เกณฑ์วิกฤต (Critical)</th>
            </tr>
          </thead>
          <tbody>
            ${d.rules.map(r => `
              <tr>
                <td><b>${esc(r.title)}</b></td>
                <td>${r.direction === 'low' ? 'ต่ำกว่า' : r.direction === 'high' ? 'สูงกว่า' : 'ออฟไลน์'}</td>
                <td>${r.direction === 'offline' ? '—' : fmt(r.warning, 1) + ' ' + r.unit}</td>
                <td>${r.direction === 'offline' ? 'สถานีหยุดส่ง' : fmt(r.critical, 1) + ' ' + r.unit}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ---------------- DRAWER & MODAL ----------------
function drawer() {
  const s = state.data.stations.find(x => x.id === state.selected);
  if (!s) return '';
  const alerts = state.data.alerts.filter(a => a.stationId === s.id).slice(0, 4);

  return `
    <div class="drawer-scrim" data-action="closeDrawer">
      <aside class="drawer" role="dialog" aria-modal="true" aria-label="รายละเอียดสถานี ${esc(s.name)}" data-stop="true">
        <div class="drawer-top">
          <span class="detail-id">${esc(s.id)} · PWA CHIANG MAI</span>
          <button class="icon-btn" data-action="closeDrawer" aria-label="ปิด">${icon('close')}</button>
        </div>

        <div>
          <h2>${esc(s.name)}</h2>
          <p class="subheading">${esc(s.district || s.region)} · ${esc(s.pwaBranch || 'การประปาส่วนภูมิภาค')}</p>
          <div style="margin-top:8px">
            <span class="state-tag ${s.status}">${s.status === 'normal' ? 'ปกติ' : severityName(s.status)}</span>
          </div>
        </div>

        <div class="drawer-metric-grid">
          ${[
            ['แรงดันน้ำ', s.pressureBar !== null ? fmt(s.pressureBar, 2) : '-', 'bar'],
            ['ระดับถังเก็บน้ำ', s.tankLevelPct !== null ? fmt(s.tankLevelPct, 1) : '-', '%'],
            ['อัตราการจ่ายน้ำ', s.flowM3h !== null ? fmt(s.flowM3h) : '-', 'm³/h'],
            ['ความขุ่น', s.turbidityNtu !== null ? fmt(s.turbidityNtu, 2) : '-', 'NTU'],
            ['คลอรีนคงเหลือ', s.chlorineMgL !== null ? fmt(s.chlorineMgL, 2) : '-', 'mg/L'],
            ['สถานะการเชื่อมต่อ', s.online ? 'ONLINE' : 'OFFLINE', '']
          ].map(([n, v, u]) => `
            <div class="drawer-metric">
              <small>${n}</small>
              <strong>${v}</strong>
              <em>${u}</em>
            </div>
          `).join('')}
        </div>

        <div class="drawer-section-title">ประวัติเหตุการณ์ของสถานีนี้</div>
        ${alerts.length ? alerts.map(alertRow).join('') : '<div class="notice-box success">ไม่มีประวัติเหตุการณ์ผิดปกติ</div>'}

        <div style="margin-top:20px">
          ${actionButton('closeDrawer', 'ปิดหน้าต่าง', 'button-ghost', 'style="width:100%"')}
        </div>
      </aside>
    </div>
  `;
}

function modal() {
  if (state.modal !== 'demo') return '';
  return `
    <div class="modal-scrim" data-action="closeModal">
      <div class="modal" role="dialog" aria-modal="true" aria-label="จำลองเหตุการณ์" data-stop="true">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <h2>จำลองเหตุผิดปกติ</h2>
          <button class="icon-btn" data-action="closeModal" aria-label="ปิด">${icon('close')}</button>
        </div>
        <p>เลือกสถานีในจังหวัดเชียงใหม่ และประเภทเหตุการณ์ เพื่อทดสอบระบบตรวจจับและแจ้งเตือน</p>

        <label class="field-label" for="demoStation">สถานีในจังหวัดเชียงใหม่</label>
        <select class="field" id="demoStation">
          ${state.data.stations.map(s => `
            <option value="${s.id}" ${s.id === state.demoStation ? 'selected' : ''}>
              ${s.name} (${s.id} - ${s.district || s.region})
            </option>
          `).join('')}
        </select>

        <label class="field-label" for="demoType">ประเภทเหตุผิดปกติ</label>
        <select class="field" id="demoType">
          <option value="pressure-low" ${state.demoType === 'pressure-low' ? 'selected' : ''}>แรงดันน้ำต่ำวิกฤต (&lt; 0.9 bar)</option>
          <option value="tank-low" ${state.demoType === 'tank-low' ? 'selected' : ''}>ระดับถังเก็บน้ำต่ำวิกฤต (&lt; 20%)</option>
          <option value="turbidity-high" ${state.demoType === 'turbidity-high' ? 'selected' : ''}>ความขุ่นสูงผิดปกติ (&gt; 4.0 NTU)</option>
          <option value="station-offline" ${state.demoType === 'station-offline' ? 'selected' : ''}>สถานีขาดการเชื่อมต่อ (Offline)</option>
        </select>

        <div class="notice-box warning" style="margin-top:14px">
          ${icon('info')} ข้อมูลจำลองจะไม่ถูกส่งไปยัง Telegram อัตโนมัติ เว้นแต่กำหนด <code>SEND_DEMO_ALERTS=true</code>
        </div>

        <div class="modal-actions">
          ${actionButton('closeModal', 'ยกเลิก', 'button-ghost')}
          ${actionButton('simulate', icon('activity') + ' จำลองเหตุการณ์', 'button-primary')}
        </div>
      </div>
    </div>
  `;
}

function notify(message, error = false) {
  state.toast = { message, error };
  clearTimeout(toastTimeout);
  render();
  toastTimeout = setTimeout(() => {
    state.toast = null;
    render();
  }, 3800);
}

async function sendReq(url, method = 'POST', bodyData) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.adminKey) headers['X-API-Key'] = state.adminKey;
  const res = await fetch(url, { method, headers, body: JSON.stringify(bodyData || {}) });
  const result = await res.json().catch(() => ({ error: 'Invalid response' }));
  if (!res.ok) throw new Error(result.error || `HTTP ${res.status}`);
  return result;
}

async function runAction(name, extra) {
  try {
    if (name === 'menu') { state.menu = !state.menu; render(); return; }
    if (name === 'openDemo') { state.modal = 'demo'; render(); return; }
    if (name === 'closeModal') { state.modal = null; render(); return; }
    if (name === 'closeDrawer') { state.selected = null; render(); return; }
    if (name === 'setMapFilter') { state.mapFilter = extra; render(); return; }
    if (name === 'simulate') {
      state.demoStation = $('#demoStation').value;
      state.demoType = $('#demoType').value;
      const res = await sendReq('/api/demo/incident', 'POST', { stationId: state.demoStation, type: state.demoType });
      state.modal = null;
      notify(`จำลองเหตุการณ์ที่สถานี ${res.stationId} สำเร็จ`);
      return;
    }
    if (name === 'reset') {
      if (!confirm('รีเซ็ตค่าจำลองทั้งหมดกลับสู่ปกติ?')) return;
      await sendReq('/api/demo/reset');
      notify('รีเซ็ตข้อมูลจำลองทุกสถานีกลับสู่ปกติแล้ว');
      return;
    }
    if (name === 'test') {
      let key = state.adminKey || prompt('กรอก ADMIN_API_KEY จาก .env สำหรับส่งข้อความทดสอบ Telegram');
      if (!key) return;
      state.adminKey = key;
      const result = await sendReq('/api/test-telegram');
      notify(`เพิ่มข้อความทดสอบเข้าคิวส่งแล้ว (${result.id})`);
      return;
    }
    if (name === 'retry') {
      let key = state.adminKey || prompt('กรอก ADMIN_API_KEY เพื่อ Retry ข้อความที่ล้มเหลว');
      if (!key) return;
      state.adminKey = key;
      const r = await sendReq('/api/queue/retry-failed');
      notify(`นำรายการส่งล้มเหลวกลับเข้าคิว ${r.retried} รายการ`);
      return;
    }
    if (name === 'ack') {
      if (!state.adminKey) {
        let k = prompt('กรอก ADMIN_API_KEY เพื่อบันทึกการรับทราบเหตุ');
        if (!k) return;
        state.adminKey = k;
      }
      await sendReq(`/api/alerts/${extra}/ack`);
      notify('บันทึกการรับทราบเหตุการณ์เรียบร้อย');
      return;
    }
    if (name === 'csv') {
      if (!state.adminKey) {
        let k = prompt('กรอก ADMIN_API_KEY เพื่อ Export ข้อมูล');
        if (!k) return;
        state.adminKey = k;
      }
      const r = await fetch('/api/export/alerts', { headers: { 'X-API-Key': state.adminKey } });
      if (!r.ok) throw Error(`Export ถูกปฏิเสธ (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'chiangmai-water-alerts.csv';
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify('ส่งออกไฟล์ CSV เหตุการณ์แล้ว');
      return;
    }
  } catch (err) {
    notify(err.message, true);
  }
}

// Global Event Listeners
document.addEventListener('click', e => {
  const view = e.target.closest('[data-view]');
  if (view) {
    state.view = view.dataset.view;
    state.selected = null;
    state.modal = null;
    state.menu = false;
    state.query = '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
    render();
    return;
  }

  const range = e.target.closest('[data-range]');
  if (range) {
    state.range = range.dataset.range;
    render();
    return;
  }

  const filter = e.target.closest('[data-filter]');
  if (filter) {
    state.filter = filter.dataset.filter;
    render();
    return;
  }

  const station = e.target.closest('[data-station]');
  if (station && station.dataset.station && state.data.stations.some(x => x.id === station.dataset.station)) {
    state.selected = station.dataset.station;
    render();
    return;
  }

  const district = e.target.closest('[data-district]');
  if (district && district.dataset.district) {
    state.selectedDistrict = state.selectedDistrict === district.dataset.district ? '' : district.dataset.district;
    render();
    return;
  }

  const mapFilterBtn = e.target.closest('[data-action="setMapFilter"]');
  if (mapFilterBtn && mapFilterBtn.dataset.filterVal) {
    state.mapFilter = mapFilterBtn.dataset.filterVal;
    render();
    return;
  }

  const ack = e.target.closest('[data-ack]');
  if (ack) {
    runAction('ack', ack.dataset.ack);
    return;
  }

  const act = e.target.closest('[data-action]');
  if (act && (!e.target.closest('[data-stop]') || act.closest('button'))) {
    runAction(act.dataset.action);
  }
});

document.addEventListener('change', e => {
  if (e.target.matches('[data-action="selectDistrict"]')) {
    state.selectedDistrict = e.target.value;
    render();
  }
});

document.addEventListener('input', e => {
  if (e.target.matches('[data-focus="station-search"]') || e.target.matches('[data-focus="alert-search"]')) {
    state.query = e.target.value;
    render();
  }
  if (e.target.matches('[data-focus="admin-key"]')) {
    state.adminKey = e.target.value;
  }
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (state.selected || state.modal) {
      state.selected = null;
      state.modal = null;
      render();
    }
  }
  if (e.key === 'Enter' && e.target.closest('.cm-station-node, .alert-item')) {
    const station = e.target.closest('[data-station]');
    if (station && station.dataset.station) {
      state.selected = station.dataset.station;
      render();
    }
  }
});

async function loadDistricts() {
  try {
    const res = await fetch('/chiangmai_svg_districts.json');
    if (res.ok) {
      const list = await res.json();
      if (Array.isArray(list)) {
        state.districts = list;
        render();
      }
    }
  } catch (err) {}
}

async function init() {
  try {
    const r = await fetch('/api/state');
    if (r.status === 401) {
      const appEl = $('#app');
      if (appEl) {
        appEl.innerHTML = `
          <div class="boot" style="max-width:440px;margin:60px auto;padding:32px;background:rgba(10,25,47,0.95);border:1px solid rgba(0,180,216,0.35);border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,0.6);text-align:center;">
            <div style="font-size:36px;color:var(--accent,#00b4d8);margin-bottom:12px;">${icon('server')}</div>
            <h2 style="margin:0 0 8px;font-size:20px;color:#f8fafc;font-weight:600;">AQUA COMMAND · ยืนยันสิทธิ์การเข้าใช้งาน</h2>
            <p style="color:#94a3b8;font-size:13px;margin:0 0 20px;line-height:1.5;">ระบบเปิดใช้งานโหมดความปลอดภัย (Distributed Lab Profile)<br/>กรุณากรอก Viewer Key เพื่อเข้าสู่ Dashboard</p>
            <form id="aqua-login-form" style="display:flex;flex-direction:column;gap:14px;text-align:left;">
              <div>
                <label style="display:block;font-size:12px;color:#cbd5e1;margin-bottom:6px;">Viewer Key / Passphrase</label>
                <input id="aqua-login-key" type="password" placeholder="กรอกรหัสผ่านเพื่อเข้าใช้งาน" autocomplete="current-password" style="width:100%;box-sizing:border-box;padding:10px 14px;border-radius:6px;border:1px solid #334155;background:#0f172a;color:#f8fafc;font-size:14px;" required />
              </div>
              <button type="submit" style="padding:11px 16px;font-weight:600;background:#0284c7;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px;transition:background 0.2s;">เข้าสู่ระบบ (Sign In)</button>
              <div id="aqua-login-error" style="color:#ef4444;font-size:13px;display:none;background:rgba(239,68,68,0.1);padding:8px 12px;border-radius:6px;border:1px solid rgba(239,68,68,0.2);"></div>
            </form>
          </div>
        `;
        const form = document.getElementById('aqua-login-form');
        form?.addEventListener('submit', async ev => {
          ev.preventDefault();
          const errEl = document.getElementById('aqua-login-error');
          const keyInput = document.getElementById('aqua-login-key');
          if (errEl) errEl.style.display = 'none';
          try {
            const res = await fetch('/api/auth/login', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ key: keyInput?.value?.trim() })
            });
            if (res.ok) {
              init();
            } else {
              const err = await res.json().catch(() => ({}));
              if (errEl) {
                errEl.textContent = err.error || 'รหัสผ่านไม่ถูกต้อง หรือสิทธิ์ไม่เพียงพอ';
                errEl.style.display = 'block';
              }
            }
          } catch (networkErr) {
            if (errEl) {
              errEl.textContent = 'ไม่สามารถติดต่อเซิร์ฟเวอร์ได้: ' + networkErr.message;
              errEl.style.display = 'block';
            }
          }
        });
      }
      return;
    }
    if (!r.ok) throw Error('Server error HTTP ' + r.status);
    state.data = await r.json();
    render();

    loadDistricts();

    const es = new EventSource('/api/stream');
    es.onopen = () => {
      state.streamOnline = true;
      render();
    };
    es.onmessage = e => {
      try {
        state.data = JSON.parse(e.data);
        render();
      } catch (err) {
        console.error(err);
      }
    };
    es.onerror = () => {
      state.streamOnline = false;
      render();
    };
  } catch (e) {
    const appEl = $('#app');
    if (appEl) {
      appEl.innerHTML = `
        <div class="boot">
          <div style="font-size:26px;color:var(--warning)">${icon('warning')}</div>
          <h2>ไม่สามารถเชื่อมต่อศูนย์ควบคุมได้</h2>
          <p>${esc(e.message)} · กรุณาตรวจสอบสถานะ Node.js Server</p>
        </div>
      `;
    }
  }
}

setInterval(() => {
  const clock = $('#clock');
  if (clock) {
    clock.textContent = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Bangkok',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false
    }).format(new Date()) + ' ICT';
  }
}, 1000);

init();
