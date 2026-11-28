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
    def _load_rgba(path: str):
        """加载图像并合成对比色背景，返回 RGB 像素列表和 (w, h)。

        透明 PNG 不能直接 convert("RGB")——透明像素会被当成黑色 (0,0,0)，
        导致黑色线条图标整图全黑、特征坍缩。正确做法：合成对比色背景。
        线条为深色→白底；线条为浅色（白色图标，深色 UI 用）→黑底。
        自动检测：非透明像素平均亮度 >128 用黑底，否则白底。
        """
        from PIL import Image
        raw = Image.open(path).convert("RGBA")
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
        return list(img.getdata()), 64, 64

    @staticmethod
    def _stats_from_pixels(px, w: int, h: int) -> Dict[str, float]:
        """从像素网格统计视觉特征。通用（全图/窗口）。

        Args:
            px: 像素列表（RGB 三元组），行优先
            w, h: 网格宽高

        Returns:
            视觉特征字典（同 image() 返回，但 edge 按 w 归一化）。
            注意：edge 归一化分母用窗口宽度（局部边缘密度相对窗口尺度），
            全图仍用 0.42（兼容现状）；窗口用窗口宽度的相对密度。
        """
        n = len(px)
        if n == 0:
            return {}
        # 颜色均值
        r = sum(p[0] for p in px) / n / 255.0
        g = sum(p[1] for p in px) / n / 255.0
        b = sum(p[2] for p in px) / n / 255.0

        # 亮度/饱和度
        bright, sat_sum = 0.0, 0.0
        for p in px:
            mx, mn = max(p), min(p)
            lum = 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
            bright += lum / 255.0
            sat_sum += (mx - mn) / 255.0
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
                hh = ((p[1] - p[2]) / d) % 6
            elif mx == p[1]:
                hh = (p[2] - p[0]) / d + 2
            else:
                hh = (p[0] - p[1]) / d + 4
            idx = min(HUE_BINS - 1, int(hh * HUE_BINS / 6))
            hues[idx] += d / 255.0
        hue_tot = sum(hues) or 1.0

        # 前景掩码：亮度偏离「众数亮度」的像素（众数而非均值，防小面积前景拉走）
        lum_hist = [0] * 256
        lums_raw = [0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in px]
        for lv in lums_raw:
            lum_hist[min(255, int(lv))] += 1
        mode_lum = max(range(256), key=lambda k: lum_hist[k])
        fg = [i for i, lv in enumerate(lums_raw) if abs(lv - mode_lum) > 24]
        use = fg if 8 < len(fg) < n * 0.75 else list(range(n))
        uf = len(use)
        cx = sum(i % w for i in use) / uf
        cy = sum(i // w for i in use) / uf
        radii = [math.sqrt((i % w - cx) ** 2 + (i // w - cy) ** 2) for i in use]
        rmean = sum(radii) / uf
        rstd = math.sqrt(sum((r - rmean) ** 2 for r in radii) / uf)
        radius_circular = _norm(1.0 - rstd / max(1e-6, rmean))

        # 外接框填充率
        xs = [i % w for i in use]
        ys = [i // w for i in use]
        bbox_area = (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)
        bbox_fill = _norm(uf / max(1, bbox_area))
        roundness = 0.5 * radius_circular + 0.5 * bbox_fill

        # 边缘密度：跨前景边界像素比例（归一化防饱和）
        edge_n = 0
        for i in range(n):
            x, y = i % w, i // w
            if x < w - 1 and abs(lums_raw[i + 1] - lums_raw[i]) > 26:
                edge_n += 1
            if y < h - 1 and abs(lums_raw[i + w] - lums_raw[i]) > 26:
                edge_n += 1
        # 归一化分母：全图用 0.42（兼容现状，防截断）；窗口用相对密度（局部尺度）
        edge = _norm(edge_n / n / 0.42)

        return {
            "red": _norm(r),
            "green": _norm(g),
            "blue": _norm(b),
            "round": _norm(roundness),
            "square": _norm(1.0 - roundness) * 0.8,
            "large": _norm(bbox_fill),
            "small": _norm(1.0 - bbox_fill),
            "bright": _norm(bright),
            "dark": _norm(1.0 - bright),
            "edge": edge,
            "saturation": _norm(sat),
            **{f"hue_{i}": _norm(h / hue_tot / max(1.0, n / 40))
               for i, hh in enumerate(hues)},
        }

    @staticmethod
    def image(path: str) -> Dict[str, float]:
        """提取图像特征（颜色直方图 + 形状 + 边缘）——全图统计。"""
        try:
            from PIL import Image
        except Exception:
            return {}
        try:
            px, w, h = MultimodalExtractor._load_rgba(path)
        except Exception:
            return {}
        return MultimodalExtractor._stats_from_pixels(px, w, h)

    @staticmethod
    def image_window(path: str, center_x: float, center_y: float, radius: float) -> Dict[str, float]:
        """提取图像指定窗口的局部特征（主动感知 Phase 1：注意力窗口）。

        Args:
            path: 图像路径
            center_x, center_y: 窗口中心（0-1 归一化坐标）
            radius: 窗口半径（0-1 归一化，相对全图）

        Returns:
            窗口局部特征字典（同 image() 结构，但仅统计窗口内像素）。
            窗口外像素不计入。用于注意力驱动的稀疏感知：
            每次只看窗口区域，SNN 逐窗口处理。

        设计（active_perception_phase1.md 4.1）：
        - 窗口中心由注意力控制器给出（可学习坐标，0-1 归一化）
        - 窗口半径自适应（多尺度池选尺度，见 4.2）
        - 返回窗口局部特征（非全图统计），空间结构在窗口内保留
        """
        try:
            from PIL import Image
        except Exception:
            return {}
        try:
            px, w, h = MultimodalExtractor._load_rgba(path)
        except Exception:
            return {}
        # 窗口中心/半径转像素坐标（0-1 归一化 → 像素）
        ccx = int(max(0, min(1, center_x)) * w)
        ccy = int(max(0, min(1, center_y)) * h)
        rr = max(1, int(max(0, min(1, radius)) * min(w, h)))
        # 窗口边界（裁剪到图内）
        x0 = max(0, ccx - rr)
        x1 = min(w, ccx + rr)
        y0 = max(0, ccy - rr)
        y1 = min(h, ccy + rr)
        if x1 <= x0 or y1 <= y0:
            return {}
        # 裁剪窗口像素（行优先，窗口尺寸 = x1-x0, y1-y0）
        ww = x1 - x0
        wh = y1 - y0
        win_px = []
        for y in range(y0, y1):
            row_start = y * w + x0
            win_px.extend(px[row_start:row_start + ww])
        return MultimodalExtractor._stats_from_pixels(win_px, ww, wh)

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