#!/usr/bin/env python3
"""SNN eval 回归测试——漂移的红灯。

与 snn_drift_guard.py 联动：护栏负责发现漂移并恢复，本脚本负责
把"漂移导致 eval 掉分"变成可观察的红灯。

两种模式：
  snn_eval_regression.py --local     # 干净拓扑（默认），应 12/12
  snn_eval_regression.py --prod      # 生产网络（容器），漂移时掉分

退出码：0=全通过, 1=有失败
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
import tempfile

# services/interface 根需可导入（models/ 与 services/ 均在其下，与容器 /app 一致）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_IFACE = os.path.join(_ROOT, "services", "interface")
sys.path.insert(0, _IFACE)

from eval_cases import EVAL_CASES, run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true",
                    help="干净拓扑模式（默认）")
    ap.add_argument("--prod", action="store_true", help="生产网络模式")
    args = ap.parse_args()

    if args.prod:
        from services.brain.snn_region import snn_region as region
        mode = "生产网络"
    else:
        from services.brain.snn_region import SNNRegion
        region = SNNRegion(save_path=tempfile.mkdtemp() + "/s.json")
        mode = "干净拓扑"

    print(f"===== SNN eval 回归（{mode}）=====")
    ok, fails = run(region)
    for f in fails:
        print(f"  ✗ #{f['index']:2d} {f['type']}/{f['urgency']} "
              f"期望 {f['expected']} 实得 {f['got']}")
    if not fails:
        print("  ✓ 全部通过")
    print(f"  == EVAL {ok}/{len(EVAL_CASES)} ==")
    return 0 if ok == len(EVAL_CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
