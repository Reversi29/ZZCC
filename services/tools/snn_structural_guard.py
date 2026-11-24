#!/usr/bin/env python3
"""结构可塑性演化护栏(闭环)。

检测: 动态区演化是否破坏 eval。
判据: eval < 12(权威用例) 且 动态区有演化(dyn_pruned_total/dyn_grown_total>0
      或 dyn_step_spread>0) → 结构可塑性是嫌疑, 触发回退。

回退: 禁用结构可塑性(写入网络文件 enable_structural_plasticity=False),
      记录漂移快照供人工审查, 保留网络状态(不硬恢复权重——演化本身不删边,
      只是参数扰动)。

与 snn_drift_guard.py 互补:
- drift_guard: 权重漂移/拓扑膨胀(网络自身状态退化)
- structural_guard: 结构可塑性演化破坏 eval(演化参数不当)

用法:
  snn_structural_guard.py              # 检测 + 必要时回退
  snn_structural_guard.py --check      # 仅检测, 不回退
  snn_structural_guard.py --enable     # 重新启用结构可塑性(审查后手动)

退出码: 0=健康, 1=已回退, 2=需介入(且 --check)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

CONTAINER = "nebula-interface"
DATA_DIR = "/app/config_data"
NETWORK = f"{DATA_DIR}/snn_network.json"
STATS = f"{DATA_DIR}/snn_network_stats.json"
STRUCT_SNAPSHOT = f"{DATA_DIR}/snn_structural_drifted_%s.json"

# eval 判据: 权威 12 用例, 掉分即嫌疑
EVAL_THRESHOLD = 12


def docker_exec(args, check=True):
    r = subprocess.run(["docker", "exec", CONTAINER] + args,
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"docker exec 失败: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def read_file(path):
    try:
        return docker_exec(["cat", path])
    except Exception:
        return None


def write_file(path, content):
    docker_exec(["sh", "-c",
                 f"cat > {path} <<'ZZCC_GUARD_EOF'\n{content}\nZZCC_GUARD_EOF"])


def get_eval_score():
    """在容器内跑 eval_cases.run, 返回 (通过数, 失败列表)。"""
    # eval_cases 在 tools 下, 容器内路径需确认
    cmd = (
        "cd /app && python3 -c "
        "\"import sys; sys.path.insert(0,'/app/tools'); "
        "sys.path.insert(0,'/app/interface'); "
        "from eval_cases import run; "
        "from services.brain.snn_region import SNNRegion; "
        "r=SNNRegion(save_path='/app/config_data/snn_network.json'); "
        "ok,f=run(r); print(ok, json.dumps(f))\""
    )
    try:
        out = docker_exec(["sh", "-c", cmd])
        parts = out.strip().rsplit(" ", 1)
        ok = int(parts[0])
        fails = json.loads(parts[1]) if len(parts) > 1 else []
        return ok, fails
    except Exception as e:
        print(f"  eval 执行失败: {e}")
        return None, []


def get_dyn_stats():
    """读容器内 stats 文件, 返回动态区演化统计。"""
    raw = read_file(STATS)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return {
        "dyn_edges": data.get("dyn_edges", 0),
        "dyn_step_spread": data.get("dyn_step_spread", 0),
        "dyn_pruned_total": data.get("dyn_pruned_total", 0),
        "dyn_grown_total": data.get("dyn_grown_total", 0),
    }


def is_evolution_active(dyn):
    """动态区是否真的演化过。"""
    return (dyn.get("dyn_pruned_total", 0) > 0
            or dyn.get("dyn_grown_total", 0) > 0
            or dyn.get("dyn_step_spread", 0) > 0)


def rollback_structural():
    """回退: 禁用结构可塑性, 记录快照。"""
    raw = read_file(NETWORK)
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except Exception:
        return False
    # 记录漂移快照
    snap = STRUCT_SNAPSHOT % time.strftime("%Y%m%d_%H%M%S")
    write_file(snap, raw)
    print(f"  已记录结构漂移快照: {snap}")
    # 禁用结构可塑性
    data["enable_structural_plasticity"] = False
    write_file(NETWORK, json.dumps(data, ensure_ascii=False, indent=2))
    print("  已禁用 enable_structural_plasticity")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="仅检测, 不回退")
    ap.add_argument("--enable", action="store_true", help="重新启用结构可塑性")
    args = ap.parse_args()

    if args.enable:
        raw = read_file(NETWORK)
        if not raw:
            print("无法读取网络文件")
            return 2
        data = json.loads(raw)
        data["enable_structural_plasticity"] = True
        write_file(NETWORK, json.dumps(data, ensure_ascii=False, indent=2))
        print("已重新启用结构可塑性(需人工确认 eval 恢复 12/12)")
        return 0

    print("=== 结构可塑性演化护栏 ===")
    dyn = get_dyn_stats()
    print(f"  动态区统计: 边={dyn.get('dyn_edges',0)}, "
          f"步长展布={dyn.get('dyn_step_spread',0)}, "
          f"修剪累计={dyn.get('dyn_pruned_total',0)}, "
          f"生长累计={dyn.get('dyn_grown_total',0)}")

    if not is_evolution_active(dyn):
        print("  动态区无演化, 结构可塑性未扰动, 健康 ✓")
        return 0

    ok, fails = get_eval_score()
    print(f"  eval: {ok}/{EVAL_THRESHOLD}")
    if ok is None:
        print("  eval 无法执行, 跳过(非致命)")
        return 0

    if ok >= EVAL_THRESHOLD:
        print(f"  eval {ok}/12 保持, 演化健康 ✓")
        return 0

    # eval 掉分且动态区有演化 → 结构可塑性嫌疑
    print(f"  ⚠️ eval {ok}/12 掉分 且 动态区演化活跃 → 结构可塑性嫌疑")
    print(f"  失败: {fails}")
    if args.check:
        print("  --check 模式, 不回退。退出码 2。")
        return 2
    if rollback_structural():
        print("  已回退(禁用结构可塑性)")
        return 1
    print("  回退失败")
    return 2


if __name__ == "__main__":
    sys.exit(main())
