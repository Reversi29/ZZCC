// 占位页 — 运营模块（待开放）
// 注: 知识图谱(graph)已由 graph_page.js 实现完整力导向可视化, 不再占位

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
