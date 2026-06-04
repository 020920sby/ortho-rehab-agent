"""
LangGraph 多智能体编排器 — 骨科康复的核心流程引擎。

改造点：
- MemorySaver → SqliteSaver：状态持久化，重启可恢复。
- 反馈采集节点改为 interrupt() 暂停点，支持人机协同。
- 节点级错误处理：异常不再用脏数据继续，而是路由到 handle_error 节点生成降级报告。
"""

import os
import logging
from typing import TypedDict, List, Dict, Any, Literal, Optional
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph

# SqliteSaver 在 langgraph 1.x 中被移出核心库，需要兼容处理
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    _HAS_SQLITE_SAVER = True
except ImportError:
    from langgraph.checkpoint.memory import InMemorySaver
    _HAS_SQLITE_SAVER = False
    SqliteSaver = InMemorySaver  # type: ignore

# interrupt / Command — LangGraph 0.2+ 人工介入机制
try:
    from langgraph.types import interrupt, Command
except ImportError:
    try:
        from langgraph import interrupt
        Command = None  # 旧版本无 Command
    except ImportError:
        interrupt = None
        Command = None

# 兼容 LangGraph 不同版本的 END 导入
try:
    from langgraph.graph import END
except ImportError:
    try:
        from langgraph.constants import END
    except ImportError:
        END = "__end__"

from src.agents.rehab_planner import RehabPlanner
from src.agents.safety_sentinel import OrthoSafetySentinel
from src.agents.followup_reporter import FollowupReporter

logger = logging.getLogger(__name__)


# ── 共享状态定义 ──────────────────────────────────

class OrthoRehabState(TypedDict, total=False):
    """骨科康复智能体的共享状态。total=False 表示所有字段可选。"""

    # 患者基础信息
    patient_id: str
    surgery_type: str
    surgery_date: str
    days_post_op: int

    # 当日康复数据
    pain_score: int
    rom: str
    daily_feedback: str
    doctor_orders: str
    pain_trend: str
    rom_trend: str
    completion_rate: float
    vital_signs: str

    # 扩展字段（安全规则匹配用）
    knee_flexion: Optional[int]
    extension_deficit: Optional[int]
    calf_swelling: Optional[bool]
    calf_pain: Optional[bool]
    wound_redness: Optional[bool]
    fever: Optional[bool]
    acute_onset: Optional[bool]
    unable_to_bear_weight: Optional[bool]
    sudden_pop: Optional[bool]
    rapid_swelling: Optional[bool]

    # 系统生成内容
    recovery_phase: str
    daily_plan: Dict[str, Any]

    # 安全判读
    safety_level: str  # normal | attention | warning | emergency
    safety_reasoning: str
    safety_recommendation: str

    # 随访报告
    followup_report: Dict[str, Any]

    # 流程控制
    current_step: str
    human_review_approved: bool
    awaiting_feedback: bool
    node_error: Optional[str]
    error: str


# ── 编排器 ───────────────────────────────────────

class OrthoRehabOrchestrator:
    """
    骨科康复多智能体编排器。

    工作流：
    init → generate_plan → collect_feedback [interrupt] → safety_assessment
       ├─ normal/attention → generate_report → END
       ├─ warning → human_review → generate_report → END
       └─ emergency → alert_doctor → END

    异常路径：
    任一关键节点（generate_plan / safety_assessment / generate_report）
    异常 → handle_error → END
    """

    def __init__(self):
        self.planner = RehabPlanner()
        self.sentinel = OrthoSafetySentinel()
        self.reporter = FollowupReporter()

        # 使用 SqliteSaver 持久化状态（不可用时回退到内存）
        if _HAS_SQLITE_SAVER:
            db_path = os.getenv("CHECKPOINT_DB_PATH", "./data/checkpoints.db")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self.checkpointer = SqliteSaver.from_conn_string(db_path)
            logger.info("SqliteSaver initialized at %s", db_path)
        else:
            self.checkpointer = InMemorySaver()
            logger.info("SqliteSaver not available, using InMemorySaver")

        self.graph = self._build_graph()

    def _build_graph(self):
        """构建 LangGraph 状态图。"""
        workflow = StateGraph(OrthoRehabState)

        # 注册节点
        workflow.add_node("init", self._init_state)
        workflow.add_node("generate_plan", self._generate_plan_node)
        workflow.add_node("collect_feedback", self._collect_feedback_node)
        workflow.add_node("safety_assessment", self._safety_assessment_node)
        workflow.add_node("generate_report", self._generate_report_node)
        workflow.add_node("alert_doctor", self._alert_doctor_node)
        workflow.add_node("human_review", self._human_review_node)
        workflow.add_node("handle_error", self._handle_error_node)

        # 入口
        workflow.set_entry_point("init")

        # init → generate_plan（直接边）
        workflow.add_edge("init", "generate_plan")

        # generate_plan → 检查错误，正常则 collect_feedback，异常则 handle_error
        workflow.add_conditional_edges(
            "generate_plan",
            self._route_after_plan,
            {
                "continue": "collect_feedback",
                "handle_error": "handle_error",
            },
        )

        # collect_feedback → safety_assessment
        workflow.add_edge("collect_feedback", "safety_assessment")

        # safety_assessment → 条件分支（安全检查 + 错误检查）
        workflow.add_conditional_edges(
            "safety_assessment",
            self._route_after_safety,
            {
                "normal": "generate_report",
                "attention": "generate_report",
                "warning": "human_review",
                "emergency": "alert_doctor",
                "handle_error": "handle_error",
            },
        )

        # human_review → generate_report
        workflow.add_edge("human_review", "generate_report")

        # generate_report → 检查错误，正常则结束
        workflow.add_conditional_edges(
            "generate_report",
            self._route_after_report,
            {
                "continue": END,
                "handle_error": "handle_error",
            },
        )

        # 终点边
        workflow.add_edge("alert_doctor", END)
        workflow.add_edge("handle_error", END)

        return workflow.compile(checkpointer=self.checkpointer)

    # ── 节点实现 ──────────────────────────────────

    def _init_state(self, state: OrthoRehabState) -> OrthoRehabState:
        """初始化状态：计算术后天数，填充默认值。"""
        if not state.get("days_post_op"):
            try:
                surgery_date = datetime.strptime(state["surgery_date"], "%Y-%m-%d")
                state["days_post_op"] = (datetime.now() - surgery_date).days
            except (ValueError, KeyError):
                state["days_post_op"] = 0

        state.setdefault("pain_trend", "stable")
        state.setdefault("rom_trend", "稳步改善")
        state.setdefault("completion_rate", 0)
        state.setdefault("vital_signs", "正常范围")
        state.setdefault("doctor_orders", "遵医嘱执行术后康复方案")
        state.setdefault("current_step", "init")
        state.setdefault("human_review_approved", False)
        state.setdefault("awaiting_feedback", False)
        state.setdefault("node_error", None)

        logger.info("Initialized state for patient %s, days_post_op=%d",
                     state.get("patient_id"), state.get("days_post_op"))
        return state

    def _generate_plan_node(self, state: OrthoRehabState) -> OrthoRehabState:
        """生成康复计划。异常时设 node_error，由条件边路由到 handle_error。"""
        try:
            plan = self.planner.generate_plan(dict(state))
            state["daily_plan"] = plan
            state["recovery_phase"] = plan.get("recovery_phase", state.get("recovery_phase", "急性期"))
            state["current_step"] = "generate_plan"
            state["node_error"] = None
            logger.info("Plan generated for patient %s", state.get("patient_id"))
        except Exception as e:
            logger.exception("Plan generation failed for patient %s", state.get("patient_id"))
            state["node_error"] = f"Plan generation failed: {str(e)}"
            state["current_step"] = "generate_plan_failed"
        return state

    def _collect_feedback_node(self, state: OrthoRehabState) -> OrthoRehabState:
        """
        反馈采集节点 — 人机协同暂停点。

        如果 daily_feedback 已包含在初始请求中，直接跳过。
        否则调用 interrupt() 暂停图执行，等待外部通过
        POST /api/v1/rehab/{patient_id}/feedback 提交反馈后恢复。
        """
        state["current_step"] = "collect_feedback"

        # 已有反馈则跳过中断
        existing = state.get("daily_feedback", "")
        if existing and existing.strip():
            logger.debug("Feedback already present for patient %s, skipping interrupt",
                         state.get("patient_id"))
            state["awaiting_feedback"] = False
            return state

        # 暂停等待外部反馈
        state["awaiting_feedback"] = True
        logger.info("Awaiting feedback for patient %s — graph interrupted", state.get("patient_id"))

        if interrupt is None:
            logger.error("interrupt() not available in this langgraph version; "
                         "upgrade to langgraph>=0.2.0")
            state["node_error"] = "Feedback collection requires langgraph>=0.2.0"
            return state

        submitted = interrupt({
            "type": "feedback_required",
            "patient_id": state.get("patient_id"),
            "message": "请提交患者日常反馈以继续康复计划生成",
        })

        # 恢复执行后更新状态
        if isinstance(submitted, dict):
            new_feedback = submitted.get("daily_feedback", "")
            if new_feedback:
                state["daily_feedback"] = new_feedback
            if submitted.get("pain_score") is not None:
                state["pain_score"] = int(submitted["pain_score"])
            if submitted.get("rom"):
                state["rom"] = str(submitted["rom"])
        elif isinstance(submitted, str) and submitted.strip():
            state["daily_feedback"] = submitted

        state["awaiting_feedback"] = False
        logger.info("Feedback received for patient %s", state.get("patient_id"))
        return state

    def _safety_assessment_node(self, state: OrthoRehabState) -> OrthoRehabState:
        """安全判读节点——双路判读。异常时设 node_error，路由到 handle_error。"""
        try:
            result = self.sentinel.assess(dict(state))
            state["safety_level"] = result.get("safety_level", "normal")
            state["safety_reasoning"] = result.get("reasoning", "")
            state["safety_recommendation"] = result.get("recommendation", "")
            state["current_step"] = "safety_assessment"
            state["node_error"] = None

            level = state["safety_level"]
            logger.info("Safety assessment: %s for patient %s", level, state.get("patient_id"))
            if level in ("warning", "emergency"):
                logger.warning(
                    "Patient %s: level=%s, reason=%s",
                    state.get("patient_id"), level, state.get("safety_reasoning"),
                )
        except Exception as e:
            logger.exception("Safety assessment failed for patient %s", state.get("patient_id"))
            state["node_error"] = f"Safety assessment failed: {str(e)}"
            state["current_step"] = "safety_assessment_failed"
            # 保留现有安全等级（如有），否则给 attention 降级默认值
            if not state.get("safety_level"):
                state["safety_level"] = "attention"
                state["safety_reasoning"] = f"安全判读异常：{e}"
                state["safety_recommendation"] = "建议人工复核"
        return state

    def _generate_report_node(self, state: OrthoRehabState) -> OrthoRehabState:
        """生成随访报告。异常时设 node_error，路由到 handle_error。"""
        try:
            report = self.reporter.generate_report(dict(state))
            state["followup_report"] = report
            state["current_step"] = "generate_report"
            state["node_error"] = None
            logger.info("Report generated for patient %s: %s",
                         state.get("patient_id"), report.get("report_id"))
        except Exception as e:
            logger.exception("Report generation failed for patient %s", state.get("patient_id"))
            state["node_error"] = f"Report generation failed: {str(e)}"
            state["current_step"] = "generate_report_failed"
        return state

    def _handle_error_node(self, state: OrthoRehabState) -> OrthoRehabState:
        """
        错误处理节点 — 降级安全兜底。

        当 generate_plan / safety_assessment / generate_report 任一节点
        异常时路由到此。记录错误日志，设置安全等级为 attention，
        并生成一份标注「系统异常，部分数据缺失」的降级报告。
        """
        error_msg = state.get("node_error", "Unknown error")
        failed_step = state.get("current_step", "unknown")
        patient_id = state.get("patient_id", "unknown")

        logger.error("Error handled for patient %s at step %s: %s",
                     patient_id, failed_step, error_msg)

        state["current_step"] = "error_handled"

        # 降级安全判读
        if not state.get("safety_level") or state["safety_level"] == "":
            state["safety_level"] = "attention"
        state["safety_reasoning"] = (
            f"系统在「{failed_step}」步骤处理异常，部分数据缺失：{error_msg}"
        )
        state["safety_recommendation"] = "建议医生人工审核患者数据并制定康复方案"

        # 降级报告
        state["followup_report"] = {
            "report_id": f"ERR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "patient_id": patient_id,
            "generated_at": datetime.now().isoformat(),
            "summary": f"系统在生成报告时遇到异常（{failed_step}），请人工审核患者状态。",
            "progress_assessment": {
                "pain_control": "unknown",
                "rom_progress": "unknown",
                "functional_status": "unknown",
                "compliance": "unknown",
            },
            "key_findings": [f"系统处理异常，部分数据缺失 — {failed_step}"],
            "risk_alerts": ["系统异常 - 建议人工全面评估患者状态"],
            "recommendations": [
                "请医生手动审核患者数据",
                "检查系统日志排查异常原因",
                "异常恢复后可重新提交康复计划生成请求",
            ],
            "next_review": "立即",
            "export_format_markdown": (
                f"# 系统异常报告\n\n"
                f"- **患者ID**：{patient_id}\n"
                f"- **异常步骤**：{failed_step}\n"
                f"- **异常信息**：{error_msg}\n\n"
                f"## 说明\n\n"
                f"处理患者数据时发生异常，系统已降级处理。请人工审核患者当前状态并制定康复方案。\n"
            ),
        }

        return state

    def _alert_doctor_node(self, state: OrthoRehabState) -> OrthoRehabState:
        """
        紧急预警节点。
        真实系统中触发：短信/App推送/护士站通知。
        当前实现输出日志并标记。
        """
        state["current_step"] = "alert_doctor"
        logger.critical(
            "EMERGENCY ALERT for patient %s: %s",
            state.get("patient_id"), state.get("safety_reasoning"),
        )
        print(f"\n{'='*60}")
        print(f"🚨 紧急预警！患者 {state.get('patient_id')} 触发紧急预警！")
        print(f"   原因：{state.get('safety_reasoning')}")
        print(f"   建议：{state.get('safety_recommendation')}")
        print(f"{'='*60}\n")
        return state

    def _human_review_node(self, state: OrthoRehabState) -> OrthoRehabState:
        """
        人工审核节点。
        真实系统中暂停流程，等待医生在审核界面确认或修改。
        """
        state["current_step"] = "human_review"
        logger.info("Human review required for patient %s", state.get("patient_id"))
        print(f"\n{'='*60}")
        print(f"⏸️  患者 {state.get('patient_id')} 需要人工审核")
        print(f"   安全等级：{state.get('safety_level')}")
        print(f"   判读依据：{state.get('safety_reasoning')}")
        print(f"   建议措施：{state.get('safety_recommendation')}")
        print(f"{'='*60}\n")
        # 默认自动通过（生产环境需改为等待医生确认）
        state["human_review_approved"] = True
        return state

    # ── 路由逻辑 ──────────────────────────────────

    @staticmethod
    def _route_after_plan(state: OrthoRehabState) -> str:
        """generate_plan 之后的路由：检查错误。"""
        if state.get("node_error"):
            return "handle_error"
        return "continue"

    @staticmethod
    def _route_after_safety(state: OrthoRehabState) -> str:
        """根据安全等级（及是否有节点错误）决定下一步。"""
        if state.get("node_error"):
            return "handle_error"

        level = state.get("safety_level", "normal")
        if level not in ("normal", "attention", "warning", "emergency"):
            logger.warning("Unknown safety level '%s', defaulting to attention", level)
            return "attention"
        return level

    @staticmethod
    def _route_after_report(state: OrthoRehabState) -> str:
        """generate_report 之后的路由：检查错误。"""
        if state.get("node_error"):
            return "handle_error"
        return "continue"

    # ── 对外接口 ──────────────────────────────────

    @staticmethod
    def _config_for(patient_id: str) -> Dict[str, Any]:
        return {"configurable": {"thread_id": patient_id}}

    def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行完整的康复管理流程，返回最终状态。

        如果流程在 collect_feedback 处被 interrupt() 暂停，
        返回包含 awaiting_feedback=True 的部分状态。
        调用方应检查此字段并提示用户提交反馈，然后使用
        resume_with_feedback() 继续。
        """
        config = self._config_for(initial_state.get("patient_id", "default"))
        try:
            result = self.graph.invoke(initial_state, config)
            return result
        except Exception as e:
            # GraphInterrupt 从 langgraph 内部抛出，类型因版本而异
            exc_name = type(e).__name__
            if "Interrupt" in exc_name or "interrupt" in str(e).lower():
                logger.info("Graph interrupted for patient %s, awaiting feedback",
                            initial_state.get("patient_id"))
                # 读取当前 checkpoint 中的状态
                current_state = self.graph.get_state(config)
                if current_state and current_state.values:
                    partial = dict(current_state.values)
                    partial["awaiting_feedback"] = True
                    partial["current_step"] = "awaiting_feedback"
                    return partial
                return {
                    **initial_state,
                    "awaiting_feedback": True,
                    "current_step": "awaiting_feedback",
                }
            raise

    def resume_with_feedback(
        self, patient_id: str, feedback: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        提交反馈并恢复被中断的流程。

        Args:
            patient_id: 患者ID（对应 graph 的 thread_id）
            feedback: 反馈数据，至少包含 daily_feedback 字段

        Returns:
            流程完成后的最终状态
        """
        if Command is None:
            raise RuntimeError(
                "langgraph.types.Command not available; "
                "upgrade to langgraph>=0.2.0"
            )

        config = self._config_for(patient_id)
        result = self.graph.invoke(Command(resume=feedback), config)
        return result

    async def arun(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """异步运行流程。"""
        config = self._config_for(initial_state.get("patient_id", "default"))
        try:
            result = await self.graph.ainvoke(initial_state, config)
            return result
        except Exception as e:
            exc_name = type(e).__name__
            if "Interrupt" in exc_name or "interrupt" in str(e).lower():
                logger.info("Async graph interrupted for patient %s",
                            initial_state.get("patient_id"))
                current_state = self.graph.get_state(config)
                if current_state and current_state.values:
                    partial = dict(current_state.values)
                    partial["awaiting_feedback"] = True
                    partial["current_step"] = "awaiting_feedback"
                    return partial
                return {
                    **initial_state,
                    "awaiting_feedback": True,
                    "current_step": "awaiting_feedback",
                }
            raise

    async def aresume_with_feedback(
        self, patient_id: str, feedback: Dict[str, Any]
    ) -> Dict[str, Any]:
        """异步恢复被中断的流程。"""
        if Command is None:
            raise RuntimeError(
                "langgraph.types.Command not available; "
                "upgrade to langgraph>=0.2.0"
            )

        config = self._config_for(patient_id)
        result = await self.graph.ainvoke(Command(resume=feedback), config)
        return result


# ── 便捷：获取编排器单例 ─────────────────────────

_orchestrator_instance: Optional[OrthoRehabOrchestrator] = None


def get_orchestrator() -> OrthoRehabOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = OrthoRehabOrchestrator()
    return _orchestrator_instance


# ── 直接运行测试 ─────────────────────────────────

if __name__ == "__main__":
    import json

    orchestrator = OrthoRehabOrchestrator()

    test_patient = {
        "patient_id": "P001",
        "surgery_type": "TKA",
        "surgery_date": "2026-04-01",
        "days_post_op": 19,
        "pain_score": 4,
        "rom": "膝关节屈曲95度，伸展0度",
        "daily_feedback": "今天走路时膝盖有点酸，但冰敷后好转。没有发热，伤口愈合良好。",
        "doctor_orders": "术后4周门诊复查，继续口服塞来昔布每日一次。",
        "pain_trend": "stable",
        "rom_trend": "稳步改善",
        "completion_rate": 85,
    }

    result = orchestrator.run(test_patient)

    print("\n📅 康复计划：")
    print(json.dumps(result.get("daily_plan", {}), indent=2, ensure_ascii=False))

    print("\n🛡️ 安全判读：")
    print(f"  等级: {result.get('safety_level')}")
    print(f"  依据: {result.get('safety_reasoning')}")

    print("\n📊 随访报告：")
    print(json.dumps(result.get("followup_report", {}), indent=2, ensure_ascii=False))
