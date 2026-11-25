// ZZCC 管理平台 — Brain Core 类脑中枢看板
// 数据源: /api/v1/brain/core/status
// 展示: 运行状态 / tick / 信号处理 / 内源时间感知 / 记忆 / 推理统计 / 配置

let brainCoreState = null;

async function renderBrainCore(container) {
  container.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const status = await apiGet('/brain/core/status');
    brainCoreState = status;
    drawBrainCore(container, status);
  } catch (e) {
    container.innerHTML = `<div class="error-box">加载失败：${e.message}</div>`;
  }
}

function drawBrainCore(container, status) {
  const cfg = status.config || {};
  const stats = status.stats || {};
  const endo = status.endogenous || {};
  const mem = status.memory || {};
  const sem = status.semantic || {};
  const wm = status.working_memory || {};
  const reasoning = status.reasoning || {};
  const rulesLoaded = status.rules_loaded ?? '-';
  const actions = status.actions || [];

  const running = status.running;
  const runTag = running ? 'tag-green' : 'tag-red';
  const runText = running ? '运行中' : '已停止';

  // 内源阶段
  const phaseMap = {
    active: ['tag-green', '活跃'],
    quiet: ['tag-yellow', '安静'],
    rest: ['tag-blue', '休息'],
  };
  const [phaseCls, phaseText] = phaseMap[endo.phase] || ['tag-blue', endo.phase || '-'];

  // 信号处理率
  const gated = stats.signals_gated_out ?? 0;
  const seen = stats.signals_seen ?? 0;

  // 推理命中率
  const l1c = reasoning.l1_calls || 0, l1h = reasoning.l1_hits || 0;
  const l2c = reasoning.l2_calls || 0, l2h = reasoning.l2_hits || 0;
  const l3c = reasoning.l3_calls || 0, l3h = reasoning.l3_hits || 0;
  const snnc = reasoning.snn_calls || 0, snnh = reasoning.snn_hits || 0;
  const pct = (h, c) => c > 0 ? (h / c * 100).toFixed(0) + '%' : '-';

  container.innerHTML = `
    <!-- 控制条 -->
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-title">控制</div>
      <div class="panel-body" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;min-height:auto">
        <button class="btn btn-primary" onclick="brainCoreStart()" ${running ? 'disabled' : ''}>▶ 启动</button>
        <button class="btn btn-danger" onclick="brainCoreStop()" ${running ? '' : 'disabled'}>⏹ 停止</button>
        <button class="btn" onclick="brainCoreTick()">⚡ 手动 tick</button>
        <span style="font-size:12px;color:var(--text-dim)">
          tick 间隔 <b>${cfg.interval_seconds ?? '-'}s</b> · 批处理 <b>${cfg.batch_limit ?? '-'}</b> · 执行动作 <b>${cfg.execute_actions ? '开' : '关'}</b>
        </span>
        <span style="font-size:12px;color:var(--text-dim);margin-left:auto">
          上次 tick: ${fmtTime(stats.last_tick_at)} · 上次处理: ${fmtTime(stats.last_processed_at)}
        </span>
      </div>
    </div>

    <!-- KPI 行 -->
    <div class="grid">
      <div class="card">
        <div class="card-label">运行状态</div>
        <div class="card-value sm"><span class="tag ${runTag}">${runText}</span></div>
        <div class="card-sub">tick 间隔 ${cfg.interval_seconds ?? '-'}s</div>
      </div>
      <div class="card">
        <div class="card-label">tick 总数</div>
        <div class="card-value">${stats.ticks ?? '-'}</div>
        <div class="card-sub">开始于 ${fmtTime(stats.started_at)}</div>
      </div>
      <div class="card">
        <div class="card-label">信号处理</div>
        <div class="card-value">${stats.signals_processed ?? 0}<span style="font-size:16px;color:var(--text-dim)"> / ${seen}</span></div>
        <div class="card-sub">门控 ${gated} · 动作 ${stats.actions_executed ?? 0}</div>
      </div>
      <div class="card">
        <div class="card-label">内源阶段</div>
        <div class="card-value sm"><span class="tag ${phaseCls}">${phaseText}</span></div>
        <div class="card-sub">空闲 ${Math.round((endo.idle_seconds || 0) / 60)}min · 内源 ${endo.endogenous_count ?? 0} 次</div>
      </div>
      <div class="card">
        <div class="card-label">记忆条目</div>
        <div class="card-value">${status.memory_entries ?? '-'}</div>
        <div class="card-sub">工作记忆 ${wm.total_entries ?? 0} 条</div>
      </div>
      <div class="card">
        <div class="card-label">语义记忆</div>
        <div class="card-value ${sem.enabled ? 'green' : 'red'}">${sem.enabled ? '在线' : '离线'}</div>
        <div class="card-sub">写 ${sem.writes ?? 0} · 读 ${sem.retrieves ?? 0} · 错误 ${sem.errors ?? 0}</div>
      </div>
    </div>

    <!-- 内源时间感知 -->
    <div class="panel">
      <div class="panel-title">内源时间感知</div>
      <div class="panel-body">
        <div class="grid" style="grid-template-columns:repeat(4,1fr)">
          <div><div class="card-label">阶段</div><div class="card-value sm"><span class="tag ${phaseCls}">${phaseText}</span></div></div>
          <div><div class="card-label">空闲时长</div><div class="card-value sm">${Math.round((endo.idle_seconds || 0) / 60)}<span style="font-size:12px;color:var(--text-dim)">min</span></div></div>
          <div><div class="card-label">安静阈值</div><div class="card-value sm">${Math.round((endo.quiet_threshold_seconds || 0) / 60)}<span style="font-size:12px;color:var(--text-dim)">min</span></div></div>
          <div><div class="card-label">休息阈值</div><div class="card-value sm">${Math.round((endo.rest_threshold_seconds || 0) / 60)}<span style="font-size:12px;color:var(--text-dim)">min</span></div></div>
        </div>
        <div style="margin-top:12px;font-size:12px;color:var(--text-dim)">
          内源最小间隔 ${Math.round((endo.min_interval_seconds || 0) / 60)}min · 最近内源活动 ${fmtTime(stats.last_endogenous_ts ? new Date(stats.last_endogenous_ts * 1000).toISOString() : null)}
        </div>
      </div>
    </div>

    <!-- 推理统计 + 配置 -->
    <div class="grid" style="grid-template-columns:1fr 1fr">
      <div class="panel">
        <div class="panel-title">推理统计</div>
        <div class="panel-body">
          <table class="topo-table" style="width:100%">
            <thead><tr><th>层级</th><th>调用</th><th>命中</th><th>命中率</th></tr></thead>
            <tbody>
              <tr><td>L1 规则</td><td>${l1c}</td><td>${l1h}</td><td>${pct(l1h, l1c)}</td></tr>
              <tr><td>L2 语义</td><td>${l2c}</td><td>${l2h}</td><td>${pct(l2h, l2c)}</td></tr>
              <tr><td>L3 LLM</td><td>${l3c}</td><td>${l3h}</td><td>${pct(l3h, l3c)}</td></tr>
              <tr><td>SNN</td><td>${snnc}</td><td>${snnh}</td><td>${pct(snnh, snnc)}</td></tr>
            </tbody>
          </table>
          <div style="margin-top:8px;font-size:12px;color:var(--text-dim)">规则加载 ${rulesLoaded} · 动作执行器 ${actions.length}</div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title">丘脑 + 记忆</div>
        <div class="panel-body">
          <div style="font-size:12px;color:var(--text-dim);margin-bottom:8px">丘脑（信号门控）</div>
          <div style="display:flex;gap:16px;flex-wrap:wrap">
            <div><span class="tag tag-blue">seen ${cfg.thalamus?.seen ?? '-'}</span></div>
            <div><span class="tag tag-blue">min_urgency ${cfg.thalamus?.min_urgency ?? '-'}</span></div>
            <div><span class="tag tag-blue">dedupe_ttl ${cfg.thalamus?.dedupe_ttl ?? '-'}s</span></div>
          </div>
          <div style="font-size:12px;color:var(--text-dim);margin:12px 0 8px">工作记忆（MemoryBroker）</div>
          <div style="display:flex;gap:16px;flex-wrap:wrap">
            <div><span class="tag tag-purple">会话 ${wm.sessions ?? '-'}</span></div>
            <div><span class="tag tag-purple">条目 ${wm.total_entries ?? '-'}</span></div>
            <div><span class="tag tag-purple">TTL ${Math.round((wm.ttl_seconds || 0) / 60)}min</span></div>
            <div><span class="tag tag-purple">上限/会话 ${wm.max_per_session ?? '-'}</span></div>
          </div>
          <div style="font-size:12px;color:var(--text-dim);margin:12px 0 8px">语义记忆（SemanticStore）</div>
          <div style="font-size:12px;color:var(--text-dim)">
            ${sem.enabled ? `空间 <b>${sem.space || '-'}</b> · schema ${sem.schema_ready ? '就绪' : '未就绪'} · 写 ${sem.writes || 0} · 读 ${sem.retrieves || 0}` : '语义记忆未启用'}
          </div>
        </div>
      </div>
    </div>
  `;
}

// ── 控制操作 ──
async function brainCoreStart() {
  try {
    await apiPost('/brain/core/start');
    renderBrainCore(document.getElementById('content'));
  } catch (e) {
    alert('启动失败: ' + e.message);
  }
}

async function brainCoreStop() {
  try {
    await apiPost('/brain/core/stop');
    renderBrainCore(document.getElementById('content'));
  } catch (e) {
    alert('停止失败: ' + e.message);
  }
}

async function brainCoreTick() {
  try {
    await apiPost('/brain/core/tick');
    renderBrainCore(document.getElementById('content'));
  } catch (e) {
    alert('tick 失败: ' + e.message);
  }
}

registerPage('braincore', {
  title: 'Brain Core 看板',
  render: renderBrainCore,
});
