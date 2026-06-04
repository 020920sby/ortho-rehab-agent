"""
Streamlit 前端 — 骨科康复智能助手（患者端 + 医生端）。

修复点：
- 原方案 `sys.path.append` 指向了错误的路径，导致 import src.* 失败。
- orchestrator 改为惰性初始化（首次点击按钮时才加载），加快页面首次渲染。
- 安全等级用颜色块直观展示。
- 添加了紧急情况时的醒目警报横幅。
"""

import sys
import os

# 将项目根目录加入 Python 路径
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
import json
from datetime import datetime, timedelta

# OCR 文档解析
from src.ocr.parser import process_uploaded_order

# ── 页面配置 ────────────────────────────────────

st.set_page_config(
    page_title="骨科康复智能助手",
    page_icon="🦴",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🦴 骨科术后康复智能助手")
st.caption("基于 Baichuan-M2-32B + LangGraph 多智能体架构 | v1.0")


# ── 惰性初始化（避免每次刷新都加载模型和知识库） ──

@st.cache_resource
def get_orchestrator():
    from src.agents.graph_orchestrator import OrthoRehabOrchestrator
    return OrthoRehabOrchestrator()


@st.cache_resource
def ensure_knowledge_base():
    """确保知识库已构建（首次运行自动加载指南文档）。"""
    from src.rag.vector_store import build_knowledge_base
    return build_knowledge_base()


# ── 侧边栏：患者信息录入 ──────────────────────

with st.sidebar:
    # ── 医嘱上传 ──────────────────────────────
    with st.expander("📄 上传医嘱文档", expanded=False):
        uploaded_file = st.file_uploader(
            "上传医嘱/出院小结/手术记录",
            type=["pdf", "txt", "md", "docx", "jpg", "jpeg", "png"],
            help="支持 PDF、Word、文本和图片格式",
        )

        if uploaded_file is not None:
            st.caption(f"已选择: {uploaded_file.name}")

            if st.button("🔍 解析医嘱", type="secondary", use_container_width=True):
                with st.spinner("正在提取文本并解析..."):
                    result = process_uploaded_order(
                        uploaded_file.getvalue(),
                        uploaded_file.name,
                    )
                    st.session_state["upload_result"] = result

                    if result.get("error"):
                        st.error(result["error"])
                    else:
                        st.success("✅ 解析完成！")
                        # 原始文本预览
                        with st.expander("📝 原始文本预览", expanded=False):
                            st.text(result.get("raw_text", ""))
                        # 结构化结果
                        st.json(result.get("parsed", {}))
                        # 标记表单已可从解析结果预填
                        st.session_state["auto_fill_from_upload"] = True

        if "upload_result" in st.session_state and st.session_state["upload_result"].get("parsed"):
            if st.button("↩️ 清除解析结果", type="tertiary"):
                st.session_state.pop("upload_result", None)
                st.session_state.pop("auto_fill_from_upload", None)
                st.rerun()

    # ── 患者信息 ──────────────────────────────
    st.header("📋 患者信息")

    # 从上传解析结果中获取默认值
    upload_parsed = (
        st.session_state.get("upload_result", {}).get("parsed", {})
        if st.session_state.get("auto_fill_from_upload")
        else {}
    )

    patient_id = st.text_input(
        "患者ID",
        value=upload_parsed.get("patient_name") or "P001",
    )
    # 从上传解析中获取手术类型默认值
    parsed_surgery = upload_parsed.get("surgery_type", "")
    surgery_options = ["TKA", "THA", "ACL", "其他"]
    surgery_labels = {
        "TKA": "TKA（全膝关节置换）",
        "THA": "THA（全髋关节置换）",
        "ACL": "ACL（前交叉韧带重建）",
        "其他": "其他骨科手术",
    }
    # 确定默认选项索引
    default_surgery_idx = 3  # 默认"其他"
    for i, opt in enumerate(surgery_options):
        if opt == parsed_surgery or parsed_surgery.upper() == opt:
            default_surgery_idx = i
            break
    surgery_type = st.selectbox(
        "手术类型",
        surgery_options,
        index=default_surgery_idx,
        format_func=lambda x: surgery_labels.get(x, x),
    )

    # 从上传解析中获取手术日期
    default_date = datetime.now().date() - timedelta(days=19)
    if upload_parsed.get("surgery_date"):
        try:
            default_date = datetime.strptime(upload_parsed["surgery_date"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    surgery_date = st.date_input("手术日期", value=default_date)

    st.markdown("---")
    st.subheader("📊 今日评估")

    pain_score = st.slider("疼痛评分 (VAS 0-10)", 0, 10, 4,
                           help="0=无痛, 10=无法忍受的剧痛")
    rom = st.text_input("关节活动度", value="膝关节屈曲95度，伸展0度",
                        help="例如：膝关节屈曲95度")
    pain_trend = st.selectbox("疼痛趋势", ["improving", "stable", "worsening"],
                              format_func=lambda x: {
                                  "improving": "逐渐好转", "stable": "保持稳定",
                                  "worsening": "持续加重"}.get(x, x))
    rom_trend = st.selectbox("活动度趋势", ["稳步改善", "按预期改善", "停滞", "倒退"])

    st.markdown("---")
    st.subheader("⚠️ 风险筛查（选填）")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        calf_swelling = st.checkbox("小腿肿胀")
        wound_redness = st.checkbox("切口发红")
        acute_onset = st.checkbox("急性发作")
    with col_s2:
        calf_pain = st.checkbox("小腿疼痛")
        fever = st.checkbox("发热>38℃")
        sudden_pop = st.checkbox("关节弹响")

    st.markdown("---")
    st.subheader("📝 今日反馈")
    # 从解析结果中获取康复计划文本作为默认反馈参考
    default_feedback = "今天走路时膝盖有点酸，但冰敷后好转。没有发热，伤口愈合良好。"
    if upload_parsed.get("rehabilitation_plan"):
        default_feedback = f"[医嘱康复指导]\n{upload_parsed['rehabilitation_plan']}\n\n[今日感受]\n{default_feedback}"
    daily_feedback = st.text_area(
        "请描述今天的感受",
        value=default_feedback,
        height=120,
    )

    # 启动按钮
    st.markdown("---")
    run_btn = st.button("🚀 生成康复计划", type="primary", use_container_width=True)

# ── 主区域：双栏布局 ──────────────────────────────

col_left, col_right = st.columns([1, 1])

# ── 核心逻辑 ────────────────────────────────────

if run_btn:
    # 后台初始化知识库（首次运行）
    with st.spinner("正在初始化知识库..."):
        ensure_knowledge_base()

    with st.spinner("正在生成个性化康复计划和安全评估..."):
        orchestrator = get_orchestrator()

        days_post_op = (datetime.now().date() - surgery_date).days

        # 拼接医嘱文本
        doctor_orders_parts = ["遵医嘱执行术后康复方案"]
        if upload_parsed.get("rehabilitation_plan"):
            doctor_orders_parts.append(f"[康复指导] {upload_parsed['rehabilitation_plan']}")
        if upload_parsed.get("weight_bearing"):
            doctor_orders_parts.append(f"[负重限制] {upload_parsed['weight_bearing']}")
        if upload_parsed.get("special_instructions"):
            doctor_orders_parts.append(f"[特殊说明] {upload_parsed['special_instructions']}")
        if upload_parsed.get("precautions"):
            doctor_orders_parts.append(f"[注意事项] {'; '.join(upload_parsed['precautions'])}")

        patient_state = {
            "patient_id": patient_id,
            "surgery_type": surgery_type,
            "surgery_date": surgery_date.strftime("%Y-%m-%d"),
            "days_post_op": days_post_op,
            "pain_score": pain_score,
            "rom": rom,
            "daily_feedback": daily_feedback,
            "doctor_orders": "\n".join(doctor_orders_parts),
            "pain_trend": pain_trend,
            "rom_trend": rom_trend,
            "completion_rate": 85,
            "calf_swelling": calf_swelling,
            "calf_pain": calf_pain,
            "wound_redness": wound_redness,
            "fever": fever,
            "acute_onset": acute_onset,
            "sudden_pop": sudden_pop,
        }
        # 附加解析出的用药信息
        if upload_parsed.get("medications"):
            patient_state["medications_from_order"] = upload_parsed["medications"]
        if upload_parsed.get("diagnosis"):
            patient_state["diagnosis"] = upload_parsed["diagnosis"]

        try:
            result = orchestrator.run(patient_state)
            st.session_state["plan"] = result.get("daily_plan", {})
            st.session_state["safety"] = {
                "level": result.get("safety_level", "normal"),
                "reasoning": result.get("safety_reasoning", ""),
                "recommendation": result.get("safety_recommendation", ""),
            }
            st.session_state["report"] = result.get("followup_report", {})
            st.session_state["error"] = result.get("error", "")
        except Exception as e:
            st.error(f"生成失败：{e}")
            st.session_state["plan"] = {}
            st.session_state["safety"] = {"level": "unknown", "reasoning": str(e)}
            st.session_state["report"] = {}

# ── 左侧：康复计划 ──────────────────────────────

with col_left:
    st.header("📅 今日康复计划")

    if "plan" not in st.session_state:
        st.info("👈 请在左侧填写患者信息后点击「生成康复计划」")
    elif st.session_state.get("plan"):
        plan = st.session_state["plan"]

        if "error" in plan:
            st.error(f"生成失败：{plan['error']}")
            st.text(plan.get("raw", ""))
        else:
            phase = plan.get("recovery_phase", "未知")
            st.success(f"📌 康复阶段：**{phase}**")
            st.info(f"🎯 今日目标：{plan.get('daily_goal', '按计划完成康复训练')}")

            # 用药提醒
            with st.expander("💊 用药提醒", expanded=True):
                meds = plan.get("medication", [])
                if meds:
                    for med in meds:
                        st.markdown(
                            f"- **{med.get('drug_name', '')}**："
                            f"{med.get('dosage', '')}，{med.get('frequency', '')}"
                        )
                        if med.get("notes"):
                            st.caption(f"  ⚠️ {med['notes']}")
                else:
                    st.text("无特殊用药")

            # 康复训练
            with st.expander("🏋️ 康复训练", expanded=True):
                exercises = plan.get("exercises", [])
                if exercises:
                    for i, ex in enumerate(exercises):
                        st.markdown(f"**{i+1}. {ex.get('name', '')}**")
                        st.markdown(f"- ⏱️ 时长：{ex.get('duration', '')}")
                        st.markdown(f"- 🔄 频率：{ex.get('frequency', '')}")
                        if ex.get("instructions"):
                            st.markdown(f"- 📝 要点：{ex.get('instructions', '')}")
                        if ex.get("caution"):
                            st.caption(f"  ⚠️ {ex['caution']}")
                        st.markdown("")
                else:
                    st.text("无训练项目")

            # 监测指标
            with st.expander("📊 健康监测", expanded=False):
                for item in plan.get("monitoring", []):
                    st.markdown(
                        f"- **{item.get('metric', '')}**："
                        f"目标 {item.get('target', '')}，{item.get('frequency', '')}"
                    )

            # 注意事项
            with st.expander("⚠️ 注意事项", expanded=False):
                for note in plan.get("precautions", []):
                    st.markdown(f"- {note}")

            # 下次随访
            if plan.get("next_followup"):
                st.caption(f"📅 下次随访：{plan['next_followup']}")

# ── 右侧：安全评估 + 随访报告 ─────────────────────

with col_right:
    st.header("🛡️ 安全评估")

    if "safety" in st.session_state:
        safety = st.session_state["safety"]
        level = safety.get("level", "normal")

        # 颜色映射
        if level == "emergency":
            st.error("### 🚨 紧急预警！请立即就医！")
        elif level == "warning":
            st.warning("### ⚠️ 需要注意 — 建议复诊")
        elif level == "attention":
            st.info("### ℹ️ 请关注")
        elif level == "normal":
            st.success("### ✅ 一切正常")
        else:
            st.text(f"状态：{level}")

        st.markdown(f"**判读依据**：{safety.get('reasoning', '—')}")
        st.markdown(f"**建议措施**：{safety.get('recommendation', '—')}")

        # 紧急情况横幅
        if level == "emergency":
            st.markdown("---")
            st.error(
                "⚠️ **请立即拨打 120 或前往最近医院急诊科。**\n\n"
                "本系统为 AI 辅助工具，不能替代专业医疗判断。"
            )

    st.markdown("---")
    st.header("📊 随访报告（医生版）")

    if "report" in st.session_state and st.session_state["report"]:
        report = st.session_state["report"]

        if "error" not in report:
            st.markdown(f"**报告ID**：{report.get('report_id', '—')}")
            st.markdown(f"**概况**：{report.get('summary', '—')}")

            # 进度评估指标
            progress = report.get("progress_assessment", {})
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("疼痛控制", progress.get("pain_control", "—"))
            with c2:
                st.metric("活动度", progress.get("rom_progress", "—"))
            with c3:
                st.metric("功能状态", progress.get("functional_status", "—"))
            with c4:
                st.metric("依从性", progress.get("compliance", "—"))

            # 关键发现
            if report.get("key_findings"):
                st.markdown("**关键发现**：")
                for f in report["key_findings"]:
                    st.markdown(f"- {f}")

            # 风险提醒
            if report.get("risk_alerts") and report["risk_alerts"][0] != "目前无特殊风险":
                st.warning("**⚠️ 风险提醒**：")
                for alert in report["risk_alerts"]:
                    st.markdown(f"- {alert}")

            # 建议
            if report.get("recommendations"):
                st.markdown("**💡 建议**：")
                for rec in report["recommendations"]:
                    st.markdown(f"- {rec}")

            # Markdown 报告可展开查看
            md_report = report.get("export_format_markdown", "")
            if md_report:
                with st.expander("📄 完整报告（Markdown）", expanded=False):
                    st.markdown(md_report)

# ── 底部声明 ───────────────────────────────────

st.markdown("---")
st.caption(
    "⚠️ **医疗免责声明**：本系统为 AI 辅助工具，所有建议仅供参考，"
    "不能替代执业医师的诊断和治疗方案。请严格遵循主治医师的指导。"
    "如遇紧急情况，请立即拨打 120 就医。"
)
