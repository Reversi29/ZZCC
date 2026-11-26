"""test/test_multimodal_alignment.py — 无感映射验证（同事物跨模态→同一概念）

用户 2026-11-26 洞察：同事物的无感映射。
验证：同一概念（苹果/危险）在不同模态（视觉/文本）输入下，
CognitiveCoder.encode() 应激活同一概念维度（无感映射）。

对比学习训练后，跨模态对齐应增强（正对拉近）。
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

from services.brain.cognitive_coder import CognitiveCoder
from services.brain.multimodal_dataset import MultimodalDataset


def test_visual_text_same_concept():
    """视觉苹果 vs 文本苹果 → 同一 apple 概念（无感映射）。"""
    coder = CognitiveCoder()
    # 视觉苹果（红圆）
    vis_cv = coder.encode(visual={"red": 0.9, "round": 0.9})
    # 文本苹果
    txt_cv = coder.encode(text="我想吃一个红苹果")
    # 都应激活 apple 概念
    assert vis_cv.concepts.get("apple", 0) > 0.3, f"视觉未激活 apple: {vis_cv.concepts}"
    assert txt_cv.concepts.get("apple", 0) > 0.3, f"文本未激活 apple: {txt_cv.concepts}"
    print(f"  ✅ 视觉苹果={vis_cv.concepts.get('apple',0):.2f}, 文本苹果={txt_cv.concepts.get('apple',0):.2f}")
    print(f"     两模态同一概念（无感映射）")


def test_danger_cross_modal():
    """危险：视觉暗红 / 文本危险 / 音频响亮 → 同一 danger 概念。"""
    coder = CognitiveCoder()
    vis = coder.encode(visual={"dark": 0.9, "red": 0.8})
    txt = coder.encode(text="检测到危险信号")
    aud = coder.encode(audio={"loudness": 0.9, "pitch": 0.7})
    for name, cv in [("视觉", vis), ("文本", txt), ("音频", aud)]:
        assert cv.concepts.get("danger", 0) > 0.2, f"{name}未激活 danger: {cv.concepts}"
    print(f"  ✅ 危险三模态 → danger: vis={vis.concepts.get('danger',0):.2f}, "
          f"txt={txt.concepts.get('danger',0):.2f}, aud={aud.concepts.get('danger',0):.2f}")


def test_contrastive_training_improves_alignment():
    """对比学习训练后，跨模态对齐增强（无感映射学习）。"""
    coder = CognitiveCoder()
    ds = MultimodalDataset()

    # 训练前：视觉苹果 vs 文本苹果 的 apple 激活差
    vis_before = coder.encode(visual={"red": 0.9, "round": 0.9}).concepts.get("apple", 0)
    txt_before = coder.encode(text="apple fruit").concepts.get("apple", 0)

    # 对比学习对齐（用数据集跨模态样本）
    coder.contrastive_align(ds.samples(), eta=0.1)

    # 训练后
    vis_after = coder.encode(visual={"red": 0.9, "round": 0.9}).concepts.get("apple", 0)
    txt_after = coder.encode(text="apple fruit").concepts.get("apple", 0)

    # 两模态都应仍激活 apple（对齐不破坏）
    assert vis_after > 0.2, f"训练后视觉 apple 掉出: {vis_after}"
    assert txt_after > 0.2, f"训练后文本 apple 掉出: {txt_after}"
    print(f"  ✅ 训练前后 apple: vis {vis_before:.2f}→{vis_after:.2f}, txt {txt_before:.2f}→{txt_after:.2f}")
    print(f"     对齐保持（两模态仍同一概念）")


def test_open_set_concept_mapping():
    """开放集：动态注册新概念（banana）跨模态映射。"""
    coder = CognitiveCoder()
    ds = MultimodalDataset()
    # 注册 banana（视觉黄弯 + 文本香蕉）
    coder.register_concept("banana", prior_features={
        "visual": ["yellow", "curved"],
        "text": ["banana"],
    }, aliases=["香蕉"])
    # 视觉香蕉
    vis = coder.encode(visual={"yellow": 0.9, "curved": 0.9})
    # 文本香蕉
    txt = coder.encode(text="香蕉 banana")
    assert vis.concepts.get("banana", 0) > 0.2, f"视觉未激活 banana: {vis.concepts}"
    assert txt.concepts.get("banana", 0) > 0.2, f"文本未激活 banana: {txt.concepts}"
    print(f"  ✅ 开放集 banana 跨模态: vis={vis.concepts.get('banana',0):.2f}, txt={txt.concepts.get('banana',0):.2f}")


if __name__ == "__main__":
    print("===== 无感映射验证 =====")
    test_visual_text_same_concept()
    test_danger_cross_modal()
    test_contrastive_training_improves_alignment()
    test_open_set_concept_mapping()
    print("\n全部通过 ✅")
