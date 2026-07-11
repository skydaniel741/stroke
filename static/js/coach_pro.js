/* Coach Pro — the real coaching dashboard, wired to your actual squads,
   swimmers, sets and assignments via /coach/pro/api/*. No fake data,
   no billing tab. Tabs: roster, attendance, builder, athlete hub,
   analytics, AI assistant. */

const STROKE_LABELS = { FR: 'Freestyle', BK: 'Backstroke', BR: 'Breaststroke', FL: 'Butterfly', IM: 'IM', Kick: 'Kick', Pull: 'Pull', Drill: 'Drill' };
const SET_CATEGORIES = ['Fast', 'Easy', 'Heart Rate', 'Drill', 'Lactate', 'Fitness', 'Open Water', 'Triathlon'];

const CP = {
  squads: [], swimmers: [], savedSets: [], assignments: [], upcomingEvents: [], announcements: [], today: null, aiEnabled: false,
  activeTab: 'roster',
  ui: {
    roster: { selectedSquadId: 'all', showAddSquad: false, showAddSwimmer: false, inviteSquadId: '', squadColor: 'blue' },
    schedule: { showCreate: false, slot: 'AM' },
    attendance: { squadId: null, date: null, marks: {}, dirty: false, saving: false },
    builder: { showCreateSet: false, editingSetId: null, blocks: [], selectedSetForAssign: null, assignTargetType: 'squad', assignTargetId: '' },
    aiGen: { show: false, loading: false },
    swimmer: { selectedSwimmerId: null },
    testsets: { squadId: null, scanning: false, result: null, error: null, saving: false },
    ai: { squadId: null, loading: false, insights: null, error: null, tone: 'balanced' },
    announcements: { squadId: null, posting: false },
    reports: { squadId: null },
  }
};

/* ---------- API helpers ---------- */

async function cpApi(url, opts) {
  const res = await fetch(url, Object.assign({ credentials: 'same-origin' }, opts || {}));
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON response */ }
  if (!res.ok || (data && data.ok === false)) {
    alert((data && data.error) || 'Something went wrong — please try again.');
    throw new Error('cp api error: ' + url);
  }
  return data;
}

function cpForm(obj) {
  const fd = new FormData();
  Object.entries(obj).forEach(([k, v]) => fd.append(k, v == null ? '' : v));
  return fd;
}

async function cpLoadState() {
  const data = await cpApi('/coach/pro/api/state');
  CP.squads = data.squads;
  CP.swimmers = data.swimmers;
  CP.savedSets = data.savedSets;
  CP.assignments = data.assignments;
  CP.upcomingEvents = data.upcomingEvents || [];
  CP.announcements = data.announcements || [];
  CP.today = data.today;
  CP.aiEnabled = !!data.aiEnabled;
}

async function cpRefresh() {
  await cpLoadState();
  cpRenderAll();
}

async function cpInit() {
  await cpLoadState();
  const firstReal = CP.swimmers.find(s => s.userId);
  CP.ui.swimmer.selectedSwimmerId = firstReal ? firstReal.userId : null;
  cpRenderAll();
}

/* ---------- shared helpers ---------- */

function cpBadgeColorClass(color) {
  switch (color) {
    case 'emerald': return 'bg-emerald-500';
    case 'blue': return 'bg-blue-500';
    case 'indigo': return 'bg-brand-500';
    case 'violet': return 'bg-violet-500';
    case 'orange': return 'bg-orange-500';
    default: return 'bg-slate-500';
  }
}

function cpSquadColorClass(color) {
  switch (color) {
    case 'emerald': return 'bg-emerald-50 border-emerald-200 text-emerald-800';
    case 'blue': return 'bg-blue-50 border-blue-200 text-blue-800';
    case 'indigo': return 'bg-brand-50 border-brand-200 text-brand-800';
    case 'violet': return 'bg-violet-50 border-violet-200 text-violet-800';
    case 'orange': return 'bg-orange-50 border-orange-200 text-orange-800';
    default: return 'bg-slate-50 border-slate-200 text-slate-800';
  }
}

function cpColorHex(color) {
  return color === 'emerald' ? '#10b981' : color === 'blue' ? '#3b82f6' : color === 'indigo' ? '#6366f1' : color === 'violet' ? '#8b5cf6' : '#f97316';
}

function cpEsc(str) {
  return String(str == null ? '' : str).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function cpStatusBadge(status) {
  const map = {
    active: 'bg-emerald-50 text-emerald-700',
    invited: 'bg-amber-50 text-amber-700',
    pending_consent: 'bg-sky-50 text-sky-700',
    declined: 'bg-rose-50 text-rose-700',
  };
  return `<span class="px-1.5 py-0.5 rounded-full font-mono font-bold text-[10px] ${map[status] || 'bg-slate-100 text-slate-600'}">${cpEsc(status || 'unknown')}</span>`;
}

/* ---------- top-level render ---------- */

function cpRenderAll() {
  cpRenderSidebar();
  cpRenderStats();
  cpRenderTab();
}

function cpRenderSidebar() {
  document.querySelectorAll('#cpSidebarNav [data-tab]').forEach(btn => {
    const active = btn.dataset.tab === CP.activeTab;
    btn.className = `w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-wide transition-all cursor-pointer text-left ${
      active ? 'cp-nav-active' : 'text-slate-300 hover:bg-slate-800 hover:text-white'
    }`;
  });
}

function cpRenderStats() {
  const realSwimmers = CP.swimmers.filter(s => s.userId);
  const totalDistance = realSwimmers.reduce((a, s) => a + (s.totalDistance || 0), 0);
  const avgDistance = realSwimmers.length ? Math.round(totalDistance / realSwimmers.length) : 0;
  const activeSetsCount = CP.assignments.filter(a => a.status === 'Assigned').length;

  const rated = realSwimmers.filter(s => s.attendanceRate != null);
  const avgAttendance = rated.length ? Math.round(rated.reduce((a, s) => a + s.attendanceRate, 0) / rated.length) : null;

  document.getElementById('cpStatSwimmers').textContent = CP.swimmers.length;
  document.getElementById('cpStatPoints').textContent = avgDistance.toLocaleString() + 'm';
  document.getElementById('cpStatAttendance').textContent = avgAttendance == null ? '—' : avgAttendance + '%';
  document.getElementById('cpStatActiveSets').textContent = activeSetsCount;
}

function cpRenderTab() {
  const root = document.getElementById('cpTabContent');
  if (CP.activeTab === 'roster') root.innerHTML = cpRenderRoster();
  else if (CP.activeTab === 'schedule') root.innerHTML = cpRenderSchedule();
  else if (CP.activeTab === 'attendance') root.innerHTML = cpRenderAttendance();
  else if (CP.activeTab === 'builder') root.innerHTML = cpRenderBuilder();
  else if (CP.activeTab === 'swimmer') root.innerHTML = cpRenderSwimmer();
  else if (CP.activeTab === 'testsets') root.innerHTML = cpRenderTestSets();
  else if (CP.activeTab === 'analytics') root.innerHTML = cpRenderAnalytics();
  else if (CP.activeTab === 'announcements') root.innerHTML = cpRenderAnnouncements();
  else if (CP.activeTab === 'reports') root.innerHTML = cpRenderReports();
  else if (CP.activeTab === 'ai') root.innerHTML = cpRenderAI();
  if (window.lucide) lucide.createIcons();
}

/* ================= TAB: SCHEDULE (what's coming up, AM/PM sessions) ================= */

function cpFmtDay(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  if (dateStr === CP.today) return 'Today';
  const names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${names[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]}`;
}

function cpSlotBadge(slot) {
  if (slot === 'AM') return '<span class="text-[9px] font-bold px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-100">AM</span>';
  if (slot === 'PM') return '<span class="text-[9px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-100">PM</span>';
  return '';
}

function cpRenderSchedule() {
  const ui = CP.ui.schedule;
  if (CP.squads.length === 0) {
    return `<div class="p-12 text-center text-slate-400 text-xs">No squads yet — create one from Squad Roster first.</div>`;
  }

  const next = CP.upcomingEvents[0];
  const nextSquad = next ? CP.squads.find(s => s.id === next.squadId) : null;
  const nextCard = next ? `
    <div class="bg-[#111111] text-white rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
      <div>
        <p class="text-[10px] font-bold text-[#ccccff] uppercase tracking-widest mb-1.5">Next session</p>
        <div class="flex items-center gap-2">
          <h4 class="text-base font-bold">${cpEsc(next.title)}</h4>
          ${cpSlotBadge(next.slot)}
        </div>
        <p class="text-[11px] text-slate-300 mt-1">${cpFmtDay(next.date)}${next.time ? ' · ' + cpEsc(next.time) : ''} · ${cpEsc(nextSquad ? nextSquad.name : 'Squad')}${next.setTitle ? ` · ${cpEsc(next.setTitle)} (${next.setDistance}m)` : ''}</p>
      </div>
      ${next.setTitle ? '<span class="text-[10px] text-[#ccccff] bg-white/10 px-3 py-1.5 rounded-lg">Auto-logs for swimmers marked present</span>' : ''}
    </div>` : `
    <div class="bg-slate-50 border border-slate-100 rounded-xl p-6 text-center text-xs text-slate-400">Nothing scheduled yet — plan your first session below.</div>`;

  const createForm = ui.showCreate ? `
    <form id="cpCreateEventForm" class="bg-slate-50 border border-slate-200 rounded-xl p-5 grid grid-cols-1 md:grid-cols-2 gap-4 shadow-sm">
      <div class="md:col-span-2 flex items-center justify-between border-b border-slate-200 pb-2">
        <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider">Plan a session</h4>
        <button type="button" data-action="cp-toggle-create-event" class="text-xs text-slate-500 hover:text-slate-700">Close</button>
      </div>
      <div>
        <label class="block text-[10px] text-slate-500 font-medium mb-1">Title</label>
        <input type="text" name="title" required placeholder="e.g. Morning aerobic swim" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
      </div>
      <div>
        <label class="block text-[10px] text-slate-500 font-medium mb-1">Squad</label>
        <select name="squad_id" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:outline-hidden">
          ${CP.squads.map(sq => `<option value="${sq.id}">${cpEsc(sq.name)}</option>`).join('')}
        </select>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <div class="col-span-1">
          <label class="block text-[10px] text-slate-500 font-medium mb-1">Date</label>
          <input type="date" name="date" required value="${cpTodayStr()}" class="w-full text-xs px-2 py-1.5 bg-white border border-slate-200 rounded focus:outline-hidden">
        </div>
        <div>
          <label class="block text-[10px] text-slate-500 font-medium mb-1">Slot</label>
          <div class="flex gap-1">
            ${['AM', 'PM'].map(s => `<button type="button" data-action="cp-pick-slot" data-slot="${s}" class="flex-1 py-1.5 rounded text-xs font-semibold ${ui.slot === s ? 'bg-[#111111] text-[#ccccff]' : 'bg-white border border-slate-200 text-slate-500'}">${s}</button>`).join('')}
          </div>
        </div>
        <div>
          <label class="block text-[10px] text-slate-500 font-medium mb-1">Time (optional)</label>
          <input type="text" name="time" placeholder="6:00" class="w-full text-xs px-2 py-1.5 bg-white border border-slate-200 rounded focus:outline-hidden">
        </div>
      </div>
      <div>
        <label class="block text-[10px] text-slate-500 font-medium mb-1">Attach a set (auto-logs for attendees)</label>
        <select name="set_id" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:outline-hidden">
          <option value="">No set — just a calendar entry</option>
          ${CP.savedSets.map(s => `<option value="${s.id}">${cpEsc(s.title)} · ${s.totalDistance}m</option>`).join('')}
        </select>
      </div>
      <div class="md:col-span-2">
        <label class="block text-[10px] text-slate-500 font-medium mb-1">Notes for the day (optional)</label>
        <input type="text" name="notes" placeholder="e.g. bring fins, lane 4-6 only" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:outline-hidden">
      </div>
      <div class="md:col-span-2 flex justify-end gap-2 pt-2 border-t border-slate-200">
        <button type="button" data-action="cp-toggle-create-event" class="px-3 py-1.5 text-xs text-slate-600 font-medium">Cancel</button>
        <button type="submit" class="px-4 py-1.5 bg-brand-600 text-white font-medium text-xs rounded hover:bg-brand-700 transition">Add to schedule</button>
      </div>
    </form>` : '';

  const byDate = {};
  CP.upcomingEvents.forEach(e => { (byDate[e.date] = byDate[e.date] || []).push(e); });
  const dayGroups = Object.keys(byDate).sort().map(date => `
    <div>
      <p class="text-[10px] font-bold uppercase tracking-widest mb-2 ${date === CP.today ? 'text-brand-600' : 'text-slate-400'}">${cpFmtDay(date)}</p>
      <div class="space-y-2">
        ${byDate[date].map(e => {
          const sq = CP.squads.find(s => s.id === e.squadId);
          return `
          <div class="bg-white border border-slate-200 rounded-xl px-4 py-3 flex items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                ${cpSlotBadge(e.slot)}
                <span class="text-xs font-semibold text-slate-900 truncate">${cpEsc(e.title)}</span>
                ${e.type === 'meet' ? '<span class="text-[9px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">Meet</span>' : ''}
              </div>
              <p class="text-[10px] text-slate-400 mt-0.5">
                ${cpEsc(sq ? sq.name : 'Squad')}${e.time ? ' · ' + cpEsc(e.time) : ''}${e.setTitle ? ` · <span class="text-brand-600 font-semibold">${cpEsc(e.setTitle)} (${e.setDistance}m)</span>` : ''}${e.notes ? ' · ' + cpEsc(e.notes) : ''}
              </p>
            </div>
            <button data-action="cp-remove-event" data-id="${e.id}" class="text-slate-300 hover:text-rose-600 transition shrink-0" title="Remove"><i data-lucide="x" class="w-3.5 h-3.5"></i></button>
          </div>`;
        }).join('')}
      </div>
    </div>`).join('');

  return `
    <div class="max-w-3xl space-y-5" id="schedule_section">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="calendar-days" class="w-4 h-4 text-slate-500"></i> Session schedule</h3>
          <p class="text-xs text-slate-400 mt-1">Plan the next two weeks. Attach a set and it logs itself for every swimmer you mark present.</p>
        </div>
        <button data-action="cp-toggle-create-event" class="px-3 py-1.5 bg-brand-600 text-white rounded-lg text-xs font-medium flex items-center gap-1.5 hover:bg-brand-700 transition"><i data-lucide="plus" class="w-3.5 h-3.5"></i> Plan session</button>
      </div>
      ${nextCard}
      ${createForm}
      ${dayGroups || ''}
    </div>`;
}

/* ================= TAB: TEST SETS (photo -> per-swimmer times) ================= */

function cpRenderTestSets() {
  const ui = CP.ui.testsets;
  if (!ui.squadId && CP.squads.length) ui.squadId = CP.squads[0].id;

  if (!CP.aiEnabled) {
    return `<div class="max-w-xl mx-auto mt-10 p-8 text-center bg-slate-50 border border-slate-200 rounded-xl">
      <i data-lucide="camera" class="w-6 h-6 text-slate-400 mx-auto mb-3"></i>
      <h3 class="text-sm font-semibold text-slate-800">Test set scanning isn't configured</h3>
      <p class="text-xs text-slate-500 mt-2">Add an ANTHROPIC_API_KEY to the server's .env to scan results boards into swimmer times.</p>
    </div>`;
  }
  if (CP.squads.length === 0) {
    return `<div class="p-12 text-center text-slate-400 text-xs">No squads yet — create one from Squad Roster first.</div>`;
  }

  const squadSwimmers = CP.swimmers.filter(s => s.userId && s.squadId === ui.squadId && s.status === 'active');
  const r = ui.result;

  const resultsPanel = ui.scanning ? `
    <div class="p-16 text-center bg-white border border-slate-200 rounded-xl">
      <div class="w-8 h-8 border-2 border-slate-200 border-t-slate-800 rounded-full animate-spin mx-auto mb-4"></div>
      <p class="text-xs text-slate-500">Reading names and times off the board…</p>
    </div>` : ui.error ? `
    <div class="p-8 text-center bg-rose-50 border border-rose-100 rounded-xl"><p class="text-xs text-rose-700">${cpEsc(ui.error)}</p></div>` : r ? `
    <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
      <div class="flex flex-wrap items-end gap-3 border-b border-slate-100 pb-3">
        <div>
          <label class="block text-[10px] text-slate-500 font-medium mb-1">Test</label>
          <input type="text" id="cpTsLabel" value="${cpEsc(r.test_label)}" class="text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded w-44">
        </div>
        <div>
          <label class="block text-[10px] text-slate-500 font-medium mb-1">Logs as event</label>
          <input type="text" id="cpTsEvent" value="${cpEsc(r.event)}" placeholder="e.g. 100m Freestyle" class="text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded w-44">
        </div>
        <div>
          <label class="block text-[10px] text-slate-500 font-medium mb-1">Pool</label>
          <select id="cpTsPool" class="text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded"><option value="25m">25m</option><option value="50m">50m</option></select>
        </div>
      </div>
      <div class="space-y-2">
        ${r.results.map((row, i) => `
          <div class="flex flex-wrap items-center gap-3 px-3 py-2.5 bg-slate-50 border border-slate-100 rounded-xl" data-ts-row="${i}">
            <select class="ts-swimmer text-xs px-2 py-1.5 bg-white border ${row.userId ? 'border-emerald-200' : 'border-amber-300'} rounded w-44">
              <option value="">Skip — don't log</option>
              ${squadSwimmers.map(sw => `<option value="${sw.userId}" ${sw.userId === row.userId ? 'selected' : ''}>${cpEsc(sw.name)}</option>`).join('')}
            </select>
            <span class="text-[10px] ${row.userId ? 'text-emerald-600' : 'text-amber-600'} font-semibold w-28">${row.userId ? 'Matched' : `Board says "${cpEsc(row.name)}"`}</span>
            <input type="text" class="ts-times flex-1 min-w-[140px] text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded font-mono" value="${cpEsc(row.times.join(', '))}">
            ${row.note ? `<span class="text-[10px] text-slate-400 italic">${cpEsc(row.note)}</span>` : ''}
          </div>`).join('')}
      </div>
      <p class="text-[10px] text-slate-400">Each swimmer's best rep is logged as a swim tagged <span class="font-mono font-bold">test</span>; all reps are kept in the notes. Fix any times the scan misread before saving.</p>
      <div class="flex justify-end gap-2">
        <button data-action="cp-ts-discard" class="px-3 py-1.5 text-xs text-slate-600 font-medium">Discard</button>
        <button data-action="cp-ts-save" class="px-5 py-2 bg-[#111111] hover:bg-slate-800 text-[#ccccff] rounded-lg text-xs font-semibold transition ${ui.saving ? 'opacity-60 pointer-events-none' : ''}">${ui.saving ? 'Saving…' : 'Log results'}</button>
      </div>
    </div>` : `
    <div class="p-12 text-center bg-slate-50 border border-slate-100 rounded-xl">
      <i data-lucide="camera" class="w-6 h-6 text-slate-400 mx-auto mb-3"></i>
      <p class="text-xs text-slate-500 max-w-sm mx-auto leading-relaxed">Ran a test set like 5×100 max? Photograph the results board or your clipboard and the times land on each swimmer's profile — no spreadsheet needed.</p>
    </div>`;

  return `
    <div class="max-w-3xl space-y-5" id="testsets_section">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="camera" class="w-4 h-4 text-slate-500"></i> Test set results</h3>
          <p class="text-xs text-slate-400 mt-1">Photo of the results board → times logged to each swimmer.</p>
        </div>
        <div class="flex gap-2.5 items-center">
          <select id="cpTsSquadSelect" class="text-xs px-3 py-2 bg-white border border-slate-200 rounded-lg font-medium focus:outline-hidden">
            ${CP.squads.map(sq => `<option value="${sq.id}" ${sq.id === ui.squadId ? 'selected' : ''}>${cpEsc(sq.name)}</option>`).join('')}
          </select>
          <input type="file" id="cpTsPhoto" accept="image/*" capture="environment" class="hidden">
          <button data-action="cp-ts-pick-photo" class="px-4 py-2 bg-[#111111] hover:bg-slate-800 text-[#ccccff] rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${ui.scanning ? 'opacity-60 pointer-events-none' : ''}">
            <i data-lucide="camera" class="w-3.5 h-3.5"></i> Scan results photo
          </button>
        </div>
      </div>
      ${resultsPanel}
    </div>`;
}

/* ================= TAB: ANNOUNCEMENTS (one-way squad message board) ================= */

function cpRenderAnnouncements() {
  const ui = CP.ui.announcements;
  if (!ui.squadId && CP.squads.length) ui.squadId = CP.squads[0].id;
  if (CP.squads.length === 0) {
    return `<div class="p-12 text-center text-slate-400 text-xs">No squads yet — create one from Squad Roster first.</div>`;
  }

  const posts = CP.announcements.filter(a => a.squadId === ui.squadId);
  const list = posts.length === 0 ? `
    <div class="p-12 text-center text-xs text-slate-400 bg-slate-50 border border-slate-100 rounded-xl">Nothing posted to this squad yet.</div>` :
    posts.map(a => `
      <div class="bg-white border border-slate-200 rounded-xl px-4 py-3 flex items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs text-slate-800 leading-relaxed">${cpEsc(a.message)}</p>
          <p class="text-[10px] text-slate-400 mt-1.5">${a.createdAt}</p>
        </div>
        <button data-action="cp-ann-delete" data-id="${a.id}" class="text-slate-300 hover:text-rose-600 transition shrink-0" title="Delete"><i data-lucide="x" class="w-3.5 h-3.5"></i></button>
      </div>`).join('');

  return `
    <div class="max-w-3xl space-y-5" id="announcements_section">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="megaphone" class="w-4 h-4 text-slate-500"></i> Announcements</h3>
          <p class="text-xs text-slate-400 mt-1">One-way message board — swimmers see these on their dashboard.</p>
        </div>
        <select id="cpAnnSquadSelect" class="text-xs px-3 py-2 bg-white border border-slate-200 rounded-lg font-medium focus:outline-hidden">
          ${CP.squads.map(sq => `<option value="${sq.id}" ${sq.id === ui.squadId ? 'selected' : ''}>${cpEsc(sq.name)}</option>`).join('')}
        </select>
      </div>

      <form id="cpAnnForm" class="bg-white border border-slate-200 rounded-xl p-4 flex gap-2.5">
        <input type="text" name="message" id="cpAnnInput" required placeholder="e.g. No training Friday — pool closed for gala setup" class="flex-1 text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
        <button type="button" data-voice-target="cpAnnInput" title="Dictate with your voice" class="voice-btn shrink-0 w-9 h-9 flex items-center justify-center border border-slate-200 rounded-lg text-slate-600 hover:text-brand-700 hover:border-brand-300 transition">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>
        </button>
        <button type="submit" class="px-4 py-2 bg-[#111111] hover:bg-slate-800 text-[#ccccff] rounded-lg text-xs font-semibold transition ${ui.posting ? 'opacity-60 pointer-events-none' : ''}">${ui.posting ? 'Posting…' : 'Post'}</button>
      </form>
      <p class="text-[10px] text-slate-400 mt-1.5">🎙️ Tap the mic to dictate your announcement.</p>

      <div class="space-y-2">${list}</div>
    </div>`;
}

/* ================= TAB: REPORTS (printable per-squad summary) ================= */

function cpRenderReports() {
  const ui = CP.ui.reports;
  if (!ui.squadId && CP.squads.length) ui.squadId = CP.squads[0].id;
  if (CP.squads.length === 0) {
    return `<div class="p-12 text-center text-slate-400 text-xs">No squads yet — create one from Squad Roster first.</div>`;
  }

  const squad = CP.squads.find(s => s.id === ui.squadId);
  const squadSwimmers = CP.swimmers.filter(s => s.userId && s.squadId === ui.squadId && s.status === 'active');

  const rows = squadSwimmers.map(s => `
    <tr class="border-b border-slate-100">
      <td class="px-4 py-3 font-semibold text-slate-900">${cpEsc(s.name)}</td>
      <td class="px-4 py-3 text-center font-mono">${s.sessionsCount}</td>
      <td class="px-4 py-3 text-center font-mono">${(s.totalDistance || 0).toLocaleString()}m</td>
      <td class="px-4 py-3 text-center font-mono">${s.attendanceRate == null ? '—' : s.attendanceRate + '%'}</td>
      <td class="px-4 py-3 text-xs">
        ${(s.personalBests || []).length === 0 ? '<span class="text-slate-400 italic">None logged</span>' :
          s.personalBests.map(pb => `<span class="inline-block mr-3 whitespace-nowrap">${cpEsc(pb.event)}: <span class="font-mono font-bold">${cpEsc(pb.time)}</span></span>`).join('')}
      </td>
    </tr>`).join('');

  return `
    <div class="max-w-4xl space-y-5" id="reports_section">
      <div class="flex flex-wrap items-end justify-between gap-4 no-print">
        <div>
          <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="file-text" class="w-4 h-4 text-slate-500"></i> Squad report</h3>
          <p class="text-xs text-slate-400 mt-1">A parent/committee-ready summary. Print it or save as PDF.</p>
        </div>
        <div class="flex gap-2.5">
          <select id="cpRepSquadSelect" class="text-xs px-3 py-2 bg-white border border-slate-200 rounded-lg font-medium focus:outline-hidden">
            ${CP.squads.map(sq => `<option value="${sq.id}" ${sq.id === ui.squadId ? 'selected' : ''}>${cpEsc(sq.name)}</option>`).join('')}
          </select>
          <button data-action="cp-rep-print" class="px-4 py-2 bg-[#111111] hover:bg-slate-800 text-[#ccccff] rounded-lg text-xs font-semibold flex items-center gap-1.5 transition"><i data-lucide="printer" class="w-3.5 h-3.5"></i> Print / PDF</button>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div class="px-5 py-4 border-b border-slate-100">
          <h4 class="text-base font-bold text-slate-900">${cpEsc(squad ? squad.name : '')} — squad report</h4>
          <p class="text-[10px] text-slate-400 mt-0.5">Generated ${CP.today} · ${squadSwimmers.length} active swimmer(s) · attendance measured over the last 30 days of roll calls</p>
        </div>
        ${squadSwimmers.length === 0 ? '<div class="p-12 text-center text-xs text-slate-400">No active swimmers in this squad yet.</div>' : `
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs text-slate-600">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-slate-500 text-[10px] uppercase">
                <th class="px-4 py-3 font-semibold">Swimmer</th>
                <th class="px-4 py-3 font-semibold text-center">Sessions</th>
                <th class="px-4 py-3 font-semibold text-center">Distance</th>
                <th class="px-4 py-3 font-semibold text-center">Attendance</th>
                <th class="px-4 py-3 font-semibold">Personal bests</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`}
      </div>
    </div>`;
}

/* ================= TAB: ATTENDANCE (deck-side roll call) ================= */

function cpTodayStr() {
  return new Date().toISOString().split('T')[0];
}

const CP_ATT_STATUSES = [
  { key: 'present', label: 'Present', on: 'bg-emerald-600 text-white', off: 'bg-white text-slate-500 border border-slate-200 hover:border-emerald-300' },
  { key: 'late', label: 'Late', on: 'bg-amber-500 text-white', off: 'bg-white text-slate-500 border border-slate-200 hover:border-amber-300' },
  { key: 'excused', label: 'Excused', on: 'bg-sky-600 text-white', off: 'bg-white text-slate-500 border border-slate-200 hover:border-sky-300' },
  { key: 'absent', label: 'Absent', on: 'bg-rose-600 text-white', off: 'bg-white text-slate-500 border border-slate-200 hover:border-rose-300' },
];

async function cpLoadAttendanceMarks() {
  const ui = CP.ui.attendance;
  if (!ui.squadId || !ui.date) return;
  const data = await cpApi(`/coach/pro/api/attendance?squad_id=${ui.squadId}&date=${ui.date}`);
  ui.marks = {};
  Object.entries(data.marks || {}).forEach(([id, status]) => { ui.marks[Number(id)] = status; });
  ui.dirty = false;
  cpRenderTab();
}

function cpRenderAttendance() {
  const ui = CP.ui.attendance;
  if (!ui.date) ui.date = cpTodayStr();
  if (!ui.squadId && CP.squads.length) ui.squadId = CP.squads[0].id;

  if (CP.squads.length === 0) {
    return `<div class="p-12 text-center text-slate-400 text-xs">No squads yet — create one from Squad Roster first.</div>`;
  }

  const squadSwimmers = CP.swimmers.filter(s => s.userId && s.squadId === ui.squadId && s.status === 'active');
  const markedCount = squadSwimmers.filter(s => ui.marks[s.userId]).length;

  const rows = squadSwimmers.map(s => {
    const current = ui.marks[s.userId];
    const buttons = CP_ATT_STATUSES.map(st => `
      <button data-action="cp-att-mark" data-swimmer-id="${s.userId}" data-status="${st.key}"
        class="px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${current === st.key ? st.on : st.off}">${st.label}</button>`).join('');
    return `
      <div class="flex items-center justify-between gap-3 px-4 py-3 bg-white border border-slate-200 rounded-xl">
        <div class="min-w-0">
          <p class="text-xs font-semibold text-slate-900 truncate">${cpEsc(s.name)}</p>
          <p class="text-[10px] text-slate-400 mt-0.5">${s.attendanceRate != null ? s.attendanceRate + '% attendance (30d)' : 'No attendance history yet'}${s.laneGroup ? ' · ' + cpEsc(s.laneGroup) : ''}</p>
        </div>
        <div class="flex gap-1.5 shrink-0">${buttons}</div>
      </div>`;
  }).join('');

  return `
    <div class="max-w-3xl space-y-5" id="attendance_section">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="check-square" class="w-4 h-4 text-slate-500"></i> Roll call</h3>
          <p class="text-xs text-slate-400 mt-1">Mark who showed up. Attendance rates feed the roster, analytics and the AI assistant.</p>
        </div>
        <div class="flex gap-2.5">
          <select id="cpAttSquadSelect" class="text-xs px-3 py-2 bg-white border border-slate-200 rounded-lg font-medium focus:outline-hidden">
            ${CP.squads.map(sq => `<option value="${sq.id}" ${sq.id === ui.squadId ? 'selected' : ''}>${cpEsc(sq.name)}</option>`).join('')}
          </select>
          <input type="date" id="cpAttDate" value="${ui.date}" class="text-xs px-3 py-2 bg-white border border-slate-200 rounded-lg font-medium focus:outline-hidden">
        </div>
      </div>

      ${squadSwimmers.length === 0 ? `<div class="p-12 text-center text-slate-400 text-xs bg-slate-50 border border-slate-100 rounded-xl">No active swimmers in this squad yet — invites still pending count once they join.</div>` : `
      <div class="flex items-center justify-between">
        <button data-action="cp-att-mark-all" class="text-xs text-brand-600 hover:text-brand-800 font-medium flex items-center gap-1"><i data-lucide="check-check" class="w-3.5 h-3.5"></i> Mark everyone present</button>
        <span class="text-[10px] text-slate-400 font-medium">${markedCount}/${squadSwimmers.length} marked</span>
      </div>
      <div class="space-y-2">${rows}</div>
      <div class="flex items-center justify-end gap-3 pt-2">
        ${ui.dirty ? '<span class="text-[10px] text-amber-600 font-medium">Unsaved changes</span>' : ''}
        <button data-action="cp-att-save" class="px-5 py-2 bg-[#111111] hover:bg-slate-800 text-[#ccccff] rounded-lg text-xs font-semibold transition ${ui.saving ? 'opacity-60 pointer-events-none' : ''}">${ui.saving ? 'Saving…' : 'Save roll call'}</button>
      </div>`}
    </div>`;
}

/* ================= TAB: AI ASSISTANT (squad insights) ================= */

function cpAIFlagStyle(kind) {
  if (kind === 'at_risk') return { chip: 'bg-rose-50 text-rose-700 border-rose-200', label: 'Needs attention', icon: 'alert-triangle' };
  if (kind === 'standout') return { chip: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Standout', icon: 'trending-up' };
  return { chip: 'bg-amber-50 text-amber-700 border-amber-200', label: 'Watch', icon: 'eye' };
}

function cpRenderAI() {
  const ui = CP.ui.ai;
  if (!ui.squadId && CP.squads.length) ui.squadId = CP.squads[0].id;

  if (!CP.aiEnabled) {
    return `<div class="max-w-xl mx-auto mt-10 p-8 text-center bg-slate-50 border border-slate-200 rounded-xl">
      <i data-lucide="sparkles" class="w-6 h-6 text-slate-400 mx-auto mb-3"></i>
      <h3 class="text-sm font-semibold text-slate-800">AI assistant isn't configured</h3>
      <p class="text-xs text-slate-500 mt-2 leading-relaxed">Add an ANTHROPIC_API_KEY to the server's .env file to unlock squad insights, at-risk swimmer flags and training focus suggestions.</p>
    </div>`;
  }
  if (CP.squads.length === 0) {
    return `<div class="p-12 text-center text-slate-400 text-xs">No squads yet — create one from Squad Roster first.</div>`;
  }

  const insights = ui.insights;
  const body = ui.loading ? `
    <div class="p-16 text-center bg-white border border-slate-200 rounded-xl">
      <div class="w-8 h-8 border-2 border-slate-200 border-t-slate-800 rounded-full animate-spin mx-auto mb-4"></div>
      <p class="text-xs text-slate-500">Reading the squad's training data…</p>
    </div>` : ui.error ? `
    <div class="p-8 text-center bg-rose-50 border border-rose-100 rounded-xl">
      <p class="text-xs text-rose-700">${cpEsc(ui.error)}</p>
    </div>` : !insights ? `
    <div class="p-16 text-center bg-slate-50 border border-slate-100 rounded-xl">
      <i data-lucide="sparkles" class="w-6 h-6 text-slate-400 mx-auto mb-3"></i>
      <p class="text-xs text-slate-500 max-w-sm mx-auto leading-relaxed">Pick a squad and hit Analyze. The assistant reads the last 60 days of logged swims, sessions, attendance and injury flags — then tells you who needs attention and what to train next.</p>
    </div>` : `
    <div class="space-y-5">
      <div class="bg-white border border-slate-200 rounded-xl p-5">
        <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2.5 flex items-center gap-1.5"><i data-lucide="sparkles" class="w-4 h-4 text-brand-500"></i> Squad summary</h4>
        <p class="text-xs text-slate-600 leading-relaxed">${cpEsc(insights.summary)}</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div class="bg-white border border-slate-200 rounded-xl p-5">
          <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 flex items-center gap-1.5"><i data-lucide="users" class="w-4 h-4 text-rose-500"></i> Swimmers to act on</h4>
          <div class="space-y-2.5">
            ${(insights.swimmer_flags || []).length === 0 ? '<p class="text-xs text-slate-400 italic">Nobody flagged — squad looks healthy.</p>' :
              (insights.swimmer_flags || []).map(f => {
                const st = cpAIFlagStyle(f.kind);
                return `
                <div class="p-3 border border-slate-100 bg-slate-50 rounded-xl">
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-xs font-bold text-slate-900">${cpEsc(f.name)}</span>
                    <span class="text-[9px] font-bold px-2 py-0.5 rounded-full border flex items-center gap-1 ${st.chip}"><i data-lucide="${st.icon}" class="w-2.5 h-2.5"></i> ${st.label}</span>
                  </div>
                  <p class="text-[11px] text-slate-600 mt-1.5 leading-relaxed">${cpEsc(f.reason)}</p>
                </div>`;
              }).join('')}
          </div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl p-5">
          <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 flex items-center gap-1.5"><i data-lucide="target" class="w-4 h-4 text-emerald-500"></i> Suggested training focus</h4>
          <div class="space-y-2">
            ${(insights.focus_suggestions || []).map((f, i) => `
              <div class="flex gap-2.5 p-3 bg-slate-50 border border-slate-100 rounded-xl">
                <span class="text-xs font-bold text-slate-400 shrink-0">${i + 1}.</span>
                <p class="text-[11px] text-slate-600 leading-relaxed">${cpEsc(f)}</p>
              </div>`).join('')}
          </div>
        </div>
      </div>
    </div>`;

  return `
    <div class="max-w-4xl space-y-5" id="ai_assistant_section">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="sparkles" class="w-4 h-4 text-slate-500"></i> AI assistant</h3>
          <p class="text-xs text-slate-400 mt-1">Squad-level analysis of the last 60 days of training, attendance and availability.</p>
        </div>
        <div class="flex gap-2.5">
          <select id="cpAISquadSelect" class="text-xs px-3 py-2 bg-white border border-slate-200 rounded-lg font-medium focus:outline-hidden">
            ${CP.squads.map(sq => `<option value="${sq.id}" ${sq.id === ui.squadId ? 'selected' : ''}>${cpEsc(sq.name)}</option>`).join('')}
          </select>
          <select id="cpAIToneSelect" title="How blunt the AI's feedback is" class="text-xs px-3 py-2 bg-white border border-slate-200 rounded-lg font-medium focus:outline-hidden">
            <option value="encouraging" ${ui.tone === 'encouraging' ? 'selected' : ''}>Encouraging</option>
            <option value="balanced" ${ui.tone === 'balanced' ? 'selected' : ''}>Balanced</option>
            <option value="direct" ${ui.tone === 'direct' ? 'selected' : ''}>Direct</option>
          </select>
          <button data-action="cp-ai-generate" class="px-4 py-2 bg-[#111111] hover:bg-slate-800 text-[#ccccff] rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${ui.loading ? 'opacity-60 pointer-events-none' : ''}">
            <i data-lucide="sparkles" class="w-3.5 h-3.5"></i> ${insights ? 'Re-analyze squad' : 'Analyze squad'}
          </button>
        </div>
      </div>
      ${body}
    </div>`;
}

/* ================= TAB 2: ROSTER MANAGER (real squads/memberships) ================= */

function cpRenderRoster() {
  const ui = CP.ui.roster;
  const filtered = ui.selectedSquadId === 'all' ? CP.swimmers : CP.swimmers.filter(s => s.squadId === ui.selectedSquadId);

  const addSquadForm = ui.showAddSquad ? `
    <form id="cpCreateSquadForm" class="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3.5 shadow-2xs">
      <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider">Create Squad Group</h4>
      <div>
        <label class="block text-[10px] text-slate-500 font-mono mb-1">Squad Name</label>
        <input type="text" name="name" required placeholder="e.g. Senior Elite" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
      </div>
      <div>
        <label class="block text-[10px] text-slate-500 font-mono mb-1">Theme Visual Indicator</label>
        <div class="flex gap-2.5 mt-1">
          ${['blue', 'emerald', 'indigo', 'violet', 'orange'].map(c => `
            <button type="button" data-action="cp-pick-squad-color" data-color="${c}" class="w-5 h-5 rounded-full flex items-center justify-center border transition ${ui.squadColor === c ? 'ring-2 ring-brand-500 ring-offset-1 border-transparent' : 'border-slate-300'}" style="background-color:${cpColorHex(c)}"></button>
          `).join('')}
        </div>
      </div>
      <div class="flex justify-end gap-2 pt-1">
        <button type="button" data-action="cp-toggle-add-squad" class="px-2.5 py-1 text-[11px] text-slate-600 hover:text-slate-800 font-medium">Cancel</button>
        <button type="submit" class="px-3 py-1 bg-brand-600 text-white font-medium text-[11px] rounded hover:bg-brand-700 transition">Create Squad</button>
      </div>
    </form>` : '';

  const squadButtons = CP.squads.map(squad => {
    const isSelected = ui.selectedSquadId === squad.id;
    return `
      <div class="group rounded-xl border p-4 transition relative flex flex-col justify-between ${isSelected ? 'bg-slate-900 text-white border-transparent' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50/60'}">
        <div class="flex items-start justify-between cursor-pointer" data-action="cp-select-squad" data-squad-id="${squad.id}">
          <div>
            <div class="flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full ${cpBadgeColorClass(squad.color)}"></span>
              <h4 class="font-semibold text-xs leading-none tracking-tight">${cpEsc(squad.name)}</h4>
            </div>
            <p class="text-[10px] mt-1.5 leading-normal ${isSelected ? 'text-slate-300' : 'text-slate-500'}">Invite code: ${cpEsc(squad.inviteCode)}</p>
          </div>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${isSelected ? 'bg-slate-800 text-slate-300' : 'bg-slate-100 text-slate-600'}">${squad.memberCount}</span>
        </div>
        <div class="mt-3.5 pt-2 border-t border-slate-200/25 flex items-center justify-between">
          <div class="flex gap-2.5 text-[9px] font-semibold ${isSelected ? 'text-slate-300' : 'text-slate-400'}">
            <button data-action="cp-set-tab" data-tab="schedule" class="hover:underline ${isSelected ? 'hover:text-white' : 'hover:text-slate-700'}">Schedule</button>
            <button data-action="cp-set-tab" data-tab="announcements" class="hover:underline ${isSelected ? 'hover:text-white' : 'hover:text-slate-700'}">Announcements</button>
            <button data-action="cp-set-tab" data-tab="reports" class="hover:underline ${isSelected ? 'hover:text-white' : 'hover:text-slate-700'}">Report</button>
          </div>
          <button data-action="cp-remove-squad" data-squad-id="${squad.id}" class="text-[9px] text-red-500 hover:text-red-700 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition">Delete</button>
        </div>
      </div>`;
  }).join('');

  const addSwimmerForm = ui.showAddSwimmer ? `
    <form id="cpInviteSwimmerForm" class="bg-slate-50 border border-slate-200 rounded-xl p-5 grid grid-cols-1 md:grid-cols-2 gap-4 shadow-sm">
      <div class="md:col-span-2 flex items-center justify-between border-b border-slate-200 pb-2">
        <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider">Invite a swimmer by email</h4>
        <button type="button" data-action="cp-toggle-add-swimmer" class="text-xs text-slate-500 hover:text-slate-700">Close</button>
      </div>
      <div>
        <label class="block text-[10px] text-slate-500 font-mono mb-1">Email address</label>
        <input type="email" name="email" required placeholder="swimmer@example.com" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
      </div>
      <div>
        <label class="block text-[10px] text-slate-500 font-mono mb-1">Squad</label>
        <select name="squadId" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
          ${CP.squads.map(sq => `<option value="${sq.id}" ${sq.id === ui.inviteSquadId ? 'selected' : ''}>${cpEsc(sq.name)}</option>`).join('')}
        </select>
      </div>
      <div class="md:col-span-2 flex justify-end gap-2 pt-2 border-t border-slate-200">
        <button type="button" data-action="cp-toggle-add-swimmer" class="px-3 py-1 text-xs text-slate-600 hover:text-slate-800 font-medium">Cancel</button>
        <button type="submit" class="px-4 py-1.5 bg-brand-600 text-white font-medium text-xs rounded hover:bg-brand-700 transition">Send invite</button>
      </div>
    </form>` : '';

  const rows = filtered.map(swimmer => {
    const swimmerSquad = CP.squads.find(sq => sq.id === swimmer.squadId);
    return `
      <tr class="hover:bg-slate-50/50 transition">
        <td class="px-4 py-3.5 font-medium text-slate-900">${cpEsc(swimmer.name)}</td>
        <td class="px-4 py-3.5">${cpStatusBadge(swimmer.status)}</td>
        <td class="px-4 py-3.5">${swimmerSquad ? `<span class="px-2 py-0.5 rounded text-[10px] font-medium border ${cpSquadColorClass(swimmerSquad.color)}">${cpEsc(swimmerSquad.name)}</span>` : '<span class="text-slate-400 text-[10px] italic">Unassigned</span>'}</td>
        <td class="px-4 py-3.5 text-center font-mono font-bold text-slate-800">${swimmer.sessionsCount}</td>
        <td class="px-4 py-3.5 text-center font-mono text-slate-600">${(swimmer.totalDistance || 0).toLocaleString()}m</td>
        <td class="px-4 py-3.5 text-center">${swimmer.attendanceRate == null ? '<span class="text-slate-300">—</span>' : `<span class="font-mono font-bold ${swimmer.attendanceRate >= 80 ? 'text-emerald-600' : swimmer.attendanceRate >= 50 ? 'text-amber-600' : 'text-rose-600'}">${swimmer.attendanceRate}%</span>`}</td>
        <td class="px-4 py-3.5 text-slate-500">${swimmer.lastActive || '—'}</td>
        <td class="px-4 py-3.5 text-center">
          <div class="flex items-center justify-center gap-3">
            <select data-action="cp-reassign-squad" data-membership-id="${swimmer.membershipId}" class="text-[10px] bg-slate-100 border-none hover:bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded font-medium focus:outline-hidden">
              ${CP.squads.map(sq => `<option value="${sq.id}" ${sq.id === swimmer.squadId ? 'selected' : ''}>Move to ${cpEsc(sq.name.split(' ')[0])}</option>`).join('')}
            </select>
            <button data-action="cp-remove-swimmer" data-membership-id="${swimmer.membershipId}" class="text-slate-400 hover:text-red-600 transition" title="Remove from roster">
              <i data-lucide="user-minus" class="w-3.5 h-3.5"></i>
            </button>
          </div>
        </td>
      </tr>`;
  }).join('');

  return `
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6" id="roster_manager_section">
      <div class="lg:col-span-4 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="users" class="w-4 h-4 text-slate-500"></i> Squad Structures</h3>
          <button data-action="cp-toggle-add-squad" class="text-xs text-brand-600 hover:text-brand-800 font-medium flex items-center gap-1 transition"><i data-lucide="folder-plus" class="w-3.5 h-3.5"></i> New Squad</button>
        </div>
        ${addSquadForm}
        <div class="space-y-2">
          <button data-action="cp-select-squad" data-squad-id="all" class="w-full text-left px-4 py-3 rounded-xl border flex items-center justify-between transition ${ui.selectedSquadId === 'all' ? 'bg-slate-900 text-white border-transparent' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'}">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full ${ui.selectedSquadId === 'all' ? 'bg-brand-400' : 'bg-slate-400'}"></span>
              <div class="font-medium text-xs">All Squads combined</div>
            </div>
            <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-semibold">${CP.swimmers.length} athletes</span>
          </button>
          ${squadButtons}
          ${CP.squads.length === 0 ? '<p class="text-xs text-slate-400 italic px-2">No squads yet — create one above.</p>' : ''}
        </div>
      </div>

      <div class="lg:col-span-8 space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-semibold text-slate-800 tracking-tight">${ui.selectedSquadId === 'all' ? 'Active Team Roster' : cpEsc((CP.squads.find(s => s.id === ui.selectedSquadId) || {}).name || '')}</h3>
            <p class="text-xs text-slate-400">Coaching ${filtered.length} athletes. Reassign, remove, or drill into performance from the Athlete Hub.</p>
          </div>
          <button data-action="cp-open-add-swimmer" class="px-3 py-1.5 bg-brand-600 text-white rounded-lg text-xs font-medium flex items-center gap-1.5 hover:bg-brand-700 transition"><i data-lucide="user-plus" class="w-3.5 h-3.5"></i> Invite Swimmer</button>
        </div>
        ${addSwimmerForm}
        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
          ${filtered.length === 0 ? `<div class="p-12 text-center text-slate-400 text-xs">No swimmers in this cohort yet — invite one above.</div>` : `
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs text-slate-600 border-collapse">
              <thead>
                <tr class="bg-slate-50 border-b border-slate-200 text-slate-500 font-mono text-[10px] uppercase">
                  <th class="px-4 py-3 font-semibold">Athlete Name</th>
                  <th class="px-4 py-3 font-semibold">Status</th>
                  <th class="px-4 py-3 font-semibold">Squad Mapping</th>
                  <th class="px-4 py-3 font-semibold text-center">Sessions</th>
                  <th class="px-4 py-3 font-semibold text-center">Distance</th>
                  <th class="px-4 py-3 font-semibold text-center">Attendance</th>
                  <th class="px-4 py-3 font-semibold">Last Active</th>
                  <th class="px-4 py-3 font-semibold text-center">Reassign / Remove</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">${rows}</tbody>
            </table>
          </div>`}
        </div>
      </div>
    </div>`;
}

/* ================= TAB 3: SESSION BUILDER (real SavedSet + CoachAssignment) ================= */

function cpBlockSummary(b) {
  const restBit = b.rest ? (b.rest_type === 'rest' ? ' · rest ' + b.rest : ' on ' + b.rest) : '';
  return `${b.reps}×${b.dist}m ${STROKE_LABELS[b.stroke] || b.stroke}${restBit}`;
}

function cpRenderBuilder() {
  const ui = CP.ui.builder;

  const blocksList = ui.blocks.map((b, i) => `
    <div class="flex items-center justify-between bg-white border border-slate-200 rounded-lg px-3 py-2 text-[11px]">
      <span class="font-medium text-slate-700">${cpEsc(b.section)}: ${cpEsc(cpBlockSummary(b))}</span>
      <button type="button" data-action="cp-remove-block" data-index="${i}" class="text-slate-400 hover:text-red-600">✕</button>
    </div>`).join('');

  const editing = ui.editingSetId ? CP.savedSets.find(s => s.id === ui.editingSetId) : null;
  const catValue = editing ? editing.category : '';
  const poolValue = editing ? editing.pool : '25m';
  const createSetForm = (ui.showCreateSet || editing) ? `
    <form id="cpCreateSetForm" class="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
      <div class="flex items-center justify-between border-b border-slate-200 pb-2">
        <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider">${editing ? 'Edit set' : 'Draft New Swim Set'}</h4>
        <button type="button" data-action="cp-toggle-create-set" class="text-xs text-slate-500 hover:text-slate-700">Cancel</button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-[10px] text-slate-500 font-mono mb-1">Set Title</label>
          <input type="text" name="name" required placeholder="e.g. Speed Endurance Laps" value="${editing ? cpEsc(editing.title) : ''}" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="block text-[10px] text-slate-500 font-mono mb-1">Category</label>
            <select name="category" class="w-full text-xs px-2 py-1.5 bg-white border border-slate-200 rounded focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
              ${SET_CATEGORIES.map(c => `<option ${c === catValue ? 'selected' : ''}>${c}</option>`).join('')}
            </select>
          </div>
          <div>
            <label class="block text-[10px] text-slate-500 font-mono mb-1">Pool</label>
            <select name="pool" class="w-full text-xs px-2 py-1.5 bg-white border border-slate-200 rounded focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
              <option value="25m" ${poolValue === '25m' ? 'selected' : ''}>25m</option><option value="50m" ${poolValue === '50m' ? 'selected' : ''}>50m</option>
            </select>
          </div>
        </div>
      </div>
      <div>
        <label class="block text-[10px] text-slate-500 font-mono mb-1">Brief Description</label>
        <input type="text" name="description" placeholder="Fosters pacing structure and high aerobic threshold." value="${editing ? cpEsc(editing.description || '') : ''}" class="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded focus:ring-1 focus:ring-brand-500 focus:outline-hidden">
      </div>

      <div class="border-t border-slate-200 pt-3">
        <label class="block text-[10px] text-slate-500 font-mono mb-2">Add a block (reps × distance × stroke)</label>
        <div class="grid grid-cols-6 gap-2">
          <select id="cpBlockSection" class="text-xs px-2 py-1.5 bg-white border border-slate-200 rounded col-span-1">
            <option>Warm up</option><option>Pre set</option><option selected>Main set</option><option>Sub set</option><option>Cool down</option>
          </select>
          <input id="cpBlockReps" type="number" min="1" value="4" placeholder="Reps" class="text-xs px-2 py-1.5 bg-white border border-slate-200 rounded">
          <input id="cpBlockDist" type="number" min="25" step="25" value="100" placeholder="Dist (m)" class="text-xs px-2 py-1.5 bg-white border border-slate-200 rounded">
          <select id="cpBlockStroke" class="text-xs px-2 py-1.5 bg-white border border-slate-200 rounded">
            ${Object.entries(STROKE_LABELS).map(([code, label]) => `<option value="${code}">${label}</option>`).join('')}
          </select>
          <input id="cpBlockRest" type="text" placeholder="Rest/interval e.g. 1:30" class="text-xs px-2 py-1.5 bg-white border border-slate-200 rounded">
          <select id="cpBlockRestType" class="text-xs px-2 py-1.5 bg-white border border-slate-200 rounded">
            <option value="interval" selected>On (interval)</option>
            <option value="rest">Rest</option>
          </select>
        </div>
        <button type="button" data-action="cp-add-block" class="mt-2 text-xs text-brand-600 hover:text-brand-800 font-medium flex items-center gap-1"><i data-lucide="plus" class="w-3.5 h-3.5"></i> Add block</button>
        <div class="mt-2 space-y-1.5">${blocksList || '<p class="text-[11px] text-slate-400 italic">No blocks added yet.</p>'}</div>
      </div>

      <div class="flex justify-end gap-2 pt-2 border-t border-slate-200">
        <button type="button" data-action="cp-toggle-create-set" class="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 font-medium">Cancel</button>
        <button type="submit" class="px-4 py-1.5 bg-brand-600 text-white font-medium text-xs rounded hover:bg-brand-700 transition">${editing ? 'Save changes' : 'Save Blueprint'}</button>
      </div>
    </form>` : '';

  const setCards = CP.savedSets.map(set => `
    <div class="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between hover:shadow-xs transition">
      <div>
        <div class="flex items-center justify-between mb-2">
          <span class="text-[9px] px-2 py-0.5 rounded-full font-bold font-mono bg-brand-50 text-brand-700">${cpEsc(set.category)}</span>
          <span class="text-[10px] font-mono font-bold text-slate-500">${set.totalDistance}m total</span>
        </div>
        <h4 class="text-xs font-bold text-slate-900 leading-tight">${cpEsc(set.title)}</h4>
        <p class="text-[10px] text-slate-500 mt-1 leading-normal mb-3">${cpEsc(set.description || 'No description.')}</p>
        <div class="text-[10.5px] border-t border-slate-100 pt-2.5 mb-4">
          <span class="text-[9px] font-mono text-slate-400 block font-semibold uppercase mb-1">Blocks (${set.blocks.length})</span>
          ${set.blocks.length ? set.blocks.slice(0, 4).map(b => `<p class="text-slate-600 font-medium">${cpEsc(cpBlockSummary(b))}</p>`).join('') : '<p class="text-slate-400 italic">No blocks recorded.</p>'}
        </div>
      </div>
      <div class="flex gap-2">
        <button data-action="cp-select-set-for-assign" data-set-id="${set.id}" class="flex-1 py-1.5 border border-slate-200 text-slate-700 hover:border-brand-600 hover:bg-brand-50 hover:text-brand-800 text-xs font-semibold rounded-lg flex items-center justify-center gap-1.5 transition">
          <i data-lucide="send" class="w-3.5 h-3.5"></i> Assign
        </button>
        <button data-action="cp-edit-set" data-set-id="${set.id}" class="px-3 py-1.5 border border-slate-200 text-slate-500 hover:text-brand-700 hover:border-brand-300 text-xs rounded-lg transition" title="Edit set"><i data-lucide="pencil" class="w-3.5 h-3.5"></i></button>
        <button data-action="cp-delete-set" data-set-id="${set.id}" class="px-3 py-1.5 border border-slate-200 text-slate-400 hover:text-red-600 hover:border-red-200 text-xs rounded-lg transition"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>
      </div>
    </div>`).join('');

  const assignableSwimmers = CP.swimmers.filter(s => s.userId);
  const selectedSet = ui.selectedSetForAssign ? CP.savedSets.find(s => s.id === ui.selectedSetForAssign) : null;

  const dispatchPanel = selectedSet ? `
    <div class="bg-slate-900 text-slate-200 rounded-xl p-5 border border-slate-800 shadow-md space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-2">
        <div>
          <span class="text-[9px] text-brand-400 font-mono uppercase font-semibold">Dispatching Set</span>
          <h4 class="text-xs font-bold text-white tracking-tight mt-0.5 truncate max-w-[200px]">${cpEsc(selectedSet.title)}</h4>
        </div>
        <button type="button" data-action="cp-cancel-assign" class="text-[10px] text-slate-400 hover:text-white">Cancel</button>
      </div>
      <form id="cpCreateAssignmentForm" class="space-y-3.5">
        <div>
          <label class="block text-[10px] text-slate-400 font-mono mb-1">Target Type</label>
          <div class="grid grid-cols-2 gap-2">
            <button type="button" data-action="cp-assign-target-type" data-type="squad" class="py-1 rounded text-xs font-medium flex items-center justify-center gap-1 ${ui.assignTargetType === 'squad' ? 'bg-brand-600 text-white' : 'bg-slate-800 text-slate-300'}"><i data-lucide="users" class="w-3 h-3"></i> Squad</button>
            <button type="button" data-action="cp-assign-target-type" data-type="swimmer" class="py-1 rounded text-xs font-medium flex items-center justify-center gap-1 ${ui.assignTargetType === 'swimmer' ? 'bg-brand-600 text-white' : 'bg-slate-800 text-slate-300'}"><i data-lucide="user" class="w-3 h-3"></i> Swimmer</button>
          </div>
        </div>
        <div>
          <label class="block text-[10px] text-slate-400 font-mono mb-1">Recipient Destination</label>
          <select name="target_id" class="w-full text-xs px-2.5 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden">
            ${ui.assignTargetType === 'squad'
              ? CP.squads.map(sq => `<option value="${sq.id}" ${sq.id === ui.assignTargetId ? 'selected' : ''}>${cpEsc(sq.name)}</option>`).join('')
              : (assignableSwimmers.length ? assignableSwimmers.map(sw => `<option value="${sw.userId}" ${sw.userId === ui.assignTargetId ? 'selected' : ''}>${cpEsc(sw.name)}</option>`).join('') : '<option value="">No signed-up swimmers yet</option>')}
          </select>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[10px] text-slate-400 font-mono mb-1">Due Date</label>
            <input type="date" name="due_date" required value="${cpTomorrow()}" class="w-full text-xs px-2.5 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden">
          </div>
        </div>
        <div>
          <label class="block text-[10px] text-slate-400 font-mono mb-1">Custom instructions / Notes</label>
          <textarea name="notes" placeholder="e.g. Focus on descending stroke counts and holding breath under flags..." rows="2" class="w-full text-xs px-2.5 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden resize-none"></textarea>
        </div>
        <button type="submit" class="w-full py-2 bg-brand-600 hover:bg-brand-700 text-white font-semibold text-xs rounded-lg flex items-center justify-center gap-1.5 transition">
          <i data-lucide="clipboard-list" class="w-3.5 h-3.5"></i> Dispatch to Active Training Queue
        </button>
      </form>
    </div>` : '';

  const queueItems = CP.assignments.length === 0 ? `<div class="p-12 text-center text-slate-400 text-xs bg-slate-50 border border-slate-100 rounded-xl">No active assignments in current training loop.</div>` :
    CP.assignments.map(assignment => {
      const isSquad = assignment.targetType === 'squad';
      const recipientName = isSquad ? ((CP.squads.find(sq => sq.id === assignment.targetId) || {}).name || 'Deleted Squad') : ((CP.swimmers.find(sw => sw.userId === assignment.targetId) || {}).name || 'Deleted Swimmer');
      return `
      <div class="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between hover:border-slate-300 transition shadow-2xs">
        <div class="flex items-start justify-between">
          <div class="max-w-[70%]">
            <span class="text-[8.5px] px-1.5 py-0.2 rounded font-mono font-bold inline-flex items-center gap-1 border uppercase ${isSquad ? 'bg-emerald-50 text-emerald-800 border-emerald-100' : 'bg-sky-50 text-sky-800 border-sky-100'}">
              <i data-lucide="${isSquad ? 'users' : 'user'}" class="w-2.5 h-2.5"></i> ${cpEsc(recipientName)}
            </span>
            <h4 class="text-xs font-bold text-slate-900 mt-2 truncate">${cpEsc(assignment.setTitle)}</h4>
          </div>
          <button data-action="cp-toggle-assignment-status" data-id="${assignment.id}" class="text-[10px] font-mono px-2 py-0.5 rounded-full font-bold flex items-center gap-1 transition ${assignment.status === 'Completed' ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100' : 'bg-amber-50 text-amber-700 hover:bg-amber-100'}" title="Click to toggle completion status">
            ${assignment.status === 'Completed' ? '<i data-lucide="check-circle" class="w-2.5 h-2.5"></i> Logged' : '<i data-lucide="clock" class="w-2.5 h-2.5"></i> Pending'}
          </button>
        </div>
        ${assignment.notes ? `<p class="text-[10px] text-slate-500 bg-slate-50 p-2 border border-slate-100 rounded-lg mt-2.5 leading-normal italic">"${cpEsc(assignment.notes)}"</p>` : ''}
        <div class="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400">
          <span class="flex items-center gap-1 font-mono"><i data-lucide="calendar" class="w-3 h-3 text-slate-400"></i> Due: ${assignment.dueDate || '—'}</span>
          <button data-action="cp-remove-assignment" data-id="${assignment.id}" class="text-slate-400 hover:text-rose-600 font-medium transition">Recall Assignment</button>
        </div>
      </div>`;
    }).join('');

  return `
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6" id="workout_builder_section">
      <div class="lg:col-span-7 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="folder-heart" class="w-4 h-4 text-slate-500"></i> Set Blueprint Library</h3>
          <div class="flex items-center gap-4">
            ${CP.aiEnabled ? '<button data-action="cp-aigen-toggle" class="text-xs text-brand-600 hover:text-brand-800 font-medium flex items-center gap-1 transition"><i data-lucide="sparkles" class="w-3.5 h-3.5"></i> Generate with AI</button>' : ''}
            <button data-action="cp-toggle-create-set" class="text-xs text-brand-600 hover:text-brand-800 font-medium flex items-center gap-1 transition"><i data-lucide="plus" class="w-4 h-4"></i> Create Set Template</button>
          </div>
        </div>
        ${cpRenderAIGenPanel()}
        ${createSetForm}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">${setCards || '<p class="text-xs text-slate-400 italic">No sets yet — create your first blueprint above.</p>'}</div>
      </div>
      <div class="lg:col-span-5 space-y-5">
        ${dispatchPanel}
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="clipboard-list" class="w-4 h-4 text-slate-500"></i> Active Assignment Queue</h3>
            <span class="text-[10px] bg-slate-100 text-slate-600 font-mono px-2 py-0.5 rounded font-semibold">${CP.assignments.length} assigned</span>
          </div>
          <div class="space-y-2.5 max-h-[460px] overflow-y-auto pr-1.5">${queueItems}</div>
        </div>
      </div>
    </div>`;
}

function cpTomorrow() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().split('T')[0];
}

/* The AI set generator: parameters in, a saved blueprint out. The backend
   prompt is grounded in elite methodology (Bowman aerobic engine, USRPT
   race-pace, sprint/power, CSS threshold) and season phasing. */

const CP_AIGEN_STYLES = [
  'Best fit for the focus',
  'Bowman-style aerobic engine (Phelps/NBAC)',
  'USRPT race-pace (Rushall)',
  'Sprint & power — max velocity, full recovery',
  'Threshold / CSS (British Swimming style)',
  'Technique & drill emphasis',
];
const CP_AIGEN_PHASES = ['Early season — base building', 'Mid season — quality', 'Taper — sharpen for racing', 'Post long-course transition'];
const CP_AIGEN_LEVELS = ['Age group (12 & under)', 'Junior (13-16)', 'Senior club', 'National / elite'];

function cpRenderAIGenPanel() {
  const ui = CP.ui.aiGen;
  if (!ui.show) return '';
  return `
    <form id="cpAIGenForm" class="bg-slate-900 text-slate-200 rounded-xl p-5 border border-slate-800 shadow-md space-y-3.5">
      <div class="flex items-center justify-between border-b border-slate-800 pb-2">
        <h4 class="text-xs font-bold text-white flex items-center gap-1.5"><i data-lucide="sparkles" class="w-3.5 h-3.5 text-[#ccccff]"></i> AI set generator</h4>
        <button type="button" data-action="cp-aigen-toggle" class="text-[10px] text-slate-400 hover:text-white">Close</button>
      </div>
      <p class="text-[11px] text-slate-400 leading-relaxed">Writes a full session — warm up to cool down — using real elite methodology: Bowman's aerobic IM engine, USRPT race-pace, sprint programs, CSS threshold work, phased for your point in the season.</p>
      <div>
        <label class="block text-[10px] text-slate-400 font-medium mb-1">Training focus</label>
        <input type="text" name="focus" placeholder="e.g. 200 free back-half endurance, fly technique under fatigue" class="w-full text-xs px-2.5 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden">
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-[10px] text-slate-400 font-medium mb-1">Methodology</label>
          <select name="style" class="w-full text-xs px-2 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden">
            ${CP_AIGEN_STYLES.map(s => `<option>${s}</option>`).join('')}
          </select>
        </div>
        <div>
          <label class="block text-[10px] text-slate-400 font-medium mb-1">Season phase</label>
          <select name="season_phase" class="w-full text-xs px-2 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden">
            ${CP_AIGEN_PHASES.map(s => `<option>${s}</option>`).join('')}
          </select>
        </div>
        <div>
          <label class="block text-[10px] text-slate-400 font-medium mb-1">Level</label>
          <select name="level" class="w-full text-xs px-2 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden">
            ${CP_AIGEN_LEVELS.map((s, i) => `<option ${i === 2 ? 'selected' : ''}>${s}</option>`).join('')}
          </select>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="block text-[10px] text-slate-400 font-medium mb-1">Pool</label>
            <select name="pool" class="w-full text-xs px-2 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden"><option>25m</option><option>50m</option></select>
          </div>
          <div>
            <label class="block text-[10px] text-slate-400 font-medium mb-1">Minutes</label>
            <input type="number" name="duration_minutes" value="60" min="20" max="180" step="5" class="w-full text-xs px-2 py-1.5 bg-slate-800 border border-slate-800 text-slate-200 rounded focus:outline-hidden">
          </div>
        </div>
      </div>
      <button type="submit" class="w-full py-2 bg-[#ccccff] hover:bg-white text-[#111111] font-semibold text-xs rounded-lg flex items-center justify-center gap-1.5 transition ${ui.loading ? 'opacity-60 pointer-events-none' : ''}">
        ${ui.loading ? '<span class="w-3.5 h-3.5 border-2 border-slate-400 border-t-slate-900 rounded-full animate-spin"></span> Writing the set…' : '<i data-lucide="sparkles" class="w-3.5 h-3.5"></i> Generate & save to library'}
      </button>
    </form>`;
}

/* ================= TAB 4: ATHLETE HUB (real personal bests + activity) ================= */

function cpRenderSwimmer() {
  const ui = CP.ui.swimmer;
  const realSwimmers = CP.swimmers.filter(s => s.userId);
  if (realSwimmers.length === 0) {
    return `<div class="p-12 text-center text-slate-400 text-xs">No signed-up swimmers yet — invite one from Squad Roster, they'll show up here once they join.</div>`;
  }
  const selected = realSwimmers.find(s => s.userId === ui.selectedSwimmerId) || realSwimmers[0];
  const swimmerSquad = CP.squads.find(sq => sq.id === selected.squadId);

  const pbList = (selected.personalBests || []).length === 0 ? `<div class="py-8 text-center text-xs text-slate-400 italic">No personal bests logged yet.</div>` :
    selected.personalBests.map(pb => `
      <div class="py-2.5 flex items-center justify-between">
        <div><span class="text-xs font-semibold text-slate-800 block">${cpEsc(pb.event)}</span><span class="text-[10px] text-slate-400 font-mono">${pb.date} · ${cpEsc(pb.pool || '25m')}</span></div>
        <span class="font-mono font-bold text-slate-900 bg-slate-50 px-2 py-1 rounded text-xs border border-slate-100 shadow-2xs">${cpEsc(pb.time)}</span>
      </div>`).join('');

  const activityList = (selected.recentActivity || []).length === 0 ? `<div class="py-12 text-center text-xs text-slate-400 italic">No swims or sessions logged yet.</div>` :
    selected.recentActivity.map(a => `
      <div class="p-3 bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-between gap-2">
        <div>
          <h5 class="text-xs font-bold text-slate-800 line-clamp-1">${cpEsc(a.label)}</h5>
          <span class="text-[9.5px] text-slate-400 font-mono block mt-0.5">${cpEsc(a.kind)} · ${a.pool} pool</span>
        </div>
        <span class="text-[10px] bg-slate-200 text-slate-700 px-2 py-0.5 rounded font-mono font-bold shrink-0">${a.loggedAt}</span>
      </div>`).join('');

  return `
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6" id="swimmer_dashboard_portal">
      <div class="lg:col-span-4 space-y-4">
        <div>
          <label class="block text-[10px] text-slate-500 font-mono mb-1.5 uppercase font-semibold">Select Athlete Profile</label>
          <select id="cpSwimmerSelect" class="w-full text-xs px-3 py-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-brand-500 focus:outline-hidden font-medium">
            ${realSwimmers.map(s => {
              const sq = CP.squads.find(x => x.id === s.squadId);
              return `<option value="${s.userId}" ${s.userId === selected.userId ? 'selected' : ''}>${cpEsc(s.name)} (${cpEsc(sq ? sq.name.split(' ')[0] : 'Unassigned')})</option>`;
            }).join('')}
          </select>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs space-y-4">
          <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <span class="text-[9px] font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-bold uppercase">${cpEsc(swimmerSquad ? swimmerSquad.name : 'Unassigned')}</span>
              <h3 class="text-base font-bold text-slate-900 mt-1.5">${cpEsc(selected.name)}</h3>
            </div>
            <div class="text-right">
              <span class="text-2xl font-black text-brand-600 tracking-tight block">${selected.sessionsCount}</span>
              <span class="text-[9px] text-slate-400 font-mono font-semibold uppercase">Sessions</span>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3.5 text-xs text-slate-600">
            <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-100"><span class="text-[9.5px] text-slate-400 block font-semibold">Total Distance</span><span class="font-semibold text-slate-800">${(selected.totalDistance || 0).toLocaleString()}m</span></div>
            <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-100"><span class="text-[9.5px] text-slate-400 block font-semibold">Personal Bests</span><span class="font-semibold text-slate-800">${(selected.personalBests || []).length}</span></div>
            <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-100"><span class="text-[9.5px] text-slate-400 block font-semibold">Last Active</span><span class="font-semibold text-slate-800">${selected.lastActive || 'Never'}</span></div>
            <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-100"><span class="text-[9.5px] text-slate-400 block font-semibold">Email</span><span class="font-semibold text-slate-800 truncate block">${cpEsc(selected.email || '—')}</span></div>
          </div>
        </div>
      </div>

      <div class="lg:col-span-8 space-y-6">
        ${cpVolumeChart(selected)}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs flex flex-col justify-between">
            <div>
              <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3.5 flex items-center gap-1.5"><i data-lucide="award" class="w-4 h-4 text-brand-500"></i> Personal Bests (PBs)</h4>
              <div class="divide-y divide-slate-100 max-h-[360px] overflow-y-auto">${pbList}</div>
            </div>
          </div>
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs">
            <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3.5 flex items-center gap-1.5"><i data-lucide="activity" class="w-4 h-4 text-emerald-500"></i> Recent Activity</h4>
            <div class="space-y-3 max-h-[360px] overflow-y-auto pr-1">${activityList}</div>
          </div>
        </div>
      </div>
    </div>`;
}

function cpVolumeChart(swimmer) {
  const vols = swimmer.weeklyVolume || [];
  const maxVol = Math.max(...vols, 1);
  const recent = vols.slice(4).reduce((a, b) => a + b, 0);
  const earlier = vols.slice(0, 4).reduce((a, b) => a + b, 0);
  const trend = earlier > 0 ? Math.round((recent - earlier) / earlier * 100) : null;
  const trendBadge = trend == null || (recent === 0 && earlier === 0) ? '' :
    trend >= 5 ? `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100">▲ ${trend}% vs previous 4 weeks</span>` :
    trend <= -5 ? `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-100">▼ ${Math.abs(trend)}% vs previous 4 weeks</span>` :
    '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">steady</span>';

  return `
    <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs">
      <div class="flex items-center justify-between mb-3.5">
        <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5"><i data-lucide="bar-chart-3" class="w-4 h-4 text-brand-500"></i> Training volume — last 8 weeks</h4>
        ${trendBadge}
      </div>
      <div class="flex items-end gap-2 h-28">
        ${vols.map((v, i) => `
          <div class="flex-1 flex flex-col items-center gap-1">
            <span class="text-[9px] text-slate-400 font-mono">${v > 0 ? (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v) : ''}</span>
            <div class="w-full rounded-t ${i === vols.length - 1 ? 'bg-brand-500' : 'bg-slate-200'}" style="height:${Math.max(Math.round(v / maxVol * 88), v > 0 ? 4 : 2)}px"></div>
            <span class="text-[8px] text-slate-400">${i === vols.length - 1 ? 'now' : (vols.length - 1 - i) + 'w'}</span>
          </div>`).join('')}
      </div>
    </div>`;
}

/* ================= TAB 5: TEAM ANALYTICS (real cohort stats) ================= */

function cpRenderAnalytics() {
  const realSwimmers = CP.swimmers.filter(s => s.userId);

  const squadMetrics = CP.squads.map(sq => {
    const squadSwimmers = realSwimmers.filter(s => s.squadId === sq.id);
    const count = squadSwimmers.length;
    const totalSessions = squadSwimmers.reduce((a, s) => a + s.sessionsCount, 0);
    const avgDistance = count > 0 ? Math.round(squadSwimmers.reduce((a, s) => a + (s.totalDistance || 0), 0) / count) : 0;
    return { squad: sq, count, totalSessions, avgDistance };
  });

  const today = new Date();
  const inactiveAlerts = realSwimmers.map(s => {
    if (!s.lastActive) return { swimmer: s, diffDays: Infinity };
    const diffDays = Math.ceil(Math.abs(today.getTime() - new Date(s.lastActive).getTime()) / 86400000);
    return { swimmer: s, diffDays };
  }).filter(item => item.diffDays >= 5).sort((a, b) => b.diffDays - a.diffDays);

  const mostActive = [...realSwimmers].sort((a, b) => (b.totalDistance || 0) - (a.totalDistance || 0)).slice(0, 3);

  const squadCards = squadMetrics.map(({ squad, count, totalSessions, avgDistance }) => `
    <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-2xs relative overflow-hidden flex flex-col justify-between min-h-[160px]">
      <div class="absolute top-0 left-0 w-full h-1" style="background-color:${cpColorHex(squad.color)}"></div>
      <div>
        <div class="flex items-center gap-1.5 mb-1">
          <span class="w-2 h-2 rounded-full ${cpBadgeColorClass(squad.color)}"></span>
          <h4 class="font-bold text-xs text-slate-800 leading-tight">${cpEsc(squad.name)}</h4>
        </div>
        <span class="text-[10px] text-slate-400 font-mono font-semibold">${count} active swimmers</span>
      </div>
      <div class="grid grid-cols-2 gap-3 mt-4 border-t border-slate-50 pt-3">
        <div><span class="text-[9px] text-slate-400 font-mono block uppercase">Total Sessions</span><span class="text-base font-black text-slate-800 font-mono">${totalSessions}</span></div>
        <div><span class="text-[9px] text-slate-400 font-mono block uppercase">Avg Distance</span><span class="text-base font-black font-mono text-slate-800">${avgDistance.toLocaleString()}m</span></div>
      </div>
    </div>`).join('');

  const alertsList = inactiveAlerts.length === 0 ? `<div class="p-8 text-center text-xs text-slate-400 italic">All swimmers active within 5 days.</div>` :
    inactiveAlerts.map(({ swimmer, diffDays }) => `
      <div class="p-3 bg-rose-50 border border-rose-100 rounded-xl flex items-start gap-2.5">
        <div class="w-2 h-2 rounded-full bg-rose-500 mt-1.5 shrink-0"></div>
        <div>
          <h5 class="text-xs font-bold text-slate-900 leading-none">${cpEsc(swimmer.name)}</h5>
          <span class="text-[10px] font-mono text-slate-400 block mt-1">${swimmer.lastActive ? `Inactive: ${diffDays} days` : 'Never logged a swim'}</span>
        </div>
      </div>`).join('');

  const climbersList = mostActive.length === 0 ? `<div class="py-6 text-center text-xs text-slate-400 italic">No swimmer activity logged yet.</div>` :
    mostActive.map((swimmer, idx) => `
      <div class="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-100 rounded-lg">
        <div class="flex items-center gap-2.5">
          <span class="text-xs font-mono font-bold text-slate-400">#${idx + 1}</span>
          <div><span class="text-xs font-bold text-slate-800 block leading-tight">${cpEsc(swimmer.name)}</span><span class="text-[9.5px] text-slate-400 font-mono">${swimmer.sessionsCount} sessions</span></div>
        </div>
        <div class="flex items-center gap-1 text-emerald-600 font-mono text-xs font-bold bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded"><i data-lucide="trending-up" class="w-3.5 h-3.5"></i> ${(swimmer.totalDistance || 0).toLocaleString()}m</div>
      </div>`).join('');

  return `
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6" id="squad_analytics_section">
      <div class="lg:col-span-8 space-y-6">
        <h3 class="text-sm font-semibold text-slate-800 flex items-center gap-2"><i data-lucide="users" class="w-4 h-4 text-slate-500"></i> Squad Aggregated Cohorts</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">${squadCards || '<p class="text-xs text-slate-400 italic">No squads yet.</p>'}</div>
      </div>
      <div class="lg:col-span-4 space-y-6">
        <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs">
          <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 flex items-center gap-1.5"><i data-lucide="shield-alert" class="w-4 h-4 text-rose-500"></i> Inactivity Alerts</h4>
          <div class="space-y-2 max-h-[190px] overflow-y-auto pr-1">${alertsList}</div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs">
          <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3.5 flex items-center gap-1.5"><i data-lucide="trending-up" class="w-4 h-4 text-emerald-500"></i> Most Active Swimmers</h4>
          <div class="space-y-3">${climbersList}</div>
        </div>
      </div>
    </div>`;
}

/* ================= EVENT WIRING ================= */

document.addEventListener('DOMContentLoaded', () => {
  cpInit();

  document.body.addEventListener('click', async (e) => {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const action = el.dataset.action;

    if (action === 'cp-set-tab') {
      CP.activeTab = el.dataset.tab;
      cpRenderAll();
      if (CP.activeTab === 'attendance') cpLoadAttendanceMarks();
    }

    // Schedule
    else if (action === 'cp-toggle-create-event') {
      CP.ui.schedule.showCreate = !CP.ui.schedule.showCreate;
      cpRenderTab();
    } else if (action === 'cp-pick-slot') {
      CP.ui.schedule.slot = el.dataset.slot;
      // Repaint just the slot buttons so typed form values survive.
      document.querySelectorAll('[data-action="cp-pick-slot"]').forEach(b => {
        b.className = `flex-1 py-1.5 rounded text-xs font-semibold ${b.dataset.slot === CP.ui.schedule.slot ? 'bg-[#111111] text-[#ccccff]' : 'bg-white border border-slate-200 text-slate-500'}`;
      });
    } else if (action === 'cp-remove-event') {
      await cpApi(`/coach/pro/api/schedule/${el.dataset.id}/delete`, { method: 'POST' });
      await cpRefresh();
    }

    // AI set generator
    else if (action === 'cp-aigen-toggle') {
      CP.ui.aiGen.show = !CP.ui.aiGen.show;
      cpRenderTab();
    }

    // Test sets
    else if (action === 'cp-ts-pick-photo') {
      document.getElementById('cpTsPhoto').click();
    } else if (action === 'cp-ts-discard') {
      CP.ui.testsets.result = null;
      CP.ui.testsets.error = null;
      cpRenderTab();
    } else if (action === 'cp-ts-save') {
      const ui = CP.ui.testsets;
      const entries = [];
      document.querySelectorAll('[data-ts-row]').forEach(rowEl => {
        const userId = rowEl.querySelector('.ts-swimmer').value;
        const times = rowEl.querySelector('.ts-times').value.split(',').map(t => t.trim()).filter(Boolean);
        if (userId && times.length) entries.push({ userId: Number(userId), times });
      });
      if (!entries.length) { alert('Assign at least one swimmer to log.'); return; }
      const event = document.getElementById('cpTsEvent').value.trim();
      if (!event) { alert('Set which event these times log as, e.g. 100m Freestyle.'); return; }
      ui.saving = true;
      cpRenderTab();
      try {
        const data = await cpApi('/coach/pro/api/test-sets/log', { method: 'POST', body: cpForm({
          squad_id: ui.squadId,
          event,
          test_label: document.getElementById('cpTsLabel').value.trim(),
          pool: document.getElementById('cpTsPool').value,
          entries: JSON.stringify(entries),
        }) });
        ui.result = null;
        await cpLoadState();
        alert(`Logged results for ${data.logged} swimmer(s).`);
      } finally {
        ui.saving = false;
        cpRenderAll();
      }
    }

    // Announcements
    else if (action === 'cp-ann-delete') {
      if (!confirm('Delete this announcement?')) return;
      await cpApi(`/coach/pro/api/announcements/${el.dataset.id}/delete`, { method: 'POST' });
      await cpRefresh();
    }

    // Reports
    else if (action === 'cp-rep-print') {
      window.print();
    }

    // Attendance
    else if (action === 'cp-att-mark') {
      const ui = CP.ui.attendance;
      const id = Number(el.dataset.swimmerId);
      ui.marks[id] = ui.marks[id] === el.dataset.status ? undefined : el.dataset.status;
      if (ui.marks[id] === undefined) delete ui.marks[id];
      ui.dirty = true;
      cpRenderTab();
    } else if (action === 'cp-att-mark-all') {
      const ui = CP.ui.attendance;
      CP.swimmers.filter(s => s.userId && s.squadId === ui.squadId && s.status === 'active')
        .forEach(s => { ui.marks[s.userId] = 'present'; });
      ui.dirty = true;
      cpRenderTab();
    } else if (action === 'cp-att-save') {
      const ui = CP.ui.attendance;
      ui.saving = true;
      cpRenderTab();
      try {
        await cpApi('/coach/pro/api/attendance', { method: 'POST', body: cpForm({
          squad_id: ui.squadId, date: ui.date, marks: JSON.stringify(ui.marks),
        }) });
        ui.dirty = false;
        await cpLoadState();
      } finally {
        ui.saving = false;
        cpRenderAll();
      }
    }

    // AI assistant
    else if (action === 'cp-ai-generate') {
      const ui = CP.ui.ai;
      ui.loading = true;
      ui.error = null;
      cpRenderTab();
      try {
        const res = await fetch('/coach/pro/api/ai/insights', {
          method: 'POST', credentials: 'same-origin',
          body: cpForm({ squad_id: ui.squadId, tone: ui.tone }),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok || !data || data.ok === false) {
          ui.error = (data && data.error) || 'Something went wrong — please try again.';
          ui.insights = null;
        } else {
          ui.insights = data.insights;
        }
      } catch (err) {
        ui.error = 'Something went wrong — please try again.';
      }
      ui.loading = false;
      cpRenderTab();
    }

    // Roster
    else if (action === 'cp-toggle-add-squad') {
      CP.ui.roster.showAddSquad = !CP.ui.roster.showAddSquad;
      cpRenderTab();
    } else if (action === 'cp-pick-squad-color') {
      CP.ui.roster.squadColor = el.dataset.color;
      cpRenderTab();
    } else if (action === 'cp-select-squad') {
      CP.ui.roster.selectedSquadId = el.dataset.squadId === 'all' ? 'all' : Number(el.dataset.squadId);
      cpRenderTab();
    } else if (action === 'cp-remove-squad') {
      if (!confirm('Delete this squad? This removes all its memberships too.')) return;
      const id = el.dataset.squadId;
      await cpApi(`/coach/pro/api/squads/${id}/delete`, { method: 'POST' });
      if (CP.ui.roster.selectedSquadId === Number(id)) CP.ui.roster.selectedSquadId = 'all';
      await cpRefresh();
    } else if (action === 'cp-open-add-swimmer') {
      if (CP.squads.length === 0) { alert('Create a squad first.'); return; }
      CP.ui.roster.inviteSquadId = CP.ui.roster.selectedSquadId === 'all' ? CP.squads[0].id : CP.ui.roster.selectedSquadId;
      CP.ui.roster.showAddSwimmer = !CP.ui.roster.showAddSwimmer;
      cpRenderTab();
    } else if (action === 'cp-toggle-add-swimmer') {
      CP.ui.roster.showAddSwimmer = false;
      cpRenderTab();
    } else if (action === 'cp-remove-swimmer') {
      if (!confirm('Remove this swimmer from the roster?')) return;
      const id = el.dataset.membershipId;
      await cpApi(`/coach/pro/api/memberships/${id}/remove`, { method: 'POST' });
      await cpRefresh();
    }

    // Builder
    else if (action === 'cp-toggle-create-set') {
      const isOpen = CP.ui.builder.showCreateSet || CP.ui.builder.editingSetId;
      CP.ui.builder.editingSetId = null;
      CP.ui.builder.showCreateSet = !isOpen;
      CP.ui.builder.blocks = [];
      cpRenderTab();
    } else if (action === 'cp-edit-set') {
      const set = CP.savedSets.find(s => s.id === Number(el.dataset.setId));
      if (!set) return;
      CP.ui.builder.editingSetId = set.id;
      CP.ui.builder.showCreateSet = false;
      CP.ui.builder.blocks = (set.blocks || []).map(b => ({ ...b }));
      cpRenderTab();
      const form = document.getElementById('cpCreateSetForm');
      if (form) form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else if (action === 'cp-add-block') {
      const section = document.getElementById('cpBlockSection').value;
      const reps = Number(document.getElementById('cpBlockReps').value) || 1;
      const dist = Number(document.getElementById('cpBlockDist').value) || 0;
      const stroke = document.getElementById('cpBlockStroke').value;
      const rest = document.getElementById('cpBlockRest').value;
      const rest_type = document.getElementById('cpBlockRestType').value;
      CP.ui.builder.blocks.push({ section, reps, dist, stroke, rest, rest_type });
      cpRenderTab();
    } else if (action === 'cp-remove-block') {
      CP.ui.builder.blocks.splice(Number(el.dataset.index), 1);
      cpRenderTab();
    } else if (action === 'cp-delete-set') {
      if (!confirm('Delete this set template?')) return;
      const id = el.dataset.setId;
      await cpApi(`/coach/pro/api/sets/${id}/delete`, { method: 'POST' });
      await cpRefresh();
    } else if (action === 'cp-select-set-for-assign') {
      CP.ui.builder.selectedSetForAssign = Number(el.dataset.setId);
      const assignable = CP.swimmers.filter(s => s.userId);
      CP.ui.builder.assignTargetId = CP.ui.builder.assignTargetType === 'squad' ? (CP.squads[0] ? CP.squads[0].id : '') : (assignable[0] ? assignable[0].userId : '');
      cpRenderTab();
    } else if (action === 'cp-cancel-assign') {
      CP.ui.builder.selectedSetForAssign = null;
      cpRenderTab();
    } else if (action === 'cp-assign-target-type') {
      const assignable = CP.swimmers.filter(s => s.userId);
      CP.ui.builder.assignTargetType = el.dataset.type;
      CP.ui.builder.assignTargetId = el.dataset.type === 'squad' ? (CP.squads[0] ? CP.squads[0].id : '') : (assignable[0] ? assignable[0].userId : '');
      cpRenderTab();
    } else if (action === 'cp-toggle-assignment-status') {
      const id = el.dataset.id;
      await cpApi(`/coach/pro/api/assignments/${id}/toggle`, { method: 'POST' });
      await cpRefresh();
    } else if (action === 'cp-remove-assignment') {
      const id = el.dataset.id;
      await cpApi(`/coach/pro/api/assignments/${id}/delete`, { method: 'POST' });
      await cpRefresh();
    }
  });

  document.body.addEventListener('change', async (e) => {
    if (e.target.id === 'cpSwimmerSelect') {
      CP.ui.swimmer.selectedSwimmerId = Number(e.target.value);
      cpRenderTab();
    } else if (e.target.id === 'cpAttSquadSelect') {
      CP.ui.attendance.squadId = Number(e.target.value);
      CP.ui.attendance.marks = {};
      await cpLoadAttendanceMarks();
    } else if (e.target.id === 'cpAttDate') {
      CP.ui.attendance.date = e.target.value;
      CP.ui.attendance.marks = {};
      await cpLoadAttendanceMarks();
    } else if (e.target.id === 'cpAISquadSelect') {
      CP.ui.ai.squadId = Number(e.target.value);
      CP.ui.ai.insights = null;
      CP.ui.ai.error = null;
      cpRenderTab();
    } else if (e.target.id === 'cpAIToneSelect') {
      CP.ui.ai.tone = e.target.value;
    } else if (e.target.id === 'cpAnnSquadSelect') {
      CP.ui.announcements.squadId = Number(e.target.value);
      cpRenderTab();
    } else if (e.target.id === 'cpRepSquadSelect') {
      CP.ui.reports.squadId = Number(e.target.value);
      cpRenderTab();
    } else if (e.target.id === 'cpTsSquadSelect') {
      CP.ui.testsets.squadId = Number(e.target.value);
      CP.ui.testsets.result = null;
      CP.ui.testsets.error = null;
      cpRenderTab();
    } else if (e.target.id === 'cpTsPhoto') {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const ui = CP.ui.testsets;
      ui.scanning = true;
      ui.error = null;
      ui.result = null;
      cpRenderTab();
      try {
        const fd = new FormData();
        fd.append('squad_id', ui.squadId);
        fd.append('photo', file);
        const res = await fetch('/coach/pro/api/test-sets/scan', { method: 'POST', credentials: 'same-origin', body: fd });
        const data = await res.json().catch(() => null);
        if (!res.ok || !data || data.ok === false) {
          ui.error = (data && data.error) || 'Something went wrong — please try again.';
        } else {
          ui.result = data;
        }
      } catch (err) {
        ui.error = 'Something went wrong — please try again.';
      }
      ui.scanning = false;
      cpRenderTab();
    } else if (e.target.dataset.action === 'cp-reassign-squad') {
      const membershipId = e.target.dataset.membershipId;
      const squadId = e.target.value;
      await cpApi(`/coach/pro/api/memberships/${membershipId}/reassign`, { method: 'POST', body: cpForm({ squad_id: squadId }) });
      await cpRefresh();
    }
  });

  document.body.addEventListener('submit', async (e) => {
    if (e.target.id === 'cpAnnForm') {
      e.preventDefault();
      const message = (new FormData(e.target).get('message') || '').toString().trim();
      if (!message) return;
      CP.ui.announcements.posting = true;
      cpRenderTab();
      try {
        await cpApi('/coach/pro/api/announcements', { method: 'POST', body: cpForm({ squad_id: CP.ui.announcements.squadId, message }) });
        await cpLoadState();
      } finally {
        CP.ui.announcements.posting = false;
        cpRenderTab();
      }
    } else if (e.target.id === 'cpCreateEventForm') {
      e.preventDefault();
      const fd = new FormData(e.target);
      fd.append('slot', CP.ui.schedule.slot);
      await cpApi('/coach/pro/api/schedule', { method: 'POST', body: fd });
      CP.ui.schedule.showCreate = false;
      await cpRefresh();
    } else if (e.target.id === 'cpAIGenForm') {
      e.preventDefault();
      const ui = CP.ui.aiGen;
      if (ui.loading) return;
      const fd = new FormData(e.target); // capture before re-render clears the form
      ui.loading = true;
      cpRenderTab();
      try {
        const res = await fetch('/coach/pro/api/ai/generate-set', {
          method: 'POST', credentials: 'same-origin', body: fd,
        });
        const data = await res.json().catch(() => null);
        if (!res.ok || !data || data.ok === false) {
          alert((data && data.error) || 'Something went wrong — please try again.');
        } else {
          ui.show = false;
          await cpLoadState();
        }
      } catch (err) {
        alert('Something went wrong — please try again.');
      }
      ui.loading = false;
      cpRenderAll();
    } else if (e.target.id === 'cpCreateSquadForm') {
      e.preventDefault();
      const fd = new FormData(e.target);
      const name = (fd.get('name') || '').toString().trim();
      if (!name) return;
      await cpApi('/coach/pro/api/squads', { method: 'POST', body: cpForm({ name, color: CP.ui.roster.squadColor }) });
      CP.ui.roster.showAddSquad = false;
      CP.ui.roster.squadColor = 'blue';
      await cpRefresh();
    } else if (e.target.id === 'cpInviteSwimmerForm') {
      e.preventDefault();
      const fd = new FormData(e.target);
      const email = (fd.get('email') || '').toString().trim();
      const squadId = fd.get('squadId');
      if (!email || !squadId) return;
      await cpApi(`/coach/pro/api/squads/${squadId}/invite`, { method: 'POST', body: cpForm({ email }) });
      CP.ui.roster.showAddSwimmer = false;
      await cpRefresh();
    } else if (e.target.id === 'cpCreateSetForm') {
      e.preventDefault();
      const fd = new FormData(e.target);
      const name = (fd.get('name') || '').toString().trim();
      if (!name) return;
      const editingId = CP.ui.builder.editingSetId;
      const url = editingId ? `/coach/pro/api/sets/${editingId}/update` : '/sets/create';
      await cpApi(url, { method: 'POST', body: cpForm({
        name, pool: fd.get('pool'), session_type: 'Training', category: fd.get('category'),
        description: fd.get('description'),
        sets_data: JSON.stringify(CP.ui.builder.blocks),
      }) });
      CP.ui.builder.showCreateSet = false;
      CP.ui.builder.editingSetId = null;
      CP.ui.builder.blocks = [];
      await cpRefresh();
    } else if (e.target.id === 'cpCreateAssignmentForm') {
      e.preventDefault();
      const fd = new FormData(e.target);
      const setId = CP.ui.builder.selectedSetForAssign;
      if (!setId) return;
      const targetId = fd.get('target_id');
      if (!targetId) { alert('No valid target selected.'); return; }
      await cpApi('/coach/pro/api/assignments', { method: 'POST', body: cpForm({
        set_id: setId, target_type: CP.ui.builder.assignTargetType, target_id: targetId,
        due_date: fd.get('due_date'), notes: fd.get('notes'),
      }) });
      CP.ui.builder.selectedSetForAssign = null;
      await cpRefresh();
    }
  });
});
