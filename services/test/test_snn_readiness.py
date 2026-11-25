"""自主接管 readiness_score 单元测试。

覆盖（用户 2026-11-25 需求：把"主动吃数据的意识"操作化为可观测判据）：
1. 未成熟网络（探索率高/分歧大/无EWC/无日志）→ score 低, stage=teacher_led
2. 成熟网络（探索收敛/对齐/EWC固化/决策一致）→ score 高, stage≥joint
3. 教师分歧率低 → teacher_aligned 高
4. 无对比样本 → teacher_aligned=0（不虚高）
5. 无 EWC → ewc_consolidated=0
6. 决策日志一致 → self_consistent 高
7. 决策日志分散 → self_consistent 低
8. status() 暴露 readiness 字段

可直接运行：python3 test_snn_readiness.py（无需 pytest）
"""
import sys
import os
import tempfile
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

# 隔离配置目录，不碰生产
os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

from services.brain.snn import SNN, NeuronType
from services.brain.snn_region import SNNRegion

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


def _mk_region() -> SNNRegion:
    td = tempfile.mkdtemp()
    r = SNNRegion(save_path=os.path.join(td, "t.json"))
    r.snn = SNN.create_default()
    return r


# ── 1. 未成熟网络 → teacher_led ─────────────────────────
print("\n[1] 未成熟网络 → score 低, stage=teacher_led")
r = _mk_region()
r._stats["exploration_rate"] = 0.3   # 探索高
r._stats["agreement"] = 10
r._stats["disagreement"] = 90        # 分歧大
r.snn._ewc_importance = {}           # 无 EWC
rd = r.readiness_score()
check("score < 0.35", rd["score"] < 0.35, f"got {rd['score']}")
check("stage=teacher_led", rd["stage"] == "teacher_led", f"got {rd['stage']}")

# ── 2. 成熟网络 → score 高 ──────────────────────────────
print("\n[2] 成熟网络 → score 高, stage≥joint")
r = _mk_region()
r._stats["exploration_rate"] = 0.02  # 收敛
r._stats["agreement"] = 95
r._stats["disagreement"] = 5         # 对齐
for k in [(0, 16), (16, 20), (20, 34), (16, 21), (17, 34)]:
    r.snn._ewc_importance[k] = 2.0   # 固化
# 决策日志一致
r._decision_log_path = os.path.join(tempfile.mkdtemp(), "dl.jsonl")
for _ in range(20):
    with open(r._decision_log_path, "a") as f:
        f.write(json.dumps({"decision": "auto_approve"}) + "\n")
rd = r.readiness_score()
check("score > 0.6", rd["score"] > 0.6, f"got {rd['score']}")
check("stage 非 teacher_led", rd["stage"] in ("joint", "student_led", "autonomous"),
      f"got {rd['stage']}")
check("teacher_aligned 高", rd["components"]["teacher_aligned"] > 0.8,
      f"got {rd['components']['teacher_aligned']}")
check("ewc_consolidated 高", rd["components"]["ewc_consolidated"] > 0.8,
      f"got {rd['components']['ewc_consolidated']}")
check("self_consistent 高", rd["components"]["self_consistent"] > 0.8,
      f"got {rd['components']['self_consistent']}")

# ── 3. 教师分歧率低 → 对齐高 ────────────────────────────
print("\n[3] 教师分歧率 → teacher_aligned")
r = _mk_region()
r._stats["agreement"] = 99
r._stats["disagreement"] = 1
check("对齐≈0.99", abs(r.readiness_score()["components"]["teacher_aligned"] - 0.99) < 0.01,
      f"got {r.readiness_score()['components']['teacher_aligned']}")

# ── 4. 无对比样本 → 不虚高 ─────────────────────────────
print("\n[4] 无对比样本 → teacher_aligned=0")
r = _mk_region()
r._stats["agreement"] = 0
r._stats["disagreement"] = 0
check("对齐=0", r.readiness_score()["components"]["teacher_aligned"] == 0.0,
      f"got {r.readiness_score()['components']['teacher_aligned']}")

# ── 5. 无 EWC → ewc=0 ──────────────────────────────────
print("\n[5] 无 EWC → ewc_consolidated=0")
r = _mk_region()
r.snn._ewc_importance = {}
check("ewc=0", r.readiness_score()["components"]["ewc_consolidated"] == 0.0,
      f"got {r.readiness_score()['components']['ewc_consolidated']}")

# ── 6. 决策日志一致 → self_consistent 高 ────────────────
print("\n[6] 决策一致 → self_consistent 高")
r = _mk_region()
r._decision_log_path = os.path.join(tempfile.mkdtemp(), "dl.jsonl")
for _ in range(30):
    with open(r._decision_log_path, "a") as f:
        f.write(json.dumps({"decision": "auto_approve"}) + "\n")
check("self_consistent > 0.9", r.readiness_score()["components"]["self_consistent"] > 0.9,
      f"got {r.readiness_score()['components']['self_consistent']}")

# ── 7. 决策日志分散 → self_consistent 低 ────────────────
print("\n[7] 决策分散 → self_consistent 低")
r = _mk_region()
r._decision_log_path = os.path.join(tempfile.mkdtemp(), "dl.jsonl")
for i in range(30):
    dec = ["auto_approve", "escalate", "need_info"][i % 3]
    with open(r._decision_log_path, "a") as f:
        f.write(json.dumps({"decision": dec}) + "\n")
check("self_consistent < 0.5", r.readiness_score()["components"]["self_consistent"] < 0.5,
      f"got {r.readiness_score()['components']['self_consistent']}")

# ── 8. status() 暴露 readiness ─────────────────────────
print("\n[8] status() 暴露 readiness")
r = _mk_region()
st = r.status()
check("readiness in status", "readiness" in st, f"keys={list(st.keys())}")
check("readiness.score 存在", "score" in st["readiness"],
      f"got {list(st['readiness'].keys())}")

# ── 汇总 ────────────────────────────────────────────────
print(f"\n{'='*46}")
print(f"通过: {PASS}   失败: {FAIL}")
if FAIL:
    sys.exit(1)
print("全部通过 ✅")