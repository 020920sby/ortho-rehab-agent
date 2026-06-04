"""
骨科安全哨兵 — 双路判读（规则引擎 + AI 辅助）。

修复点：
- 原方案的 _rule_based_assessment 中 rules["warning_rules"] 的 condition 字段是字符串，
  需要用 eval() 执行，极不安全。改为解析结构化 conditions。
- 抽取 OperatorEvaluator，支持 equals/greater_than/less_than/is_true 等操作符。
- 规则匹配结果包含匹配到的具体规则名，便于追踪。
- AI 判读现在使用 chat_json() 高层封装，自动处理 JSON 解析错误。
"""

import logging
import yaml
from typing import Dict, Any, Optional
from pathlib import Path

from src.models.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# 默认规则文件路径
DEFAULT_RULES_PATH = Path(__file__).parent.parent / "rules" / "ortho_rules.yaml"


class OperatorEvaluator:
    """安全的条件求值器，替代 eval()。"""

    @staticmethod
    def evaluate(actual_value: Any, operator: str, target_value: Any) -> bool:
        if operator == "equals":
            return str(actual_value).strip() == str(target_value).strip()
        elif operator == "greater_than":
            return float(actual_value) > float(target_value)
        elif operator == "less_than":
            return float(actual_value) < float(target_value)
        elif operator == "greater_than_or_equal":
            return float(actual_value) >= float(target_value)
        elif operator == "less_than_or_equal":
            return float(actual_value) <= float(target_value)
        elif operator == "is_true":
            return bool(actual_value) is True
        elif operator == "is_false":
            return bool(actual_value) is False
        elif operator == "contains":
            return str(target_value).lower() in str(actual_value).lower()
        elif operator == "not_equals":
            return str(actual_value).strip() != str(target_value).strip()
        else:
            logger.warning("Unknown operator: %s", operator)
            return False


class OrthoSafetySentinel:
    """骨科安全哨兵：规则引擎（快速、确定性）+ AI 判读（语义理解）。"""

    SAFETY_PROMPT = """你是一位骨科术后康复安全监测专家。
请根据患者今日反馈进行安全判读，以 JSON 格式返回结果。

【患者基本信息】
手术类型：{surgery_type}
手术日期：{surgery_date}
术后天数：{days_post_op}
今日疼痛评分(VAS 0-10)：{pain_score}
当前关节活动度：{rom}

【今日患者反馈】
{patient_feedback}

【正常恢复范围参考】
{normal_range}

返回 JSON 格式：
{{
    "safety_level": "normal|attention|warning|emergency",
    "reasoning": "判读的临床依据",
    "recommendation": "具体建议措施",
    "requires_doctor_review": true或false
}}

⚠️ 分级规则（按严重度从高到低）：

【emergency — 立即就医】
触发条件（满足任一条即为 emergency）：
1. 关键词：胸痛、呼吸困难、咯血、意识模糊、伤口大量出血、高热不退(>39℃)、突然不能呼吸
2. THA 特有：腹股沟突然剧痛 + 下肢短缩感/无法移动 → 疑似脱位
3. TKA/THA 特有：小腿突然剧烈肿痛 + 无法承重 → 疑似DVT
4. ACL 特有：弹响后关节明显松动/不稳 + 无法承重 → 疑似移植物断裂
→ 行动：建议立即拨打120或急诊，不要建议"观察"

【warning — 尽快联系医生】
触发条件（满足任一条即为 warning）：
1. 疼痛评分≥7 且止痛药无效
2. 术后早期(<7天)疼痛评分≥7（即使药物有效也要警惕）
3. 伤口红肿范围扩大 + 渗液增多 + 体温>37.5℃（两条以上触发）
4. 药物副作用明显：头晕+恶心+昏沉（阿片类）或胃痛+黑便（NSAIDs）
5. 弹响/咔哒声伴不稳定感（ACL术后）
6. ROM 两周以上无改善或退步
→ 行动：建议尽快联系医生评估，不要拖延

【attention — 密切监测】
触发条件：
1. 多症状模糊叠加（疲劳+低热+小腿胀），每个信号不强但组合需关注
2. 情绪持续低落、失眠、训练动力明显下降
3. 疼痛评分4-6但趋势非改善
→ 行动：建议监测具体指标（体温/小腿围度/疼痛趋势），如加重则联系医生

【normal — 正常恢复】
触发条件：
1. 术后预期内的疼痛（训练后暂时加重，休息缓解，评分≤5）
2. 术后天数与症状匹配（如术后21天，ROM稳步改善中，疼痛3-4分）
3. 无危险信号叠加
→ 行动：安抚+解释+鼓励继续，不需要过度警示

🔑 关键：术后天数决定阈值！
- 术后第3天疼痛7分 ≈ 正常（术后急性疼痛期）
- 术后第30天疼痛7分 ≈ 异常（应已显著缓解）
- 请在 reasoning 中明确说明术后天数对判读的影响

📋 药物安全特别注意：
- 患者提到"止痛药后头晕恶心" → 至少 attention，可能 warning
- 患者提到"想停药""想换药" → 这不是此 prompt 的判读范围，但需在 recommendation 中建议咨询医生
- 注意区分 NSAIDs（胃肠风险）、阿片类（呼吸抑制/便秘）、抗凝药（出血风险）

请以 JSON 格式返回结果。"""

    def __init__(self, rules_path: Optional[str] = None):
        rules_path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)
        self.emergency_keywords = self.rules.get("emergency_keywords", [])
        self.warning_rules = self.rules.get("warning_rules", [])

    def assess(self, patient_state: Dict[str, Any]) -> Dict[str, Any]:
        """双路判读主入口。"""
        # 第一路：规则引擎（快速确定性判读）
        rule_result = self._rule_based_assessment(patient_state)

        # 紧急情况直接返回，不浪费 AI 调用
        if rule_result["safety_level"] == "emergency":
            return rule_result

        # 第二路：AI 判读（处理复杂语义和模糊表达）
        ai_result = self._ai_based_assessment(patient_state)

        # 融合策略：取更严重的结果
        return self._merge_results(rule_result, ai_result)

    def _rule_based_assessment(self, patient_state: Dict) -> Dict[str, Any]:
        """基于结构化规则的确定性判读。"""
        feedback = patient_state.get("daily_feedback", "").lower()

        # 1. 紧急关键词拦截（最优先）
        for keyword in self.emergency_keywords:
            if keyword in feedback:
                logger.warning(
                    "Patient %s triggered emergency keyword: %s",
                    patient_state.get("patient_id"), keyword,
                )
                return {
                    "safety_level": "emergency",
                    "reasoning": f"患者反馈中检测到高危关键词「{keyword}」",
                    "recommendation": "建议立即急诊就医，不要等待",
                    "requires_doctor_review": True,
                    "source": "rule_engine",
                    "rule_matched": "emergency_keyword",
                }

        # 2. 结构化预警规则匹配
        for rule in self.warning_rules:
            if self._match_rule(rule, patient_state):
                logger.info("Rule matched: %s for patient %s",
                            rule.get("name"), patient_state.get("patient_id"))
                return {
                    "safety_level": rule.get("severity", "warning"),
                    "reasoning": f"触发规则：{rule.get('name', '')}",
                    "recommendation": rule.get("action", ""),
                    "requires_doctor_review": rule.get("requires_doctor_review", False),
                    "source": "rule_engine",
                    "rule_matched": rule.get("name"),
                }

        # 3. 未触发任何预警 → normal
        return {
            "safety_level": "normal",
            "reasoning": "规则引擎未触发预警，各项指标在安全范围内",
            "recommendation": "继续按计划执行康复训练",
            "requires_doctor_review": False,
            "source": "rule_engine",
            "rule_matched": None,
        }

    @staticmethod
    def _match_rule(rule: Dict, patient_state: Dict) -> bool:
        """判断一条规则是否匹配当前患者状态。"""
        conditions = rule.get("conditions", [])
        if not conditions:
            return False

        for cond in conditions:
            field = cond["field"]
            operator = cond["operator"]
            value = cond.get("value")

            # 从 patient_state 中获取字段值
            actual_value = patient_state.get(field)

            # 如果字段不存在，视为不匹配
            if actual_value is None and operator not in ("is_false",):
                return False

            if not OperatorEvaluator.evaluate(actual_value, operator, value):
                return False

        return True

    def _ai_based_assessment(self, patient_state: Dict) -> Dict[str, Any]:
        """基于 AI 的语义判读。"""
        days_post_op = patient_state.get("days_post_op", 0)
        surgery_type = patient_state.get("surgery_type", "")

        prompt = self.SAFETY_PROMPT.format(
            surgery_type=surgery_type,
            surgery_date=patient_state.get("surgery_date", "未知"),
            days_post_op=days_post_op,
            pain_score=patient_state.get("pain_score", 0),
            rom=patient_state.get("rom", "未记录"),
            patient_feedback=patient_state.get("daily_feedback", ""),
            normal_range=self._get_normal_range(days_post_op, surgery_type),
        )

        llm = get_llm_client()
        result = llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        result["source"] = "ai"
        return result

    @staticmethod
    def _get_normal_range(days_post_op: int, surgery_type: str) -> str:
        """根据术后天数和手术类型返回正常恢复范围参考。"""
        ranges = {
            "TKA": {
                (0, 14): "术后0-2周急性期：膝关节屈曲0→90度，疼痛VAS≤5分，助行器部分负重。冰敷+踝泵+DVT预防。",
                (15, 42): "术后2-6周亚急性期：膝关节屈曲≥90→110度，过渡至手杖。闭链运动+平衡训练。",
                (43, 90): "术后6周-3月恢复期：恢复正常步态，屈曲≥110度。上下楼梯+功率自行车。",
                (91, 999): "术后3月+维持期：完全功能恢复，回归运动。活动度≥120度，肌力≥健侧85%。",
            },
            "THA": {
                (0, 14): "术后0-2周急性期：严格遵守防脱位注意事项（后外侧入路：不屈髋>90度、不内收、不内旋）。助行器部分负重。",
                (15, 42): "术后2-6周亚急性期：逐步过渡至手杖完全负重。加强臀中肌+髋外展训练。",
                (43, 90): "术后6周-3月恢复期：恢复正常步态。6周后逐渐解除活动限制。游泳+功率自行车。",
                (91, 999): "术后3月+维持期：完全功能恢复。避免高冲击运动，维持体重。",
            },
            "ACL": {
                (0, 14): "术后0-2周急性保护期：支具锁定0度，双拐足尖触地负重。目标完全伸展，激活股四头肌。",
                (15, 42): "术后2-6周早期保护期：屈曲≥120度，逐步脱拐。闭链运动，严禁开链伸膝抗阻。",
                (43, 90): "术后6周-3月肌力重建期：深蹲+弓步+单腿训练。功率自行车。仍避免开链伸膝。",
                (91, 180): "术后3-6月运动准备期：跳跃训练+敏捷性训练。等速肌力测试评估。",
                (181, 999): "术后6-12月回归运动期：运动专项训练。需通过全套回归运动标准测试。",
            },
        }

        surgery_ranges = ranges.get(surgery_type, ranges["TKA"])
        for (low, high), desc in surgery_ranges.items():
            if low <= days_post_op <= high:
                return desc
        return "参照标准骨科康复指南执行"

    @staticmethod
    def _merge_results(rule_result: Dict, ai_result: Dict) -> Dict:
        """融合规则引擎和 AI 判读结果，取更严重的。"""
        severity_order = {"normal": 0, "attention": 1, "warning": 2, "emergency": 3}
        rule_severity = severity_order.get(rule_result.get("safety_level", "normal"), 0)
        ai_severity = severity_order.get(ai_result.get("safety_level", "normal"), 0)

        if ai_severity > rule_severity:
            logger.info("AI escalated from %s to %s", rule_result.get("safety_level"), ai_result.get("safety_level"))
            merged = dict(ai_result)
            merged["sources"] = ["rule_engine", "ai"]
            return merged

        rule_result["sources"] = ["rule_engine"]
        if ai_severity > 0:
            rule_result["sources"].append("ai")
        return rule_result
