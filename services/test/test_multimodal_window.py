"""测试主动感知 Phase 1：感受器窗口化（image_window）。

验证：
1. image() 全图统计无回归（保留现有特征结构）
2. image_window() 返回窗口局部特征（同结构，仅窗口内像素）
3. 窗口位置影响特征（不同窗口看到不同内容——注意力基础）
4. 窗口尺度影响特征（尺度变化改变信息量）
5. 窗口边界裁剪（窗口超出图内不出错）
"""
import os
import sys
from pathlib import Path

import pytest

# 与同目录其他测试一致：把 interface/ 加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from services.brain.multimodal_features import MultimodalExtractor

# 真实业务图标（静态资源，相对 interface/）
_ICON_DIR = str(Path(__file__).resolve().parents[1] / "interface" / "static" / "assets" / "packages" / "flutter_chat_ui" / "assets")


def _first_icon() -> str:
    icons = sorted(os.listdir(_ICON_DIR))
    pngs = [f for f in icons if f.endswith(".png")]
    assert pngs, f"无 PNG 图标: {_ICON_DIR}"
    return os.path.join(_ICON_DIR, pngs[0])


# ── 1. image() 全图无回归 ──
def test_image_full_stats_structure():
    """image() 应产出全部核心特征键，值在 [0,1]。"""
    feats = MultimodalExtractor.image(_first_icon())
    for key in ("red", "green", "blue", "round", "square", "large", "small",
                "bright", "dark", "edge", "saturation"):
        assert key in feats, f"缺特征 {key}"
        assert 0.0 <= feats[key] <= 1.0, f"{key} 越界: {feats[key]}"


# ── 2. image_window() 结构 ──
def test_image_window_structure():
    """image_window() 应返回同结构特征（窗口局部）。"""
    feats = MultimodalExtractor.image_window(_first_icon(), 0.5, 0.5, 0.3)
    assert feats, "窗口特征不应为空"
    for key in ("red", "green", "blue", "round", "square", "large", "small",
                "bright", "dark", "edge", "saturation"):
        assert key in feats, f"缺特征 {key}"
        assert 0.0 <= feats[key] <= 1.0, f"{key} 越界: {feats[key]}"


# ── 3. 窗口位置影响特征（注意力基础）──
def test_window_position_changes_features():
    """同一图标，不同窗口位置应产出不同特征（看到不同内容）。"""
    icon = _first_icon()
    f1 = MultimodalExtractor.image_window(icon, 0.2, 0.2, 0.2)
    f2 = MultimodalExtractor.image_window(icon, 0.8, 0.8, 0.2)
    assert f1 and f2
    # 至少一个特征有差异（不同窗口看到不同内容）
    diff = any(abs(f1.get(k, 0) - f2.get(k, 0)) > 0.01 for k in ("edge", "bright", "round"))
    assert diff, f"不同窗口特征完全一致，注意力失去意义: {f1} vs {f2}"


# ── 4. 窗口尺度影响特征 ──
def test_window_scale_changes_features():
    """同一位置，不同尺度应产出不同特征（信息量变化）。"""
    icon = _first_icon()
    f_small = MultimodalExtractor.image_window(icon, 0.5, 0.5, 0.1)
    f_large = MultimodalExtractor.image_window(icon, 0.5, 0.5, 0.5)
    assert f_small and f_large
    diff = any(abs(f_small.get(k, 0) - f_large.get(k, 0)) > 0.01
               for k in ("edge", "bright", "round"))
    assert diff, f"不同尺度特征完全一致: {f_small} vs {f_large}"


# ── 5. 窗口边界裁剪 ──
def test_window_clip_bounds():
    """窗口中心在角落（越界裁剪）不应报错，返回有效特征。"""
    icon = _first_icon()
    # 中心在 (0,0) 角落，半径大——窗口裁剪到图内
    feats = MultimodalExtractor.image_window(icon, 0.0, 0.0, 0.5)
    assert feats, "角落窗口应返回特征"
    # 中心/半径归一化越界（<0 或 >1）应被夹紧
    feats2 = MultimodalExtractor.image_window(icon, -0.5, 1.5, 2.0)
    assert feats2, "越界参数应被夹紧返回特征"


# ── 6. 窗口半径全图 ≈ 全图统计 ──
def test_window_full_radius_approx_full():
    """大窗口（r≈0.5，覆盖大半图）应接近全图统计（注意力聚焦大区域）。"""
    icon = _first_icon()
    full = MultimodalExtractor.image(icon)
    big = MultimodalExtractor.image_window(icon, 0.5, 0.5, 0.5)
    assert full and big
    # bright/round 应接近（大窗口信息量大）
    assert abs(full.get("bright", 0) - big.get("bright", 0)) < 0.1
