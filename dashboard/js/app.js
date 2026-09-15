/**
 * DISTRIBUTED TRAFFIC MONITORING - DASHBOARD JS CLIENT
 * Handles real-time API polling, KPI updating, live Chart.js rendering, 
 * log ticker stream, and traffic surge simulation triggers.
 */

let trafficChart = null;
let currentChartMode = 'speed'; // 'speed' or 'vehicles'
let historicalDataStore = {}; // { junction_id: [{ timestamp, avg_speed_kmh, vehicle_count }] }
let knownSequenceNums = {}; // { junction_id: last_seq }

document.addEventListener('DOMContentLoaded', () => {
  initChart();
  fetchSystemStatus();
  fetchAlerts();

  // Auto-poll central monitoring server every 3 seconds
  setInterval(() => {
    fetchSystemStatus();
    fetchAlerts();
  }, 3000);
});

/**
 * Fetches central server status via GET /api/status
 */
async function fetchSystemStatus() {
  const icon = document.getElementById('refresh-icon');
  if (icon) icon.classList.add('fa-spin');

  try {
    const res = await fetch('/api/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    updateKPIs(data.summary);
    renderJunctionGrid(data.junctions);
    processNodeLogs(data.junctions);
    fetchHistoryForNodes(data.junctions);

  } catch (err) {
    console.error('Error fetching system status:', err);
    document.getElementById('system-status-text').textContent = 'SERVER DISCONNECTED';
    document.getElementById('system-status-text').style.color = '#ef4444';
  } finally {
    if (icon) setTimeout(() => icon.classList.remove('fa-spin'), 600);
  }
}

/**
 * Updates top header KPI cards
 */
function updateKPIs(summary) {
  if (!summary) return;

  document.getElementById('kpi-active-nodes').textContent = `${summary.active_nodes} / ${summary.total_nodes}`;
  document.getElementById('kpi-total-vehicles').textContent = summary.total_vehicles.toLocaleString();
  document.getElementById('kpi-avg-speed').textContent = `${summary.network_avg_speed} km/h`;
  document.getElementById('kpi-overall-status').textContent = summary.overall_status.replace('_', ' ');
  document.getElementById('kpi-highest-node').textContent = summary.highest_traffic_junction;

  // Color code overall network health
  const healthEl = document.getElementById('kpi-overall-status');
  const descEl = document.getElementById('kpi-status-desc');
  if (summary.overall_status === 'HEAVY_CONGESTION') {
    healthEl.style.color = '#ef4444';
    descEl.textContent = 'High congestion alert';
  } else if (summary.overall_status === 'MODERATE_TRAFFIC') {
    healthEl.style.color = '#f59e0b';
    descEl.textContent = 'Moderate density';
  } else {
    healthEl.style.color = '#10b981';
    descEl.textContent = 'Normal flow';
  }
}

/**
 * Renders junction grid cards dynamically
 */
function renderJunctionGrid(junctions) {
  const container = document.getElementById('junction-grid-container');
  if (!junctions || junctions.length === 0) {
    container.innerHTML = `
      <div class="loading-state">
        <i class="fa-solid fa-triangle-exclamation" style="color: #f59e0b;"></i> 
        No active nodes registered yet. Start node_simulator.py instances!
      </div>
    `;
    return;
  }

  container.innerHTML = junctions.map(j => {
    const cLevel = j.congestion_level.toLowerCase();
    const weatherIcon = getWeatherIcon(j.weather_condition);
    const timeAgo = formatTimeAgo(j.last_seen);

    return `
      <div class="junction-card status-${cLevel}">
        <div class="card-top">
          <div class="node-title">
            <h4>${escapeHtml(j.junction_name)}</h4>
            <span class="node-id-tag">Node ID: ${escapeHtml(j.junction_id)}</span>
          </div>
          <span class="status-tag ${cLevel}">${j.congestion_level}</span>
        </div>

        <div class="card-metrics">
          <div class="metric-box">
            <label><i class="fa-solid fa-car"></i> Vehicles</label>
            <span>${j.vehicle_count}</span>
          </div>
          <div class="metric-box">
            <label><i class="fa-solid fa-gauge"></i> Avg Speed</label>
            <span>${j.avg_speed_kmh} <small>km/h</small></span>
          </div>
        </div>

        <div class="card-footer">
          <span><i class="fa-solid ${weatherIcon}"></i> ${escapeHtml(j.weather_condition)}</span>
          <span><i class="fa-solid fa-clock"></i> ${timeAgo}</span>
        </div>

        <div style="margin-top: 12px; text-align: right;">
          <button class="btn btn-surge" onclick="triggerSurge('${j.junction_id}')">
            <i class="fa-solid fa-bolt"></i> Simulate Traffic Surge
          </button>
        </div>
      </div>
    `;
  }).join('');
}

/**
 * Logs stream visualizer displaying incoming node reports
 */
function processNodeLogs(junctions) {
  const logContainer = document.getElementById('node-log-stream');
  if (!logContainer) return;

  junctions.forEach(j => {
    const lastSeq = knownSequenceNums[j.junction_id] || 0;

    if (j.report_count > lastSeq) {
      knownSequenceNums[j.junction_id] = j.report_count;

      const timeStr = new Date().toLocaleTimeString();
      const entry = document.createElement('div');
      entry.className = 'log-entry';
      entry.innerHTML = `
        <span class="log-time">[${timeStr}]</span> 
        <span class="log-node">[Node-${j.junction_id}]</span> 
        <span class="log-msg">Reported telemetry: ${j.vehicle_count} vehicles, ${j.avg_speed_kmh} km/h (${j.congestion_level} Congestion)</span>
      `;

      logContainer.insertBefore(entry, logContainer.firstChild);

      // Limit max log entries to 30
      if (logContainer.children.length > 30) {
        logContainer.removeChild(logContainer.lastChild);
      }
    }
  });
}

/**
 * Fetches history logs for all nodes to populate Chart.js
 */
async function fetchHistoryForNodes(junctions) {
  for (const j of junctions) {
    try {
      const res = await fetch(`/api/history/${j.junction_id}?limit=15`);
      if (res.ok) {
        const data = await res.json();
        historicalDataStore[j.junction_id] = data.history;
      }
    } catch (e) {
      console.error(`Failed to fetch history for node ${j.junction_id}`, e);
    }
  }
  updateChart();
}

/**
 * Initializes real-time Chart.js graph
 */
function initChart() {
  const ctx = document.getElementById('trafficChart').getContext('2d');
  trafficChart = new Chart(ctx, {
    type: 'line',
    data: { labels: [], datasets: [] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 12 } }
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: '#1e293b',
          titleColor: '#f8fafc',
          bodyColor: '#cbd5e1',
          borderColor: '#334155',
          borderWidth: 1
        }
      },
      scales: {
        x: {
          ticks: { color: '#64748b', maxRotation: 0, font: { family: 'JetBrains Mono', size: 10 } },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        y: {
          ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          beginAtZero: true
        }
      }
    }
  });
}

/**
 * Updates Chart.js dataset based on mode
 */
function updateChart() {
  if (!trafficChart) return;

  const nodeIds = Object.keys(historicalDataStore);
  if (nodeIds.length === 0) return;

  // Use timestamps from first node as X-axis labels
  const sampleHist = historicalDataStore[nodeIds[0]] || [];
  const labels = sampleHist.map(r => {
    const d = new Date(r.timestamp);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  });

  const colors = [
    { border: '#3b82f6', bg: 'rgba(59, 130, 246, 0.1)' },
    { border: '#10b981', bg: 'rgba(16, 185, 129, 0.1)' },
    { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.1)' },
    { border: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.1)' },
    { border: '#ec4899', bg: 'rgba(236, 72, 153, 0.1)' }
  ];

  const datasets = nodeIds.map((id, index) => {
    const hist = historicalDataStore[id] || [];
    const color = colors[index % colors.length];
    const dataPoints = hist.map(r => currentChartMode === 'speed' ? r.avg_speed_kmh : r.vehicle_count);

    return {
      label: `Node ${id}`,
      data: dataPoints,
      borderColor: color.border,
      backgroundColor: color.bg,
      fill: true,
      tension: 0.35,
      borderWidth: 2,
      pointRadius: 2
    };
  });

  trafficChart.data.labels = labels;
  trafficChart.data.datasets = datasets;
  trafficChart.update('quiet');
}

function switchChartMode(mode) {
  currentChartMode = mode;
  document.getElementById('btn-chart-speed').classList.toggle('active', mode === 'speed');
  document.getElementById('btn-chart-vehicles').classList.toggle('active', mode === 'vehicles');
  updateChart();
}

/**
 * Fetches recent alerts from server
 */
async function fetchAlerts() {
  try {
    const res = await fetch('/api/alerts?limit=10');
    if (!res.ok) return;
    const data = await res.json();
    renderAlerts(data.alerts);
  } catch (err) {
    console.error('Error fetching alerts:', err);
  }
}

function renderAlerts(alerts) {
  const container = document.getElementById('alerts-container');
  const badge = document.getElementById('alert-counter-badge');

  if (badge) badge.textContent = `${alerts.length} Alerts`;

  if (!alerts || alerts.length === 0) {
    container.innerHTML = `
      <div class="empty-alerts">
        <i class="fa-solid fa-circle-check"></i>
        <p>No active congestion alerts detected.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = alerts.map(a => `
    <div class="alert-item">
      <i class="fa-solid fa-triangle-exclamation"></i>
      <div class="alert-content">
        <p>${escapeHtml(a.message)}</p>
        <span>${formatTimeAgo(a.timestamp)}</span>
      </div>
    </div>
  `).join('');
}

/**
 * Triggers simulated surge via POST /api/simulate-surge/{junction_id}
 */
async function triggerSurge(junctionId) {
  try {
    const res = await fetch(`/api/simulate-surge/${junctionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vehicle_count: 110, avg_speed_kmh: 8.5 })
    });
    if (res.ok) {
      fetchSystemStatus();
      fetchAlerts();
    }
  } catch (e) {
    alert(`Failed to trigger traffic surge for ${junctionId}: ${e.message}`);
  }
}

// Helpers
function getWeatherIcon(weather) {
  switch (weather) {
    case 'Rainy': return 'fa-cloud-showers-heavy';
    case 'Foggy': return 'fa-smog';
    case 'Overcast': return 'fa-cloud';
    default: return 'fa-sun';
  }
}

function formatTimeAgo(isoString) {
  if (!isoString) return 'Just now';
  try {
    const date = new Date(isoString);
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 5) return 'Just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ago`;
  } catch (e) {
    return 'Recently';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
