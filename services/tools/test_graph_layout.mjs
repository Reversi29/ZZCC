// 力导向布局纯函数单测 —— 不依赖 DOM
// 从 graph_page.js 提取 computeGraphLayout（纯计算部分），在 Node 中验证

const W = 1080, H = 520;
const REPULSE = 2600, SPRING_LEN = 90, SPRING_K = 0.035, CENTER_K = 0.004, DAMPING = 0.85;

function computeGraphLayout(nodes, links, W, H, iterations) {
  const pos = {};
  nodes.forEach((n, i) => {
    const cx = W / 2 + (Math.cos(i * 2.4) * (120 + (n.category || 0) * 60));
    const cy = H / 2 + (Math.sin(i * 2.4) * (100 + (n.category || 0) * 40));
    pos[n.id] = { x: cx, y: cy, vx: 0, vy: 0 };
  });
  const iters = iterations || 300;
  for (let it = 0; it < iters; it++) {
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

// ── 构造测试数据 ──
function makeData(nNodes, edgeRate, seed) {
  let s = seed || 42;
  const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return (s & 0xffff) / 0xffff; };
  const nodes = Array.from({ length: nNodes }, (_, i) => ({
    id: `n${i}`, category: i % 3, label: `node_${i}`,
  }));
  // 每个节点至少一条边(连通性), 剩余按 edgeRate 随机加
  const links = [];
  const seen = new Set();
  for (let i = 0; i < nNodes; i++) {
    const t = (i + 1 + Math.floor(rnd() * 3)) % nNodes;
    const k = [i, t].sort().join('>');
    if (!seen.has(k) && i !== t) { links.push({ source: `n${i}`, target: `n${t}` }); seen.add(k); }
  }
  while (links.length < nNodes * edgeRate) {
    const a = Math.floor(rnd() * nNodes), b = Math.floor(rnd() * nNodes);
    if (a === b) continue;
    const k = [a, b].sort().join('>');
    if (seen.has(k)) continue;
    seen.add(k); links.push({ source: `n${a}`, target: `n${b}` });
  }
  return { nodes, links };
}

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ✗ ${name}${detail ? ' → ' + detail : ''}`); }
}

// 1) 生产规模(300 节点/300 边)可计算且位置有限
console.log('\n[1] 生产规模 300 节点');
{
  const { nodes, links } = makeData(300, 1.0, 42);
  const t0 = Date.now();
  const pos = computeGraphLayout(nodes, links, W, H, 300);
  const ms = Date.now() - t0;
  check('所有节点有位置', nodes.every(n => pos[n.id] && Number.isFinite(pos[n.id].x) && Number.isFinite(pos[n.id].y)));
  check('布局耗时 < 3s', ms < 3000, `实际 ${ms}ms`);
  // 2) 边端点距离应比"随机初始"更接近 SPRING_LEN
  const dists = links.map(l => {
    const a = pos[l.source], b = pos[l.target];
    return Math.hypot(a.x - b.x, a.y - b.y);
  });
  const avg = dists.reduce((s, d) => s + d, 0) / dists.length;
  check(`平均边长接近 SPRING_LEN=${SPRING_LEN}`, Math.abs(avg - SPRING_LEN) < 60, `avg=${avg.toFixed(1)}`);
}

// 3) 收敛后无严重重叠
console.log('\n[2] 收敛后节点重叠度');
{
  const { nodes, links } = makeData(200, 1.0, 7);
  const pos = computeGraphLayout(nodes, links, W, H, 300);
  let minGap = Infinity;
  for (let a = 0; a < nodes.length; a++)
    for (let b = a + 1; b < nodes.length; b++) {
      const d = Math.hypot(pos[nodes[a].id].x - pos[nodes[b].id].x, pos[nodes[a].id].y - pos[nodes[b].id].y);
      if (d < minGap) minGap = d;
    }
  check('最近节点间距 > 12px(无严重重叠)', minGap > 12, `最近 ${minGap.toFixed(1)}px`);
}

// 4) 分类分区: 不同 category 的节点应有可区分的位置分布
console.log('\n[3] 分类分区有效');
{
  const { nodes, links } = makeData(90, 1.0, 99);
  const pos = computeGraphLayout(nodes, links, W, H, 300);
  const catCX = {};
  nodes.forEach(n => {
    const c = catCX[n.category] || { sx: 0, sy: 0, n: 0 };
    c.sx += pos[n.id].x; c.sy += pos[n.id].y; c.n++; catCX[n.category] = c;
  });
  const centers = Object.entries(catCX).map(([c, v]) => ({ c, x: v.sx / v.n, y: v.sy / v.n }));
  let distinct = 0;
  for (let i = 0; i < centers.length; i++)
    for (let j = i + 1; j < centers.length; j++)
      if (Math.hypot(centers[i].x - centers[j].x, centers[i].y - centers[j].y) > 10) distinct++;
  check(`${centers.length} 个分类的中心点两两可区分`, distinct >= centers.length - 1, `可区分对数=${distinct}`);
}

// 5) 空图/单节点不崩
console.log('\n[4] 边界输入');
{
  const pos1 = computeGraphLayout([{ id: 'x' }], [], W, H, 50);
  check('单节点不崩', Number.isFinite(pos1.x.x));
  const pos0 = computeGraphLayout([], [], W, H, 50);
  check('空图不崩', Object.keys(pos0).length === 0);
  // 悬空边(端点不存在)不应抛错
  const pos3 = computeGraphLayout([{ id: 'a' }], [{ source: 'a', target: 'ghost' }], W, H, 50);
  check('悬空边不崩', Number.isFinite(pos3.a.x));
}

// ── 生产数据拓扑检测 + 分层布局 ──
console.log('\n[5] 生产 brain_semantic 图(150 对 signal→decision 星形)');
// 移植 detectTopology + computeLayeredLayout(纯计算部分)
function detectTopology(nodes, links) {
  const deg = {};
  nodes.forEach(n => { deg[n.id] = 0; });
  links.forEach(l => {
    if (deg[l.source] !== undefined) deg[l.source]++;
    if (deg[l.target] !== undefined) deg[l.target]++;
  });
  let maxDeg = 0;
  nodes.forEach(n => { const d = deg[n.id] || 0; if (d > maxDeg) maxDeg = d; });
  if (maxDeg <= 1 && nodes.length >= 2) return 'star';
  return 'force';
}
function computeLayeredLayout(nodes, links, W, H) {
  const pos = {};
  const isSource = {}, isTarget = {};
  links.forEach(l => { isSource[l.source] = true; isTarget[l.target] = true; });
  const left = nodes.filter(n => isSource[n.id] && !isTarget[n.id]);
  const right = nodes.filter(n => isTarget[n.id] && !isSource[n.id]);
  const center = nodes.filter(n => !isSource[n.id] && !isTarget[n.id]);
  function placeColumn(list, x) {
    const n = list.length || 1;
    const spacing = Math.min(16, (H - 80) / n);
    const total = spacing * (n - 1);
    const y0 = (H - total) / 2;
    list.forEach((node, i) => { pos[node.id] = { x, y: y0 + i * spacing }; });
  }
  placeColumn(left, W * 0.18);
  placeColumn(right, W * 0.82);
  placeColumn(center, W * 0.5);
  return pos;
}
{
  // 构造与生产一致的 150 对星形图
  const nodes = [], links = [];
  for (let i = 0; i < 150; i++) {
    nodes.push({ id: `signal_${i}`, category: 0, label: `signal_${i}` });
    nodes.push({ id: `decision_${i}`, category: 1, label: `decision_${i}` });
    links.push({ source: `signal_${i}`, target: `decision_${i}`, label: 'RELATES_TO' });
  }
  check('拓扑检测判为 star', detectTopology(nodes, links) === 'star');

  const pos = computeLayeredLayout(nodes, links, W, H);
  const sigX = pos.signal_0.x, decX = pos.decision_0.x;
  check('signal 列在左, decision 列在右', sigX < decX, `sigX=${sigX.toFixed(0)} decX=${decX.toFixed(0)}`);

  // 分层布局核心优势: 无节点重叠(力导向在星形图会中心过密)
  let minGap = Infinity;
  const ids = nodes.map(n => n.id);
  for (let a = 0; a < ids.length; a++)
    for (let b = a + 1; b < ids.length; b++) {
      const p = pos[ids[a]], q = pos[ids[b]];
      const d = Math.hypot(p.x - q.x, p.y - q.y);
      if (d < minGap) minGap = d;
    }
  check('分层布局最近节点间距 > 15px(力导向仅 12-18px)', minGap > 15, `实际 ${minGap.toFixed(1)}px`);

  // 普通图(有枢纽)应判为 force
  const hubNodes = [{ id: 'hub', category: 0 }, { id: 'a', category: 1 }, { id: 'b', category: 1 }, { id: 'c', category: 1 }];
  const hubLinks = [{ source: 'hub', target: 'a' }, { source: 'hub', target: 'b' }, { source: 'hub', target: 'c' }];
  check('有枢纽的图判为 force', detectTopology(hubNodes, hubLinks) === 'force');

  // 孤立节点不应崩, 且排入中间列
  const iso = computeLayeredLayout([{ id: 'lonely', category: 0 }], [], W, H);
  check('孤立节点排入中间列', Math.abs(iso.lonely.x - W * 0.5) < 1e-6, `x=${iso.lonely.x.toFixed(1)}`);
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败`);
process.exit(fail ? 1 : 0);