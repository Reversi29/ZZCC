// 知识图谱 — 交互式力导向可视化
// 数据源: GET /api/v1/brain/graph  { nodes:[{id,label,category,symbolSize,tags,props}], links:[{source,target,...}] }
//
// 设计要点:
// - 力导向布局(弹簧+库仑排斥), 与 snn_dashboard 一致的实现范式
// - 缩放(滚轮)/平移(拖拽)/hover 高亮邻居 + tooltip
// - 300 节点量级在单 canvas 下 60fps 可渲染

const GRAPH_CAT_COLORS = [
  '#58a6ff', // 0 信号/输入类
  '#3fb950', // 1 决策/输出类
  '#f85149', // 2
  '#bc8cff', // 3
  '#d29922', // 4
  '#39c5cf', // 5
];

let _graphState = null; // 当前可视化状态(供 resize 重绘)
let _graphAnimId = null;

registerPage('graph', {
  title: '知识图谱',
  render: renderGraphPage,
});

async function renderGraphPage(container) {
  container.innerHTML = '<div class="loading">加载图谱数据...</div>';
  try {
    const data = await apiGet('/brain/graph');
    const payload = data.data || data;
    const nodes = payload.nodes || [];
    let rawLinks = payload.links || payload.edges || [];
    const cats = payload.categories || [];

    // 悬空边过滤: 生产 /brain/graph 的 300 条 links 中仅 150 条两端都是真实节点,
    // 另 150 条端点引用了不在 nodes 里的 id(后端数据质量遗留)。
    // 不过滤会导致布局/度统计/KPI 全部失真。
    const nodeIds = new Set(nodes.map(n => n.id));
    const links = rawLinks.filter(l =>
      nodeIds.has(l.source) && nodeIds.has(l.target));
    const dangling = rawLinks.length - links.length;

    if (!nodes.length) {
      container.innerHTML = `
        <div class="placeholder"><div class="ph-icon">🕸️</div>
        <div class="ph-title">图谱为空</div>
        <div>暂无 brain_semantic 节点数据</div></div>`;
      return;
    }

    // KPI
    const catCount = new Set(nodes.map(n => n.category)).size;
    const degreeMap = {};
    links.forEach(l => {
      degreeMap[l.source] = (degreeMap[l.source] || 0) + 1;
      degreeMap[l.target] = (degreeMap[l.target] || 0) + 1;
    });
    // 拓扑类型(决定布局策略, 也影响 KPI 语义)
    const topology = detectTopology(nodes, links);

    // KPI 4: 按拓扑语义给出有意义的指标
    // 星形/二部图(生产现状): "最高连接度"恒为 1, 无信息量 → 改为"配对数"
    // 普通图: 保留枢纽节点度
    let hubText, hubSub;
    if (topology === 'star') {
      // 生产实际: 150 signal × 150 decision, 每 signal 连 2 decision, 共 300 边。
      // 配对数 = 去重后的 source 节点数(二部图一侧); 之前误用 links.length=300
      // (那只是边数, 不等于对数); "跨节点"也误用 srcSet+tgtSet 相加(600),
      // 实际 srcSet/tgtSet 是不同节点集, 并集才是节点总数。
      const srcSet = new Set(links.map(l => l.source));
      const tgtSet = new Set(links.map(l => l.target));
      hubText = srcSet.size;
      hubSub = `${srcSet.size} signal ↔ ${tgtSet.size} decision · 星形${dangling ? ` · 已滤 ${dangling} 悬空边` : ''}`;
    } else {
      let topNode = { label: '-', deg: 0 };
      nodes.forEach(n => {
        const d = degreeMap[n.id] || 0;
        if (d > topNode.deg) topNode = { label: n.label || n.id, deg: d };
      });
      hubText = topNode.label;
      hubSub = `${topNode.deg} 条边`;
    }

    container.innerHTML = `
      <div class="grid">
        <div class="card"><div class="card-label">图节点</div>
          <div class="card-value accent">${nodes.length}</div>
          <div class="card-sub">brain_semantic</div></div>
        <div class="card"><div class="card-label">图边</div>
          <div class="card-value accent">${links.length}</div>
          <div class="card-sub">RELATES_TO${dangling ? ` (已滤 ${dangling} 悬空)` : ''}</div></div>
        <div class="card"><div class="card-label">分类</div>
          <div class="card-value sm">${catCount}</div>
          <div class="card-sub">类别数</div></div>
        <div class="card"><div class="card-label">${topology === 'star' ? '配对数' : '最高连接度'}</div>
          <div class="card-value sm">${hubText}</div>
          <div class="card-sub">${hubSub}</div></div>
      </div>

      <div class="panel">
        <div class="panel-title">
          <span>知识图谱可视化</span>
          <span class="tag tag-blue">${topology === 'star' ? '分层布局' : '力导向布局'}</span>
        </div>
        <div class="panel-body">
          <div class="graph-toolbar">
            <button class="btn" id="graph-zoom-in">＋ 放大</button>
            <button class="btn" id="graph-zoom-out">－ 缩小</button>
            <button class="btn" id="graph-fit">⤢ 适应画布</button>
            <span class="graph-hint">滚轮缩放 · 拖拽平移 · 悬停查看节点详情</span>
          </div>
          <div class="graph-canvas-wrap">
            <canvas id="graph-canvas" width="1080" height="520"></canvas>
            <div id="graph-tooltip" class="graph-tooltip" style="display:none"></div>
          </div>
          <div class="graph-legend" id="graph-legend"></div>
        </div>
      </div>
    `;

    // 图例
    const legendEl = document.getElementById('graph-legend');
    const catLabels = cats.map(c => c.label || c).filter(Boolean);
    legendEl.innerHTML = [...new Set(nodes.map(n => n.category))].map(c => {
      const lbl = catLabels[c] || `类别 ${c}`;
      return `<span class="legend-item"><span class="legend-dot" style="background:${GRAPH_CAT_COLORS[c % GRAPH_CAT_COLORS.length]}"></span>${lbl}</span>`;
    }).join('');

    initGraphCanvas(nodes, links);
  } catch (e) {
    container.innerHTML = `<div class="error-box">加载失败：${e.message}</div>`;
  }
}

// ── 力导向布局 ──
function computeGraphLayout(nodes, links, W, H, iterations) {
  const pos = {};
  nodes.forEach((n, i) => {
    // 初始位置按分类分区, 收敛后结构更清晰
    const cx = W / 2 + (Math.cos(i * 2.4) * (120 + (n.category || 0) * 60));
    const cy = H / 2 + (Math.sin(i * 2.4) * (100 + (n.category || 0) * 40));
    pos[n.id] = { x: cx, y: cy, vx: 0, vy: 0 };
  });

  const REPULSE = 2600;      // 库仑排斥常数
  const SPRING_LEN = 90;     // 理想边长
  const SPRING_K = 0.035;    // 弹簧常数
  const CENTER_K = 0.002;    // 向心力(防飘出画布) —— 星形图必须低, 见 detectTopology
  const DAMPING = 0.85;

  const iters = iterations || 300;
  for (let it = 0; it < iters; it++) {
    // 库仑排斥(全部节点对)
    for (let a = 0; a < nodes.length; a++) {
      for (let b = a + 1; b < nodes.length; b++) {
        const pa = pos[nodes[a].id], pb = pos[nodes[b].id];
        let dx = pa.x - pb.x, dy = pa.y - pb.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 0.01) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 0.25; }
        const d = Math.sqrt(d2);
        const f = REPULSE / d2;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        pa.vx += fx; pa.vy += fy;
        pb.vx -= fx; pb.vy -= fy;
      }
    }
    // 弹簧引力(边)
    links.forEach(l => {
      const pa = pos[l.source], pb = pos[l.target];
      if (!pa || !pb) return;
      const dx = pb.x - pa.x, dy = pb.y - pa.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = SPRING_K * (d - SPRING_LEN);
      const fx = (dx / d) * f, fy = (dy / d) * f;
      pa.vx += fx; pa.vy += fy;
      pb.vx -= fx; pb.vy -= fy;
    });
    // 向心力 + 积分 + 阻尼
    nodes.forEach(n => {
      const p = pos[n.id];
      p.vx += (W / 2 - p.x) * CENTER_K;
      p.vy += (H / 2 - p.y) * CENTER_K;
      p.x += p.vx * DAMPING;
      p.y += p.vy * DAMPING;
      p.vx *= (1 - DAMPING * 0.6);
      p.vy *= (1 - DAMPING * 0.6);
    });
  }
  return pos;
}

// ── 拓扑检测 ──
// 生产 brain_semantic 图是 150 对 (signal → decision) 的星形结构: 无簇、无枢纽、
// 所有节点度=1(实测 300 边 600 度总和, deg 唯一值=[1])。这种图用力导向会把
// 所有孤立对拉到中心造成过密, 必须走分层布局。判据: 所有节点度 ≤ 1。
function detectTopology(nodes, links) {
  const deg = {};
  nodes.forEach(n => { deg[n.id] = 0; });
  links.forEach(l => {
    if (deg[l.source] !== undefined) deg[l.source]++;
    if (deg[l.target] !== undefined) deg[l.target]++;
  });
  let maxDeg = 0, hubCount = 0;
  nodes.forEach(n => {
    const d = deg[n.id] || 0;
    if (d > maxDeg) maxDeg = d;
    if (d >= 3) hubCount++;
  });
  // 星形: 无枢纽(度全 ≤1) → 分层布局可读性远高于力导向
  if (maxDeg <= 1 && nodes.length >= 2) return 'star';
  // 普通图: 有枢纽节点, 力导向能把结构簇表达出来
  return 'force';
}

// 分层布局每行的像素高度 —— 布局函数与画布高度计算共用同一常量,
// 避免两处各自定义行高导致高度与布局不自洽。
const LAYER_ROW_PX = 48; // 每行 46px + 2px 行间距

// 分层布局: 每行横向铺排 COL_COLUMNS 对(signal 左半 / decision 右半), 行间纵向堆叠。
// 150 对 ÷ 10 = 15 行 → 高度仅 ~700px, 边是短水平线不交叉。
// 单列布局需 150 行×26px=3900px 高, 即使容器滚动也让用户翻很久。
const COL_COLUMNS = 10;

// 二部图两侧节点 —— 布局函数与画布高度计算共用
function bipartiteSides(nodes, links) {
  const isSource = {}, isTarget = {};
  links.forEach(l => { isSource[l.source] = true; isTarget[l.target] = true; });
  const left = nodes.filter(n => isSource[n.id] && !isTarget[n.id]);
  const right = nodes.filter(n => isTarget[n.id] && !isSource[n.id]);
  const center = nodes.filter(n => !isSource[n.id] && !isTarget[n.id]);
  return { left, right, center };
}
function rowCount(nodes, links) {
  const { left, right } = bipartiteSides(nodes, links);
  return Math.max(1, Math.ceil(Math.max(left.length, right.length) / COL_COLUMNS));
}

// ── 分层布局(星形/二部图)──
// 配对列布局: 每列放 1 对(signal 上 / decision 下), 列内短垂直边连接,
// COL_COLUMNS 列横向铺排, 行间纵向堆叠。150 对 ÷ 10 列 = 15 行 → 高 ~760px。
//
// 为什么不用"signal 左半 / decision 右半各自铺 COL_COLUMNS 槽":
// 那样两个半区各自从起点铺满, x 会叠加溢出画布(实测 x 到 1376 > 1080)。
// 配对列让每列宽度 = 列距, 不存在叠加。
function computeLayeredLayout(nodes, links, W, H) {
  const pos = {};
  const { left, right, center } = bipartiteSides(nodes, links);
  const rows = rowCount(nodes, links);
  const rowH = (H - 40) / rows;
  const colStep = (W * 0.9) / COL_COLUMNS;
  const x0 = (W - colStep * COL_COLUMNS) / 2;

  function placePair(i, sig, dec) {
    const col = i % COL_COLUMNS, row = Math.floor(i / COL_COLUMNS);
    const x = x0 + col * colStep;
    const y = 20 + row * rowH;
    if (sig) pos[sig.id] = { x, y: y + rowH * 0.22, vx: 0, vy: 0 };
    if (dec) pos[dec.id] = { x, y: y + rowH * 0.78, vx: 0, vy: 0 };
  }

  // 配对对应: 第 i 个 left 与第 i 个 right 同列(两侧不等长时单独续排)
  const L = Math.min(left.length, right.length);
  for (let i = 0; i < L; i++) placePair(i, left[i], right[i]);
  for (let i = L; i < left.length; i++) placePair(i, left[i], null);
  for (let i = L; i < right.length; i++) placePair(i, null, right[i]);

  // 孤立节点居中排一列
  center.forEach((node, i) => {
    pos[node.id] = { x: W / 2, y: 20 + i * 24, vx: 0, vy: 0 };
  });
  return pos;
}

// ── 画布初始化 + 交互 ──
function initGraphCanvas(nodes, links) {
  const canvas = document.getElementById('graph-canvas');
  const tooltip = document.getElementById('graph-tooltip');
  if (!canvas) return;

  let W = canvas.width;
  let H = canvas.height;  // let: 星形布局会按节点数自适应增高, 需重新赋值
  // 布局策略: 星形/二部图用分层布局(力导向会把所有孤立对挤到中心),
  // 有簇/有枢纽的普通图才用全力导向。
  const topology = detectTopology(nodes, links);

  // 星形布局需要每行足够间距才可读。带宽固定, 高度由带数决定;
  // 超出可视区由容器垂直滚动(避免 fitView 缩放把线宽放大到不可读)。
  // 行数/行高与布局函数共用 rowCount / LAYER_ROW_PX, 不在此重复定义。
  const rows = rowCount(nodes, links);
  canvas.height = topology === 'star'
    ? Math.max(520, Math.min(2400, rows * LAYER_ROW_PX + 80))
    : H;
  H = canvas.height;          // 同步给 draw/fitView/hitTest 使用
  const layoutH = canvas.height;
  // canvas 以 1:1 CSS 尺寸显示(不让 width:100% 压缩), 让 offsetX 与 canvas 坐标
  // 严格一致; 超出容器由 .graph-canvas-wrap 双向滚动。
  canvas.style.width = W + 'px';

  // 用自适应后的画布高度重算分层布局
  const pos = (topology === 'star')
    ? computeLayeredLayout(nodes, links, W, layoutH)
    : computeGraphLayout(nodes, links, W, H, 300);

  // 邻接表(hover 高亮用)
  const neighbors = {};
  nodes.forEach(n => { neighbors[n.id] = new Set([n.id]); });
  links.forEach(l => {
    if (neighbors[l.source]) neighbors[l.source].add(l.target);
    if (neighbors[l.target]) neighbors[l.target].add(l.source);
  });
  const deg = {};
  links.forEach(l => {
    deg[l.source] = (deg[l.source] || 0) + 1;
    deg[l.target] = (deg[l.target] || 0) + 1;
  });

  const view = { x: 0, y: 0, k: 1 };   // 视图变换: 世界坐标 → 屏幕坐标
  let hoverId = null;
  let dragging = false, dragMoved = false, lastX = 0, lastY = 0;

  function screenToWorld(sx, sy) {
    return { x: (sx - view.x) / view.k, y: (sy - view.y) / view.k };
  }

  function draw() {
    const ctx = canvas.getContext('2d');
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, W, H);
    ctx.setTransform(view.k, 0, 0, view.k, view.x, view.y);

    const hovSet = hoverId ? neighbors[hoverId] : null;

    // 边
    links.forEach(l => {
      const a = pos[l.source], b = pos[l.target];
      if (!a || !b) return;
      const hl = hovSet && hovSet.has(l.source) && hovSet.has(l.target);
      ctx.strokeStyle = hovSet
        ? (hl ? 'rgba(255,190,80,0.85)' : 'rgba(139,148,158,0.10)')
        : 'rgba(139,148,158,0.32)';
      ctx.lineWidth = (hl ? 1.6 : 0.7) / view.k;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    });

    // 节点(度越大半径越大)
    nodes.forEach(n => {
      const p = pos[n.id];
      if (!p) return;
      const d = deg[n.id] || 0;
      const r = (2.5 + Math.min(9, Math.sqrt(d) * 2.2)) / view.k;
      const color = GRAPH_CAT_COLORS[(n.category || 0) % GRAPH_CAT_COLORS.length];
      const dim = hovSet && !hovSet.has(n.id);
      ctx.globalAlpha = dim ? 0.22 : 0.92;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      if (n.id === hoverId) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = '#f0f6fc';
        ctx.lineWidth = 1.8 / view.k;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    });

    // 高亮节点标签
    if (hoverId && pos[hoverId]) {
      const n = nodes.find(x => x.id === hoverId);
      const p = pos[hoverId];
      const label = (n && (n.label || n.id)) || hoverId;
      ctx.font = `${11 / view.k}px -apple-system, sans-serif`;
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = 'rgba(13,17,23,0.9)';
      ctx.fillRect(p.x + r_of(hoverId) + 4, p.y - 8 / view.k, tw + 8, 16 / view.k);
      ctx.fillStyle = '#f0f6fc';
      ctx.fillText(label, p.x + r_of(hoverId) + 8, p.y + 4 / view.k);
    }

    function r_of(id) {
      const d = deg[id] || 0;
      return (2.5 + Math.min(9, Math.sqrt(d) * 2.2)) / view.k;
    }
  }

  function hitTest(sx, sy) {
    const { x, y } = screenToWorld(sx, sy);
    let best = null, bestD = Infinity;
    nodes.forEach(n => {
      const p = pos[n.id];
      if (!p) return;
      const d = deg[n.id] || 0;
      // 与 draw 的屏幕半径(base/view.k)保持同一几何基准: draw 在世界坐标系里
      // 把半径除以 view.k, 使屏幕像素半径恒定; hitTest 比较的是世界坐标距离,
      // 故这里同样要除以 view.k。漏掉这一步时 view.k=1 碰巧匹配, 但 fitView
      // 缩放后(本图 2400px 高需缩到 ~0.22)命中半径被放大 ~4.5 倍, hover 全失效。
      const r = (2.5 + Math.min(9, Math.sqrt(d) * 2.2) + 3) / view.k;
      const dist = (p.x - x) ** 2 + (p.y - y) ** 2;
      if (dist < r * r && dist < bestD) { bestD = dist; best = n.id; }
    });
    return best;
  }

  function showTooltip(nid, sx, sy) {
    const n = nodes.find(x => x.id === nid);
    if (!n) return hideTooltip();
    const d = deg[nid] || 0;
    const catLbl = (n.category || 0);
    const props = n.props && Object.keys(n.props).length
      ? Object.entries(n.props).map(([k, v]) => `<div class="tt-row"><span>${k}</span><b>${v}</b></div>`).join('')
      : '';
    const tags = (n.tags || []).length
      ? n.tags.map(t => `<span class="tag tag-blue">${t}</span>`).join(' ') : '';
    tooltip.innerHTML = `
      <div class="tt-title">${n.label || n.id}</div>
      <div class="tt-row"><span>分类</span><b>${catLbl}</b></div>
      <div class="tt-row"><span>连接度</span><b>${d}</b></div>
      ${tags ? `<div class="tt-tags">${tags}</div>` : ''}
      ${props}
      <div class="tt-id">${nid}</div>
    `;
    tooltip.style.display = 'block';
    const wrap = canvas.parentElement.getBoundingClientRect();
    tooltip.style.left = (sx - wrap.left + 14) + 'px';
    tooltip.style.top = (sy - wrap.top + 10) + 'px';
  }
  function hideTooltip() { if (tooltip) tooltip.style.display = 'none'; }

  function zoomAt(factor, sx, sy) {
    const { x, y } = screenToWorld(sx, sy);
    view.k = Math.max(0.25, Math.min(6, view.k * factor));
    view.x = sx - x * view.k;
    view.y = sy - y * view.k;
    draw();
  }

  function fitView() {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(n => {
      const p = pos[n.id];
      if (!p) return;
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
    });
    const pad = 50;
    const k = Math.min((W - pad * 2) / (maxX - minX), (H - pad * 2) / (maxY - minY));
    view.k = Math.max(0.25, Math.min(6, k));
    view.x = (W - (maxX - minX) * view.k) / 2 - minX * view.k;
    view.y = (H - (maxY - minY) * view.k) / 2 - minY * view.k;
    draw();
  }

  canvas.addEventListener('mousedown', e => {
    dragging = true; dragMoved = false;
    lastX = e.offsetX; lastY = e.offsetY;
  });
  canvas.addEventListener('mousemove', e => {
    if (dragging) {
      const dx = e.offsetX - lastX, dy = e.offsetY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) dragMoved = true;
      view.x += dx; view.y += dy;
      lastX = e.offsetX; lastY = e.offsetY;
      draw();
      hideTooltip();
      return;
    }
    const nid = hitTest(e.offsetX, e.offsetY);
    hoverId = nid;
    canvas.style.cursor = nid ? 'pointer' : 'grab';
    draw();
    if (nid) showTooltip(nid, e.offsetX, e.offsetY);
    else hideTooltip();
  });
  window.addEventListener('mouseup', () => { dragging = false; });
  canvas.addEventListener('mouseleave', () => {
    hoverId = null; hideTooltip(); draw();
  });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    zoomAt(e.deltaY < 0 ? 1.12 : 0.89, e.offsetX, e.offsetY);
  }, { passive: false });

  // 工具栏按钮
  const zi = document.getElementById('graph-zoom-in');
  const zo = document.getElementById('graph-zoom-out');
  const ff = document.getElementById('graph-fit');
  if (zi) zi.addEventListener('click', () => zoomAt(1.2, W / 2, H / 2));
  if (zo) zo.addEventListener('click', () => zoomAt(0.83, W / 2, H / 2));
  if (ff) ff.addEventListener('click', fitView);

  // 初始适应视图
  fitView();
    // 注: 早期版本曾对星形布局跳过 fitView(直接 view.k=1), 但分层布局的行 y
    // 可达 3960px, 不缩放会被裁在画布顶部之外。fitView 会把 k 解算到 ~1.0,
    // 高度自适应由 canvas.height 在布局前就设置好。

  _graphState = { draw, fitView };
}