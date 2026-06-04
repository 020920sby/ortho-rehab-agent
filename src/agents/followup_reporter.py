"""
随访报告生成器 — 面向医生的结构化康复进展报告。

修复点：
- 去掉了原方案 `safety_result` 作为独立 dict 参数传入，
  改为从 patient_state 直接读取安全判读结果，减少参数传递链。
- prompt 末尾明确要求 JSON 返回。
- 添加了趋势数据的量化描述。
- export_format_markdown 现在由 LLM 真正生成而非空占位。
"""

import logging
from typing import Dict, Any
from datetime import datetime

from src.models.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class FollowupReporter:
    """骨科随访报告生成器（医生视角）。"""

    REPORT_PROMPT = """你是一位骨科临床随访专员。
请根据患者的康复数据，生成一份结构化的随访报告。

【患者基本信息】
患者ID：{patient_id}
手术类型：{surgery_type}
手术日期：{surgery_date}
术后天数：{days_post_op}
康复阶段：{recovery_phase}

【康复执行数据】
- 计划完成率：{completion_rate}%
- 疼痛评分（当前）：{pain_score}分（VAS 0-10）
- 疼痛趋势：{pain_trend}
- 关节活动度：{rom}
- 活动度趋势：{rom_trend}
- 关键体征：{vital_signs}

【患者自述反馈】
{patient_feedback}

【AI 安全判读】
- 安全等级：{safety_level}
- 判读依据：{safety_reasoning}
- 处置建议：{safety_recommendation}

请以 JSON 格式返回随访报告：
{{
    "report_date": "YYYY-MM-DD",
    "summary": "康复概况总结（1-2句话，概括进展和主要问题）",
    "progress_assessment": {{
        "pain_control": "excellent|good|fair|poor",
        "rom_progress": "on_track|slightly_delayed|significantly_delayed",
        "functional_status": "independent|partially_dependent|fully_dependent",
        "compliance": "high|moderate|low"
    }},
    "key_findings": [
        "基于数据的正向发现1",
        "需要关注的问题1"
    ],
    "risk_alerts": [
        "存在的风险提示（如无则写'目前无特殊风险'）"
    ],
    "recommendations": [
        "针对性的康复建议1",
        "用药调整建议（如有）",
        "复诊建议"
    ],
    "next_review": "建议下次复诊时间（术后X周或X个月）",
    "export_format_markdown": "完整的Markdown格式随访报告，包含标题、分段、列表，适合打印或导出PDF"
}}

注意：
- risk_alerts 必须如实反映安全判读结果，不能轻描淡写。
- 如果安全等级为 warning 或 emergency，recommendations 中必须包含明确的就医建议。
- Markdown 报告需包含结构化的标题层级（#、##），便于医生快速浏览。

请以 JSON 格式返回结果。"""

    def generate_report(self, patient_state: Dict[str, Any]) -> Dict[str, Any]:
        """生成随访报告。安全判读信息直接从 patient_state 中读取。"""
        prompt = self.REPORT_PROMPT.format(
            patient_id=patient_state.get("patient_id", "未知"),
            surgery_type=patient_state.get("surgery_type", "未知"),
            surgery_date=patient_state.get("surgery_date", "未知"),
            days_post_op=patient_state.get("days_post_op", 0),
            recovery_phase=patient_state.get("recovery_phase", "未知"),
            completion_rate=patient_state.get("completion_rate", 0),
            pain_score=patient_state.get("pain_score", 0),
            pain_trend=patient_state.get("pain_trend", "稳定"),
            rom=patient_state.get("rom", "未记录"),
            rom_trend=patient_state.get("rom_trend", "稳步改善"),
            vital_signs=patient_state.get("vital_signs", "正常范围"),
            patient_feedback=patient_state.get("daily_feedback", "无反馈"),
            safety_level=patient_state.get("safety_level", "normal"),
            safety_reasoning=patient_state.get("safety_reasoning", ""),
            safety_recommendation=patient_state.get("safety_recommendation", ""),
        )

        llm = get_llm_client()
        report = llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2560,
        )

        report["report_id"] = f"RPT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        report["patient_id"] = patient_state.get("patient_id")
        report["generated_at"] = datetime.now().isoformat()

        return report


def generate_discharge_summary(patient_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成出院/转阶段摘要报告。
    当患者从一个康复阶段进入下一阶段时调用。
    """
    DISCHARGE_PROMPT = """你是一位骨科康复医师。患者即将结束当前康复阶段，请撰写阶段总结和下一阶段指导。

【当前阶段信息】
手术类型：{surgery_type}
术后天数：{days_post_op}
当前康复阶段：{recovery_phase}
当前活动度：{rom}
疼痛评分：{pain_score}

【执行数据】
计划完成率：{completion_rate}%

请以 JSON 格式返回：
{{
    "phase_summary": "本阶段康复总结（2-3句话）",
    "goals_achieved": ["已达成的目标1", "已达成的目标2"],
    "goals_pending": ["尚未达成的目标1"],
    "next_phase_goals": ["下一阶段目标1", "下一阶段目标2"],
    "transition_recommendations": ["转入下一阶段的注意事项"],
    "next_review": "建议下次复诊时间"
}}

请以 JSON 格式返回结果。"""

    prompt = DISCHARGE_PROMPT.format(
        surgery_type=patient_state.get("surgery_type", ""),
        days_post_op=patient_state.get("days_post_op", 0),
        recovery_phase=patient_state.get("recovery_phase", ""),
        rom=patient_state.get("rom", "未记录"),
        pain_score=patient_state.get("pain_score", 0),
        completion_rate=patient_state.get("completion_rate", 0),
    )

    llm = get_llm_client()
    return llm.chat_json(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
