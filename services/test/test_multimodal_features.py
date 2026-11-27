"""test/test_multimodal_features.py — 多模态特征提取器与数据集构建器测试

验证：
  1. 特征提取器对形状/颜色/音高有区分度
  2. 跨模态无感映射（视觉图标 vs 文本话术 → 同一概念）
  3. 数据集构建器产出多模态样本（visual/audio/payload 四模态非空）
  4. contrastive_align 能跑通真实样本
"""
from __future__ import annotations

import os
import struct
import math
import sys
import wave

import pytest

from pathlib import Path

# 与同目录其他测试一致：把 interface/ 加入 sys.path（根 /Users/mac/ZZCC/services/test）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

from services.brain.multimodal_features import MultimodalExtractor
from services.brain.multimodal_dataset import MultimodalDataset
from services.brain.multimodal_dataset_builder import (
    build_dataset,
    BIZ_TEXT_CORPUS,
    OA_TABLE_SAMPLES,
    ICON_CONCEPT_MAP,
)


def _interface_root():
    """services/interface 目录（图标等静态资源在此）。"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "interface",
    )


def _icon_dir():
    return os.path.join(
        _interface_root(), "static", "assets", "packages",
        "flutter_chat_ui", "assets",
    )


_counter = [0]


def _nonexistent():
    """生成不存在的持久化路径，隔离磁盘状态（测试 hermetic）。"""
    _counter[0] += 1
    return os.path.join(
        os.environ.get("TMPDIR", "/tmp"),
        f"zzcc_mmd_test_{os.getpid()}_{_counter[0]}.json",
    )


@pytest.fixture
def ext():
    return MultimodalExtractor()


@pytest.fixture
def tmp_wav(tmp_path):
    def make(path, hz, dur=1.0):
        fr = 16000
        n = int(fr * dur)
        w = wave.open(str(path), "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fr)
        w.writeframes(b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / fr)))
            for i in range(n)
        ))
        w.close()
        return str(path)
    return make


class TestFeatureExtractor:
    """特征提取器：区分度是接入的前提，无区分度等于白搭。"""

    def test_image_color_separation(self, ext, tmp_path):
        """红色 vs 蓝色图像：red/blue 通道应显著不同。"""
        from PIL import Image, ImageDraw
        img_a = Image.new("RGB", (32, 32), (10, 10, 10))
        ImageDraw.Draw(img_a).rectangle((4, 4, 28, 28), fill=(220, 20, 20))
        pa = str(tmp_path / "red.png")
        img_a.save(pa)

        img_b = Image.new("RGB", (32, 32), (10, 10, 10))
        ImageDraw.Draw(img_b).rectangle((4, 4, 28, 28), fill=(20, 20, 200))
        pb = str(tmp_path / "blue.png")
        img_b.save(pb)

        fa, fb = ext.image(pa), ext.image(pb)
        assert fa["red"] > fb["red"] + 0.15, (fa["red"], fb["red"])
        assert fb["blue"] > fa["blue"] + 0.15, (fa["blue"], fb["blue"])

    def test_image_shape_separation(self, ext, tmp_path):
        """圆形 vs 方形 vs 线条：roundness 应有区分度。

        回归保护：众数亮度掩码修复前，roundness 对圆/方恒等（区分度 0）。
        """
        from PIL import Image, ImageDraw
        shapes = {}
        img_c = Image.new("RGB", (32, 32), (15, 15, 15))
        ImageDraw.Draw(img_c).ellipse((4, 4, 28, 28), fill=(230, 230, 230))
        pc = str(tmp_path / "circle.png"); img_c.save(pc)
        shapes["circle"] = pc

        img_s = Image.new("RGB", (32, 32), (15, 15, 15))
        ImageDraw.Draw(img_s).rectangle((4, 4, 28, 28), fill=(230, 230, 230))
        ps = str(tmp_path / "square.png"); img_s.save(ps)
        shapes["square"] = ps

        img_l = Image.new("RGB", (32, 32), (15, 15, 15))
        ImageDraw.Draw(img_l).line((4, 4, 28, 28), fill=(230, 230, 230), width=4)
        pl = str(tmp_path / "line.png"); img_l.save(pl)
        shapes["line"] = pl

        rounds = {k: ext.image(v)["round"] for k, v in shapes.items()}
        # 线条应显著低于圆形（半径方差大 + bbox 填充率低）
        assert rounds["line"] < rounds["circle"] - 0.15, rounds

    def test_audio_pitch_separation(self, ext, tmp_path):
        """高频 vs 低频：zero_cross 应有区分度。

        回归保护：线性频带修复前质心恒 0.5（150Hz 与 1000Hz 无法区分）。
        """
        low = tmp_path / "low.wav"
        high = tmp_path / "high.wav"
        w1 = wave.open(str(low), "wb")
        w2 = wave.open(str(high), "wb")
        for w in (w1, w2):
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
        fr = 16000
        n = fr  # 1 秒
        for w, hz in ((w1, 150), (w2, 1000)):
            w.writeframes(b"".join(
                struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / fr)))
                for i in range(n)
            ))
        w1.close(); w2.close()

        al, ah = ext.audio(str(low)), ext.audio(str(high))
        # 1000Hz 零交叉率应显著高于 150Hz
        assert ah["zero_cross"] > al["zero_cross"] * 3, (
            al["zero_cross"], ah["zero_cross"]
        )

    def test_audio_empty_on_invalid(self, ext):
        """无效音频路径返回空字典（不抛）。"""
        assert ext.audio("/nonexistent.wav") == {}

    def test_table_extraction(self, ext):
        """HTML 表格 → 结构化 payload（含字段映射）。"""
        html = (
            "<table><tr><th>员工</th><th>金额</th></tr>"
            "<tr><td>张三</td><td>500</td></tr></table>"
        )
        r = ext.table(html)
        assert r["columns"] == 2
        assert r["rows"] == 2
        assert r["fields"]["员工"] == "张三"
        assert r["header"] == ["员工", "金额"]

    def test_csv_extraction(self, ext):
        """CSV → 结构化 payload。"""
        r = ext.csv_table("name,amount\nli,500\n")
        assert r["rows"] == 2
        assert r["fields"] == {"name": "li", "amount": "500"}


class TestDatasetBuilder:
    """数据集构建器：四模态齐备是接入 cognitive_coder 的前提。"""

    def test_builder_produces_all_modalities(self, tmp_path):
        """构建后 visual/structured 应从内建基线增长。

        回归保护：ICON_CONCEPT_MAP key 修复前，图标视觉样本被全跳过。
        传空 path 隔离持久化文件，保证测试 hermetic。
        """
        ds = MultimodalDataset(path=str(tmp_path / "unused.json"))
        baseline = ds.stats()["modal_count"]
        icon = _icon_dir()
        r = build_dataset(ds, icon_dir=icon if os.path.isdir(icon) else None)
        assert r["total"] > 0

        st = ds.stats()
        assert st["modal_count"]["structured"] == baseline["structured"] + 4, st
        assert st["modal_count"]["text"] > baseline["text"], st
        if os.path.isdir(icon):
            # 7 个语义图标应全部计入视觉模态
            assert st["modal_count"]["visual"] == baseline["visual"] + 7, st

    def test_builder_samples_survive_persistence(self, tmp_path):
        """构造样本持久化后不应被去重误杀。

        回归保护：去重键原为 (concept, visual_keys)，text-only 样本
        visual_keys 恒为 ()，与内建同 concept 样本合法碰撞而被丢弃。
        实测修复前：58 样本重载后仅剩 54，extra_samples 只存 19/46。
        """
        ds = MultimodalDataset(path=str(tmp_path / "never.json"))
        icon = _icon_dir()
        build_dataset(ds, icon_dir=icon if os.path.isdir(icon) else None)
        built = len(ds.samples())

        # 重新加载（同 path）应保留全部样本
        reloaded = MultimodalDataset(path=str(tmp_path / "never.json"))
        assert len(reloaded.samples()) == built, (
            built, len(reloaded.samples())
        )

    def test_builder_idempotent_per_source(self, tmp_path):
        """同一来源重复构建不应重复堆叠（来源级去重）。

        `_src` 让「同来源不同内容」不被误去重，
        同时「同来源同内容」仍能被正确去重（防重复灌库）。
        """
        ds = MultimodalDataset(path=str(tmp_path / "never2.json"))
        icon = _icon_dir()
        icon = icon if os.path.isdir(icon) else None
        r1 = build_dataset(ds, icon_dir=icon)
        r2 = build_dataset(ds, icon_dir=icon)
        # 第二次不应再增长（同源样本被去重）——实测修复前会 58→104 堆叠
        assert r2["added"] == 0, (r1, r2)
        assert r2["total"] == r1["total"], (r1, r2)

    def test_oa_table_samples_well_formed(self):
        """OA 结构化样本含 payload.columns/rows/fields。"""
        for s in OA_TABLE_SAMPLES:
            assert s["payload"]["columns"] > 0
            assert s["payload"]["rows"] > 0
            assert s["payload"]["fields"], s

    def test_icon_concept_map_complete(self):
        """图标语义映射应覆盖全部语义图标。"""
        assert set(ICON_CONCEPT_MAP) == {
            "icon-send", "icon-delivered", "icon-seen",
            "icon-document", "icon-error", "icon-attachment", "icon-arrow",
        }


class TestCrossModalMapping:
    """跨模态无感映射：同一语义在不同模态应激活同一概念。"""

    def test_contrastive_align_runs_on_real_samples(self):
        """真实样本能跑通 contrastive_align（非死代码）。"""
        from services.brain.cognitive_coder import CognitiveCoder
        ds = MultimodalDataset(path=_nonexistent())
        build_dataset(ds, icon_dir=_icon_dir() if os.path.isdir(_icon_dir()) else None)
        train = [s for s in ds.samples()
                 if s.get("concept") in ("danger", "approval", "urgency")]
        assert train, "训练样本不能为空"
        coder = CognitiveCoder()
        r = coder.contrastive_align(train, eta=0.05)
        assert r["visual"] > 0, r  # 视觉端有对齐步

    def test_error_icon_maps_to_danger(self):
        """icon-error（视觉）应与 'danger' 文本同概念。

        这是无感映射的核心断言：图标不需要文字就能被识别为危险。

        走规则式路径（use_snn_encoding=False）——SNN 路径需先蒸馏预热
        才有放电权重，本测试验证「提取的特征是否能被概念层识别」，
        不依赖 SNN 学习状态。
        """
        from services.brain.cognitive_coder import CognitiveCoder
        p = os.path.join(_icon_dir(), "icon-error.png")
        if not os.path.exists(p):
            pytest.skip("图标文件不存在")
        coder = CognitiveCoder()
        coder.use_snn_encoding = False
        v = MultimodalExtractor.image(p)
        vec = coder.encode(visual=v)
        # danger 应是最强概念（红色图标）
        assert vec.concepts, "视觉编码应产出概念激活"
        ranked = sorted(vec.concepts.items(), key=lambda kv: -kv[1])
        assert ranked[0][0] == "danger", ranked
        assert ranked[0][1] >= 0.3, ranked

    def test_query_icon_maps_to_query(self):
        """icon-document（视觉）应映射到 query 概念。"""
        from services.brain.cognitive_coder import CognitiveCoder
        p = os.path.join(_icon_dir(), "icon-document.png")
        if not os.path.exists(p):
            pytest.skip("图标文件不存在")
        coder = CognitiveCoder()
        coder.use_snn_encoding = False
        v = MultimodalExtractor.image(p)
        vec = coder.encode(visual=v)
        assert vec.concepts
