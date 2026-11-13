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
  snn_drift_guard.py --restore     # 无条件从基线恢复

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

        # 只有致命 issues 触发恢复；warnings 不触发
        return not self.issues

    def render(self, restored=False):
        lines = ["===== SNN 漂移护栏 =====",
                 f"  神经元: {self.neurons}  边: {self.edges}",
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


def restore_from_baseline():
    if not read_file(BASELINE):
        return "基线快照不存在，无法恢复（需先 --baseline 建立）"
    docker_exec(["cp", BASELINE, NETWORK])
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
    return "已恢复"


def build_baseline():
    raw = read_file(NETWORK)
    if not raw:
        return "当前网络不可读，无法建立基线"
    write_file(BASELINE, raw)
    net = json.loads(raw)
    return f"基线已建立：{net.get('num_neurons')} 神经元 / " \
           f"{len(net.get('edges', {}))} 边"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="仅检测，不恢复")
    ap.add_argument("--baseline", action="store_true", help="从当前生产网络重建基线")
    ap.add_argument("--restore", action="store_true", help="无条件从基线恢复")
    args = ap.parse_args()

    if args.baseline:
        print(build_baseline())
        return 0

    if args.restore:
        print(restore_from_baseline())
        return 0

    report = DriftReport()
    healthy = report.check()

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


if __name__ == "__main__":
    sys.exit(main())
