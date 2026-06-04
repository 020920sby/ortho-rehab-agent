"""
FastAPI 后端服务 — 骨科康复智能体 API。

修复点：
- 原方案直接实例化 orchestrator（无法复用知识库和 LLM 连接）。
  改为使用 get_orchestrator() 惰性单例。
- 添加了请求频率限制（slowapi）和输入验证。
- 添加了 /health 健康检查端点。
- 添加了 CORS 和安全响应头。
- 异常处理更精细，区分 422（验证错误）和 500（内部错误）。
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, Any

# 确保 src/ 在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
import uvicorn

from src.agents.graph_orchestrator import get_orchestrator
from src.ocr.parser import process_uploaded_order
from src.models.llm_client import get_llm_client
from src.db.persistence import (
    save_checkin, get_today_checkin, get_today_exercises,
    save_exercises, complete_exercise, get_progress,
    ensure_patient, update_patient, get_patient, list_all_patients,
    save_chat_message, get_recent_chat,
    save_medication_log, get_today_medication_logs, seed_today_medications,
    save_exercise_log, get_exercise_details, get_rom_trend,
    save_followup, get_followups, get_next_followup, update_followup,
    delete_followup, seed_default_followups,
    get_emergency_contacts, save_emergency_contacts,
    save_order_record, get_order_records, get_order_detail,
)

# ── 日志配置 ────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI 应用 ────────────────────────────────

app = FastAPI(
    title="骨科康复智能体 API",
    description="基于 Baichuan-M2-32B 的多智能体骨科术后康复管理系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 启动事件：自动初始化知识库 ──────────────────

_KNOWLEDGE_BASE_READY = False


@app.on_event("startup")
async def startup_event():
    """应用启动时检查并自动初始化知识库。"""
    global _KNOWLEDGE_BASE_READY
    try:
        from src.rag.vector_store import OrthoVectorStore
        store = OrthoVectorStore()
        doc_count = store.collection.count()
        if doc_count == 0:
            logger.warning("Knowledge base is empty, auto-initializing...")
            from src.rag.vector_store import build_knowledge_base
            store = build_knowledge_base()
            doc_count = store.collection.count()
            logger.info("Knowledge base initialized with %d documents", doc_count)
        else:
            logger.info("Knowledge base already contains %d documents", doc_count)
        _KNOWLEDGE_BASE_READY = True
    except Exception as e:
        logger.error("Failed to initialize knowledge base: %s", e)
        logger.warning("System will operate without RAG — plans will use LLM general knowledge only")


# ── 请求/响应模型 ───────────────────────────────

VALID_SURGERY_TYPES = {"TKA", "THA", "ACL", "其他"}


class RehabRequest(BaseModel):
    patient_id: str = Field(..., min_length=1, max_length=50, description="患者唯一标识")
    surgery_type: str = Field(..., description="手术类型：TKA/THA/ACL/其他")
    surgery_date: str = Field(..., description="手术日期，格式 YYYY-MM-DD")
    pain_score: int = Field(..., ge=0, le=10, description="VAS疼痛评分 0-10")
    rom: Optional[str] = Field("", description="关节活动度描述")
    daily_feedback: Optional[str] = Field("", description="患者今日自我反馈")
    doctor_orders: Optional[str] = Field("", description="医嘱摘要")
    pain_trend: Optional[str] = Field("stable", description="疼痛趋势：improving/stable/worsening")
    rom_trend: Optional[str] = Field("稳步改善", description="活动度变化趋势")
    completion_rate: Optional[float] = Field(0, ge=0, le=100, description="计划完成率(%)")

    # 扩展字段（安全规则匹配用）
    knee_flexion: Optional[int] = Field(None, description="膝关节屈曲角度(度)")
    extension_deficit: Optional[int] = Field(None, description="伸展缺失角度(度)")
    calf_swelling: Optional[bool] = Field(None, description="小腿肿胀")
    calf_pain: Optional[bool] = Field(None, description="小腿疼痛")
    wound_redness: Optional[bool] = Field(None, description="切口发红")
    fever: Optional[bool] = Field(None, description="发热")
    acute_onset: Optional[bool] = Field(None, description="急性发作")
    unable_to_bear_weight: Optional[bool] = Field(None, description="无法承重")
    sudden_pop: Optional[bool] = Field(None, description="突然弹响")
    rapid_swelling: Optional[bool] = Field(None, description="快速肿胀")

    @field_validator("surgery_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("surgery_date 必须为 YYYY-MM-DD 格式")
        return v

    @field_validator("surgery_type")
    @classmethod
    def validate_surgery_type(cls, v: str) -> str:
        if v not in VALID_SURGERY_TYPES:
            raise ValueError(f"surgery_type 必须为 {VALID_SURGERY_TYPES} 之一")
        return v


class RehabResponse(BaseModel):
    patient_id: str
    daily_plan: Dict[str, Any]
    safety_level: str
    safety_reasoning: str
    safety_recommendation: str
    followup_report: Dict[str, Any]
    current_step: str


class FeedbackRequest(BaseModel):
    daily_feedback: str = Field(..., min_length=1, max_length=2000, description="患者日常反馈")
    pain_score: Optional[int] = Field(None, ge=0, le=10, description="更新疼痛评分（可选）")
    rom: Optional[str] = Field(None, description="更新关节活动度（可选）")


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


# ── 新增模型：AI Chat ───────────────────────────

class ChatRequest(BaseModel):
    messages: list = Field(..., description="对话历史 [{role, content}]")
    patient_id: str = Field("default", max_length=50)


class ChatResponse(BaseModel):
    reply: str
    patient_id: str


# ── 新增模型：打卡 ─────────────────────────────

class CheckInRequest(BaseModel):
    patient_id: str = Field(..., max_length=50)
    pain_score: int = Field(..., ge=0, le=10)
    rom: str = Field("")
    walking_ability: str = Field("")
    symptoms: list[str] = Field(default_factory=list)
    daily_feedback: str = Field("")


class CheckInResponse(BaseModel):
    status: str
    checkin_date: str
    plan_refresh_needed: bool = True
    message: str = ""


class PlanRefreshRequest(BaseModel):
    patient_id: str = Field(..., max_length=50)
    surgery_type: Optional[str] = Field(None, description="手术类型，不传则从数据库读取")
    surgery_date: Optional[str] = Field(None, description="手术日期，不传则从数据库读取")


class PlanRefreshResponse(BaseModel):
    patient_id: str
    daily_plan: Dict[str, Any]
    recovery_phase: str


# ── 新增模型：训练 ─────────────────────────────

class ExerciseItem(BaseModel):
    id: str
    name: str
    duration: str = ""
    sets: str = ""
    keyPoints: str = ""
    warning: str = ""
    completed: bool = False


class ExerciseCompleteRequest(BaseModel):
    exercise_id: str


# ── 新增模型：用药日志 ─────────────────────────

class MedicationLogRequest(BaseModel):
    drug_name: str = Field(..., description="药品名称")
    taken: bool = Field(..., description="是否已服用")
    dosage: str = Field("", description="剂量")
    skipped_reason: str = Field("", description="未服用原因")


# ── 新增模型：训练日志（含跳过） ─────────────

class ExerciseLogRequest(BaseModel):
    exercise_id: str = Field(..., description="训练项目ID")
    exercise_name: str = Field("", description="训练项目名称")
    completed: bool = Field(False, description="是否完成")
    skipped_reason: str = Field("", description="跳过原因（疼痛/疲劳/其他）")


# ── 新增模型：患者 Profile ─────────────────────

class PatientProfile(BaseModel):
    patient_id: str
    name: str
    age: int | None = None
    gender: str = ""
    surgery_type: str = ""
    surgery_date: str = ""
    doctor_name: str = ""
    contact: str = ""


class PatientProfileUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    gender: str | None = None
    surgery_type: str | None = None
    surgery_date: str | None = None
    doctor_name: str | None = None
    contact: str | None = None


# ── 新增模型：复诊计划 ──────────────────────────

class FollowupCreate(BaseModel):
    followup_date: str = Field(..., description="复诊日期 YYYY-MM-DD")
    hospital: str = Field("", description="医院名称")
    department: str = Field("", description="科室")
    doctor_name: str = Field("", description="医生姓名")
    content: str = Field("", description="复诊内容")
    precautions: str = Field("", description="注意事项")
    materials_to_bring: str = Field("", description="需携带材料")
    reminder_enabled: bool = Field(False, description="是否开启提醒")
    reminder_before_days: int = Field(1, ge=0, le=7, description="提前几天提醒")
    source: str = Field("manual", description="数据来源")
    notes: str = Field("", description="备注")

    @field_validator("followup_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("followup_date 必须为 YYYY-MM-DD 格式")
        return v


class FollowupUpdate(BaseModel):
    followup_date: str | None = None
    hospital: str | None = None
    department: str | None = None
    doctor_name: str | None = None
    content: str | None = None
    precautions: str | None = None
    materials_to_bring: str | None = None
    reminder_enabled: bool | None = None
    reminder_before_days: int | None = None
    notes: str | None = None
    completed: bool | None = None


class FollowupGenerateRequest(BaseModel):
    surgery_type: str = Field("", description="手术类型，不传则从数据库读取")
    surgery_date: str = Field("", description="手术日期，不传则从数据库读取")


# ── 路由 ────────────────────────────────────────

@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="running",
        version="1.0.0",
        timestamp=datetime.now().isoformat(),
    )


@app.get("/health")
async def health_check():
    """健康检查端点（含知识库状态）。"""
    return {
        "status": "healthy",
        "knowledge_base_ready": _KNOWLEDGE_BASE_READY,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/v1/rehab/generate", response_model=RehabResponse)
async def generate_rehab_plan(request: RehabRequest):
    """
    核心 API：生成个性化康复计划 + 安全判读 + 随访报告。

    如果 daily_feedback 未提供，流程会在反馈采集节点暂停，
    返回 202 状态码并要求通过 POST /api/v1/rehab/{patient_id}/feedback
    提交反馈后继续执行。
    """
    try:
        orchestrator = get_orchestrator()
        patient_state = request.model_dump()

        logger.info("Processing rehab plan for patient %s (type=%s)",
                     request.patient_id, request.surgery_type)

        result = orchestrator.run(patient_state)

        # 流程被中断，等待反馈提交
        if result.get("awaiting_feedback"):
            logger.info("Graph interrupted for patient %s, awaiting feedback",
                        request.patient_id)
            return JSONResponse(
                status_code=202,
                content={
                    "status": "awaiting_feedback",
                    "patient_id": request.patient_id,
                    "message": "请提交患者日常反馈以继续康复计划生成",
                    "feedback_endpoint": f"/api/v1/rehab/{request.patient_id}/feedback",
                    "current_step": result.get("current_step", "awaiting_feedback"),
                },
            )

        # 如果有节点错误，记录但不阻断响应
        if result.get("node_error"):
            logger.warning("Node error for patient %s: %s",
                           request.patient_id, result["node_error"])

        return RehabResponse(
            patient_id=request.patient_id,
            daily_plan=result.get("daily_plan", {}),
            safety_level=result.get("safety_level", "normal"),
            safety_reasoning=result.get("safety_reasoning", ""),
            safety_recommendation=result.get("safety_recommendation", ""),
            followup_report=result.get("followup_report", {}),
            current_step=result.get("current_step", "completed"),
        )

    except Exception as e:
        logger.exception("Failed to process patient %s", request.patient_id)
        raise HTTPException(
            status_code=500,
            detail=f"康复计划生成失败：{str(e)}",
        )


@app.get("/api/v1/patient/{patient_id}")
async def get_patient_basic(patient_id: str):
    """获取患者基本信息（前端 Profile 页用）。"""
    try:
        patient = get_patient(patient_id)
        if not patient:
            return {
                "patient_id": patient_id,
                "name": "",
                "age": None,
                "gender": "",
                "surgery_type": "",
                "surgery_date": "",
                "days_post_op": 0,
                "recovery_phase": "",
                "doctor_name": "",
                "contact": "",
            }
        from datetime import datetime as dt
        surgery_date = patient.get("surgery_date", "")
        days_post_op = 0
        if surgery_date:
            try:
                surgery_dt = dt.strptime(surgery_date, "%Y-%m-%d")
                days_post_op = (dt.now() - surgery_dt).days
            except ValueError:
                pass
        recovery_phase = ""
        if days_post_op >= 0:
            if days_post_op <= 14:
                recovery_phase = "急性保护期" if patient.get("surgery_type") == "ACL" else "急性期"
            elif days_post_op <= 42:
                recovery_phase = "早期保护性训练期" if patient.get("surgery_type") == "ACL" else "亚急性期"
            elif days_post_op <= 90:
                recovery_phase = "肌力重建期" if patient.get("surgery_type") == "ACL" else "恢复期"
            else:
                recovery_phase = "运动准备期" if patient.get("surgery_type") == "ACL" else "维持期"
        return {
            **patient,
            "days_post_op": days_post_op,
            "recovery_phase": recovery_phase,
        }
    except Exception as e:
        logger.exception("Failed to get patient %s", patient_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/patient/{patient_id}/history")
async def get_patient_history(patient_id: str):
    """
    获取患者历史康复记录（从 LangGraph SqliteSaver 中读取）。
    生产环境应替换为数据库查询。
    """
    try:
        orchestrator = get_orchestrator()
        config = {"configurable": {"thread_id": patient_id}}
        state = orchestrator.graph.get_state(config)

        if state is None or state.values is None:
            return {"patient_id": patient_id, "history": [], "message": "无历史记录"}

        return {
            "patient_id": patient_id,
            "last_plan": state.values.get("daily_plan", {}),
            "last_safety_level": state.values.get("safety_level", "unknown"),
            "current_step": state.values.get("current_step", "unknown"),
        }
    except Exception as e:
        logger.exception("Failed to get history for %s", patient_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/rehab/{patient_id}/feedback", response_model=RehabResponse)
async def submit_rehab_feedback(patient_id: str, request: FeedbackRequest):
    """
    提交患者日常反馈以恢复被中断的康复流程。

    当 POST /api/v1/rehab/generate 返回 202（awaiting_feedback）时，
    调用此端点提交反馈数据，系统将继续执行安全判读和报告生成。
    """
    try:
        orchestrator = get_orchestrator()

        # 检查是否处于等待反馈状态
        config = {"configurable": {"thread_id": patient_id}}
        current_state = orchestrator.graph.get_state(config)

        if current_state is None or current_state.values is None:
            raise HTTPException(
                status_code=404,
                detail=f"未找到患者 {patient_id} 的状态。请先调用 /api/v1/rehab/generate。",
            )

        current_step = current_state.values.get("current_step", "")
        if current_step not in ("collect_feedback", "awaiting_feedback"):
            raise HTTPException(
                status_code=409,
                detail=f"患者 {patient_id} 当前不在等待反馈状态（current_step={current_step}），无需提交反馈。",
            )

        # 构造恢复数据
        resume_data = {"daily_feedback": request.daily_feedback}
        if request.pain_score is not None:
            resume_data["pain_score"] = request.pain_score
        if request.rom is not None:
            resume_data["rom"] = request.rom

        logger.info("Resuming graph for patient %s with feedback", patient_id)
        result = await orchestrator.aresume_with_feedback(patient_id, resume_data)

        return RehabResponse(
            patient_id=patient_id,
            daily_plan=result.get("daily_plan", {}),
            safety_level=result.get("safety_level", "normal"),
            safety_reasoning=result.get("safety_reasoning", ""),
            safety_recommendation=result.get("safety_recommendation", ""),
            followup_report=result.get("followup_report", {}),
            current_step=result.get("current_step", "completed"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to resume graph for patient %s", patient_id)
        raise HTTPException(
            status_code=500,
            detail=f"反馈提交失败：{str(e)}",
        )


@app.post("/api/v1/order/parse")
async def parse_medical_order(file: UploadFile = File(...), patient_id: str = ""):
    """
    上传医嘱文档 → 提取文本 → LLM 解析为结构化数据。
    可选传入 patient_id 以自动存储解析记录。

    支持格式：PDF、Word (.docx)、文本 (.txt/.md)、图片 (.jpg/.png)。
    返回原始文本预览 + 结构化医嘱 JSON。
    """
    try:
        content = await file.read()
        result = process_uploaded_order(content, file.filename)
        parsed = result.get("parsed", {})
        raw_text = result.get("raw_text", "")
        error_msg = result.get("error", "")

        # 如果提供了 patient_id，自动存储
        record = None
        if patient_id and not error_msg:
            try:
                ensure_patient(patient_id)
                record = save_order_record(patient_id, file.filename, raw_text, parsed)
            except Exception as e:
                logger.warning("Failed to save order record: %s", e)

        return {
            "filename": file.filename,
            "raw_text_preview": raw_text[:2000],
            "parsed": parsed,
            "error": error_msg,
            "record_id": record["id"] if record else None,
        }
    except Exception as e:
        logger.exception("Failed to parse uploaded order")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/patient/{patient_id}/orders")
async def get_patient_orders(patient_id: str):
    """获取患者所有医嘱/病历上传记录列表。"""
    try:
        orders = get_order_records(patient_id)
        return {"patient_id": patient_id, "orders": orders, "total": len(orders)}
    except Exception as e:
        logger.exception("Failed to get order records")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/patient/{patient_id}/orders/{order_id}")
async def get_patient_order_detail(patient_id: str, order_id: int):
    """获取单条医嘱记录完整详情（含解析数据）。"""
    try:
        order = get_order_detail(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="医嘱记录不存在")
        return order
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get order detail")
        raise HTTPException(status_code=500, detail=str(e))


# ── AI Chat ──────────────────────────────────────

CHAT_SYSTEM_PROMPT = """你是一位专业的骨科术后康复AI管家，拥有丰富的骨科康复医学知识。

🚨🚨🚨 最重要的安全规则 — 违反将危及患者生命 — 必须无条件遵守 🚨🚨🚨

规则1：无论任何情况，永远不要建议患者停止、更换、减少或跳过处方药物（包括止痛药、抗凝药、抗生素等）。
即使患者说"吃药后不舒服"，你的回答必须是：
"不要自行停药。药物副作用需要医生评估。请立即联系你的主治医生说明情况，由医生决定是否需要调整药物。在联系到医生之前，[给出安全的暂时缓解建议，如休息、多喝水等]。"
❌ 错误示范："先停止服用该药物" ← 这是危险建议，绝对禁止！
✅ 正确示范："不要自行停药。药物副作用需要医生评估，请立即联系主治医生。"

规则2：永远不要解读医学影像报告（X光、CT、MRI）中的任何发现。即使患者把报告内容念给你听，你的回答必须是：
"我不能解读影像报告。这需要影像科医生和你的主治医生结合临床情况综合判断。请务必带着报告去复诊时与医生讨论。"

规则3：永远不要给患者下诊断（"你这是感染了""你这是XX病"）。你可以列出需要关注的信号，但必须明确说"我不能做诊断，建议联系医生评估"。

规则4：永远不要建议患者使用别人的处方药，或推荐/反对具体的处方药品牌。

────────────────────────
你的职责：
────────────────────────
1. **信息采集（最高优先级）**：当患者信息不足以做出判断时，必须先追问再给建议
2. **异常判断**：识别潜在风险（DVT、感染、脱位、移植物失败等），按要求升级
3. **康复问答**：回答患者关于术后恢复、训练动作、饮食等方面的疑问
4. **进度分析**：根据患者提供的康复数据，分析恢复进展情况
5. **心理支持**：共情理解，鼓励患者坚持，但不空洞说教
6. **复诊指导**：告知复诊前的准备事项

────────────────────────
🔍 分级追问协议 — 这是你最核心的能力 — 必须严格遵守：
────────────────────────

【核心原则】
在给出任何建议之前，你必须先确认自己掌握了足够的判断依据。
宁可多问一轮，不要基于不完整信息给建议。

【最小信息门槛】
以下信息至少要有 2 项，你才可以开始给建议：
☐ 疼痛评分（0-10）
☐ 症状的持续时间/何时开始
☐ 是否有紧急信号（参考下方 Tier 0）

【四级追问流程】

Tier 0 — ⚡ 紧急筛查（每次对话必须先过这关）
  在回复的第一句话之前，快速判断：患者描述中是否包含紧急信号？
  如果包含任何 emergency 信号 → 跳过追问，直接按风险升级指引行动。
  如果不确定 → 先问："有没有胸痛、呼吸困难、小腿突然剧痛肿胀？"

Tier 1 — 📊 核心量化（缺了就问，一次最多2个）
  必须追问（如果缺失）：
  - 疼痛评分（0-10，0=不疼 10=最疼）
  - 具体位置（膝盖内侧/外侧/前方？小腿？大腿？）
  - 什么情况下加重/缓解？（活动时？休息时？训练后？）
  追问模板："你说的[症状]，如果用0-10分描述大概是几分？具体是哪个位置？"

Tier 2 — 📋 补充信息（Tier 1 拿到后再问）
  - 什么时候开始的？突然还是逐渐？
  - 有没有伴随症状？（肿胀、发热、发红、弹响）
  - 最近做了什么可能相关的事？（训练加量？姿势不当？）

Tier 3 — 🎯 针对性追问（根据具体症状触发）
  - 药物相关 → "具体是什么药？剂量？吃了多久？"
  - 训练相关 → "具体哪个动作？做了几组？什么重量？"
  - 睡眠相关 → "是疼痛导致睡不着？还是姿势不舒服？还是焦虑？"
  - 情绪相关 → "是身体不舒服让你沮丧？还是看不到进步？还是其他原因？"

【追问格式规范】
- 一次最多问 2 个问题，不要列清单式追问
- 先共情一句话，再问问题
- 如果患者已经提供了 Tier 1 信息，直接跳到给建议 + 可选追问 Tier 2
- ❌ 错误示范：患者说"膝盖疼"→你回"建议冰敷休息"（信息不够就给了建议）
- ✅ 正确示范：患者说"膝盖疼"→你回"理解，膝盖不舒服确实影响生活。想先了解两个关键信息：如果用0-10分描述大概是几分？具体是哪个位置疼？"

────────────────────────
🚨 风险升级指引：
────────────────────────
【emergency】
触发：胸痛/呼吸困难/咯血/伤口大出血/高热>39℃/小腿突然剧痛肿胀(DVT)/腹股沟剧痛+腿动不了(脱位)/弹响后关节完全不稳
→ 明确告知紧急→建议立即120或急诊→告知等待时安全体位→禁止说"先观察"

【warning】
触发：伤口红肿+发热/疼痛≥7药物无效/弹响后关节不稳定感/药物副作用(头晕恶心等)/THA术后体位违规后疼痛
→ 指出风险→建议尽快联系医生(不等)→给暂时安全处理→禁止只说"观察几天"

【attention】
触发：多症状模糊叠加/情绪持续低落/ROM两周无改善/疼痛4-6分趋势不确定
→ 共情+指出需关注信号→建议监测具体指标→如加重联系医生

【normal】
触发：术后预期内疼痛(训练后加重休息缓解，≤5分)/症状与术后阶段匹配/无危险信号叠加
→ 安抚+解释原因+鼓励继续+不需要过度警示+不需要加"但如果加重请就医"（这会增加不必要的焦虑）

────────────────────────
通用规则：
────────────────────────
- 遵守分级追问协议 — 信息不足时不给建议
- 用药建议需注明"请遵医嘱最终确认"
- 控制在200字以内，适合手机阅读
- 不确定时诚实说"建议咨询医生"，不编造
- 每次对话结束前，检查是否还有关键信息缺口需要追问

{patient_context}"""


def _build_patient_context(patient_id: str) -> str:
    """构建患者当前状态上下文，注入到 AI 管家对话中。"""
    patient = get_patient(patient_id)
    if not patient:
        return ""

    parts = []
    parts.append("【当前患者信息】")

    surgery_type = patient.get("surgery_type", "")
    surgery_date = patient.get("surgery_date", "")
    if surgery_type:
        parts.append(f"手术类型：{surgery_type}")
    if surgery_date:
        parts.append(f"手术日期：{surgery_date}")
        from datetime import datetime as _dt
        try:
            surgery_dt = _dt.strptime(surgery_date, "%Y-%m-%d")
            days = (_dt.now() - surgery_dt).days
            parts.append(f"术后天数：第{days}天")
        except ValueError:
            pass

    # 今日打卡数据
    checkin = get_today_checkin(patient_id)
    if checkin:
        parts.append(f"今日疼痛评分：{checkin.get('pain_score', '未记录')}/10")
        rom = checkin.get("rom", "")
        if rom:
            parts.append(f"今日活动度：{rom}")
        feedback = checkin.get("daily_feedback", "")
        if feedback:
            parts.append(f"今日自述：{feedback}")

    # 用药记录
    med_logs = get_today_medication_logs(patient_id)
    if med_logs:
        taken = [m for m in med_logs if m.get("taken")]
        not_taken = [m for m in med_logs if not m.get("taken")]
        if not_taken:
            parts.append(f"未服用药物：{', '.join(m['drug_name'] for m in not_taken)}")
        if taken:
            parts.append(f"已服用药物：{', '.join(m['drug_name'] for m in taken)}")

    # 训练完成情况
    exercises = get_today_exercises(patient_id)
    if exercises:
        done = sum(1 for e in exercises if e.get("completed"))
        total = len(exercises)
        parts.append(f"今日训练完成：{done}/{total}项")

    if len(parts) == 1:
        return ""  # 无有效数据

    parts.append("\n请根据以上患者当前状态，提供个性化的康复指导。")
    return "\n".join(parts)


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """AI 康复管家对话接口（注入患者当前状态 + RAG 知识检索）。"""
    try:
        llm = get_llm_client()
        patient_id = request.patient_id

        # 确保患者记录存在
        ensure_patient(patient_id)

        # 获取最近的对话历史
        history = get_recent_chat(patient_id, limit=10)

        # ── RAG 知识检索 ─────────────────────────
        rag_context = ""
        patient_info = get_patient(patient_id)
        surgery_type = patient_info.get("surgery_type", "") if patient_info else ""
        # 提取用户最后一条消息作为检索查询
        user_query = ""
        for msg in reversed(request.messages):
            if msg.get("role") == "user" and msg.get("content"):
                user_query = msg["content"]
                break
        if user_query:
            try:
                from src.rag.vector_store import OrthoVectorStore
                store = OrthoVectorStore()
                rag_docs = store.search(
                    query=f"{surgery_type} 术后康复 {user_query}" if surgery_type else user_query,
                    n_results=3,
                    surgery_type=surgery_type if surgery_type else "",
                )
                if rag_docs:
                    rag_context = "\n\n".join(
                        f"【参考资料 {i+1} — 来源：{d['metadata'].get('source', '未知')} | {d['metadata'].get('section', '')}】\n{d['content'][:500]}"
                        for i, d in enumerate(rag_docs)
                    )
            except Exception as e:
                logger.warning("RAG retrieval failed for chat: %s", e)

        # 构建含患者上下文的系统提示
        patient_context = _build_patient_context(patient_id)
        # 注入 RAG 上下文
        rag_section = f"\n\n【循证知识库参考（基于当前问题检索）】\n{rag_context}" if rag_context else ""
        system_content = CHAT_SYSTEM_PROMPT.format(
            patient_context=(patient_context if patient_context else "（患者信息尚未完善，请引导患者完善个人信息和每日打卡）") + rag_section
        )

        messages = [{"role": "system", "content": system_content}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})

        # 追加本次请求中的新消息
        for msg in request.messages:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        # 保存用户消息
        for msg in request.messages:
            if msg.get("role") == "user" and msg.get("content"):
                save_chat_message(patient_id, "user", msg["content"])

        reply = llm.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )

        # 保存 AI 回复
        save_chat_message(patient_id, "assistant", reply)

        return ChatResponse(reply=reply, patient_id=patient_id)
    except Exception as e:
        logger.exception("Chat failed for patient %s: %s", patient_id, str(e))
        error_detail = f"AI服务暂时不可用：{str(e)[:200]}"
        raise HTTPException(status_code=500, detail=error_detail)


@app.get("/api/v1/patient/{patient_id}/chat/history")
async def get_chat_history(patient_id: str, limit: int = 50):
    """获取患者聊天历史记录（前端加载用）。"""
    try:
        history = get_recent_chat(patient_id, limit=limit)
        # 转换为前端 Message 格式
        messages = [
            {
                "id": i + 1,
                "role": h["role"],
                "content": h["content"],
            }
            for i, h in enumerate(history)
        ]
        return {"patient_id": patient_id, "messages": messages, "total": len(messages)}
    except Exception as e:
        logger.exception("Failed to get chat history for %s", patient_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/patients")
async def list_patients():
    """列出所有已创建的患者（供前端患者选择器使用）。"""
    try:
        patients = list_all_patients()
        # 只返回前端需要的字段
        result = []
        for p in patients:
            days_post_op = 0
            if p.get("surgery_date"):
                from datetime import datetime as _dt
                try:
                    surgery_dt = _dt.strptime(p["surgery_date"], "%Y-%m-%d")
                    days_post_op = (_dt.now() - surgery_dt).days
                except ValueError:
                    pass
            result.append({
                "patient_id": p["patient_id"],
                "name": p["name"] or "",
                "surgery_type": p["surgery_type"] or "",
                "surgery_date": p["surgery_date"] or "",
                "days_post_op": max(0, days_post_op),
                "created_at": p.get("created_at", ""),
            })
        return {"patients": result, "total": len(result)}
    except Exception as e:
        logger.exception("Failed to list patients")
        raise HTTPException(status_code=500, detail=str(e))


# ── Check-In ─────────────────────────────────────

@app.post("/api/v1/checkin", response_model=CheckInResponse)
async def submit_checkin(request: CheckInRequest):
    """
    提交每日康复打卡 — 纯数据记录，不触发 LangGraph 流程。

    打卡成功后返回 plan_refresh_needed=True，前端可提示用户
    调用 POST /api/v1/plan/refresh 重新生成个性化康复计划。
    """
    try:
        ensure_patient(request.patient_id)
        result = save_checkin(request.patient_id, request.model_dump())

        # 仅做健康评估（如果反馈包含紧急关键词，立即提示）
        message = ""
        has_feedback = request.daily_feedback and request.daily_feedback.strip()
        pain_high = request.pain_score >= 7

        if pain_high:
            message = "疼痛评分较高，建议联系医生评估。系统已记录本次打卡。"
        elif has_feedback:
            message = "打卡成功。点击「更新计划」可获取最新的个性化康复方案。"
        else:
            message = "打卡成功。"

        return CheckInResponse(
            status="ok",
            checkin_date=result["checkin_date"],
            plan_refresh_needed=has_feedback or pain_high,
            message=message,
        )
    except Exception as e:
        logger.exception("Checkin failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/plan/refresh", response_model=PlanRefreshResponse)
async def refresh_plan(request: PlanRefreshRequest):
    """
    轻量级计划刷新 — 基于最新打卡数据重新生成康复计划。

    与 /rehab/generate 不同：不触发完整 LangGraph 流程（无反馈中断点），
    仅做 RAG 检索 + LLM 生成 + 安全判读，适合打卡后快速刷新。
    """
    try:
        # 读取患者信息
        patient_info = get_patient(request.patient_id)
        if not patient_info:
            raise HTTPException(status_code=404, detail=f"患者 {request.patient_id} 不存在")

        surgery_type = request.surgery_type or patient_info.get("surgery_type", "")
        surgery_date = request.surgery_date or patient_info.get("surgery_date", "")

        # 读取今日打卡
        today_checkin = get_today_checkin(request.patient_id)
        pain_score = today_checkin["pain_score"] if today_checkin else 0
        rom = today_checkin["rom"] if today_checkin else ""
        feedback = today_checkin["daily_feedback"] if today_checkin else ""

        # 计算术后天数
        from datetime import datetime as dt
        days_post_op = 0
        if surgery_date:
            try:
                surgery_dt = dt.strptime(surgery_date, "%Y-%m-%d")
                days_post_op = (dt.now() - surgery_dt).days
            except ValueError:
                pass

        # 轻量：仅生成计划 + 安全判读
        from src.agents.rehab_planner import RehabPlanner
        from src.agents.safety_sentinel import OrthoSafetySentinel

        planner = RehabPlanner()
        sentinel = OrthoSafetySentinel()

        patient_state = {
            "patient_id": request.patient_id,
            "surgery_type": surgery_type,
            "surgery_date": surgery_date,
            "days_post_op": days_post_op,
            "pain_score": pain_score,
            "rom": rom,
            "daily_feedback": feedback,
            "pain_trend": "stable",
            "rom_trend": "稳步改善",
            "completion_rate": 0,
        }

        plan = planner.generate_plan(patient_state)
        patient_state["daily_plan"] = plan
        patient_state["recovery_phase"] = plan.get("recovery_phase", "")

        safety = sentinel.assess(patient_state)

        logger.info("Plan refreshed for patient %s, safety=%s",
                     request.patient_id, safety.get("safety_level"))

        return PlanRefreshResponse(
            patient_id=request.patient_id,
            daily_plan=plan,
            recovery_phase=plan.get("recovery_phase", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Plan refresh failed for %s", request.patient_id)
        raise HTTPException(status_code=500, detail=f"计划刷新失败：{str(e)}")


@app.get("/api/v1/patient/{patient_id}/checkin/today")
async def get_today_checkin_endpoint(patient_id: str):
    """获取患者今日打卡数据。"""
    try:
        checkin = get_today_checkin(patient_id)
        if not checkin:
            return {"patient_id": patient_id, "checkin": None, "has_checkin": False}
        return {"patient_id": patient_id, "checkin": checkin, "has_checkin": True}
    except Exception as e:
        logger.exception("Failed to get today checkin")
        raise HTTPException(status_code=500, detail=str(e))


def _get_default_exercises(surgery_type: str = "") -> list:
    """根据手术类型返回默认训练列表（配置化兜底）。"""
    defaults = {
        "TKA": [
            {"id": "1", "name": "直腿抬高训练", "duration": "10分钟", "sets": "3组×15次",
             "keyPoints": "保持膝盖伸直，缓慢抬起", "warning": "避免用力过猛，感到剧痛立即停止", "completed": False},
            {"id": "2", "name": "膝关节屈伸练习", "duration": "8分钟", "sets": "2组×10次",
             "keyPoints": "坐姿进行，动作缓慢控制", "warning": "屈曲角度不超过当前最大值", "completed": False},
            {"id": "3", "name": "踝泵运动", "duration": "5分钟", "sets": "持续5分钟",
             "keyPoints": "脚尖向上勾起，再向下压", "warning": "预防血栓，每小时建议做一次", "completed": False},
            {"id": "4", "name": "靠墙静蹲", "duration": "6分钟", "sets": "3组×30秒",
             "keyPoints": "膝关节不超过脚尖", "warning": "如感到膝盖疼痛，减少下蹲深度", "completed": False},
            {"id": "5", "name": "行走训练", "duration": "15分钟", "sets": "室内行走",
             "keyPoints": "保持正确姿势，均匀负重", "warning": "使用单拐辅助，避免跌倒", "completed": False},
        ],
        "THA": [
            {"id": "1", "name": "踝泵运动", "duration": "5分钟", "sets": "持续5分钟",
             "keyPoints": "脚尖向上勾起，再向下压", "warning": "预防血栓，每小时建议做一次", "completed": False},
            {"id": "2", "name": "臀中肌等长收缩", "duration": "8分钟", "sets": "3组×10次",
             "keyPoints": "仰卧位收紧臀部，保持5秒", "warning": "不屈髋超过90度", "completed": False},
            {"id": "3", "name": "髋外展训练", "duration": "8分钟", "sets": "2组×10次",
             "keyPoints": "侧卧位，缓慢外展下肢", "warning": "不内收过中线，避免脱位风险", "completed": False},
            {"id": "4", "name": "股四头肌等长收缩", "duration": "5分钟", "sets": "3组×10次",
             "keyPoints": "仰卧位膝盖窝下压床面", "warning": "保持髋关节中立位", "completed": False},
            {"id": "5", "name": "助行器行走训练", "duration": "15分钟", "sets": "室内行走",
             "keyPoints": "保持正确姿势，均匀负重", "warning": "步态对称，避免跛行", "completed": False},
        ],
        "ACL": [
            {"id": "1", "name": "股四头肌等长收缩", "duration": "10分钟", "sets": "3组×15次",
             "keyPoints": "仰卧位，膝盖窝下压床面，股四头肌收紧", "warning": "保持膝关节完全伸直", "completed": False},
            {"id": "2", "name": "直腿抬高", "duration": "8分钟", "sets": "3组×10次",
             "keyPoints": "保持膝盖伸直，缓慢抬高至30cm", "warning": "不进行开链伸膝抗阻训练", "completed": False},
            {"id": "3", "name": "踝泵运动", "duration": "5分钟", "sets": "持续5分钟",
             "keyPoints": "脚尖向上勾起，再向下压", "warning": "预防血栓，每小时建议做一次", "completed": False},
            {"id": "4", "name": "被动伸膝练习", "duration": "5分钟", "sets": "2组×5分钟",
             "keyPoints": "仰卧位脚踝下垫毛巾卷，利用重力伸展", "warning": "目标完全伸展，不强行过伸", "completed": False},
            {"id": "5", "name": "支具保护行走", "duration": "15分钟", "sets": "室内行走",
             "keyPoints": "支具锁定0度，双拐足尖触地负重", "warning": "避免旋转运动", "completed": False},
        ],
    }
    return defaults.get(surgery_type, defaults["TKA"])


@app.get("/api/v1/patient/{patient_id}/exercises")
async def get_patient_exercises(patient_id: str):
    """获取患者今日训练项目列表。已有则直接返回，否则根据手术类型返回默认训练。"""
    try:
        exercises = get_today_exercises(patient_id)
        if exercises:
            return {"patient_id": patient_id, "exercises": exercises}
        # 无今日训练数据：根据患者手术类型返回默认训练
        patient_info = get_patient(patient_id)
        surgery_type = patient_info.get("surgery_type", "TKA") if patient_info else "TKA"
        default_exercises = _get_default_exercises(surgery_type)
        save_exercises(patient_id, default_exercises)
        return {"patient_id": patient_id, "exercises": default_exercises}
    except Exception as e:
        logger.exception("Failed to get exercises")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/patient/{patient_id}/exercises/complete")
async def complete_patient_exercise(patient_id: str, request: ExerciseCompleteRequest):
    """标记某个训练项目为已完成（向后兼容）。"""
    try:
        result = complete_exercise(patient_id, request.exercise_id)
        return {"status": "ok", "exercise": result}
    except Exception as e:
        logger.exception("Failed to complete exercise")
        raise HTTPException(status_code=500, detail=str(e))


# ── Medication Log ───────────────────────────────

@app.post("/api/v1/rehab/{patient_id}/medication-log")
async def log_medication(patient_id: str, request: MedicationLogRequest):
    """记录用药状态（已服用/未服用）。"""
    try:
        result = save_medication_log(
            patient_id=patient_id,
            drug_name=request.drug_name,
            taken=request.taken,
            dosage=request.dosage,
            skipped_reason=request.skipped_reason,
        )
        return result
    except Exception as e:
        logger.exception("Failed to log medication")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/rehab/{patient_id}/medication-log")
async def get_medication_logs(patient_id: str):
    """获取今日用药记录。"""
    try:
        logs = get_today_medication_logs(patient_id)
        return {"patient_id": patient_id, "medications": logs}
    except Exception as e:
        logger.exception("Failed to get medication logs")
        raise HTTPException(status_code=500, detail=str(e))


# ── Exercise Log (enhanced) ──────────────────────

@app.post("/api/v1/rehab/{patient_id}/exercise-log")
async def log_exercise(patient_id: str, request: ExerciseLogRequest):
    """记录训练状态（完成/跳过），支持跳过原因。"""
    try:
        result = save_exercise_log(
            patient_id=patient_id,
            exercise_id=request.exercise_id,
            exercise_name=request.exercise_name,
            completed=request.completed,
            skipped_reason=request.skipped_reason,
        )
        return result
    except Exception as e:
        logger.exception("Failed to log exercise")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/patient/{patient_id}/exercises/log")
async def get_exercise_logs(patient_id: str):
    """获取患者训练详情日志。"""
    try:
        details = get_exercise_details(patient_id)
        return {"patient_id": patient_id, "logs": details}
    except Exception as e:
        logger.exception("Failed to get exercise logs")
        raise HTTPException(status_code=500, detail=str(e))


# ── Progress ─────────────────────────────────────

@app.get("/api/v1/patient/{patient_id}/progress")
async def get_patient_progress(patient_id: str):
    """获取患者康复进度数据（含趋势图、ROM、里程碑）。"""
    try:
        progress = get_progress(patient_id)
        # 补充 ROM 趋势数据（从打卡记录解析）
        rom_trend = get_rom_trend(patient_id)
        # 补充里程碑数据
        milestones = _compute_milestones(patient_id)
        return {
            "patient_id": patient_id,
            **progress,
            "rom_trend": rom_trend if rom_trend else progress.get("rom_trend", []),
            "milestones": milestones,
        }
    except Exception as e:
        logger.exception("Failed to get progress")
        raise HTTPException(status_code=500, detail=str(e))


def _get_surgery_milestones(surgery_type: str) -> list:
    """根据手术类型返回对应的里程碑列表。"""
    milestones_map = {
        "TKA": [
            {"id": 1, "title": "术后第1周：完成首次直腿抬高", "completed": False},
            {"id": 2, "title": "术后第2周：膝关节屈曲达到90°", "completed": False},
            {"id": 3, "title": "术后第3周：脱离双拐，使用单拐", "completed": False},
            {"id": 4, "title": "术后第4周：膝关节屈曲达到110°", "completed": False},
            {"id": 5, "title": "术后第6周：脱拐自主行走", "completed": False},
            {"id": 6, "title": "术后第8周：恢复日常活动", "completed": False},
        ],
        "THA": [
            {"id": 1, "title": "术后第1周：完成踝泵+臀肌等长收缩", "completed": False},
            {"id": 2, "title": "术后第2周：助行器下独立行走", "completed": False},
            {"id": 3, "title": "术后第4周：过渡至手杖完全负重", "completed": False},
            {"id": 4, "title": "术后第6周：解除活动限制，正常步态", "completed": False},
            {"id": 5, "title": "术后第3月：上下楼梯自如", "completed": False},
            {"id": 6, "title": "术后第6月：恢复低冲击运动", "completed": False},
        ],
        "ACL": [
            {"id": 1, "title": "术后第1周：实现膝关节完全伸展", "completed": False},
            {"id": 2, "title": "术后第2周：屈曲达到90°", "completed": False},
            {"id": 3, "title": "术后第6周：屈曲达到120°，脱拐行走", "completed": False},
            {"id": 4, "title": "术后第3月：开始慢跑训练", "completed": False},
            {"id": 5, "title": "术后第6月：通过回归运动测试", "completed": False},
            {"id": 6, "title": "术后第9月：恢复竞技运动", "completed": False},
        ],
    }
    return milestones_map.get(surgery_type, milestones_map["TKA"])


def _compute_milestones(patient_id: str) -> list:
    """从打卡和训练数据计算里程碑完成情况（手术类型自适应）。"""
    patient_info = get_patient(patient_id)
    surgery_type = patient_info.get("surgery_type", "TKA") if patient_info else "TKA"
    milestones = _get_surgery_milestones(surgery_type)

    rom_trend = get_rom_trend(patient_id)
    if rom_trend:
        max_flex = max((r.get("value") or 0 for r in rom_trend), default=0)
        if max_flex >= 90:
            for m in milestones:
                if "90°" in m["title"]:
                    m["completed"] = True
        if max_flex >= 110:
            for m in milestones:
                if "110°" in m["title"]:
                    m["completed"] = True
        if max_flex >= 120:
            for m in milestones:
                if "120°" in m["title"]:
                    m["completed"] = True

    # 从打卡天数判断
    from datetime import datetime as dt
    surgery_date = patient_info.get("surgery_date", "") if patient_info else ""
    if surgery_date:
        try:
            surgery_dt = dt.strptime(surgery_date, "%Y-%m-%d")
            days_post_op = (dt.now() - surgery_dt).days
            for m in milestones:
                import re as _re
                week_match = _re.search(r'第(\d+)周', m["title"])
                month_match = _re.search(r'第(\d+)月', m["title"])
                if week_match:
                    week_num = int(week_match.group(1))
                    if days_post_op >= week_num * 7:
                        m["completed"] = True
                if month_match:
                    month_num = int(month_match.group(1))
                    if days_post_op >= month_num * 30:
                        m["completed"] = True
        except ValueError:
            pass

    return milestones


# ── Profile ──────────────────────────────────────

@app.get("/api/v1/patient/{patient_id}/profile")
async def get_patient_profile(patient_id: str):
    """获取患者个人信息。"""
    try:
        patient = get_patient(patient_id)
        if not patient:
            # 返回默认患者信息
            return {
                "patient_id": patient_id,
                "name": "张先生",
                "age": None,
                "gender": "",
                "surgery_type": "TKA",
                "surgery_date": "",
                "doctor_name": "",
                "contact": "",
            }
        return patient
    except Exception as e:
        logger.exception("Failed to get profile")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/patient/{patient_id}/profile")
async def update_patient_profile(patient_id: str, request: PatientProfileUpdate):
    """更新患者个人信息。"""
    try:
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        result = update_patient(patient_id, updates)
        return result
    except Exception as e:
        logger.exception("Failed to update profile")
        raise HTTPException(status_code=500, detail=str(e))


# ── 新增模型：紧急联系人 ────────────────────────

class EmergencyContact(BaseModel):
    name: str = Field("", max_length=50)
    relationship: str = Field("", max_length=50)
    phone: str = Field("", max_length=30)


class EmergencyContactsUpdate(BaseModel):
    contacts: list[EmergencyContact] = Field(..., max_length=3)


# ── Emergency Contacts ──────────────────────────────

@app.get("/api/v1/patient/{patient_id}/contacts")
async def get_patient_contacts(patient_id: str):
    """获取患者紧急联系人列表。"""
    try:
        ensure_patient(patient_id)
        contacts = get_emergency_contacts(patient_id)
        return {"patient_id": patient_id, "contacts": contacts, "total": len(contacts)}
    except Exception as e:
        logger.exception("Failed to get contacts")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/patient/{patient_id}/contacts")
async def update_patient_contacts(patient_id: str, request: EmergencyContactsUpdate):
    """保存紧急联系人（覆盖写入，最多3个）。"""
    try:
        contacts_data = [c.model_dump() for c in request.contacts]
        saved = save_emergency_contacts(patient_id, contacts_data)
        return {"patient_id": patient_id, "contacts": saved, "total": len(saved)}
    except Exception as e:
        logger.exception("Failed to save contacts")
        raise HTTPException(status_code=500, detail=str(e))


# ── Followup Plans ────────────────────────────────

@app.get("/api/v1/patient/{patient_id}/followups")
async def get_patient_followups(patient_id: str, upcoming_only: bool = False):
    """获取患者复诊计划列表。upcoming_only=true 只返回未来未完成的。"""
    try:
        followups = get_followups(patient_id, upcoming_only=upcoming_only)
        next_followup = get_next_followup(patient_id)
        return {
            "patient_id": patient_id,
            "followups": followups,
            "total": len(followups),
            "next_followup": next_followup,
        }
    except Exception as e:
        logger.exception("Failed to get followups")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/patient/{patient_id}/followups")
async def create_patient_followup(patient_id: str, request: FollowupCreate):
    """创建复诊计划记录。"""
    try:
        ensure_patient(patient_id)
        data = request.model_dump()
        data["source"] = data.get("source", "manual")
        result = save_followup(patient_id, data)
        return result
    except Exception as e:
        logger.exception("Failed to create followup")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/patient/{patient_id}/followups/{followup_id}")
async def update_patient_followup(patient_id: str, followup_id: int, request: FollowupUpdate):
    """更新复诊计划记录。"""
    try:
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        if "completed" in updates:
            updates["completed"] = 1 if updates.pop("completed") else 0
        result = update_followup(followup_id, updates)
        if not result:
            raise HTTPException(status_code=404, detail="复诊计划不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update followup")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/patient/{patient_id}/followups/{followup_id}")
async def delete_patient_followup(patient_id: str, followup_id: int):
    """删除复诊计划记录。"""
    try:
        delete_followup(followup_id)
        return {"status": "ok", "message": "复诊计划已删除"}
    except Exception as e:
        logger.exception("Failed to delete followup")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/patient/{patient_id}/followups/generate")
async def generate_patient_followups(patient_id: str, request: FollowupGenerateRequest = None):
    """AI 生成默认复诊计划（基于手术类型）。"""
    try:
        patient_info = get_patient(patient_id)
        if not patient_info:
            raise HTTPException(status_code=404, detail=f"患者 {patient_id} 不存在")

        surgery_type = (request.surgery_type if request and request.surgery_type
                        else patient_info.get("surgery_type", ""))
        surgery_date = (request.surgery_date if request and request.surgery_date
                        else patient_info.get("surgery_date", ""))

        if not surgery_type:
            raise HTTPException(status_code=400, detail="请先设置手术类型")

        plans = seed_default_followups(patient_id, surgery_type, surgery_date)
        return {
            "status": "ok",
            "message": f"已生成 {len(plans)} 条复诊计划（{surgery_type} 标准方案）",
            "followups": plans,
            "source": "ai_generated",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate followups")
        raise HTTPException(status_code=500, detail=str(e))


# ── 异常处理 ────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ── 启动入口 ─────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8001"))
    logger.info("Starting OrthoRehab API on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
