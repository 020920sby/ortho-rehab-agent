"""
GraphRAG — 骨科知识图谱增强检索。

与普通向量检索不同，GraphRAG 利用知识图谱中实体之间的关系
进行更深层的推理。例如：
- "TKA术后疼痛" → 自动关联 "多模式镇痛方案" → "塞来昔布" → "NSAIDs禁忌证"
- 支持多跳推理：查询症状 → 关联并发症 → 关联紧急处理流程

本模块使用轻量级实体关系图谱（基于 networkx + JSON 定义），
结合向量检索形成混合召回。
"""

import json
import logging
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)


# ── 骨科实体关系图谱定义 ──────────────────────────────────

ORTHO_KNOWLEDGE_GRAPH = {
    "entities": {
        "TKA": {
            "name": "全膝关节置换术",
            "aliases": ["膝关节置换", "人工膝关节"],
            "related_complications": ["DVT", "肺栓塞", "关节僵硬", "假体感染", "假体松动"],
            "rehab_phases": ["急性期", "亚急性期", "恢复期", "维持期"],
            "key_muscles": ["股四头肌", "腘绳肌", "腓肠肌"],
            "contraindicated_actions": ["深蹲>90度", "高冲击运动", "跳跃"],
        },
        "THA": {
            "name": "全髋关节置换术",
            "aliases": ["髋关节置换", "人工髋关节"],
            "related_complications": ["DVT", "肺栓塞", "假体脱位", "假体感染", "神经损伤"],
            "rehab_phases": ["急性期", "亚急性期", "恢复期", "维持期"],
            "key_muscles": ["臀中肌", "臀大肌", "髂腰肌", "股四头肌"],
            "contraindicated_actions": ["屈髋>90度(后外侧入路)", "内收过中线", "内旋", "翘二郎腿"],
        },
        "ACL": {
            "name": "前交叉韧带重建术",
            "aliases": ["ACL重建", "韧带重建"],
            "related_complications": ["移植物再断裂", "关节纤维化", "前膝痛", "DVT"],
            "rehab_phases": ["急性保护期", "早期保护性训练期", "肌力重建期", "运动准备期", "回归运动期"],
            "key_muscles": ["股四头肌", "腘绳肌", "腓肠肌", "臀肌"],
            "contraindicated_actions": ["开链伸膝抗阻训练(术后6个月内)", "过早旋转运动"],
        },
        "DVT": {
            "name": "深静脉血栓",
            "emergency_level": "emergency",
            "symptoms": ["单侧小腿肿胀", "疼痛", "皮温升高", "Homans征阳性"],
            "prevention": ["IPC装置", "低分子肝素", "弹力袜", "踝泵运动"],
            "diagnosis": "下肢血管超声",
            "action": "立即就医",
        },
        "肺栓塞": {
            "name": "肺栓塞",
            "emergency_level": "emergency",
            "symptoms": ["突发胸痛", "呼吸困难", "咯血", "心率增快", "血氧下降"],
            "source": "多由DVT脱落引起",
            "action": "立即急诊就医（120急救）",
        },
        "假体感染": {
            "name": "假体周围感染",
            "emergency_level": "emergency",
            "symptoms": ["切口红肿热痛", "发热>38.5℃", "脓性分泌物", "寒战"],
            "diagnosis": "血常规+CRP+ESR+关节液培养",
            "action": "立即就医",
        },
        "关节僵硬": {
            "name": "关节僵硬/关节纤维化",
            "emergency_level": "warning",
            "symptoms": ["活动度停滞", "屈曲<90度(术后12周)", "伸展缺失>5度"],
            "treatment": ["强化康复", "麻醉下手法松解(评估指征)"],
        },
    },
    "relations": [
        # 手术 → 并发症
        ("TKA", "has_complication", "DVT"),
        ("TKA", "has_complication", "肺栓塞"),
        ("TKA", "has_complication", "关节僵硬"),
        ("TKA", "has_complication", "假体感染"),
        ("THA", "has_complication", "DVT"),
        ("THA", "has_complication", "肺栓塞"),
        ("THA", "has_complication", "假体脱位"),
        ("THA", "has_complication", "假体感染"),
        ("ACL", "has_complication", "移植物再断裂"),
        ("ACL", "has_complication", "关节纤维化"),
        # DVT → 肺栓塞
        ("DVT", "may_lead_to", "肺栓塞"),
        # 康复阶段顺序
        ("急性期", "next_phase", "亚急性期"),
        ("亚急性期", "next_phase", "恢复期"),
        ("恢复期", "next_phase", "维持期"),
    ],
}


class OrthoGraphRAG:
    """
    骨科知识图谱增强检索。

    结合 GraphRAG 和传统向量检索，实现：
    1. 实体匹配：从查询中识别手术类型、症状、阶段
    2. 图遍历：沿着关系扩展相关知识
    3. 混合召回：图谱结果 + 向量检索结果合并去重
    """

    def __init__(self, kg: Optional[Dict] = None):
        self.kg = kg or ORTHO_KNOWLEDGE_GRAPH
        self._build_index()

    def _build_index(self):
        """构建别名索引，用于快速实体查找。"""
        self._alias_to_entity: Dict[str, str] = {}
        for entity_id, data in self.kg["entities"].items():
            self._alias_to_entity[entity_id.lower()] = entity_id
            self._alias_to_entity[data["name"].lower()] = entity_id
            for alias in data.get("aliases", []):
                self._alias_to_entity[alias.lower()] = entity_id

    def find_entity(self, keyword: str) -> Optional[str]:
        """根据关键词查找实体ID。"""
        return self._alias_to_entity.get(keyword.lower())

    def get_related_complications(self, surgery_type: str) -> List[str]:
        """获取某手术类型的相关并发症。"""
        entity = self.kg["entities"].get(surgery_type, {})
        return entity.get("related_complications", [])

    def get_emergency_symptoms(self, entity_id: str) -> List[str]:
        """获取某个实体的紧急症状列表。"""
        entity = self.kg["entities"].get(entity_id, {})
        return entity.get("symptoms", [])

    def get_contraindicated_actions(self, surgery_type: str) -> List[str]:
        """获取某手术类型的禁忌动作。"""
        entity = self.kg["entities"].get(surgery_type, {})
        return entity.get("contraindicated_actions", [])

    def graph_search(self, query: str, max_hops: int = 2) -> Dict[str, Any]:
        """
        基于知识图谱的多跳检索。

        流程：
        1. 从查询中提取手术类型关键词
        2. 找到对应实体及其关系
        3. 沿关系遍历 1-2 跳获取相关知识
        返回结构化知识片段。
        """
        query_lower = query.lower()

        # 匹配手术类型
        matched_surgeries = []
        for surgery_id in ["TKA", "THA", "ACL"]:
            entity = self.kg["entities"].get(surgery_id, {})
            if surgery_id.lower() in query_lower:
                matched_surgeries.append(surgery_id)
            elif any(alias.lower() in query_lower for alias in entity.get("aliases", [])):
                matched_surgeries.append(surgery_id)

        # 匹配并发症/症状
        matched_complications = []
        for comp_id in ["DVT", "肺栓塞", "假体感染", "关节僵硬", "假体脱位"]:
            entity = self.kg["entities"].get(comp_id, {})
            if entity and (comp_id.lower() in query_lower):
                matched_complications.append(comp_id)

        # 构建返回结果
        context_parts: List[str] = []

        for surgery_id in matched_surgeries:
            entity = self.kg["entities"].get(surgery_id, {})
            # 直接相关的禁忌动作
            if max_hops >= 1 and entity.get("contraindicated_actions"):
                context_parts.append(
                    f"【{entity['name']}禁忌动作】{'; '.join(entity['contraindicated_actions'])}"
                )
            # 关键肌群
            if entity.get("key_muscles"):
                context_parts.append(
                    f"【{entity['name']}关键肌群】{', '.join(entity['key_muscles'])}"
                )

        # 2跳：匹配到并发症时获取其紧急处理措施
        for comp_id in matched_complications:
            entity = self.kg["entities"].get(comp_id, {})
            if entity.get("symptoms"):
                context_parts.append(
                    f"【{entity['name']}症状】{'; '.join(entity['symptoms'])}"
                )
            if entity.get("action"):
                context_parts.append(
                    f"【{entity['name']}处理】{entity['action']}"
                )
            if entity.get("prevention"):
                context_parts.append(
                    f"【{entity['name']}预防】{'; '.join(entity['prevention'])}"
                )

        return {
            "matched_surgeries": matched_surgeries,
            "matched_complications": matched_complications,
            "context": "\n".join(context_parts),
            "relations_used": max_hops,
        }
