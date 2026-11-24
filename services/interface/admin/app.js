// ZZCC 管理平台 — 应用入口
// 路由 + API 层 + 页面分发

const API_BASE = '/api/v1';

// ── API 层 ──
async function apiGet(path, params) {
  const url = new URL(API_BASE + path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    });
  }
  const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!resp.ok) throw new Error(`API ${resp.status}: ${path}`);
  return resp.json();
}

async function apiPost(path, body) {
  const resp = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new Error(`API ${resp.status}: ${path}`);
  return resp.json();
}

// ── 页面注册 ──
const PAGES = {}; // pageId -> { title, render(container) }

function registerPage(id, def) {
  PAGES[id] = def;
}

// ── 路由 ──
function currentPage() {
  const hash = window.location.hash.replace(/^#/, '').replace(/^\//, '');
  return hash.split('?')[0] || 'snn';
}

function navigate(pageId) {
  window.location.hash = pageId;
}

function render() {
  const pageId = currentPage();
  const page = PAGES[pageId];

  // 导航高亮
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === pageId);
  });

  const content = document.getElementById('content');
  const title = document.getElementById('page-title');
  document.querySelectorAll('.nav-item').forEach(el => {
    if (el.dataset.page === pageId) {
      title.textContent = el.querySelector('span:nth-child(2)').textContent;
    }
  });

  if (!page) {
    content.innerHTML = '<div class="placeholder"><div class="ph-icon">🚧</div>' +
      '<div class="ph-title">页面开发中</div><div>该模块尚未实现</div></div>';
    return;
  }
  content.innerHTML = '<div class="loading">加载中...</div>';
  page.render(content);
}

// ── 健康检查 ──
async function checkConn() {
  const el = document.getElementById('conn-status');
  try {
    // 健康端点在 /health（不带 /api/v1 前缀），需直接请求
    const resp = await fetch('/health', { headers: { 'Accept': 'application/json' } });
    if (!resp.ok) throw new Error(`health ${resp.status}`);
    el.className = 'conn-status ok';
    el.innerHTML = '<span class="dot"></span><span>服务正常</span>';
  } catch (e) {
    el.className = 'conn-status err';
    el.innerHTML = '<span class="dot"></span><span>连接异常</span>';
  }
}

// ── 通用工具 ──
function fmtNumber(n) {
  if (n === null || n === undefined) return '-';
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(n);
}

function fmtTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleString('zh-CN', { hour12: false });
}

function decisionTag(decision) {
  const map = {
    escalate: ['tag-red', 'escalate'],
    auto_approve: ['tag-green', 'auto_approve'],
    reject: ['tag-red', 'reject'],
    flag: ['tag-yellow', 'flag'],
    need_info: ['tag-blue', 'need_info'],
    chat: ['tag-purple', 'chat'],
    no_action: ['tag-blue', 'no_action'],
  };
  const [cls, label] = map[decision] || ['tag-blue', decision];
  return `<span class="tag ${cls}">${label}</span>`;
}

// ── 刷新 ──
let lastRefresh = null;
function refreshAll() {
  const page = PAGES[currentPage()];
  if (page && page.refresh) {
    page.refresh();
  }
  lastRefresh = new Date();
  document.getElementById('last-refresh').textContent =
    '上次刷新 ' + lastRefresh.toLocaleTimeString('zh-CN', { hour12: false });
}

// ── 启动 ──
window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', () => {
  render();
  checkConn();
  setInterval(checkConn, 30000);
});
