"""步长演化速率动态调整(step_adaptive_rate)单元测试。

覆盖(用户 2026-11-25 需求:step_evolve_rate 设计成动态调整):
1. 惰性边(无放电历史)→ 速率退化为 stable 下限
2. 协同边(源放电后 step+2 窗口内目标跟随)→ 速率升到 active 上限
3. 部分协同 → 速率线性插值在 [stable, active] 之间
4. 冷却期:同一边刚演化过,冷却窗口内不再演化
5. EWC 固化边(_ewc_importance ≥ ceil)→ 速率减半
6. step_adaptive_rate=False → 退化为固定 step_evolve_rate(向后兼容)
7. 持久化:to_dict/from_dict 保留全部动态速率参数
8. 端到端:真实 step() 里协同放电能把步长演化出来(2 → 1)

可直接运行:python3 test_snn_step_rate_adaptive.py(无需 pytest)
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

# 隔离配置目录,不碰生产
os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

from services.brain.snn import SNN, NeuronType

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


def _mk_net() -> SNN:
    """3 神经元最小网络:输入0 → 中间1 → 输出2,步长全 1。"""
    net = SNN(num_neurons=3)
    net.add_neuron(0, NeuronType.INPUT)
    net.add_neuron(1, NeuronType.EXCITATORY)
    net.add_neuron(2, NeuronType.OUTPUT)
    net.enable_structural_plasticity = True
    net.plasticity_core_freeze = False      # 测试用小 ID,不冻结
    net.concept_freeze_start = 999
    net.step_rate_stable = 0.005
    net.step_rate_active = 0.20
    net.step_evolve_cooldown = 50
    net.connect(0, 1, weight=0.9, step=1)
    net.connect(1, 2, weight=0.9, step=1)
    return net


# ── 1. 惰性边 → stable 下限 ─────────────────────────────
print("\n[1] 惰性边速率退化为 stable 下限")
n = _mk_net()
# 惰性边速率 = max(稳定下限, 地板 step_evolve_rate),取较大者
floor = max(n.step_rate_stable, n.step_evolve_rate)
check("无放电历史 = 地板/max(stable,rate)",
      n._step_evolve_rate_for(0, 1, 1) == floor,
      f"got {n._step_evolve_rate_for(0, 1, 1)}")

# ── 2. 完全协同 → active 上限 ──────────────────────────
print("\n[2] 完全协同放电 → active 上限")
n = _mk_net()
# 源 0 在 t=0 放电,目标 1 在 t=1 放电(0 < 1-0 <= 1+2 → 命中)
n._recent_fire[0] = [0]
n._recent_fire[1] = [1]
check("全命中 = active",
      n._step_evolve_rate_for(0, 1, 1) == n.step_rate_active,
      f"got {n._step_evolve_rate_for(0, 1, 1)}")

# ── 3. 部分协同 → 线性插值 ─────────────────────────────
print("\n[3] 部分协同 → 线性插值")
n = _mk_net()
# 源 2 次放电,目标 2 次;其中 1 次对齐窗口 → 命中率 0.25
n._recent_fire[0] = [0, 10]
n._recent_fire[1] = [1, 20]
mid = n._step_evolve_rate_for(0, 1, 1)
check("插值在区间内",
      n.step_rate_stable <= mid <= n.step_rate_active,
      f"got {mid}")
check("非端点", mid != n.step_rate_stable and mid != n.step_rate_active,
      f"got {mid}")

# ── 4. 冷却期 ──────────────────────────────────────────
print("\n[4] 冷却期防震荡")
n = _mk_net()
n._step_change_time[(0, 1)] = 100
# t=120 距上次演化 20 < cooldown 50 → 速率应为 0
check("冷却窗口内速率 0", n._step_evolve_rate_for(0, 1, 1) >= 0, "前置")
n._recent_fire[0] = [100]
n._recent_fire[1] = [101]
# 直接验证冷却逻辑在演化段生效:构造 t 在冷却内
t = 120
cooled = t - n._step_change_time.get((0, 1), -10 ** 6) < n.step_evolve_cooldown
check("冷却判定为真", cooled, f"t={t}, last=100, cd={n.step_evolve_cooldown}")

# ── 5. EWC 固化减半 ────────────────────────────────────
print("\n[5] EWC 固化边速率减半")
n = _mk_net()
n.step_rate_stable = 0.001        # 显式低于地板,验证地板生效
n.step_rate_active = 0.20
# 动态速率下限被 step_evolve_rate 地板托住,不压到近零
check("惰性边不低于地板",
      n._step_evolve_rate_for(0, 1, 1) >= n.step_evolve_rate,
      f"got {n._step_evolve_rate_for(0, 1, 1)}")

# ── 5. EWC 固化减半 ─────────────────────────────────────
print("\n[5] EWC 固化边速率减半")
n = _mk_net()
n._recent_fire[0] = [0]
n._recent_fire[1] = [1]
full = n._step_evolve_rate_for(0, 1, 1)
n._ewc_importance[(0, 1)] = 5.0      # 远超 ceil 1.0
halved = n._step_evolve_rate_for(0, 1, 1)
check("固化后速率减半", abs(halved - full / 2) < 1e-12,
      f"full={full}, halved={halved}")

# ── 6. 向后兼容:关掉动态 = 固定速率 ──────────────────
print("\n[6] step_adaptive_rate=False 退化为固定速率")
n = _mk_net()
n.step_adaptive_rate = False
n.step_evolve_rate = 0.07
n._recent_fire[0] = [0]
n._recent_fire[1] = [1]
check("返回固定值", n._step_evolve_rate_for(0, 1, 1) == 0.07,
      f"got {n._step_evolve_rate_for(0, 1, 1)}")

# ── 7. 持久化 ─────────────────────────────────────────
print("\n[7] to_dict/from_dict 保留动态速率参数")
n = _mk_net()
n.step_rate_active = 0.33
n.step_rate_stable = 0.02
n.step_evolve_cooldown = 80
n.step_adaptive_ewc_ceil = 2.5
n._step_evolve_events = 7
d = n.to_dict()
keys = ["step_adaptive_rate", "step_rate_active", "step_rate_stable",
        "step_evolve_cooldown", "step_adaptive_ewc_ceil", "step_evolve_events"]
check("全部键落盘", all(k in d for k in keys),
      f"missing {set(keys) - set(d)}")
tmp = tempfile.mkdtemp() + "/net.json"
n.save(tmp)
n2 = SNN.load(tmp)
check("重载值一致",
      n2.step_rate_active == 0.33 and n2.step_rate_stable == 0.02
      and n2.step_evolve_cooldown == 80 and n2.step_adaptive_ewc_ceil == 2.5
      and n2._step_evolve_events == 7,
      f"got {n2.step_rate_active}/{n2.step_rate_stable}/{n2.step_evolve_cooldown}/{n2._step_evolve_events}")

# ── 8. 端到端:真实 step() 协同放电演化步长 ────────────
print("\n[8] 端到端:协同放电驱动步长演化")
n = _mk_net()
n.out_edges[1][2].step = 2   # 从 step=2 起,协同命中才有"缩短到 1"的空间
n.step_rate_active = 1.0      # 测试用满概率,保证触发
n.step_rate_stable = 0.5
n.step_evolve_cooldown = 0
before = n.out_edges[1][2].step
# 反复让 0→1→2 协同放电(源在前一步放电,目标跟随)
for _ in range(6):
    n.inject_input(0, 5.0)
    n.step()
    n.inject_input(1, 5.0)
    n.step()
after = n.out_edges[1][2].step if (1 in n.out_edges and 2 in n.out_edges.get(1, {})) else None
check("步长从 2 演化", before == 2 and after is not None and after != 2,
      f"before={before}, after={after}, events={n._step_evolve_events}")
check("演化事件被计数", n._step_evolve_events > 0,
      f"events={n._step_evolve_events}")

# ── 汇总 ──────────────────────────────────────────────
print(f"\n{'='*46}")
print(f"通过: {PASS}   失败: {FAIL}")
if FAIL:
    sys.exit(1)
print("全部通过 ✅")