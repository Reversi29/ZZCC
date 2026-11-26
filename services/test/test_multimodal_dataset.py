"""test/test_multimodal_dataset.py — 多模态数据集 + 无感映射测试

覆盖用户 2026-11-26 洞察：
1. 同一概念的多模态表示（视觉/文本/音频）
2. 无感映射：不同模态 → 同一概念（编码验证）
3. 对比学习正/负对构造
4. 数据集持久化 + 动态扩充（开放集）
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

# 隔离配置目录
os.environ["BRAIN_CONFIG_DIR"] = tempfile.mkdtemp()

from services.brain.multimodal_dataset import (
    MultimodalDataset, MULTIMODAL_SAMPLES, build_contrastive_pairs,
)


def test_dataset_basic():
    """数据集基本结构：样本含多模态表示 + 概念标注。"""
    ds = MultimodalDataset()
    samples = ds.samples()
    assert len(samples) >= 10
    # 概念覆盖
    concepts = ds.concepts()
    assert "apple" in concepts
    assert "danger" in concepts
    # 多模态：至少一个样本同时有 visual+text
    multi = [s for s in samples if s.get("visual") and s.get("text")]
    assert len(multi) >= 1
    print(f"  ✅ 数据集 {len(samples)} 样本, {len(concepts)} 概念, {len(multi)} 多模态")


def test_labeled_format():
    """有监督标注：concept → concepts 字典。"""
    ds = MultimodalDataset()
    labeled = ds.labeled()
    assert len(labeled) >= 10
    for s in labeled:
        assert s.get("concepts"), f"样本缺 concepts 标注: {s.get('concept')}"
        assert s["concepts"].get(s["concept"]) == 0.9
    print(f"  ✅ labeled 样本 {len(labeled)} 条，concept 标注正确")


def test_by_concept():
    """按概念检索。"""
    ds = MultimodalDataset()
    apples = ds.by_concept("apple")
    assert len(apples) >= 2
    for s in apples:
        assert s["concept"] == "apple"
    print(f"  ✅ apple 样本 {len(apples)} 条")


def test_contrastive_pairs():
    """对比学习正/负对构造。"""
    ds = MultimodalDataset()
    pairs = build_contrastive_pairs(ds.samples())
    assert len(pairs["positive"]) >= 1, "应有跨模态正对"
    assert len(pairs["negative"]) >= 1, "应有跨概念负对"
    # 正对：同概念
    for p in pairs["positive"][:5]:
        assert p["anchor"]["concept"] == p["other"]["concept"]
    # 负对：异概念
    for p in pairs["negative"][:5]:
        assert p["anchor"]["concept"] != p["other"]["concept"]
    print(f"  ✅ 正对 {len(pairs['positive'])} / 负对 {len(pairs['negative'])}")


def test_persist_and_expand():
    """数据集持久化 + 动态扩充（开放集）。"""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "ds.json")
    ds = MultimodalDataset(path=path)
    n_before = len(ds.samples())
    # 动态扩充：新概念 banana
    ds.add_sample({
        "concept": "banana",
        "visual": {"yellow": 0.9, "curved": 0.9},
        "text": "香蕉 banana",
    })
    assert "banana" in ds.concepts()
    # 重新加载（持久化验证）
    ds2 = MultimodalDataset(path=path)
    assert len(ds2.samples()) == n_before + 1
    assert "banana" in ds2.concepts()
    print(f"  ✅ 扩充后 {len(ds2.samples())} 样本, banana 已持久化")


if __name__ == "__main__":
    print("===== 多模态数据集测试 =====")
    test_dataset_basic()
    test_labeled_format()
    test_by_concept()
    test_contrastive_pairs()
    test_persist_and_expand()
    print("\n全部通过 ✅")
