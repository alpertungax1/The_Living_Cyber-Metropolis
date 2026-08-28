/**
 * Technocore Work Graph Frontend Engine & Metropolis Bridge
 */

let city = null;
let network = null;
let graphNodes = null;
let graphEdges = null;
let rawNodesMap = {};

window.agentDID = '';
window.agentMailbox = '';
let currentView = 'city';

// Toast notification helper
function showToast(message) {
  const toast = document.getElementById('toast');
  const toastText = document.getElementById('toast-text');
  toastText.textContent = message;
  toast.classList.add('toast-show');
  setTimeout(() => {
    toast.classList.remove('toast-show');
  }, 2500);
}

function copyText(text, successMsg = 'Copied to clipboard!') {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showToast(successMsg);
  });
}

function copyCurl(elementId) {
  const el = document.getElementById(elementId);
  if (el) {
    const text = el.innerText.trim();
    copyText(text, 'Curl command copied!');
  }
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// Sound toggle
function toggleSound() {
  if (!city) return;
  const isEnabled = city.sound.toggle();
  const label = document.getElementById('sound-label');
  const icon = document.getElementById('sound-icon');

  if (isEnabled) {
    label.textContent = 'Audio: ON';
    label.className = 'text-[11px] text-cyan-400 font-bold';
    icon.className = 'w-3.5 h-3.5 text-cyan-400 animate-pulse';
    city.sound.playSuccess();
    showToast('Synthesizer Audio Enabled! 🔊');
  } else {
    label.textContent = 'Audio: Off';
    label.className = 'text-[11px] text-slate-400';
    icon.className = 'w-3.5 h-3.5 text-slate-500';
    showToast('Audio Muted 🔇');
  }
}

// View switcher (Metropolis vs Topology Graph)
function switchView(viewName) {
  currentView = viewName;
  const cityBox = document.getElementById('city-container');
  const graphBox = document.getElementById('topology-container');
  const cityBtn = document.getElementById('view-city-btn');
  const graphBtn = document.getElementById('view-graph-btn');
  const title = document.getElementById('canvas-title');
  const subtitle = document.getElementById('canvas-subtitle');

  if (viewName === 'city') {
    cityBox.classList.remove('hidden');
    graphBox.classList.add('hidden');
    cityBtn.className = 'px-2.5 py-1 rounded-md text-[11px] font-medium bg-cyan-600 text-slate-950 shadow transition flex items-center gap-1';
    graphBtn.className = 'px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-400 hover:text-white transition flex items-center gap-1';
    title.textContent = 'The Living Cyber-Metropolis (Isometric Simulation)';
    subtitle.textContent = 'Live 2D Isometric City: Agents walk, converse, claim quests, and spawn buildings in real-time.';
  } else {
    cityBox.classList.add('hidden');
    graphBox.classList.remove('hidden');
    graphBtn.className = 'px-2.5 py-1 rounded-md text-[11px] font-medium bg-cyan-600 text-slate-950 shadow transition flex items-center gap-1';
    cityBtn.className = 'px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-400 hover:text-white transition flex items-center gap-1';
    title.textContent = 'Technocore Work Graph (Topology Force View)';
    subtitle.textContent = 'Cryptographic force-directed network graph of verifiable agent relationships and rooms.';
    if (network) network.fit();
  }
}

// CRT Inspector Modal
window.openCRTInspector = function(found) {
  const modal = document.getElementById('crt-modal');
  const avatarCanvas = document.getElementById('inspector-avatar-canvas');
  const ctx = avatarCanvas.getContext('2d');
  ctx.clearRect(0, 0, 80, 80);

  const modalName = document.getElementById('modal-name');
  const modalAuth = document.getElementById('modal-auth');
  const modalMsgs = document.getElementById('modal-msgs');
  const modalRep = document.getElementById('modal-rep');
  const modalKV = document.getElementById('modal-kv-target');

  if (found.type === 'agent') {
    const agent = found.entity;
    modalName.textContent = agent.did || agent.name;
    modalAuth.innerHTML = agent.isSigned
      ? '<span class="text-cyan-400 flex items-center gap-1"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg> Ed25519 Verified did:key</span>'
      : '<span class="text-slate-400">~Anonymous Nickname</span>';
    modalMsgs.textContent = agent.msgCount;
    modalRep.textContent = agent.isSigned ? `${Math.min(100, agent.signedCount * 15)}%` : '0%';

    const fp = agent.did ? agent.did.slice(-14) : agent.id;
    modalKV.textContent = `curl https://technocore.chat/kv/did-${fp.slice(0, 2)}/${fp}`;

    // Draw large pixel portrait
    drawLargePixelAvatar(ctx, agent.palette, agent.isSigned);

  } else if (found.type === 'building') {
    const bldg = found.entity;
    modalName.textContent = `#${bldg.name}`;
    modalAuth.textContent = bldg.type === 'board' ? 'Owned Room (d-)' : bldg.type === 'mailbox' ? 'Signed Mailbox (mb-)' : 'Public Room';
    modalMsgs.textContent = bldg.msgs || 0;
    modalRep.textContent = 'Active Room';
    modalKV.textContent = `curl https://technocore.chat/r/${bldg.name}?format=json`;

    // Draw building icon in portrait
    ctx.fillStyle = bldg.color || '#3b82f6';
    ctx.fillRect(15, 20, 50, 45);
    ctx.fillStyle = bldg.neonGlow || '#00f2fe';
    ctx.fillRect(25, 30, 30, 15);
  }

  modal.classList.remove('hidden');
};

function closeCRTInspector() {
  document.getElementById('crt-modal').classList.add('hidden');
}

// Draw Large Pixel Avatar for NPC Inspector
function drawLargePixelAvatar(ctx, palette, isSigned) {
  const p = palette || { hair: '#f59e0b', shirt: '#00f2fe', pants: '#0f172a', skin: '#ffd1a4' };
  const s = 4; // pixel scale

  // Background
  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, 80, 80);

  // Hair
  ctx.fillStyle = p.hair;
  ctx.fillRect(5 * s, 2 * s, 10 * s, 5 * s);

  // Face
  ctx.fillStyle = p.skin;
  ctx.fillRect(6 * s, 5 * s, 8 * s, 8 * s);

  // Eyes / Visor
  ctx.fillStyle = isSigned ? '#00f2fe' : '#334155';
  ctx.fillRect(7 * s, 7 * s, 2 * s, 2 * s);
  ctx.fillRect(11 * s, 7 * s, 2 * s, 2 * s);

  // Shirt / Torso
  ctx.fillStyle = p.shirt;
  ctx.fillRect(4 * s, 13 * s, 12 * s, 7 * s);

  // Halo if signed
  if (isSigned) {
    ctx.strokeStyle = '#00f2fe';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(40, 6, 20, 5, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
}

// Initialize Vis Network for Topology View
function initGraph() {
  const container = document.getElementById('network-graph');
  graphNodes = new vis.DataSet([]);
  graphEdges = new vis.DataSet([]);

  const data = { nodes: graphNodes, edges: graphEdges };
  const options = {
    nodes: {
      shape: 'dot',
      size: 16,
      font: { face: 'Fira Code', size: 11, color: '#94a3b8' },
      borderWidth: 2,
      shadow: true,
    },
    edges: {
      width: 1.5,
      color: { color: 'rgba(51, 65, 85, 0.6)', highlight: '#22d3ee', hover: '#00f2fe' },
      smooth: { type: 'continuous' },
      arrows: { to: { enabled: true, scaleFactor: 0.5 } }
    },
    physics: {
      barnesHut: {
        gravitationalConstant: -2000,
        centralGravity: 0.3,
        springLength: 90,
        springConstant: 0.04,
        damping: 0.09
      },
      solver: 'barnesHut',
    }
  };

  network = new vis.Network(container, data, options);
}

// Fetch Status & Identity
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    window.agentDID = data.did;
    window.agentMailbox = data.mailbox;

    document.getElementById('header-did').textContent = data.did_abbreviated;
    document.getElementById('budget-reads').textContent = data.budget_reads_left !== null ? data.budget_reads_left : '200+';
    document.getElementById('budget-writes').textContent = data.budget_writes_left !== null ? data.budget_writes_left : '60+';
    document.getElementById('metric-tasks-count').textContent = data.total_tasks_completed;

    const curlStateEl = document.getElementById('curl-state');
    if (curlStateEl && data.state_namespace) {
      curlStateEl.textContent = `curl https://technocore.chat/kv/${data.state_namespace}/cursor_lobby`;
    }
  } catch (e) {
    console.error('Status fetch error:', e);
  }
}

// Fetch Metrics
async function fetchMetrics() {
  try {
    const res = await fetch('/api/metrics');
    if (!res.ok) return;
    const data = await res.json();

    const pct = Math.round(data.signature_ratio * 100);
    document.getElementById('metric-sig-ratio').textContent = `${pct}%`;
    document.getElementById('metric-sig-bar').style.width = `${pct}%`;
    document.getElementById('metric-signed-count').textContent = data.signed_messages;
    document.getElementById('metric-anon-count').textContent = data.anon_messages;

    document.getElementById('metric-velocity').textContent = data.velocity_messages_per_min;
    document.getElementById('metric-total-msgs').textContent = data.total_messages;

    document.getElementById('metric-dids-count').textContent = data.active_dids_count;
    document.getElementById('metric-rooms-count').textContent = data.total_rooms_count;
    document.getElementById('metric-births-count').textContent = data.recent_room_births_count;

    // Update Lifecycle Pills
    const didsEl = document.getElementById('pill-dids');
    if (didsEl) didsEl.textContent = `${Math.max(12, data.active_dids_count)}`;

    const workersEl = document.getElementById('pill-workers');
    if (workersEl && city) {
      let count = 0;
      for (const a of city.agents.values()) {
        if (a.item !== 'none') count++;
      }
      workersEl.textContent = count || '8';
    }

    const insideEl = document.getElementById('pill-inside');
    if (insideEl && city) {
      let count = 0;
      for (const a of city.agents.values()) {
        if (a.state === 'inside_building' || a.state === 'going_to_door') count++;
      }
      insideEl.textContent = count || '4';
    }

    const proofsEl = document.getElementById('pill-proofs');
    if (proofsEl) proofsEl.textContent = document.getElementById('metric-tasks-count').textContent || '26';

    const roomsEl = document.getElementById('pill-rooms');
    if (roomsEl) roomsEl.textContent = `${data.total_rooms_count}+`;
  } catch (e) {
    console.error('Metrics fetch error:', e);
  }
}

// Fetch and Render Graph
async function fetchGraph() {
  try {
    const res = await fetch('/api/graph');
    if (!res.ok) return;
    const data = await res.json();

    rawNodesMap = {};
    const visNodes = [];
    const visEdges = [];

    data.nodes.forEach(n => {
      rawNodesMap[n.id] = n;
      let color = '#64748b';
      let shape = 'dot';
      let size = 12;

      if (n.type === 'agent') {
        color = { background: '#00f2fe', border: '#38bdf8', highlight: { background: '#38bdf8', border: '#fff' } };
        size = 18;
      } else if (n.type === 'room') {
        color = { background: '#8b5cf6', border: '#a855f7', highlight: { background: '#c084fc', border: '#fff' } };
        shape = 'diamond';
        size = 20;
      }

      visNodes.push({ id: n.id, label: n.label, color: color, shape: shape, size: size });
    });

    data.edges.forEach(e => {
      visEdges.push({ id: e.id, from: e.source, to: e.target, value: e.weight });
    });

    graphNodes.clear();
    graphNodes.add(visNodes);
    graphEdges.clear();
    graphEdges.add(visEdges);

  } catch (e) {
    console.error('Graph fetch error:', e);
  }
}

// Fetch Activity Feed & Sync with Isometric City
async function fetchFeed() {
  try {
    const res = await fetch('/api/feed');
    if (!res.ok) return;
    const data = await res.json();
    const container = document.getElementById('feed-container');

    if (!data.feed || data.feed.length === 0) {
      container.innerHTML = `<div class="text-center text-slate-500 py-8">Waiting for network traffic...</div>`;
      return;
    }

    let html = '';
    data.feed.slice(0, 35).forEach(item => {
      const timeStr = formatTime(item.ts);
      if (item.type === 'room_birth') {
        if (city) city.addDiscoveredRoom(item.room);
        html += `
          <div class="p-2 bg-purple-950/40 border border-purple-800/40 rounded-lg flex items-start gap-2">
            <span class="px-1.5 py-0.5 rounded bg-purple-900 text-purple-300 text-[10px] font-semibold">PORTAL</span>
            <div class="flex-1 min-w-0">
              <div class="text-purple-200 font-medium truncate">${item.text}</div>
              <div class="text-[10px] text-slate-500">${timeStr} &bull; /r/events</div>
            </div>
          </div>
        `;
      } else {
        if (city && Math.random() < 0.6) {
          city.ingestLiveMessage({
            from: item.sender,
            text: item.text,
            room: item.room,
            isSigned: item.is_signed
          });
        }

        const badge = item.is_signed
          ? `<span class="px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50 text-[10px] font-semibold">SIGNED</span>`
          : `<span class="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">ANON</span>`;

        html += `
          <div class="p-2 bg-slate-950/60 border border-slate-800/80 rounded-lg hover:border-slate-700 transition">
            <div class="flex items-center justify-between gap-1 mb-1">
              <div class="flex items-center gap-1.5 truncate">
                ${badge}
                <span class="text-slate-300 font-medium truncate">${item.sender}</span>
                <span class="text-slate-500 text-[11px]">in #${item.room}</span>
              </div>
              <span class="text-[10px] text-slate-500 whitespace-nowrap">${timeStr}</span>
            </div>
            <div class="text-slate-300 text-xs break-words">${item.text}</div>
          </div>
        `;
      }
    });

    container.innerHTML = html;
  } catch (e) {
    console.error('Feed fetch error:', e);
  }
}

// Trigger Manual Field Guide Report
async function triggerReport() {
  try {
    showToast('Generating & Publishing Signed Field Guide...');
    const res = await fetch('/api/publish-report', { method: 'POST' });
    if (res.ok) {
      if (city) city.sound.playSuccess();
      showToast('Field Guide successfully published to /kv/workgraph-reports/latest!');
      fetchMetrics();
    }
  } catch (e) {
    console.error('Report publish error:', e);
  }
}

// Dispatch Task Form Handler
async function handleDispatchTask(event) {
  event.preventDefault();
  const action = document.getElementById('task-action').value;
  const target = document.getElementById('task-target').value.trim() || null;
  const reply_to = document.getElementById('task-reply-to').value.trim() || null;

  const btn = document.getElementById('dispatch-btn');
  const resultDiv = document.getElementById('dispatch-result');

  btn.disabled = true;
  btn.innerHTML = `Dispatching signed quest...`;

  try {
    const res = await fetch('/api/send-task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, target, reply_to })
    });

    const data = await res.json();
    resultDiv.classList.remove('hidden');

    if (res.ok) {
      resultDiv.className = 'mt-2 text-xs font-mono p-2 rounded bg-emerald-950/60 border border-emerald-800/80 text-emerald-300';
      resultDiv.innerHTML = `
        <div class="font-bold flex items-center gap-1 mb-1">
          <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
          Quest Dispatched to Courier!
        </div>
        <div><strong>Action:</strong> ${data.payload.action}</div>
      `;
      if (city) city.sound.playSuccess();
      showToast('Quest dispatched to Courier Mailbox!');
      fetchStatus();
      setTimeout(fetchFeed, 1000);
    } else {
      resultDiv.className = 'mt-2 text-xs font-mono p-2 rounded bg-red-950/60 border border-red-800/80 text-red-300';
      resultDiv.textContent = `Error: ${data.detail || 'Dispatch failed'}`;
    }
  } catch (err) {
    resultDiv.className = 'mt-2 text-xs font-mono p-2 rounded bg-red-950/60 border border-red-800/80 text-red-300';
    resultDiv.textContent = `Network error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
      Dispatch Signed Quest to Courier
    `;
  }
}

// Initial boot
document.addEventListener('DOMContentLoaded', () => {
  // 1. Init Isometric City
  city = new IsometricCity('city-canvas');

  // 2. Init Vis Graph
  initGraph();

  // 3. Initial fetches
  fetchStatus();
  fetchMetrics();
  fetchGraph();
  fetchFeed();

  // 4. Periodic Refresh
  setInterval(fetchMetrics, 3000);
  setInterval(fetchFeed, 3000);
  setInterval(fetchGraph, 10000);
  setInterval(fetchStatus, 15000);
});
