// 用户管理 — 权限(user/admin) + 封禁(is_active)
//
// 鉴权: X-Admin-Key 密钥头。密钥不写死在本文件里 —— 静态文件任何人都能抓,
// 写死等于把管理密钥公开。改从 URL ?adminKey= 传入并存 sessionStorage,
// 运维第一次用: /admin/?adminKey=xxx#users, 之后免传。

const ADMIN_USERS = {
  page: { skip: 0, limit: 20, q: '', data: [], total: 0, loading: false },
};

// ── 密钥 ──
function adminKey() {
  const p = new URLSearchParams(window.location.search);
  const k = p.get('adminKey');
  if (k) sessionStorage.setItem('zzcc_admin_key', k);
  return sessionStorage.getItem('zzcc_admin_key');
}

async function adminReq(method, path, body) {
  const key = adminKey();
  if (!key) throw new Error('未配置管理密钥');
  const resp = await fetch(API_BASE + path, {
    method,
    headers: {
      'X-Admin-Key': key,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    let detail = `API ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch (e) { /* 非 JSON 错误体 */ }
    throw new Error(detail);
  }
  return resp.json();
}

// ── 工具 ──
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtDate(v) {
  if (!v) return '<span class="dim">从未</span>';
  const d = new Date(v);
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}

// ── KPI: 从首屏数据本地聚合(后端未提供 stats 端点) ──
function renderStats(container, data) {
  const admins = data.filter(u => u.role === 'admin').length;
  const banned = data.filter(u => !u.is_active).length;
  const active = data.length - banned;
  container.innerHTML = [
    ['用户总数', ADMIN_USERS.page.total, '活跃 + 封禁', 'accent'],
    ['活跃', active, '可正常登录', ''],
    ['封禁', banned, 'is_active = false', banned ? 'danger' : ''],
    ['管理员', admins, 'role = admin', 'accent'],
  ].map(([label, val, sub, cls]) => `
    <div class="card">
      <div class="card-label">${label}</div>
      <div class="card-value ${cls}">${val}</div>
      <div class="card-sub">${sub}</div>
    </div>`).join('');
}

function renderTable(container, data) {
  if (!data.length) {
    container.innerHTML = `<div class="placeholder">
      <div class="ph-icon">👥</div><div class="ph-title">暂无用户</div>
      <div>还没有注册用户。新用户通过 /api/v1/auth/register 创建。</div></div>`;
    return;
  }
  const rows = data.map((u, i) => `
    <tr class="u-row" data-id="${esc(u.id)}">
      <td><span class="u-name">${esc(u.username)}</span>
        ${u.display_name && u.display_name !== u.username ? `<div class="u-sub">${esc(u.display_name)}</div>` : ''}</td>
      <td class="dim">${esc(u.email || '-')}</td>
      <td>${u.role === 'admin' ? '<span class="tag tag-purple">admin</span>' : '<span class="tag tag-blue">user</span>'}</td>
      <td>${u.is_active ? '<span class="tag tag-green">正常</span>' : '<span class="tag tag-red">已封禁</span>'}</td>
      <td class="dim">${fmtDate(u.created_at)}</td>
      <td class="dim">${fmtDate(u.last_login_at)}</td>
      <td class="u-ops">
        ${u.is_active
          ? `<button class="btn btn-sm" data-act="ban" data-id="${esc(u.id)}" data-name="${esc(u.username)}">封禁</button>`
          : `<button class="btn btn-sm btn-primary" data-act="unban" data-id="${esc(u.id)}" data-name="${esc(u.username)}">解封</button>`}
        ${u.role === 'admin'
          ? `<button class="btn btn-sm" data-act="revoke" data-id="${esc(u.id)}" data-name="${esc(u.username)}">撤销管理员</button>`
          : `<button class="btn btn-sm" data-act="promote" data-id="${esc(u.id)}" data-name="${esc(u.username)}">设为管理员</button>`}
      </td>
    </tr>`).join('');

  container.innerHTML = `
    <div class="panel">
      <div class="panel-body no-pad">
        <table class="u-table">
          <thead><tr>
            <th>用户</th><th>邮箱</th><th>角色</th><th>状态</th>
            <th>创建</th><th>最近登录</th><th>操作</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;

  container.querySelector('tbody').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const act = btn.dataset.act, id = btn.dataset.id, name = btn.dataset.name;
    btn.disabled = true;
    try {
      let path, body;
      if (act === 'ban') { path = `/admin/users/${id}/ban`; body = null; }
      else if (act === 'unban') { path = `/admin/users/${id}/unban`; body = null; }
      else if (act === 'promote') { path = `/admin/users/${id}`; body = { role: 'admin' }; }
      else { path = `/admin/users/${id}`; body = { role: 'user' }; }

      const method = body ? 'PATCH' : 'POST';
      const res = await adminReq(method, path, body);
      showUserNotice(`${name}: ${act === 'ban' ? '已封禁' : act === 'unban' ? '已解封' : act === 'promote' ? '已设为管理员' : '已撤销管理员'}`);
      loadUsers();
    } catch (err) {
      showUserNotice('操作失败: ' + err.message, true);
      btn.disabled = false;
    }
  });
}

let _noticeTimer = null;
function showUserNotice(text, isError) {
  const el = document.getElementById('user-notice');
  if (!el) return;
  el.textContent = text;
  el.className = 'user-notice show ' + (isError ? 'err' : 'ok');
  clearTimeout(_noticeTimer);
  _noticeTimer = setTimeout(() => { el.className = 'user-notice'; }, 4000);
}

// ── 加载 ──
async function loadUsers() {
  const p = ADMIN_USERS.page;
  p.loading = true;
  const container = document.getElementById('users-body');
  if (container && p.data.length === 0) container.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const params = new URLSearchParams();
    params.set('skip', p.skip);
    params.set('limit', p.limit);
    if (p.q) params.set('q', p.q);
    const res = await adminReq('GET', `/admin/users?${params}`);
    p.total = res.total || 0;
    p.data = res.data || [];
    renderStats(document.getElementById('users-stats'), p.data);
    renderTable(container, p.data);
    renderPager(document.getElementById('users-pager'), p);
  } catch (err) {
    container.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  } finally {
    p.loading = false;
  }
}

function renderPager(container, p) {
  const pages = Math.max(1, Math.ceil(p.total / p.limit));
  const cur = Math.floor(p.skip / p.limit) + 1;
  container.innerHTML = `
    <button class="btn btn-sm" data-pg="prev" ${cur <= 1 ? 'disabled' : ''}>上一页</button>
    <span class="pager-info">第 ${cur} / ${pages} 页 · 共 ${p.total} 人</span>
    <button class="btn btn-sm" data-pg="next" ${cur >= pages ? 'disabled' : ''}>下一页</button>`;
  container.onclick = async (e) => {
    const btn = e.target.closest('button[data-pg]');
    if (!btn || btn.disabled) return;
    p.skip = btn.dataset.pg === 'prev'
      ? Math.max(0, p.skip - p.limit)
      : p.skip + p.limit;
    loadUsers();
  };
}

function renderToolbar(container, ready) {
  container.innerHTML = ready ? `
    <div class="u-toolbar">
      <input id="users-search" class="input" type="text" placeholder="搜索用户名 / 邮箱 / 手机号" value="${esc(ADMIN_USERS.page.q)}">
      <button class="btn btn-primary" id="users-search-btn">搜索</button>
      <span class="dim">共 ${ADMIN_USERS.page.total || 0} 人</span>
    </div>` : `
    <div class="u-keybar">
      <div class="u-keyhint">此接口需管理密钥 <code>X-Admin-Key</code>。
        首次访问请带上: <code>/admin/?adminKey=xxx#users</code><br>
        密钥值见服务端 <code>.env</code> 的 <code>ZZCC_ADMIN_API_KEY</code>。
        填入后会存入浏览器 sessionStorage, 本次会话内免传。</div>
      <div class="u-keyrow">
        <input id="users-key-input" class="input" type="password" placeholder="ZZCC_ADMIN_API_KEY">
        <button class="btn btn-primary" id="users-key-btn">连接</button>
      </div>`;
  if (ready) {
    const onSearch = () => {
      ADMIN_USERS.page.q = document.getElementById('users-search').value.trim();
      ADMIN_USERS.page.skip = 0;
      loadUsers();
    };
    container.querySelector('#users-search-btn').onclick = onSearch;
    container.querySelector('#users-search').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') onSearch();
    });
  } else {
    const btn = container.querySelector('#users-key-btn');
    const input = container.querySelector('#users-key-input');
    const submit = () => {
      const k = input.value.trim();
      if (!k) return;
      sessionStorage.setItem('zzcc_admin_key', k);
      renderUsersPage();
    };
    btn.onclick = submit;
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  }
}

function renderUsersPage() {
  const root = document.getElementById('content');
  const ready = !!adminKey();
  root.innerHTML = `
    <div id="users-toolbar"></div>
    <div id="user-notice" class="user-notice"></div>
    <div class="grid" id="users-stats"></div>
    <div id="users-body"></div>
    <div id="users-pager" class="u-pager"></div>`;
  renderToolbar(document.getElementById('users-toolbar'), ready);
  if (ready) loadUsers();
}

registerPage('users', {
  title: '用户管理',
  render: renderUsersPage,
  refresh: () => { if (adminKey()) loadUsers(); },
});