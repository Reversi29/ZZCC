import vm from 'vm';
import fs from 'fs';

const src = fs.readFileSync(
  '/Users/mac/ZZCC/services/interface/admin/graph_page.js', 'utf8');
// 抽取纯计算函数段(跳过 DOM 依赖的 initGraphCanvas 之后部分)
const start = src.indexOf('function computeGraphLayout');
const end = src.indexOf('// ── 画布初始化 + 交互 ──');
const pure = src.slice(start, end) +
  '\nglobalThis.__api = { detectTopology, rowCount, computeLayeredLayout,' +
  ' bipartiteSides, computeGraphLayout, COL_COLUMNS };';

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(pure, sandbox);
const { detectTopology, rowCount, computeLayeredLayout, computeGraphLayout } = sandbox.__api;

// 构造与生产一致的 150 对 (signal→decision) 星形图
const nodes = [], links = [];
for (let i = 0; i < 150; i++) {
  nodes.push({ id: 's' + i, category: 0, label: 'sig' + i });
  nodes.push({ id: 'd' + i, category: 1, label: 'dec' + i });
  links.push({ source: 's' + i, target: 'd' + i });
}

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + (detail ? ' → ' + detail : '')); }
}

console.log('\n[网格分层布局] 150 对生产图');
check('detectTopology → star', detectTopology(nodes, links) === 'star');
const rows = rowCount(nodes, links);
check('150 对 ÷ 10 列 = 15 行', rows === 15, '实际 ' + rows);
const H = Math.max(520, Math.min(2400, rows * 48 + 80));
check('画布高度合理(520~2400)', H >= 520 && H <= 2400, 'H=' + H);

const pos = computeLayeredLayout(nodes, links, 1080, H);
const ids = nodes.map(n => n.id);
let minGap = Infinity;
for (let a = 0; a < ids.length; a++)
  for (let b = a + 1; b < ids.length; b++) {
    const d = Math.hypot(pos[ids[a]].x - pos[ids[b]].x, pos[ids[a]].y - pos[ids[b]].y);
    if (d < minGap) minGap = d;
  }
check('最近节点间距 > 12px(无严重重叠)', minGap > 12, '实际 ' + minGap.toFixed(1) + 'px');

const xs = Object.values(pos).map(p => p.x), ys = Object.values(pos).map(p => p.y);
const inX = xs.every(x => x >= 0 && x <= 1080);
check('所有节点 x 在画布内(0~1080)', inX,
  Math.min(...xs).toFixed(0) + '~' + Math.max(...xs).toFixed(0));
check('所有节点 y 在画布内(0~H)', ys.every(y => y >= 0 && y <= H),
  Math.min(...ys).toFixed(0) + '~' + Math.max(...ys).toFixed(0) + ' / H=' + H);

const s0 = pos.s0, d0 = pos.d0;
// 配对列布局: 同列内 signal 在上、decision 在下 → 边为短垂直线
check('配对节点同列(边为垂直线)', Math.abs(s0.x - d0.x) < 1e-6);
check('边垂直长度 > 20px(可见)', Math.abs(d0.y - s0.y) > 20, '长=' + Math.abs(d0.y - s0.y).toFixed(1));
check('signal 在 decision 上方', s0.y < d0.y, 's0.y=' + s0.y.toFixed(1) + ' d0.y=' + d0.y.toFixed(1));

console.log('\n[边界] 不等长两侧 + 孤立节点');
const unbal = [
  { id: 'a1', category: 0 }, { id: 'a2', category: 0 }, { id: 'a3', category: 0 },
  { id: 'b1', category: 1 }, { id: 'lonely', category: 0 },
];
const unbalLinks = [{ source: 'a1', target: 'b1' }];
const p2 = computeLayeredLayout(unbal, unbalLinks, 1080, 400);
check('不等长两侧全部有位置', unbal.every(n => p2[n.id] && Number.isFinite(p2[n.id].y)));
check('孤立节点排入中间', Math.abs(p2.lonely.x - 540) < 1e-6);

console.log('\n[回归] 力导向布局未被破坏');
const forceNodes = [{ id: 'h', category: 0 }, { id: 'x', category: 1 }, { id: 'y', category: 1 }, { id: 'z', category: 1 }];
const forceLinks = [{ source: 'h', target: 'x' }, { source: 'h', target: 'y' }, { source: 'h', target: 'z' }];
check('有枢纽图 → force', detectTopology(forceNodes, forceLinks) === 'force');
const p3 = computeGraphLayout(forceNodes, forceLinks, 1080, 520, 300);
check('力导向所有节点有位置', forceNodes.every(n => p3[n.id] && Number.isFinite(p3[n.id].x)));
check('空图不崩', Object.keys(computeGraphLayout([], [], 1080, 520, 50)).length === 0);

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail ? 1 : 0);