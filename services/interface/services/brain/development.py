"""services/brain/development.py — 发育式 SNN 结构形成（增殖→探索→分化）

用户 2026-11-26 洞察：
- 人脑神经元先增殖再分化，突触由无到有探索
- 当前 SNN 增值分化的骨架未形成（生产网络 40-199 区 160 神经元 0 内部边）
- 单网络自发分簇成脑区，加弱引导信号避免完全乱分化

本模块实现四阶段发育（详见 DEVELOPMENT.md）：

Stage 1  增殖期  : 大量生成未分化神经元（动态区扩容），不接线
Stage 2  突触探索: 突触从无到有，弱随机连接互相试探，STDP/强化收敛
Stage 3  分化期  : 自发分簇成功能脑区（感知/语义/决策）+ 弱引导

设计原则：
1. **不破坏现有 12/12**：发育只作用于动态区（40-199）与预留区，
   固定核心（0-39）完全不动（plasticity_core_freeze 已保护）
2. **弱引导**：标签/概念先验 + 共同激活 + 化学亲和梯度 + 侧向抑制，
   防完全乱分化（非纯随机）
3. **可观测**：阶段/分簇/边数/聚类统计可查（/brain/dev/status）
4. **渐进**：发育速率可调，默认保守（不突然改变网络行为）

v2 修订（2026-11-27）：修复"探索空转/骨架未形成"
- 分功能区配额探索（非全对遍历低 ID 集中）
- 功能链打通：输出区→概念区/核心输出（消除死端）
- 探索边权重重设 0.35-0.55（>keep_weight，骨架稳固）
- 步长演化接入发育（非全 1）

用法：
    dev = DevelopmentDriver(snn)
    dev.proliferate(n=50)            # 增殖
    dev.explore_synapses()           # 突触探索
    dev.differentiate()              # 分化
    dev.status()                     # 发育状态
"""
from __future__ import annotations

import logging
import math
import random
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from services.brain.snn import NeuronType

logger = logging.getLogger("brain.development")

# 发育区边界：动态区 40-199（输入槽 40-99 / 输出槽 100-199）
# 概念区 220+ 由 concept_registry 管理，不在发育驱动范围内
_DEV_START = 40
_DEV_INPUT_END = 99
_DEV_OUTPUT_START = 100
_DEV_OUTPUT_END = 199
_DEV_END = 199

# 功能链目标：核心输出神经元（决策输出 32-37）与概念区起点
_CORE_OUTPUTS = (32, 33, 34, 35, 36, 37)   # 决策输出层
_CONCEPT_START = 220                        # 概念区起点

# 发育参数（默认保守，不突然改变行为）
_DEFAULT_PARAMS = {
    "proliferate_size": 20,        # 每轮增殖神经元数
    "max_proliferate": 200,        # 增殖上限（动态区容量）
    # v2: 探索边权重提升到 0.35-0.55（> keep_weight=0.20），骨架稳固，停止空转
    "explore_weight_min": 0.35,    # 探索连接初始权重下限
    "explore_weight_max": 0.55,    # 探索连接初始权重上限
    "explore_step": 1,             # 探索连接初始步长（演化会调）
    "explore_prob": 0.08,          # 探索连接概率（每对神经元）
    "keep_weight": 0.20,           # 突触保留阈值（STDP 后 < 此值剪除）
    "cluster_hop": 3,              # 分簇 BFS 跳数
    "weak_guide": 0.3,             # 弱引导强度（0=纯随机, 1=强先验引导）
    "lateral_inhibition": 0.15,    # 侧向抑制强度
    "synapse_prune_every": 50,     # 突触修剪间隔（时间步）
    "min_cluster_size": 4,         # 最小功能簇大小
    "max_dev_edges": 120,          # 发育区最大内部边（防过度生长，667 边前科）
    "prune_ratio": 0.35,           # 每轮修剪最弱边的比例（收敛）
    # v2: 分功能区探索配额（每轮每功能区最大新边）
    "zone_quota": 12,              # 每功能区每轮探索配额
    # v2: 步长演化参数（发育路径）
    "step_evolve_enabled": True,   # 发育边是否演化步长
    "step_evolve_rate": 0.05,      # 步长演化速率（每轮）
    "step_evolve_cooldown": 50,    # 同一边两次演化最小间隔
    "step_min": 1,
    "step_max": 8,
    # v2: 输出链打通参数
    "ensure_output_chain": True,   # 确保输出区→核心输出/概念区连通
}


class DevelopmentDriver:
    """发育式结构形成驱动器。

    包装 SNN，提供增殖/突触探索/分化/修剪的发育操作。
    不替换现有推理，只在结构层生长。
    """

    def __init__(self, snn, params: Optional[Dict] = None):
        self.snn = snn
        self.p = dict(_DEFAULT_PARAMS)
        if params:
            self.p.update(params)
        self.stage = "embryo"        # embryo / proliferating / exploring / differentiated
        self.stage_history: List[str] = []
        self._stats = {
            "proliferated": 0,
            "explored_edges": 0,
            "pruned_edges": 0,
            "clusters": [],
            "guide_signals": 0,
            # v2 统计
            "zone_explored": {"input": 0, "output": 0, "concept": 0},
            "output_chain_edges": 0,
            "step_evolve_events": 0,
        }
        self._last_proliferate_time = 0
        self._step_change_time: Dict[Tuple[int, int], int] = {}
        # v2 修复：显式跟踪已增殖神经元 ID（不依赖 neuron_type 判断，
        # 因为 add_neuron 填充的中间神经元默认 EXCITATORY，会污染计数）
        self._proliferated_ids: Set[int] = set()

    # ── Stage 1: 增殖期 ──────────────────────────────────
    def proliferate(self, n: Optional[int] = None, time: int = 0) -> int:
        """增殖未分化神经元（动态区扩容）。

        只创建神经元，不接线（增殖后进入探索期）。
        用显式已增殖集合跟踪（不依赖 neuron_type，避免 add_neuron
        填充中间神经元的默认 EXCITATORY 污染计数）。
        """
        n = n or self.p["proliferate_size"]
        created = 0
        # 找动态区空闲槽（40-199 未增殖）
        candidates = [i for i in range(_DEV_START, _DEV_END + 1)
                      if i not in self._proliferated_ids]
        # 随机取 n 个（不按顺序，避免 ID 聚类偏置）
        random.shuffle(candidates)
        for nid in candidates[:n]:
            # 确保神经元存在（add_neuron 会扩展并填充中间槽，
            # 但填充的中间槽标记为默认，不影响 _proliferated_ids 跟踪）
            if nid >= self.snn.num_neurons:
                self.snn.add_neuron(nid, NeuronType.EXCITATORY, threshold=1.2)
            else:
                self.snn.neurons[nid].neuron_type = NeuronType.EXCITATORY
                self.snn.neurons[nid].threshold = 1.2
            self._proliferated_ids.add(nid)
            created += 1
        if created:
            self._stats["proliferated"] += created
            self._set_stage("proliferating")
            self._last_proliferate_time = time
            logger.info(f"development: proliferated {created} neurons (total {self._stats['proliferated']})")
        return created

    def _used_dev_slots(self) -> Set[int]:
        """动态区已占用神经元 ID 集合（用显式增殖跟踪）。"""
        return set(self._proliferated_ids)

    # ── Stage 2: 突触探索（v2 分功能区配额）────────────────
    def explore_synapses(self, time: int = 0, max_new: Optional[int] = None) -> int:
        """突触从无到有探索：分功能区配额 + 功能链打通（v2）。

        v1 问题：全对遍历 40-199 + attempts 上限 → 低 ID 集中，输出区死端。
        v2 修复：每个功能区（输入40-99/输出100-199/语义220+）独立探索配额，
        保证覆盖均匀；输出区显式连到核心输出/概念区，打通决策链。

        探索边权重 0.35-0.55（>keep_weight=0.20），骨架稳固，停止空转。
        """
        max_new = max_new or 50
        created = 0
        # 边数上限：防过度生长（667 边暴涨前科）
        current_dev_edges = self._count_dev_edges()
        if current_dev_edges >= self.p["max_dev_edges"]:
            return 0
        remaining = min(max_new, self.p["max_dev_edges"] - current_dev_edges)
        if remaining <= 0:
            return 0

        # v2: 输出链打通（最高优先，消除死端）
        # 注意：链边（输出→核心输出）目标 <40，不计入 _count_dev_edges，
        # 因此独立于骨架预算——不消耗 remaining，否则会耗尽预算导致
        # _explore_zone（真正的区内骨架）不跑。
        if self.p["ensure_output_chain"]:
            chain_created = self._ensure_output_chain()
            created += chain_created
            # 注：_ensure_output_chain 内部已统计 output_chain_edges，不重复

        # v2: 分功能区配额探索
        quota = self.p["zone_quota"]
        zones = self._dev_zones()
        # 每功能区探索（输入区优先连语义/中继；输出区连概念/核心输出）
        for zone_name, neurons in zones.items():
            if remaining <= 0:
                break
            zone_new = self._explore_zone(zone_name, neurons, min(quota, remaining))
            created += zone_new
            remaining -= zone_new
            self._stats["zone_explored"][zone_name] = \
                self._stats["zone_explored"].get(zone_name, 0) + zone_new

        # v2: 步长演化（发育边按协同放电演化步长，非全 1）
        if self.p["step_evolve_enabled"] and created > 0:
            evolved = self._evolve_steps(time)
            self._stats["step_evolve_events"] += evolved

        if created:
            self._stats["explored_edges"] += created
            logger.info(
                f"development: explored {created} synapses (total {self._stats['explored_edges']}, "
                f"zones={self._stats['zone_explored']})")
        return created

    def _count_dev_edges(self) -> int:
        """动态区内部边数。"""
        return sum(
            1 for s in self.snn.out_edges
            for t in self.snn.out_edges[s]
            if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END
        )

    def _is_active(self, nid: int) -> bool:
        """神经元是否已增殖/激活（发育区 40-199 用显式增殖跟踪，
        概念区 220+ 用神经元存在判断）。"""
        if _DEV_START <= nid <= _DEV_END:
            return nid in self._proliferated_ids
        if nid >= _CONCEPT_START:
            return nid < len(self.snn.neurons) and self.snn.neurons[nid].neuron_type.value != "unused"
        return False

    def _dev_zones(self) -> Dict[str, List[int]]:
        """动态区分功能区神经元列表（基于增殖跟踪，不依赖 neuron_type）。"""
        zones: Dict[str, List[int]] = {"input": [], "output": [], "concept": []}
        for nid in range(_DEV_START, _DEV_END + 1):
            if nid in self._proliferated_ids:
                if nid <= _DEV_INPUT_END:
                    zones["input"].append(nid)
                else:
                    zones["output"].append(nid)
        # 概念区：神经元存在且非默认
        for n in self.snn.neurons:
            if n.id >= _CONCEPT_START and n.neuron_type.value != "unused":
                zones["concept"].append(n.id)
        return zones

    def _explore_zone(self, zone_name: str, neurons: List[int], budget: int) -> int:
        """单个功能区探索（预算内建边）。

        - input:  连到概念区/中继/输出区（感知→语义/动作）
        - output: 连到核心输出/概念区（动作→决策）
        - concept: 连到输出区/中继（语义→决策）
        探索边权重 0.35-0.55（骨架稳固）。
        """
        if budget <= 0 or len(neurons) < 2:
            return 0
        created = 0
        # 功能区目标池（按功能链方向）
        if zone_name == "input":
            targets = self._zone_targets("input")
        elif zone_name == "output":
            targets = self._zone_targets("output")
        else:  # concept
            targets = self._zone_targets("concept")

        # 随机起点 + 预算内尝试（避免低 ID 集中）
        random.shuffle(neurons)
        attempts = 0
        for src in neurons:
            if created >= budget:
                break
            tgt_pool = [t for t in targets if t != src and t not in self.snn.out_edges.get(src, {})]
            if not tgt_pool:
                continue
            random.shuffle(tgt_pool)
            for tgt in tgt_pool:
                attempts += 1
                # 基础概率 + 弱引导（同功能区倾向连接）
                prob = self.p["explore_prob"]
                if self._same_zone(src, tgt):
                    prob += self.p["weak_guide"] * 0.3
                if random.random() > prob:
                    continue
                # 弱权重连接（v2: 0.35-0.55 稳固）
                w = random.uniform(self.p["explore_weight_min"], self.p["explore_weight_max"])
                if self.snn.connect(src, tgt, weight=w, step=self.p["explore_step"]):
                    created += 1
                    self._stats["explored_edges"] += 1
                if created >= budget or attempts > budget * 30:
                    break
            if attempts > budget * 30:
                break
        return created

    def _same_zone(self, a: int, b: int) -> bool:
        """两个神经元是否同功能区。"""
        za = self._zone_of(a)
        zb = self._zone_of(b)
        return za is not None and za == zb

    def _zone_of(self, nid: int) -> Optional[str]:
        if _DEV_START <= nid <= _DEV_INPUT_END:
            return "input"
        if _DEV_OUTPUT_START <= nid <= _DEV_OUTPUT_END:
            return "output"
        if nid >= _CONCEPT_START:
            return "concept"
        return None

    def _zone_targets(self, zone_name: str) -> List[int]:
        """功能区可连目标池（功能链方向）。

        每个功能区都包含自身区神经元（区内互连，保证单区也能形成骨架），
        跨区作为功能链补充：
        - input  → 自身输入区 + 输出区 + 概念区（感知→语义/动作）
        - output → 自身输出区 + 核心输出 + 概念区（动作→决策）
        - concept→ 自身概念区 + 核心输出（语义→决策）
        """
        targets = []
        # 用增殖跟踪 + 概念区存在判断（不依赖 neuron_type）
        existing_ids = set(self._proliferated_ids)
        for n in self.snn.neurons:
            if n.id >= _CONCEPT_START and n.neuron_type.value != "unused":
                existing_ids.add(n.id)
        if zone_name == "input":
            # 自身输入区 + 感知 → 动作/语义
            targets.extend([i for i in range(_DEV_START, _DEV_INPUT_END + 1) if i in existing_ids])
            targets.extend([i for i in range(_DEV_OUTPUT_START, _DEV_OUTPUT_END + 1) if i in existing_ids])
            targets.extend([i for i in range(_CONCEPT_START, min(_CONCEPT_START + 40, self.snn.num_neurons)) if i in existing_ids])
        elif zone_name == "output":
            # 自身输出区 + 动作 → 决策（核心输出 32-37）
            targets.extend([i for i in range(_DEV_OUTPUT_START, _DEV_OUTPUT_END + 1) if i in existing_ids])
            targets.extend([c for c in _CORE_OUTPUTS if c < self.snn.num_neurons])
            targets.extend([i for i in range(_CONCEPT_START, min(_CONCEPT_START + 40, self.snn.num_neurons)) if i in existing_ids])
        else:  # concept
            # 自身概念区 + 语义 → 决策
            targets.extend([i for i in range(_CONCEPT_START, min(_CONCEPT_START + 40, self.snn.num_neurons)) if i in existing_ids])
            targets.extend([c for c in _CORE_OUTPUTS if c < self.snn.num_neurons])
        # 去重
        return list(dict.fromkeys(targets))

    def _ensure_output_chain(self) -> int:
        """确保输出区(100-199)连到核心输出/概念区（打通决策链）。

        输出区神经元若无出边（死端），连到核心输出（32-37）或概念区，
        让"感知→动作→决策"链路完整。返回新建边数。
        """
        created = 0
        output_neurons = [
            nid for nid in range(_DEV_OUTPUT_START, _DEV_OUTPUT_END + 1)
            if nid in self._proliferated_ids
        ]
        if not output_neurons:
            return 0
        for out_nid in output_neurons:
            # 已有出边则无需打通
            if self.snn.out_edges.get(out_nid):
                continue
            # 连到核心输出（决策）
            for c in _CORE_OUTPUTS:
                if c < self.snn.num_neurons and c not in self.snn.out_edges.get(out_nid, {}):
                    w = random.uniform(self.p["explore_weight_min"], self.p["explore_weight_max"])
                    if self.snn.connect(out_nid, c, weight=w, step=self.p["explore_step"]):
                        created += 1
                        self._stats["output_chain_edges"] += 1
                        break  # 每输出神经元至少连一个核心输出
            # 若核心输出不可达，连概念区
            if created and not self.snn.out_edges.get(out_nid):
                concept_ids = [i for i in range(_CONCEPT_START, min(_CONCEPT_START + 40, self.snn.num_neurons))]
                if concept_ids:
                    c = random.choice(concept_ids)
                    w = random.uniform(self.p["explore_weight_min"], self.p["explore_weight_max"])
                    if self.snn.connect(out_nid, c, weight=w, step=self.p["explore_step"]):
                        created += 1
                        self._stats["output_chain_edges"] += 1
        if created:
            logger.info(f"development: output chain {created} edges (打通决策链)")
        return created

    def _evolve_steps(self, time: int) -> int:
        """发育边步长演化（v2：接入发育路径）。

        每轮确定性地演化若干条边（按 step_evolve_rate 比例取边，
        非纯随机门控——避免随机序列不合适时永不演化）。
        演化方向按协同放电相关性/权重启发：
        - 强相关（目标跟随源放电或权重高）→ 缩短步长（路径快）
        - 弱相关 → 加长步长（路径慢）
        """
        evolved = 0
        t = time if time > 0 else self.snn.time
        recent_fire = getattr(self.snn, "_recent_fire", {})
        # 候选发育边（40-199，冷却期外，且权重≥keep_weight——将被保留的边）
        # 弱边（<keep_weight）会被修剪，演化无意义，不纳入候选。
        candidates = []
        for src in list(self.snn.out_edges.keys()):
            for tgt, conn in list(self.snn.out_edges[src].items()):
                if not (_DEV_START <= src <= _DEV_END and _DEV_START <= tgt <= _DEV_END):
                    continue
                if conn.weight < self.p["keep_weight"]:
                    continue
                if t - self._step_change_time.get((src, tgt), -10**6) < self.p["step_evolve_cooldown"]:
                    continue
                candidates.append((src, tgt, conn))
        if not candidates:
            return 0
        # 确定性取边：按比例取（至少 1 条）
        # 排序优先“可演化”边（new_step != conn.step），避免取到权重最高
        # 但已是下界（step=1 且 strong → 缩短到 1 不变）的边导致永不演化。
        def _can_evolve(e):
            _, _, conn = e
            correlated = conn.weight >= 0.4
            new_step = max(self.p["step_min"], conn.step - 1) if correlated else min(self.p["step_max"], conn.step + 1)
            return new_step != conn.step
        candidates.sort(key=lambda e: (not _can_evolve(e), -e[2].weight))
        n_evolve = max(1, int(len(candidates) * self.p["step_evolve_rate"]))
        for src, tgt, conn in candidates[:n_evolve]:
            # 演化方向：放电相关性优先，无放电用权重启发
            src_hist = recent_fire.get(src, [])
            tgt_hist = recent_fire.get(tgt, [])
            if tgt_hist:
                correlated = False
                for st in src_hist:
                    for tt in tgt_hist:
                        if 0 < tt - st <= conn.step + 2:
                            correlated = True
                            break
                    if correlated:
                        break
            else:
                correlated = conn.weight >= 0.4
            if correlated:
                new_step = max(self.p["step_min"], conn.step - 1)
            else:
                new_step = min(self.p["step_max"], conn.step + 1)
            if new_step != conn.step:
                self.snn.set_step(src, tgt, new_step)
                self._step_change_time[(src, tgt)] = t
                evolved += 1
        return evolved

    def _build_guide_map(self, dev_neurons: List[int]) -> Dict[int, Optional[str]]:
        """构建弱引导映射：神经元 → 先验群标签。

        用 ID 区间做粗引导（输入槽 40-99 → "percept"，输出槽 100-199 → "action"），
        这是弱引导（非硬编码），只倾向同群连接，不强制。
        """
        guide: Dict[int, Optional[str]] = {}
        for nid in dev_neurons:
            if _DEV_INPUT_END >= nid >= _DEV_START:
                guide[nid] = "percept"
            elif _DEV_OUTPUT_END >= nid >= _DEV_OUTPUT_START:
                guide[nid] = "action"
            else:
                guide[nid] = None
        return guide

    # ── Stage 3: 分化期 ──────────────────────────────────
    def differentiate(self, time: int = 0) -> Dict:
        """自发分簇成功能脑区（感知/语义/决策）。

        用拓扑 BFS + 活跃度聚类，加弱引导。
        返回分簇结果（每簇神经元列表）。
        """
        dev_neurons = [
            i for i in range(_DEV_START, _DEV_END + 1)
            if i in self._proliferated_ids
        ]
        clusters = self._cluster_by_activity(dev_neurons)
        self._stats["clusters"] = [list(c) for c in clusters]
        self._set_stage("differentiated")
        return {"clusters": [list(c) for c in clusters], "count": len(clusters)}

    def _cluster_by_activity(self, dev_neurons: List[int]) -> List[List[int]]:
        """拓扑 BFS 分簇 + 活跃度加权。

        复用 SNN 的 _cluster_by_topology（若存在），否则 BFS 实现。
        """
        if not dev_neurons:
            return []
        # 优先用 SNN 现有聚类（拓扑距离）
        if hasattr(self.snn, "_cluster_by_topology"):
            try:
                clusters = self.snn._cluster_by_topology(dev_neurons)
                return [c for c in clusters if len(c) >= self.p["min_cluster_size"]]
            except Exception:
                pass
        # 回退：简单 BFS
        return self._bfs_clusters(dev_neurons)

    def _bfs_clusters(self, dev_neurons: List[int]) -> List[List[int]]:
        """BFS 跳数聚类（拓扑连通性）。"""
        region_set = set(dev_neurons)
        unvisited = set(dev_neurons)
        clusters = []
        while unvisited:
            seed = min(unvisited)
            queue = [(seed, 0)]
            cluster = set()
            visited = {seed}
            while queue:
                node, d = queue.pop(0)
                if d > self.p["cluster_hop"]:
                    continue
                if node in region_set:
                    cluster.add(node)
                if d == self.p["cluster_hop"]:
                    continue
                for nb in list(self.snn.out_edges.get(node, {}).keys()):
                    if nb not in visited:
                        visited.add(nb)
                        queue.append((nb, d + 1))
                for nb in list(self.snn.in_edges.get(node, {}).keys()):
                    if nb not in visited:
                        visited.add(nb)
                        queue.append((nb, d + 1))
            clusters.append(sorted(cluster))
            unvisited -= cluster
        return [c for c in clusters if len(c) >= self.p["min_cluster_size"]]

    # ── 突触修剪（STDP 后收敛）──────────────────────────
    def prune_weak_synapses(self) -> int:
        """剪除弱突触（权重 < keep_weight），突触收敛。

        只剪正权重弱边（兴奋性冗余）；负权重抑制边（侧向抑制）
        是功能性的，不剪。
        """
        pruned = 0
        for src in list(self.snn.out_edges.keys()):
            for tgt in list(self.snn.out_edges[src].keys()):
                # 只剪发育区连接（不动核心区）
                if not (_DEV_START <= src <= _DEV_END and _DEV_START <= tgt <= _DEV_END):
                    continue
                conn = self.snn.out_edges[src][tgt]
                if 0 < conn.weight < self.p["keep_weight"]:
                    self.snn.disconnect(src, tgt)
                    pruned += 1
        if pruned:
            self._stats["pruned_edges"] += pruned
            logger.info(f"development: pruned {pruned} weak synapses (total {self._stats['pruned_edges']})")
        return pruned

    # ── 侧向抑制（分化期，防过度收敛）──────────────────
    def apply_lateral_inhibition(self, clusters: List[List[int]]) -> int:
        """同簇内加弱侧向抑制，防过度收敛成单簇。

        簇内神经元之间加弱抑制边（负权重），鼓励分化。
        """
        added = 0
        for cluster in clusters:
            for i, src in enumerate(cluster):
                for tgt in cluster[i + 1:]:
                    if tgt in self.snn.out_edges.get(src, {}):
                        continue
                    w = -self.p["lateral_inhibition"]
                    if self.snn.connect(src, tgt, weight=w, step=1):
                        added += 1
        if added:
            logger.info(f"development: lateral inhibition {added} edges")
        return added

    # ── 状态 ────────────────────────────────────────────
    def _set_stage(self, stage: str):
        if stage != self.stage:
            self.stage = stage
            self.stage_history.append(stage)

    def status(self) -> Dict:
        """发育状态（可观测 /brain/dev/status）。"""
        dev_neurons = [
            i for i in range(_DEV_START, _DEV_END + 1)
            if i in self._proliferated_ids
        ]
        dev_edges = [
            (src, tgt) for src in self.snn.out_edges
            for tgt in self.snn.out_edges[src]
            if _DEV_START <= src <= _DEV_END and _DEV_START <= tgt <= _DEV_END
        ]
        return {
            "stage": self.stage,
            "stage_history": self.stage_history,
            "dev_neurons": len(dev_neurons),
            "dev_edges": len(dev_edges),
            "dev_neuron_ids": dev_neurons[:50],
            "proliferated": self._stats["proliferated"],
            "explored_edges": self._stats["explored_edges"],
            "pruned_edges": self._stats["pruned_edges"],
            "clusters": self._stats["clusters"],
            "zone_explored": self._stats.get("zone_explored", {}),
            "output_chain_edges": self._stats.get("output_chain_edges", 0),
            "step_evolve_events": self._stats.get("step_evolve_events", 0),
            "params": self.p,
        }

    def run_development_cycle(self, time: int = 0) -> Dict:
        """完整发育循环（增殖→探索→分化→修剪），幂等渐进。

        供 Brain Core tick 或手动调用。
        收敛机制：达到 max_dev_edges 后转为修剪最弱边（防 667 边暴涨）。
        """
        # 增殖（若动态区未满）
        if self._stats["proliferated"] < self.p["max_proliferate"]:
            self.proliferate(time=time)
        # 突触探索（边数上限内）
        self.explore_synapses(time=time)
        # 分化（周期刷新）
        clusters = self.differentiate(time=time)
        # 突触修剪：收敛机制
        # - 每 prune_every 步剪弱边
        # - 达到 max_dev_edges 后剪 prune_ratio 最弱边（防过度生长）
        current_dev_edges = self._count_dev_edges()
        if current_dev_edges >= self.p["max_dev_edges"]:
            self._prune_weakest(self.p["prune_ratio"])
        elif time % self.p["synapse_prune_every"] == 0 and time > 0:
            self.prune_weak_synapses()
        return {"stage": self.stage, **self.status()}

    def _prune_weakest(self, ratio: float) -> int:
        """剪除发育区最弱的 ratio 比例边（收敛，防过度生长）。

        多尺度边（step≠1）优先保留——它们是发育产生的结构，
        权重即使略低也不剪（除非全部都是多尺度边）。
        """
        dev_edges = [
            (s, t, self.snn.out_edges[s][t].weight, self.snn.out_edges[s][t].step)
            for s in self.snn.out_edges
            for t in self.snn.out_edges[s]
            if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END
        ]
        if not dev_edges:
            return 0
        # 排序：step=1 的弱边先剪（多尺度 step≠1 排后，优先保留）
        # 注意：bool 排序 False < True，用 (step != 1) 让 step≠1 的边排后
        dev_edges.sort(key=lambda e: (e[3] != 1, e[2]))
        n_prune = max(1, int(len(dev_edges) * ratio))
        pruned = 0
        for s, t, _w, _step in dev_edges[:n_prune]:
            self.snn.disconnect(s, t)
            pruned += 1
        if pruned:
            self._stats["pruned_edges"] += pruned
            logger.info(f"development: converged-pruned {pruned} edges (ratio {ratio})")
        return pruned
