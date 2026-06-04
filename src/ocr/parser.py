"""
医嘱文档解析器 — 文件提取 + LLM 结构化。

支持格式：
- .txt / .md — 直接读取
- .pdf — pypdf 提取文本
- .docx — python-docx 提取文本
- .jpg / .png — pytesseract OCR（可选，需 brew install tesseract）

流程：
上传文件 → 提取原始文本 → LLM 解析为结构化医嘱 → 填入康复计划生成表单
"""

import io
import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ── 可选依赖 ──────────────────────────────────────

try:
    from PyPDF2 import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ── 文件文本提取 ──────────────────────────────────

def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """
    从上传文件中提取原始文本。

    Args:
        file_bytes: 文件字节内容
        filename: 原始文件名（用于判断扩展名）

    Returns:
        提取的原始文本字符串

    Raises:
        ValueError: 不支持的文件类型
        ImportError: 缺少必要的可选依赖
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext in (".txt", ".md"):
        return file_bytes.decode("utf-8", errors="replace")

    elif ext == ".pdf":
        if not HAS_PYPDF:
            raise ImportError("需要安装 PyPDF2：pip install PyPDF2")
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        return "\n".join(pages_text)

    elif ext == ".docx":
        if not HAS_DOCX:
            raise ImportError("需要安装 python-docx：pip install python-docx")
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)

    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff"):
        if not HAS_PIL:
            raise ImportError("需要安装 Pillow：pip install Pillow")
        try:
            import pytesseract
        except ImportError:
            raise ImportError(
                "图片 OCR 需要 pytesseract。\n"
                "安装步骤：\n"
                "  1. brew install tesseract tesseract-lang\n"
                "  2. pip install pytesseract Pillow"
            )
        img = Image.open(io.BytesIO(file_bytes))
        # chi_sim = 简体中文, eng = 英文
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        return text

    else:
        raise ValueError(f"不支持的文件类型: {ext}，支持的格式：txt, md, pdf, docx, jpg, png")


# ── LLM 结构化解析 ────────────────────────────────

MEDICAL_ORDER_PARSE_SYSTEM = """你是一位资深的骨科临床文档解析专家。你的任务是从医嘱、出院小结、手术记录等医疗文档中提取关键信息，输出结构化 JSON。

提取规则：
1. 手术类型 (surgery_type)：根据文档内容判断，必须是 "TKA"（全膝关节置换）、"THA"（全髋关节置换）、"ACL"（前交叉韧带重建）或 "其他"
2. 手术日期 (surgery_date)：统一转为 YYYY-MM-DD 格式；如果只有大概时间，尽量推断
3. 用药信息 (medications)：从医嘱中提取每种药的名称、剂量、频次、疗程和备注
4. 康复指导 (rehabilitation_plan)：提取医嘱中关于康复训练的说明
5. 注意事项 (precautions)：提取文档中提到的禁忌、限制、警告等
6. 如果文档中某字段缺失，用 null

请以 JSON 格式返回结果。"""

MEDICAL_ORDER_PARSE_PROMPT = """请从以下医疗文档中提取结构化信息：

---
{document_text}
---

请返回一个 JSON 对象，包含以下字段（缺失的用 null）：

{{
    "patient_name": "患者姓名",
    "surgery_type": "TKA / THA / ACL / 其他",
    "surgery_date": "YYYY-MM-DD",
    "diagnosis": "术前诊断",
    "surgical_procedure": "手术名称/方式",
    "medications": [
        {{
            "drug_name": "药品名",
            "dosage": "剂量",
            "frequency": "频次",
            "duration": "疗程",
            "notes": "备注/注意事项"
        }}
    ],
    "rehabilitation_plan": "医嘱中的康复训练指导原文或摘要",
    "precautions": ["注意事项1", "注意事项2"],
    "weight_bearing": "负重限制说明",
    "rom_target": "关节活动度目标",
    "follow_up": "随访安排",
    "special_instructions": "其他特殊说明"
}}

只返回 JSON，不要包含其他文字。"""


def parse_medical_order(document_text: str, llm_client=None) -> Dict[str, Any]:
    """
    用 LLM 将医嘱原始文本解析为结构化数据。

    Args:
        document_text: 从文件中提取的原始文本
        llm_client: LLMClient 实例（可选，不传则自动获取）

    Returns:
        结构化医嘱 dict，包含 surgery_type, surgery_date, medications 等
    """
    if not document_text or not document_text.strip():
        return {"error": "文档内容为空"}

    if llm_client is None:
        from src.models.llm_client import get_llm_client
        llm_client = get_llm_client()

    messages = [
        {"role": "system", "content": MEDICAL_ORDER_PARSE_SYSTEM},
        {"role": "user", "content": MEDICAL_ORDER_PARSE_PROMPT.format(
            document_text=document_text[:6000]  # 截断过长文本
        )},
    ]

    try:
        result = llm_client.chat_json(messages=messages, temperature=0.1, max_tokens=2048)
        if "error" in result:
            logger.warning("LLM parse returned error: %s", result["error"])
        return result
    except Exception as e:
        logger.exception("Failed to parse medical order")
        return {"error": str(e)}


# ── 端到端解析 ────────────────────────────────────

def process_uploaded_order(file_bytes: bytes, filename: str, llm_client=None) -> Dict[str, Any]:
    """
    端到端处理：上传文件 → 提取文本 → LLM 解析 → 返回结构化医嘱。

    这是供 UI 和 API 调用的高层入口。

    Returns:
        {
            "raw_text": "提取的原始文本（截断前500字）",
            "parsed": { ... 结构化医嘱 ... },
            "error": "如果有错误"
        }
    """
    result = {"raw_text": "", "parsed": {}, "error": ""}

    try:
        raw_text = extract_text_from_file(file_bytes, filename)
        result["raw_text"] = raw_text[:500] + ("..." if len(raw_text) > 500 else "")
        logger.info("Extracted %d chars from %s", len(raw_text), filename)

        if not raw_text.strip():
            result["error"] = "未能从文件中提取到文字内容。如果是扫描件图片，请确保已安装 tesseract OCR。"
            return result

        parsed = parse_medical_order(raw_text, llm_client)
        result["parsed"] = parsed
        return result

    except ValueError as e:
        result["error"] = str(e)
        return result
    except ImportError as e:
        result["error"] = str(e)
        return result
    except Exception as e:
        logger.exception("process_uploaded_order failed")
        result["error"] = f"解析失败：{str(e)}"
        return result
