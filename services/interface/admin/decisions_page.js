// 决策历史页 — 独立模块
// 从 /brain/decisions 拉取，支持分页/筛选

let decisionState = { page: 1, limit: 20, total: 0, filter: '' };

async function renderDecisions(container) {
  container.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const params = { limit: decisionState.limit, offset: (decisionState.page - 1) * decisionState.limit };
    const data = await apiGet('/brain/decisions', params);
    decisionState.total = data.count || 0;
    drawDecisions(container, data.decisions || []);
  } catch (e) {
    container.innerHTML = `<div class="error-box">加载失败：${e.message}</div>`;
  }
}

function drawDecisions(container, decs) {
  const totalPages = Math.max(1, Math.ceil(decisionState.total / decisionState.limit));
  const filtered = decs.filter(d =>
    !decisionState.filter ||
    (d.signal_type || '').includes(decisionState.filter) ||
    (d.decision || '').includes(decisionState.filter)
  );

  container.innerHTML = `
    <div class="panel">
      <div class="panel-title">
        <span>决策记录 <span style="color:var(--text-dim);font-size:12px">(共 ${decisionState.total} 条)</span></span>
        <input id="dec-filter" placeholder="按类型/决策筛选" value="${decisionState.filter}"
          style="background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:6px 10px;font-size:13px">
      </div>
      <div class="panel-body" style="overflow-x:auto">
        <table>
          <thead>
            <tr><th>时间</th><th>信号类型</th><th>决策</th><th>置信度</th><th>层级</th><th>推理</th></tr>
          </thead>
          <tbody>
            ${filtered.map(d => `
              <tr>
                <td style="white-space:nowrap">${fmtTime(d.created_at)}</td>
                <td>${d.signal_type || '-'}</td>
                <td>${decisionTag(d.decision)}</td>
                <td>${d.confidence ?? '-'}</td>
                <td>L${d.reasoning_level ?? '-'}</td>
                <td style="max-width:300px;color:var(--text-dim);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${(d.reasoning || '').replace(/"/g, '&quot;')}">${d.reasoning || '-'}</td>
              </tr>`).join('') || '<tr><td colspan="6">暂无决策</td></tr>'}
          </tbody>
        </table>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;font-size:13px;color:var(--text-dim)">
        <span>第 ${decisionState.page} / ${totalPages} 页</span>
        <div>
          <button class="btn" onclick="decPrev()" ${decisionState.page <= 1 ? 'disabled style="opacity:0.4"' : ''}>上一页</button>
          <button class="btn" onclick="decNext()" ${decisionState.page >= totalPages ? 'disabled style="opacity:0.4"' : ''}>下一页</button>
        </div>
      </div>
    </div>
  `;

  const input = document.getElementById('dec-filter');
  if (input) {
    input.addEventListener('keyup', (e) => {
      if (e.key === 'Enter') {
        decisionState.filter = e.target.value.trim();
        decisionState.page = 1;
        renderDecisions(container);
      }
    });
  }
}

window.decPrev = function() {
  if (decisionState.page > 1) {
    decisionState.page--;
    renderDecisions(document.getElementById('content'));
  }
};
window.decNext = function() {
  decisionState.page++;
  renderDecisions(document.getElementById('content'));
};

registerPage('decisions', {
  title: '决策历史',
  render: renderDecisions,
});
