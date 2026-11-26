// SNN 类脑看板 — 高优先级模块
// KPI + 拓扑可视化（canvas）+ 决策趋势（ECharts）+ 决策历史表

// ECharts 从 static/echarts 加载（管理平台页面内联引用，避免依赖外网 CDN）
// 注意：ECharts 在 static/echarts/echarts.min.js，路径相对 /static/echarts/echarts.min.js

let snnState = null; // 最近一次 status+graph
let topologyCanvas = null;
let topoGraphCache = null; // 拓扑图数据缓存（供明细表渲染）

function loadECharts() {
  // ECharts 是全局变量，若未加载则动态引入
  if (typeof echarts !== 'undefined') return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = '/static/echarts/echarts.min.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('ECharts 加载失败'));
    document.head.appendChild(s);
  });
}

// ── 渲染入口 ──
async function renderSnnDashboard(container) {
  container.innerHTML = '<div class="loading">加载中...</div>';
  try {
    await loadECharts();
    const [status, graph, decisions] = await Promise.all([
      apiGet('/brain/snn/status'),
      apiGet('/brain/snn/graph'),
      apiGet('/brain/decisions', { limit: 30 }),
    ]);
    snnState = { status, graph, decisions };
    drawSnn(container, status, graph, decisions);
  } catch (e) {
    container.innerHTML = `<div class="error-box">加载失败：${e.message}</div>`;
  }
}

// ── 绘制主界面 ──
function drawSnn(container, status, graph, decisions) {
  const st = status.stats || {};
  const net = status.network || {};
  const decs = decisions.decisions || [];

  // 健康状态（status.health 是对象 {status, ...}）
  const healthObj = status.health || {};
  const health = healthObj.status || 'unknown';
  const healthTag = health === 'healthy' ? 'tag-green' :
    health === 'degraded' ? 'tag-yellow' : 'tag-red';
  const healthText = health === 'healthy' ? '健康' : health === 'degraded' ? '退化' : '未知';
  const noDecision = healthObj.consecutive_no_decision ?? '-';

  const penRatio = st.edges_penalized > 0 ?
    (st.edges_strengthened / st.edges_penalized).toFixed(2) : '∞';

  container.innerHTML = `
    <!-- KPI 行 -->
    <div class="grid">
      <div class="card">
        <div class="card-label">健康状态</div>
        <div class="card-value sm"><span class="tag ${healthTag}">${healthText}</span></div>
        <div class="card-sub">consecutive_no_decision: ${noDecision}</div>
      </div>
      <div class="card">
        <div class="card-label">神经元 / 边</div>
        <div class="card-value">${net.num_neurons ?? '-'}<span style="font-size:16px;color:var(--text-dim)"> / ${net.num_edges ?? '-'}</span></div>
        <div class="card-sub">活跃边: ${net.active_edges ?? '-'}</div>
      </div>
      <div class="card">
        <div class="card-label">训练计数</div>
        <div class="card-value ${(st.training_count || 0) > 20 ? 'yellow' : ''}">${st.training_count ?? '-'}</div>
        <div class="card-sub">护栏阈值 20</div>
      </div>
      <div class="card">
        <div class="card-label">加强/惩罚比</div>
        <div class="card-value ${parseFloat(penRatio) < 1.3 ? 'yellow' : 'green'}">${penRatio}</div>
        <div class="card-sub">强 ${st.edges_strengthened ?? 0} / 罚 ${st.edges_penalized ?? 0}</div>
      </div>
      <div class="card">
        <div class="card-label">推理调用</div>
        <div class="card-value">${st.reason_calls ?? '-'}</div>
        <div class="card-sub">命中 ${st.reason_hits ?? '-'}</div>
      </div>
      <div class="card">
        <div class="card-label">最近决策</div>
        <div class="card-value sm">${decisionTag(st.last_decision || '-')}</div>
        <div class="card-sub">conf ${st.last_confidence ?? '-'}</div>
      </div>
    </div>

    <!-- 发育状态面板（增殖→突触探索→自发分簇，用户 2026-11-26） -->
    <div class="panel">
      <div class="panel-title">
        <span>发育状态</span>
        <div style="display:flex;align-items:center;gap:10px">
          <span id="dev-stage" class="tag tag-purple">加载中</span>
          <button class="btn btn-sm" id="dev-tick-btn" onclick="runDevTick()">触发发育</button>
          <button class="btn btn-sm" onclick="refreshDevPanel()">刷新</button>
        </div>
      </div>
      <div class="panel-body" id="dev-panel-body">
        <div class="loading">发育状态加载中...</div>
      </div>
    </div>

    <!-- SNN 拓扑可视化 -->
    <div class="panel">
      <div class="panel-title">
        <span>SNN 网络拓扑</span>
        <div style="display:flex;align-items:center;gap:10px">
          <div class="legend">
            <span class="legend-item"><span class="legend-dot" style="background:#58a6ff"></span>输入</span>
            <span class="legend-item"><span class="legend-dot" style="background:#3fb950"></span>隐藏</span>
            <span class="legend-item"><span class="legend-dot" style="background:#f85149"></span>输出</span>
            <span class="legend-item"><span class="legend-dot" style="background:#bc8cff"></span>中继</span>
            <span class="legend-item"><span class="legend-dot" style="background:#d29922"></span>抑制</span>
          </div>
          <div class="legend" style="margin-left:8px">
            <span class="legend-item" style="color:#8b949e;font-size:11px">边步长:</span>
            <span class="legend-item"><span class="legend-dot" style="background:rgba(139,148,158,0.8)"></span>1(近/快)</span>
            <span class="legend-item"><span class="legend-dot" style="background:rgba(201,121,113,0.8)"></span>5</span>
            <span class="legend-item"><span class="legend-dot" style="background:rgba(248,100,80,0.8)"></span>8(远/慢)</span>
          </div>
          <a class="topo-link" href="#" onclick="toggleTopoTable('nodes');return false;">神经元表</a>
          <a class="topo-link" href="#" onclick="toggleTopoTable('edges');return false;">路径表</a>
        </div>
      </div>
      <div class="snn-canvas-wrap">
        <canvas id="snn-graph" width="1000" height="420"></canvas>
      </div>
      <details class="topo-details" id="topo-nodes" hidden>
        <summary>神经元明细（${graph.nodes.length}）</summary>
        <div class="topo-table-wrap">
          <table>
            <thead><tr><th>ID</th><th>类型</th><th>膜电位</th><th>放电次数</th><th>last_fire</th></tr></thead>
            <tbody id="topo-nodes-body"></tbody>
          </table>
        </div>
      </details>
      <details class="topo-details" id="topo-edges" hidden>
        <summary>路径明细（${graph.edges.length}）</summary>
        <div class="topo-table-wrap">
          <table>
            <thead><tr><th>源</th><th>目标</th><th>权重</th><th>步长</th></tr></thead>
            <tbody id="topo-edges-body"></tbody>
          </table>
        </div>
      </details>
    </div>

    <!-- 决策趋势 + 决策历史 -->
    <div class="panel">
      <div class="panel-title"><span>决策置信度趋势</span></div>
      <div class="panel-body"><div id="decision-chart" style="width:100%;height:220px"></div></div>
    </div>

    <div class="panel">
      <div class="panel-title"><span>最近决策</span></div>
      <div class="panel-body">
        <table>
          <thead><tr><th>时间</th><th>类型</th><th>决策</th><th>置信度</th><th>层级</th></tr></thead>
          <tbody>
            ${decs.map(d => `
              <tr>
                <td>${fmtTime(d.created_at)}</td>
                <td>${d.signal_type || '-'}</td>
                <td>${decisionTag(d.decision)}</td>
                <td>${d.confidence ?? '-'}</td>
                <td>L${d.reasoning_level ?? '-'}</td>
              </tr>`).join('') || '<tr><td colspan="5">暂无决策</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>
  `;

  // 绘制拓扑
  drawTopology(graph);
  // 绘制决策趋势
  drawDecisionChart(decs);

  // 首次加载后自动定位到拓扑面板（按钮/明细表可见）
  // scrollIntoView 比手动计算 scrollTo 更可靠（浏览器自行处理滚动容器）
  setTimeout(() => {
    const panel = document.querySelector('.snn-canvas-wrap');
    if (panel) {
      try {
        panel.scrollIntoView({ behavior: 'auto', block: 'start' });
        // 双保险：scrollIntoView 可能被 sticky topbar 遮住，手动再校正
        const rect = panel.getBoundingClientRect();
        if (rect.top < 60 && rect.top > -10) {
          window.scrollBy(0, rect.top - 80);
        }
      } catch (e) { /* 忽略 */ }
    }
    // URL ?open=nodes|edges 自动展开对应明细表（深链/调试入口）
    // 参数可能在 query（?open=）或 hash（#/snn?open=）中
    let openParam = new URLSearchParams(location.search).get('open');
    if (!openParam) {
      const hashQ = location.hash.indexOf('?');
      if (hashQ >= 0) {
        openParam = new URLSearchParams(location.hash.slice(hashQ + 1)).get('open');
      }
    }
    if (openParam === 'nodes' || openParam === 'edges') {
      toggleTopoTable(openParam);
    }
  }, 350);
}

// ── 拓扑可视化（canvas 手绘） ──
function drawTopology(graph) {
  const canvas = document.getElementById('snn-graph');
  if (!canvas) return;
  topoGraphCache = graph;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;

  const nodes = graph.nodes || [];
  const edges = graph.edges || [];

  // 布局：步长驱动的力导向（边距离反映传播步长）
  const layout = layoutNodesByStep(nodes, edges, W, H);

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, W, H);

  // 画边：步长决定颜色+粗细（step 大→传播慢→橙红粗线, step 小→蓝青细线）
  const edgeCount = Math.min(edges.length, 800); // 防卡顿
  for (let i = 0; i < edgeCount; i++) {
    const e = edges[i];
    const a = layout[e.source];
    const b = layout[e.target];
    if (!a || !b) continue;
    const w = e.weight || 0.5;
    const step = e.step ?? e.delay ?? 1;
    const alpha = Math.min(0.45, 0.08 + w * 0.1);
    // 步长着色: step=1 蓝青, step 增大向橙红渐变(传播延迟直观化)
    const stepT = Math.min(1, (step - 1) / 7); // 1→8 归一化
    const r = Math.round(139 + stepT * (248 - 139));   // 139→248
    const g = Math.round(148 - stepT * (148 - 100));   // 148→100
    const b2 = Math.round(158 - stepT * (158 - 80));   // 158→80
    ctx.strokeStyle = `rgba(${r}, ${g}, ${b2}, ${alpha})`;
    ctx.lineWidth = 0.6 + stepT * 1.4;  // 步长越大线越粗
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }
  ctx.lineWidth = 0.6; // 恢复默认

  // 画节点
  const typeColor = {
    input: '#58a6ff',
    hidden: '#3fb950',
    output: '#f85149',
    relay: '#bc8cff',
    inhibitory: '#d29922',
  };

  for (const n of nodes) {
    const pos = layout[n.id];
    if (!pos) continue;
    const type = n.neuron_type || n.type || 'hidden';
    const color = typeColor[type] || '#8b949e';
    const r = type === 'output' ? 8 : type === 'input' ? 6 : 5;

    // 节点圈
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.85;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = '#0d1117';
    ctx.lineWidth = 1;
    ctx.stroke();

    // 活跃节点高亮
    if (n.fire_count > 0) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r + 3, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // 输出层标签
    if (type === 'output') {
      ctx.fillStyle = '#e6edf3';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(String(n.id), pos.x, pos.y + 18);
    }
  }
}

// ── 拓扑明细表（神经元/路径） ──
function toggleTopoTable(kind) {
  const details = document.getElementById(kind === 'nodes' ? 'topo-nodes' : 'topo-edges');
  if (!details) return;
  // 切换：用原生 open 属性（<details> 展开由 open 控制，hidden 只控显示）
  const willOpen = !details.open;
  if (willOpen && topoGraphCache) {
    if (kind === 'nodes') {
      const body = document.getElementById('topo-nodes-body');
      if (body && !body.childElementCount) {
        body.innerHTML = topoGraphCache.nodes.map(n => `
          <tr>
            <td>${n.id}</td>
            <td>${(n.neuron_type || n.type || '-')}</td>
            <td>${(n.membrane ?? '-')}</td>
            <td>${(n.fire_count ?? 0)}</td>
            <td>${(n.last_fire_time ?? '-')}</td>
          </tr>`).join('') || '<tr><td colspan="5">无数据</td></tr>';
      }
    } else {
      const body = document.getElementById('topo-edges-body');
      if (body && !body.childElementCount) {
        body.innerHTML = topoGraphCache.edges.map(e => `
          <tr>
            <td>${e.source}</td>
            <td>${e.target}</td>
            <td>${e.weight}</td>
            <td>${e.step ?? e.delay ?? '-'}</td>
          </tr>`).join('') || '<tr><td colspan="4">无数据</td></tr>';
      }
    }
  }
  details.open = willOpen;
  // hidden 属性会强制 display:none，与 open 独立——必须同步移除/设置
  // 否则 <details hidden> 即使 open=true 仍不可见
  if (willOpen) {
    details.removeAttribute('hidden');
  } else {
    details.setAttribute('hidden', '');
  }
}

// 按类型分层布局
function layoutNodes(nodes, W, H) {
  const layout = {};
  const groups = { input: [], hidden: [], output: [], relay: [], inhibitory: [] };
  for (const n of nodes) {
    const type = n.neuron_type || n.type || 'hidden';
    const key = groups[type] ? type : 'hidden';
    groups[key].push(n);
  }
  const zones = {
    input: { x: 60, y: 40, h: H - 80 },
    hidden: { x: 300, y: 40, h: H - 80 },
    output: { x: W - 70, y: 40, h: H - 80 },
    relay: { x: 180, y: 10, h: 60 },
    inhibitory: { x: 600, y: H - 50, h: 40 },
  };
  for (const [type, arr] of Object.entries(groups)) {
    if (!arr.length) continue;
    const z = zones[type] || zones.hidden;
    arr.forEach((n, i) => {
      layout[n.id] = {
        x: z.x + (type === 'relay' ? (i % 2) * 40 : 0),
        y: z.y + (arr.length === 1 ? z.h / 2 : (i * z.h) / (arr.length - 1 || 1)),
      };
    });
  }
  return layout;
}

// ── 步长驱动的力导向布局 ──────────────────────────────
// 神经元间距离反映传播步长(step): 步长大→自然距离远(传播慢), 步长小→近。
// 力导向: 弹簧力拉向理想长度(base + step*scale), 库仑排斥推开节点。
// 初始位置用类型分区(layoutNodes), 迭代收敛后保留大体结构。
function layoutNodesByStep(nodes, edges, W, H) {
  // 初始位置: 类型分区(输入左/隐藏中/输出右/中继上下)
  const pos = layoutNodes(nodes, W, H);
  const ids = nodes.map(n => n.id);
  const idx = {};
  ids.forEach((id, i) => idx[id] = i);

  // 边列表(带 step): 只取有效边
  const es = [];
  for (const e of edges) {
    const a = pos[e.source], b = pos[e.target];
    if (!a || !b) continue;
    const step = e.step ?? e.delay ?? 1;
    es.push({ s: e.source, t: e.target, step });
  }

  // 力导向参数
  const BASE = 40;          // 步长=1 时的基准距离
  const STEP_SCALE = 18;    // 每步长增加的像素
  const REPULSION = 1200;   // 库仑排斥强度
  const ITERS = 80;         // 迭代次数

  // 迭代: 弹簧 + 排斥
  for (let iter = 0; iter < ITERS; iter++) {
    const forces = {};
    for (const id of ids) forces[id] = { x: 0, y: 0 };

    // 弹簧力(拉向理想长度)
    for (const e of es) {
      const a = pos[e.s], b = pos[e.t];
      const dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.max(1, Math.hypot(dx, dy));
      const ideal = BASE + e.step * STEP_SCALE;
      const force = (dist - ideal) * 0.02;  // 弹簧常数
      const fx = (dx / dist) * force, fy = (dy / dist) * force;
      forces[e.s].x += fx; forces[e.s].y += fy;
      forces[e.t].x -= fx; forces[e.t].y -= fy;
    }

    // 库仑排斥(节点间)
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = pos[ids[i]], b = pos[ids[j]];
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.max(1, Math.hypot(dx, dy));
        const f = REPULSION / (dist * dist);
        const fx = (dx / dist) * f, fy = (dy / dist) * f;
        forces[ids[i]].x -= fx; forces[ids[i]].y -= fy;
        forces[ids[j]].x += fx; forces[ids[j]].y += fy;
      }
    }

    // 应用力(带阻尼, 限制单步位移防震荡)
    const MAX_STEP = 8;
    for (const id of ids) {
      const f = forces[id];
      const mag = Math.hypot(f.x, f.y);
      if (mag < 0.01) continue;
      const scale = Math.min(MAX_STEP / mag, 0.5);
      pos[id].x += f.x * scale;
      pos[id].y += f.y * scale;
      // 边界约束
      pos[id].x = Math.max(20, Math.min(W - 20, pos[id].x));
      pos[id].y = Math.max(20, Math.min(H - 20, pos[id].y));
    }
  }
  return pos;
}

// ── 决策趋势图（ECharts） ──
function drawDecisionChart(decs) {
  const el = document.getElementById('decision-chart');
  if (!el || !window.echarts) return;
  const chart = echarts.init(el);
  const sorted = [...decs].reverse().slice(0, 20);
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    tooltip: { trigger: 'axis', backgroundColor: '#1c2128', borderColor: '#30363d', textStyle: { color: '#e6edf3' } },
    xAxis: {
      type: 'category',
      data: sorted.map(d => (d.created_at ? d.created_at.slice(5, 16) : '')),
      axisLine: { lineStyle: { color: '#30363d' } },
      axisLabel: { color: '#8b949e', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      max: 1,
      axisLine: { lineStyle: { color: '#30363d' } },
      splitLine: { lineStyle: { color: '#21262d' } },
      axisLabel: { color: '#8b949e', fontSize: 10 },
    },
    series: [{
      type: 'line',
      data: sorted.map(d => d.confidence || 0),
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color: '#58a6ff', width: 2 },
      itemStyle: { color: '#58a6ff' },
      areaStyle: { color: 'rgba(88, 166, 255, 0.1)' },
    }],
  });
}

// ── 发育面板（增殖→突触探索→自发分簇）──
async function refreshDevPanel() {
  const body = document.getElementById('dev-panel-body');
  const stageEl = document.getElementById('dev-stage');
  if (!body) return;
  body.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const dev = await apiGet('/brain/dev/status');
    const stageMap = { embryo: '胚胎', proliferating: '增殖', exploring: '探索', differentiated: '分化' };
    if (stageEl) {
      stageEl.textContent = stageMap[dev.stage] || dev.stage;
    }
    const clusters = (dev.clusters || []).map(c => c.length);
    body.innerHTML = `
      <div class="grid" style="margin-bottom:8px">
        <div class="card"><div class="card-label">发育阶段</div><div class="card-value sm">${stageMap[dev.stage] || dev.stage}</div></div>
        <div class="card"><div class="card-label">动态区神经元</div><div class="card-value">${dev.dev_neurons ?? '-'}</div></div>
        <div class="card"><div class="card-label">骨架边</div><div class="card-value ${(dev.dev_edges||0) > 0 ? 'green' : 'yellow'}">${dev.dev_edges ?? 0}</div></div>
        <div class="card"><div class="card-label">自发分簇</div><div class="card-value">${clusters.length || '-'}</div></div>
        <div class="card"><div class="card-label">探索累计</div><div class="card-value">${dev.explored_edges ?? 0}</div></div>
        <div class="card"><div class="card-label">修剪累计</div><div class="card-value">${dev.pruned_edges ?? 0}</div></div>
      </div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:6px">
        增殖 ${dev.proliferated ?? 0} 神经元 · 分簇大小: ${clusters.length ? clusters.join(', ') : '未分簇'}
      </div>
      ${(dev.dev_edges||0) > 0
        ? '<div style="font-size:12px;color:var(--green)">✅ 骨架已形成：动态区内部边 > 0（增殖分化的网络骨架）</div>'
        : '<div style="font-size:12px;color:var(--yellow)">⚠️ 骨架未形成：动态区内部边 = 0（增殖了但没探索连接）</div>'}
    `;
  } catch (e) {
    body.innerHTML = `<div class="error-box">发育状态加载失败：${e.message}</div>`;
  }
}

async function runDevTick() {
  const btn = document.getElementById('dev-tick-btn');
  const body = document.getElementById('dev-panel-body');
  if (btn) { btn.disabled = true; btn.textContent = '发育中...'; }
  try {
    await apiPost('/brain/dev/tick', {});
    await refreshDevPanel();
  } catch (e) {
    if (body) body.innerHTML = `<div class="error-box">发育触发失败：${e.message}</div>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '触发发育'; }
  }
}

// 注册页面
registerPage('snn', {
  title: 'SNN 类脑看板',
  render: renderSnnDashboard,
});
