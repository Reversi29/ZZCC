// 占位页 — 知识图谱 + 运营模块（待开放）

// 知识图谱占位（后端 /brain/graph 已存在，后续可做力导可视化）
async function renderGraphPlaceholder(container) {
  container.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const data = await apiGet('/brain/graph');
    const nodes = (data.data && data.data.nodes) || data.nodes || [];
    const edges = (data.data && data.data.links) || data.edges || [];
    const cats = (data.data && data.data.categories) || data.categories || [];
    container.innerHTML = `
      <div class="grid">
        <div class="card"><div class="card-label">图节点</div><div class="card-value accent">${nodes.length}</div><div class="card-sub">brain_semantic</div></div>
        <div class="card"><div class="card-label">图边</div><div class="card-value accent">${edges.length}</div><div class="card-sub">RELATES_TO</div></div>
        <div class="card"><div class="card-label">分类</div><div class="card-value sm">${cats.length}</div><div class="card-sub">类别</div></div>
      </div>
      <div class="panel">
        <div class="panel-title"><span>知识图谱</span><span class="tag tag-blue">接口就绪</span></div>
        <div class="panel-body">
          <div class="placeholder">
            <div class="ph-icon">🕸️</div>
            <div class="ph-title">图谱可视化待实现</div>
            <div>后端 /brain/graph 已就绪（${nodes.length} 节点），可在此做力导布局交互可视化</div>
          </div>
        </div>
      </div>
    `;
  } catch (e) {
    container.innerHTML = `<div class="error-box">加载失败：${e.message}</div>`;
  }
}

// 运营占位
function renderOpPlaceholder(container, title, desc) {
  container.innerHTML = `
    <div class="placeholder">
      <div class="ph-icon">📦</div>
      <div class="ph-title">${title}</div>
      <div>${desc}<br><br><span class="tag tag-yellow">运营需求 · 规划中</span></div>
    </div>
  `;
}

registerPage('graph', {
  title: '知识图谱',
  render: renderGraphPlaceholder,
});
registerPage('content', {
  title: '内容管理',
  render: (c) => renderOpPlaceholder(c, '内容管理', '广场内容 CRUD / 审核 / 下架，待运营需求明确后开放'),
});
registerPage('users', {
  title: '用户管理',
  render: (c) => renderOpPlaceholder(c, '用户管理', '用户列表 / 封禁 / 角色分配，待运营需求明确后开放'),
});
registerPage('interactions', {
  title: '互动监控',
  render: (c) => renderOpPlaceholder(c, '互动监控', '点赞 / 评论 / 分享 / 观看统计，待运营需求明确后开放'),
});
