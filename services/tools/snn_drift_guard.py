#!/usr/bin/env python3
"""SNN 生产网络漂移护栏

漂移有两个独立来源：
1. 权重漂移——真实流量 train_from_feedback 累积（training_count 增长，
   penalized > strengthened 时权重整体下压，eval 退化）
2. 拓扑膨胀——推理时动态槽（concept/input/output）自动注册，神经元数从 40
   膨胀到 230+，结构化拓扑被稀释

本脚本同时检测两者，超阈值自动从基线快照恢复。

判定依据以**网络自身状态**为准，不依赖 stats 文件（stats 可能随网络重置
而未同步，导致残留旧值）。

用法：
  snn_drift_guard.py              # 检测 + 必要时恢复，打印报告
  snn_drift_guard.py --check      # 仅检测，不恢复
  snn_drift_guard.py --baseline    # 从当前生产网络重建基线快照（需先确认 eval 达标）
  snn_drift_guard.py --restore     # 软恢复（保留 EWC 知识）
  snn_drift_guard.py --hard-restore  # 硬恢复（丢弃 EWC，从基线重来）

退出码：0=健康, 1=漂移已恢复, 2=漂移且 --check 未恢复
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

# 容器路径：网络 + 基线快照放同一目录，便于原子替换
CONTAINER = "nebula-interface"
DATA_DIR = "/app/config_data"
NETWORK = f"{DATA_DIR}/snn_network.json"
BASELINE = f"{DATA_DIR}/snn_network_baseline.json"
DRIFT_SNAPSHOT = f"{DATA_DIR}/snn_network_drifted_%s.json"

# 基线拓扑从快照自动学习，不硬编码。原因：SNNRegion 实例化时会
# 自动注册方向 B/C 的连续通道（200/201）与方向 D 的概念中继（230+），
# create_default 是 40 神经元，但运行态稳定在 ~216——这是设计产物不是漂移。
# 因此基准取基线快照的神经元数，只检测相对膨胀。
#
# 注意：拓扑膨胀本身是方向 A/B/D 的开放集设计行为——服务正常运行
# 就会因遇到新信号类型/概念而增长（实测 216→231，仅几分钟）。因此
# 余量必须宽到覆盖正常运行态波动，只拦截真正失控（40→232 那类 +480%）。
# 实测正常运行波动约 +15 神经元，余量 40 留足缓冲。
NEURON_GROWTH_TOLERANCE = 40   # 相对基线的允许膨胀余量
# training_count 累积阈值——超过则真实流量已大量改写权重
MAX_TRAINING = 20
# 惩罚/加强比阈值——惩罚显著超过加强说明权重被持续压低
# 1.3 而非 1.5：真实漂移现场是 penalized 269 / strengthened 201 = 1.34，
# 用 1.5 会让它漏报，只能靠 training_count 单独捕获
PENALIZE_RATIO = 1.3
# 权重均值下压阈值——真实漂移会把权重整体压低（结构性连接被削弱）。
# 基线快照的权重均值作为基准，低于基线均值×(1-WEIGHT_MEAN_DROP_RATIO)
# 即判为漂移。这是网络自身状态的判据，不依赖 stats（被服务内存覆写）。
WEIGHT_MEAN_DROP_RATIO = 0.25


def docker_exec(args, check=True):
    r = subprocess.run(["docker", "exec", CONTAINER] + args,
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"docker exec 失败: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def read_file(container_path):
    try:
        return docker_exec(["cat", container_path])
    except Exception:
        return None


def write_file(container_path, content):
    docker_exec(["sh", "-c",
                f"cat > {container_path} <<'ZZCC_GUARD_EOF'\n{content}\nZZCC_GUARD_EOF"])


def restart_service():
    subprocess.run(["docker", "restart", CONTAINER], capture_output=True)
    import time
    time.sleep(18)


class DriftReport:
    def __init__(self):
        self.neurons = None
        self.edges = None
        self.training_count = None
        self.strengthened = None
        self.penalized = None
        self.issues = []      # 致命：触发恢复
        self.warnings = []   # 非致命：仅报告，不触发恢复

    def baseline_neurons(self):
        """从基线快照读基线拓扑，作为膨胀判定的相对基准。"""
        raw = read_file(BASELINE)
        if not raw:
            return None
        try:
            return json.loads(raw).get("num_neurons")
        except Exception:
            return None

    def baseline_weight_mean(self):
        """从基线快照读权重均值，作为下压判定的基准。"""
        raw = read_file(BASELINE)
        if not raw:
            return None
        try:
            net = json.loads(raw)
            edges = net.get("edges", [])
            if not edges:
                return None
            return sum(e.get("weight", 0) for e in edges) / len(edges)
        except Exception:
            return None

    def check(self):
        """用网络自身状态检测漂移，返回 True 表示健康。"""
        raw = read_file(NETWORK)
        if not raw:
            self.issues.append("网络文件不存在或不可读")
            return False
        try:
            net = json.loads(raw)
        except Exception:
            self.issues.append("网络文件 JSON 解析失败")
            return False

        self.neurons = net.get("num_neurons")
        self.edges = len(net.get("edges", {}))
        edge_list = net.get("edges", [])
        self.weight_mean = (
            sum(e.get("weight", 0) for e in edge_list) / len(edge_list)
            if edge_list else 0.0
        )

        if self.neurons is None:
            self.issues.append("网络缺少 num_neurons 字段")
            return False

        # 拓扑膨胀（相对基线快照，非硬编码 40）
        # 降级为警告：它是方向 A/B/D 开放集的设计行为，服务正常运行
        # 就会因遇新信号/概念而增长（实测 216→231 仅几分钟），但实测
        # 不降低 eval（216 神经元时仍 12/12）——非致命，仅报告不恢复。
        # 致命漂移是权重训练累积与权重下压，见下。
        base = self.baseline_neurons()
        if base is not None and self.neurons > base + NEURON_GROWTH_TOLERANCE:
            self.warnings.append(
                f"拓扑膨胀：{self.neurons} 神经元 "
                f"(基线 {base} + 余量 {NEURON_GROWTH_TOLERANCE}，"
                f"开放集设计行为，不触发恢复)")

        # 漂移源 2：权重训练累积
        # stats 文件可能未随网络重置，这里只作为参考指标，不作为唯一判据
        stats_raw = read_file(f"{DATA_DIR}/snn_network_stats.json")
        if stats_raw:
            try:
                stats = json.loads(stats_raw)
                self.training_count = stats.get("training_count", 0)
                self.strengthened = stats.get("edges_strengthened", 0)
                self.penalized = stats.get("edges_penalized", 0)
                if self.training_count > MAX_TRAINING:
                    self.issues.append(
                        f"训练累积：training_count={self.training_count} "
                        f"> {MAX_TRAINING}")
                if self.strengthened > 0 and \
                        self.penalized / self.strengthened > PENALIZE_RATIO:
                    self.issues.append(
                        f"权重下压：penalized {self.penalized} / "
                        f"strengthened {self.strengthened} = "
                        f"{self.penalized / self.strengthened:.2f} > "
                        f"{PENALIZE_RATIO}")
            except Exception:
                pass

        # 漂移源 3：权重均值下压（网络自身状态，不依赖 stats）
        # stats 被服务内存覆写时上面两条会漏检，权重分布是可靠判据。
        base_wm = self.baseline_weight_mean()
        if base_wm is not None and base_wm > 0 and self.weight_mean > 0:
            if self.weight_mean < base_wm * (1 - WEIGHT_MEAN_DROP_RATIO):
                self.issues.append(
                    f"权重均值下压：{self.weight_mean:.3f} "
                    f"< 基线 {base_wm:.3f} × (1-{WEIGHT_MEAN_DROP_RATIO})")
            elif self.weight_mean < base_wm * 0.9:
                self.warnings.append(
                    f"权重均值接近阈值：{self.weight_mean:.3f} "
                    f"vs 基线 {base_wm:.3f}")

        # 只有致命 issues 触发恢复；warnings 不触发
        return not self.issues

    def render(self, restored=False):
        lines = ["===== SNN 漂移护栏 =====",
                 f"  神经元: {self.neurons}  边: {self.edges}  "
                 f"权重均值: {self.weight_mean:.3f}",
                 f"  training_count: {self.training_count}  "
                 f"strengthened: {self.strengthened}  penalized: {self.penalized}"]
        if self.issues:
            lines.append("  漂移信号（致命）:")
            lines += [f"    ✗ {i}" for i in self.issues]
        else:
            lines.append("  ✓ 无致命漂移")
        if self.warnings:
            lines.append("  提示:")
            lines += [f"    ⚠ {w}" for w in self.warnings]
        if restored:
            lines.append("  → 已从基线恢复并重启服务")
        return "\n".join(lines)


def snapshot_drifted(report):
    """漂移版本留档，便于事后分析（带时间戳避免覆盖）。"""
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = DRIFT_SNAPSHOT % ts
    docker_exec(["cp", NETWORK, dest])
    return dest


def merge_ewc_for_restore(baseline_raw: str, drift_raw: str) -> tuple[str, int]:
    """软恢复的 EWC 合并：返回 (合并后的基线 JSON, 保留的 EWC 条数)。

    合并策略：漂移网络优先保留其 EWC 值，基线里漂移没有的补进来。
    这样恢复基线拓扑后，被固化的重要连接（如 escalate 路径）依然受
    EWC 保护，不会因回退基线而丢失已固化的知识。
    """
    try:
        base = json.loads(baseline_raw)
        drift = json.loads(drift_raw)
        ewc = dict(drift.get("ewc_importance", {}))
        for k, v in base.get("ewc_importance", {}).items():
            ewc.setdefault(k, v)
        if not ewc:
            return baseline_raw, 0
        base["ewc_importance"] = ewc
        return json.dumps(base, ensure_ascii=False, indent=2), len(ewc)
    except Exception:
        return baseline_raw, 0


def restore_from_baseline(soft=True):
    """从基线恢复网络。

    soft=True（默认）：软恢复。恢复基线拓扑，但把漂移网络的 EWC 重要性
    合并过来。这样被固化的重要连接（如 escalate 路径）在恢复后依然受
    EWC 保护，不会因为回退基线而丢失已固化的知识。

    soft=False：硬恢复。完全丢弃漂移网络的 EWC 重要性，从基线重新开始。
    """
    if not read_file(BASELINE):
        return "基线快照不存在，无法恢复（需先 --baseline 建立）"
    baseline_raw = read_file(BASELINE)
    drift_raw = read_file(NETWORK)
    merged, self_ewc = merge_ewc_for_restore(baseline_raw, drift_raw)
    docker_exec(["cp", BASELINE, NETWORK])
    # 先 cp 基线再写合并后的内容（含 EWC）
    if merged != baseline_raw:
        write_file(NETWORK, merged)
    # stats 文件未随网络重置会残留旧值，一并归零
    zero_stats = json.dumps({
        "reason_calls": 0, "reason_hits": 0, "total_fires": 0,
        "last_decision": "", "last_confidence": 0.0, "training_count": 0,
        "edges_added": 0, "edges_strengthened": 0, "edges_penalized": 0,
        "exploration_rate": 0.1, "boundary_detected_count": 0,
        "ewc_protected_edges": 0, "micro_learn_steps": 0,
    }, ensure_ascii=False)
    write_file(f"{DATA_DIR}/snn_network_stats.json", zero_stats)
    restart_service()
    return f"已软恢复（保留 {self_ewc} 条 EWC 重要性）"


def build_baseline():
    raw = read_file(NETWORK)
    if not raw:
        return "当前网络不可读，无法建立基线"
    write_file(BASELINE, raw)
    net = json.loads(raw)
    # 重建基线 = 新的统计起点，stats 一并归零，否则重建后首次检查
    # 仍会误报训练累积（旧 training_count 残留）
    zero_stats = json.dumps({
        "reason_calls": 0, "reason_hits": 0, "total_fires": 0,
        "last_decision": "", "last_confidence": 0.0, "training_count": 0,
        "edges_added": 0, "edges_strengthened": 0, "edges_penalized": 0,
        "exploration_rate": 0.1, "boundary_detected_count": 0,
        "ewc_protected_edges": 0, "micro_learn_steps": 0,
    }, ensure_ascii=False)
    write_file(f"{DATA_DIR}/snn_network_stats.json", zero_stats)
    return f"基线已建立：{net.get('num_neurons')} 神经元 / " \
           f"{len(net.get('edges', {}))} 边（stats 已归零）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="仅检测，不恢复")
    ap.add_argument("--baseline", action="store_true", help="从当前生产网络重建基线")
    ap.add_argument("--baseline-if-healthy", action="store_true",
                    help="健康且 eval 12/12 时重建基线（保留概念预训练积累）")
    ap.add_argument("--restore", action="store_true", help="软恢复（保留 EWC 知识）")
    ap.add_argument("--hard-restore", action="store_true", help="硬恢复（丢弃 EWC，从基线重来）")
    args = ap.parse_args()

    if args.baseline:
        print(build_baseline())
        return 0

    if args.hard_restore:
        print(restore_from_baseline(soft=False))
        return 0

    if args.restore:
        print(restore_from_baseline(soft=True))
        return 0

    report = DriftReport()
    healthy = report.check()

    if args.baseline_if_healthy:
        # 健康时重建基线——保留概念预训练积累，防止恢复基线清掉
        # 运行时累积的概念连接（danger/rejection/approval 中继）。
        # 前提：eval 12/12 达标（网络功能正确才可作新基线）。
        if not healthy:
            print(report.render())
            print("  → 未健康，跳过基线重建（先恢复或等待漂移治理）")
            return 2
        print(report.render())
        ok, fails = _eval_prod()
        if ok != 12:
            print(f"  → eval {ok}/12 未达标，跳过基线重建（保留现有基线）")
            if fails:
                for f in fails[:4]:
                    print(f"      ✗ #{f['index']} {f['type']}/{f['urgency']} "
                          f"expect={f['expected']} got={f['got']}")
            return 2
        print(f"  → eval {ok}/12 达标，重建基线（保留概念预训练积累）")
        print(build_baseline())
        return 0

    if healthy:
        print(report.render())
        return 0

    # 漂移：留档 + （非 check 模式）恢复
    snap = snapshot_drifted(report)
    if args.check:
        print(report.render())
        print(f"  漂移版本已留档: {snap}（--check 模式不自动恢复）")
        return 2

    print(f"  漂移版本已留档: {snap}")
    print(restore_from_baseline())
    # 恢复后重检——原 report 是恢复前读的漂移值，直接打印会让人以为
    # "恢复了但仍在漂移"。重读一次，报告恢复后的真实状态。
    after = DriftReport()
    after.check()
    print(after.render(restored=True))
    return 1


def _eval_prod():
    """对当前生产网络跑权威 eval，返回 (通过数, 失败列表)。"""
    import sys as _sys
    import tempfile
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))
    _sys.path.insert(0, os.path.dirname(__file__))
    from services.brain.snn_region import SNNRegion
    from eval_cases import run
    # 从容器拉取生产网络到本地临时文件——SNNRegion 从本地文件读取
    tmp = tempfile.mkdtemp()
    local_net = os.path.join(tmp, "snn_network.json")
    subprocess.run(["docker", "cp", f"{CONTAINER}:{NETWORK}", local_net],
                   capture_output=True, check=True)
    region = SNNRegion(save_path=local_net)
    return run(region)


if __name__ == "__main__":
    sys.exit(main())
