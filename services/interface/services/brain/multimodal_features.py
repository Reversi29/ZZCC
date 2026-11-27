"""services/brain/multimodal_features.py — 多模态离线特征提取器

把真实图像/音频/表格/文本压成 cognitive_coder.encode() 能吃的轻量特征字典。

设计约束（实测，见 DEVELOPMENT 记录）：
- 生产容器只有 numpy，无 torch/transformers → 容器内不能跑编码器
- 宿主机有 PIL + numpy + stdlib → 离线侧在这里提特征
- 特征字典纯 JSON 可序列化，落到 /app/config_data/multimodal_dataset.json

产出特征空间（与 cognitive_coder 的 modal_concepts 对齐）：
  visual: {red, green, blue, bright, dark, round, square, edge, saturation, hue_0..7}
  audio:  {loudness, pitch, rhythm, spectral_centroid, zero_cross}
  payload: {columns, rows, cells, fields:{name:value}}   ← 表格结构化

用法（离线）：
    from services.brain.multimodal_features import MultimodalExtractor
    ex = MultimodalExtractor()
    feats = ex.image(path)      # 图像 → visual
    feats = ex.audio(path)      # 音频 → audio
    feats = ex.table(html)      # HTML 表格 → payload
"""
from __future__ import annotations

import csv
import io
import math
import re
import struct
import wave
from typing import Any, Dict, List, Optional

# ── 视觉特征维度（固定，供概念向量对齐）──
HUE_BINS = 8
_EDGES = ("red", "green", "blue", "bright", "dark", "round", "square",
          "edge", "saturation")


def _norm(x: float) -> float:
    """夹紧到 [0,1]。"""
    return 0.0 if x <= 0 else (1.0 if x >= 1 else float(x))


class MultimodalExtractor:
    """多模态特征提取器：纯 stdlib + PIL + numpy，无重依赖。"""

    # ── 图像 → visual ──
    @staticmethod
    def image(path: str) -> Dict[str, float]:
        """提取图像特征（颜色直方图 + 形状 + 边缘）。"""
        try:
            from PIL import Image
        except Exception:
            return {}
        # 关键：透明 PNG 不能直接 convert("RGB")——透明像素会被当成黑色 (0,0,0)，
        # 导致黑色线条图标整图全黑、特征坍缩（edge/bright/颜色全 0，round 恒 0.81）。
        # 正确做法：合成对比色背景。线条为深色→白底；线条为浅色（白色图标，深色 UI 用）→黑底。
        # 自动检测：非透明像素平均亮度 >128 用黑底，否则白底。
        raw = Image.open(path).convert("RGBA")
        # 先用非透明像素判断线条明暗
        non_alpha = [p for p in raw.getdata() if p[3] > 0]
        if non_alpha:
            line_lum = sum(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in non_alpha) / len(non_alpha)
        else:
            line_lum = 0.0
        if line_lum > 128:  # 浅色线条（白色图标）→ 黑底
            bg_color = (0, 0, 0, 255)
        else:  # 深色线条（黑色图标）→ 白底
            bg_color = (255, 255, 255, 255)
        bg = Image.new("RGBA", raw.size, bg_color)
        img = Image.alpha_composite(bg, raw).convert("RGB")
        img = img.resize((64, 64))  # 降采样控成本
        px = list(img.getdata())
        n = len(px)

        # 颜色均值
        r = sum(p[0] for p in px) / n / 255.0
        g = sum(p[1] for p in px) / n / 255.0
        b = sum(p[2] for p in px) / n / 255.0

        # 亮度/饱和度
        bright, sat_sum, contrast_sum = 0.0, 0.0, 0.0
        for p in px:
            mx, mn = max(p), min(p)
            lum = 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
            bright += lum / 255.0
            sat_sum += (mx - mn) / 255.0
            contrast_sum += mx - mn
        bright /= n
        sat = sat_sum / n

        # 色相直方图（8 分箱）
        hues = [0.0] * HUE_BINS
        for p in px:
            mx, mn = max(p), min(p)
            d = mx - mn
            if d < 8:
                continue
            if mx == p[0]:
                h = ((p[1] - p[2]) / d) % 6
            elif mx == p[1]:
                h = (p[2] - p[0]) / d + 2
            else:
                h = (p[0] - p[1]) / d + 4
            idx = min(HUE_BINS - 1, int(h * HUE_BINS / 6))
            hues[idx] += d / 255.0
        hue_tot = sum(hues) or 1.0

        # 前景掩码：亮度偏离「众数亮度」的像素。
        # 众数而非均值——均值会被小面积前景拉走，导致阈值对圆/方不稳定
        # （实测均值基准：红圆 fg=100% 全选中，蓝方 fg=0% 全落空）
        lum_hist = [0] * 256
        lums_raw = [0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in px]
        for lv in lums_raw:
            lum_hist[min(255, int(lv))] += 1
        mode_lum = max(range(256), key=lambda k: lum_hist[k])
        fg = [i for i, lv in enumerate(lums_raw) if abs(lv - mode_lum) > 24]
        # 若前景过少/过多（整屏都是内容），退回全像素
        use = fg if 8 < len(fg) < n * 0.75 else list(range(n))
        uf = len(use)
        cx = sum(i % 64 for i in use) / uf
        cy = sum(i // 64 for i in use) / uf
        radii = [math.sqrt((i % 64 - cx) ** 2 + (i // 64 - cy) ** 2) for i in use]
        rmean = sum(radii) / uf
        rstd = math.sqrt(sum((r - rmean) ** 2 for r in radii) / uf)
        # 紧凑度 = 1 - 半径标准差/半径均值。圆形半径恒定→std 小；方形角上半径大→std 大
        radius_circular = _norm(1.0 - rstd / max(1e-6, rmean))

        # 外接框填充率：圆 π/4≈0.785，方≈1.0——比半径方差更稳的形状指标
        xs = [i % 64 for i in use]
        ys = [i // 64 for i in use]
        bbox_area = (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)
        bbox_fill = _norm(uf / max(1, bbox_area))
        roundness = 0.5 * radius_circular + 0.5 * bbox_fill

        # 边缘密度：跨前景边界的像素比例（归一化防饱和）
        edge_n = 0
        for i in range(n):
            x, y = i % 64, i // 64
            if x < 63 and abs(lums_raw[i + 1] - lums_raw[i]) > 26:
                edge_n += 1
            if y < 63 and abs(lums_raw[i + 64] - lums_raw[i]) > 26:
                edge_n += 1
        # 归一化分母 0.42：实测 7 图标原始密度 0.103~0.402，
        # 用 0.30 会把 attachment(1.34)/error(1.27)/send(1.12) 截断到 1.0，
        # 三个不同笔画密度压平成同一个值，区分度被丢弃。
        # 0.42 让最大值 0.402/0.42=0.957 恰好不触顶。
        edge = _norm(edge_n / n / 0.42)

        # 关键：必须产出 VISUAL_FEATURES 全部 9 键，否则 SNN 输入层丢弃未知特征
        # （认知层视觉 SNN 输入层固定 9 维，extra 键不影响但会漏激活）
        return {
            "red": _norm(r),
            "green": _norm(g),
            "blue": _norm(b),
            "round": _norm(roundness),
            "square": _norm(1.0 - roundness) * 0.8,
            # large/small 由前景占屏比（bbox 填充率）推导
            "large": _norm(bbox_fill),
            "small": _norm(1.0 - bbox_fill),
            "bright": _norm(bright),
            "dark": _norm(1.0 - bright),
            # 附加特征（供规则式 _visual_to_concepts 与非 SNN 路径使用）
            "edge": edge,
            "saturation": _norm(sat),
            **{f"hue_{i}": _norm(h / hue_tot / max(1.0, n / 40))
               for i, h in enumerate(hues)},
        }

    # ── 音频 → audio ──
    @staticmethod
    def audio(path: str) -> Dict[str, float]:
        """提取音频特征（响度 + 音高 + 节奏）。"""
        try:
            wf = wave.open(path, "rb")
        except Exception:
            return {}
        fr = wf.getframerate()
        ch = wf.getnchannels()
        wbits = wf.getsampwidth()
        n = wf.getnframes()
        raw = wf.readframes(n)
        wf.close()

        if wbits == 2:
            samples = list(struct.unpack("<%dh" % (len(raw) // 2), raw))
        elif wbits == 1:
            samples = [s - 128 for s in struct.unpack("<%dB" % len(raw), raw)]
        else:
            return {}
        if ch > 1:
            samples = samples[::ch]

        if not samples:
            return {}

        # 响度：RMS
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0

        # 零交叉率 → 音高近似
        zc = sum(1 for i in range(1, len(samples))
                 if (samples[i - 1] < 0) != (samples[i] < 0)) / max(1, len(samples))

        # 节奏：按 50ms 窗的能量起伏
        win = max(1, fr // 20)
        energy = []
        for i in range(0, len(samples) - win, win):
            seg = samples[i:i + win]
            energy.append(math.sqrt(sum(s * s for s in seg) / len(seg)) / 32768.0)
        rhythm = 0.0
        if len(energy) > 1:
            diff = sum(abs(energy[i + 1] - energy[i]) for i in range(len(energy) - 1))
            rhythm = diff / (len(energy) - 1)

        # 频谱质心（对数频带 DFT，避免低频挤在同一 bin）
        # 线性 bin 会把 150Hz 和 1000Hz 都落到 b=0 → 质心恒 0.5，无区分度
        # 改对数频率：bin k 中心频率 = 60 * 2^(k/2.13) Hz，覆盖 60Hz~8kHz
        step = max(1, len(samples) // 6000)
        subs = samples[::step]
        L = len(subs)
        bands: List[float] = []
        freqs: List[float] = []
        for k in range(8):
            f_hz = 60.0 * (2.0 ** (k / 2.13))
            freqs.append(f_hz)
            f = f_hz / fr  # 归一化到子采样后的采样率
            s = c = 0.0
            for i, v in enumerate(subs):
                ang = 2 * math.pi * f * i * step
                s += v * math.sin(ang)
                c += v * math.cos(ang)
            bands.append(math.sqrt(s * s + c * c))
        btot = sum(bands) or 1.0
        # 质心按对数频率加权 → 高频段自然拉开
        log_f = [math.log2(fx / 60.0) for fx in freqs]
        lrng = max(log_f) or 1.0
        centroid = sum(x / lrng * v for x, v in zip(log_f, bands)) / btot

        return {
            "loudness": _norm(rms * 4.0),
            "pitch": _norm(zc * 3.0),
            "rhythm": _norm(rhythm * 8.0),
            "spectral_centroid": _norm(centroid),
            "zero_cross": _norm(zc),
        }

    # ── HTML 表格 → payload ──
    @staticmethod
    def table(html: str) -> Dict[str, Any]:
        """HTML 表格 → 结构化 payload。"""
        from html.parser import HTMLParser

        class TP(HTMLParser):
            def __init__(self):
                super().__init__()
                self.rows: List[List[str]] = []
                self._row: Optional[List[str]] = None
                self._cell: Optional[str] = None

            def handle_starttag(self, tag, attrs):
                if tag == "tr":
                    self._row = []
                elif tag in ("td", "th") and self._row is not None:
                    self._cell = ""

            def handle_endtag(self, tag):
                if tag in ("td", "th") and self._cell is not None and self._row is not None:
                    self._row.append(self._cell.strip())
                    self._cell = None
                elif tag == "tr" and self._row is not None:
                    self.rows.append(self._row)
                    self._row = None

            def handle_data(self, data):
                if self._cell is not None:
                    self._cell += data

        try:
            tp = TP()
            tp.feed(html)
        except Exception:
            return {}

        rows = [r for r in tp.rows if any(c for c in r)]
        if not rows:
            return {}
        ncols = max(len(r) for r in rows)
        header = rows[0] if len(rows) > 1 else []
        fields: Dict[str, str] = {}
        for r in rows[1:]:
            for i, v in enumerate(r):
                if i < len(header) and header[i] and v:
                    fields[header[i]] = fields.get(header[i], v)

        return {
            "columns": ncols,
            "rows": len(rows),
            "cells": sum(len(r) for r in rows),
            "fields": fields,
            "header": header,
        }

    # ── CSV → payload ──
    @staticmethod
    def csv_table(text: str) -> Dict[str, Any]:
        """CSV 文本 → 结构化 payload。"""
        rows: List[List[str]] = []
        try:
            for r in csv.reader(io.StringIO(text)):
                rows.append(r)
        except Exception:
            return {}
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            return {}
        ncols = max(len(r) for r in rows)
        header = rows[0] if len(rows) > 1 else []
        fields: Dict[str, str] = {}
        for r in rows[1:]:
            for i, v in enumerate(r):
                if i < len(header) and header[i] and v:
                    fields[header[i]] = fields.get(header[i], v)
        return {
            "columns": ncols,
            "rows": len(rows),
            "cells": sum(len(r) for r in rows),
            "fields": fields,
            "header": header,
        }

    # ── 文本 → 标签（配合真实数据集的 caption 列）──
    @staticmethod
    def caption_of(row: Dict[str, Any], keys: List[str]) -> str:
        """从数据行取 caption/描述列。"""
        for k in keys:
            v = row.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""


__all__ = ["MultimodalExtractor", "HUE_BINS"]