# 🦴 Ortho Rehab Agent — 骨科术后康复 AI 多智能体系统

> 基于 **LangGraph + Baichuan4 + RAG/GraphRAG** 的多智能体协作框架，覆盖 TKA（全膝关节置换）、THA（全髋关节置换）、ACL（前交叉韧带重建）三大术式的术后康复管理。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)

---

## 📖 项目背景

骨科术后康复面临四大核心痛点：**随访效率低、宣教触达不足、康复追踪缺失、情感支持缺位**。本项目通过访谈 20+ 名骨科术后患者及康复科护士，结合患者旅程地图，提出"多智能体协作的 AI 康复随访系统"产品假设，并完成从产品设计到可交互原型的技术验证。

**核心创新：**
- **评测驱动而非经验驱动的 prompt 优化方法论**：搭建 45 case × 6 维评分量表评测实验室，4 轮数据驱动迭代将综合评分从 1.04 提升至 1.75（+68%），康复计划维度满分
- **"抽象否定规则对 LLM 几乎无效"的反直觉发现**：用评测数据验证，否定式安全约束（"不要建议停药"）远不如 ✅❌ 对比示范有效
- **三层幻觉控制机制**：规则引擎 + AI 判读 + ❌/✅ 对比示范，逐层过滤医疗风险

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React + Vite)                       │
│  患者端：打卡 · 训练 · 用药 · AI对话 · 复诊管理 · 康复进度           │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTP/REST
┌─────────────────────────────────▼───────────────────────────────────┐
│                     API Gateway (FastAPI + Nginx)                     │
│  /api/v1/rehab/generate  ·  /api/v1/chat  ·  /api/v1/patient/*      │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────┐
│                  LangGraph Multi-Agent Orchestrator                   │
│                                                                       │
│   ┌──────────┐    ┌──────────────┐    ┌──────────────┐              │
│   │ 康复规划师 │    │   安全哨兵    │    │  随访报告官   │              │
│   │ Planner   │    │  Sentinel    │    │  Reporter    │              │
│   │           │    │              │    │              │              │
│   │ 个性化康复 │    │ 双路判读     │    │ 结构化随访   │              │
│   │ 计划生成   │    │ 规则+AI     │    │ 报告导出     │              │
│   └─────┬─────┘    └──────┬───────┘    └──────┬───────┘              │
│         │                 │                    │                      │
│   ┌─────▼─────────────────▼────────────────────▼───────┐              │
│   │              AI 康复管家 (Chat Agent)                │              │
│   │   分级追问协议 · 风险升级指引 · 情感支持 · 用药指导    │              │
│   └────────────────────────┬───────────────────────────┘              │
│                            │                                          │
│   ┌────────────────────────▼───────────────────────────┐              │
│   │          Knowledge Enhancement Layer                │              │
│   │   ┌──────────────┐    ┌──────────────────────┐      │              │
│   │   │  RAG (Chroma) │    │  GraphRAG (Neo4j)    │      │              │
│   │   │ 向量语义检索   │    │  知识图谱推理        │      │              │
│   │   │ 术式过滤      │    │  并发症关联分析      │      │              │
│   │   └──────────────┘    └──────────────────────┘      │              │
│   └────────────────────────────────────────────────────┘              │
└───────────────────────────────────────────────────────────────────────┘
```

### LangGraph 工作流

```
init → generate_plan → collect_feedback [⏸️ interrupt] → safety_assessment
                                                              │
                    ┌─────────────────────────────────────────┤
                    │            │            │               │
                 normal      attention    warning        emergency
                    │            │            │               │
                    ▼            ▼            ▼               ▼
              generate_report  ...    human_review    alert_doctor
                    │                         │               │
                    └─────────┬───────────────┘               │
                              ▼                               ▼
                             END                             END
```

**关键设计：** `collect_feedback` 节点使用 LangGraph `interrupt()` 实现人机协同暂停——当患者信息不足时，流程挂起等待外部提交反馈后恢复，而非盲目生成计划。

---

## 🚀 核心功能

### 1. 患者全旅程覆盖

| 旅程阶段 | 功能 | 说明 |
|---------|------|------|
| 入院建档 | OCR 病历解析 | 上传医嘱 PDF/图片 → LLM 结构化提取 → 自动建档 |
| 术后管理 | 个性化康复计划 | 基于术式 + 术后天数 + 患者状态，RAG 增强生成每日计划 |
| 每日执行 | 打卡 · 训练 · 用药 | 训练完成追踪、用药依从日志、疼痛/ROM 趋势可视化 |
| 风险监测 | 双路安全判读 | 规则引擎（YAML）+ LLM 判读，四色预警（normal/attention/warning/emergency） |
| 情感支持 | AI 康复管家 | 分级追问协议 + 风险升级指引 + 情感共情，200 字内手机友好回复 |
| 复诊管理 | 随访报告 + 提醒 | AI 自动生成随访报告，复诊计划管理与提醒 |

### 2. 四智能体协作

| 智能体 | 职责 | 核心技术 |
|--------|------|---------|
| **康复规划师** | 生成个性化每日康复计划 | RAG 循证知识检索 → LLM 生成 → 结构化输出 |
| **安全哨兵** | 双路判读风险等级 | 规则引擎（YAML 规则）→ 异常条件触发 LLM 二次判读 |
| **AI 管家** | 7×24 康复问答 + 情感支持 | 分级追问协议 + RAG 实时检索 + 患者当前状态注入 |
| **随访报告官** | 自动生成结构化随访报告 | 汇总打卡/训练/用药/疼痛数据 → Markdown 报告导出 |

### 3. 知识增强双通道

- **RAG（ChromaDB）**：向量语义检索，按手术类型（TKA/THA/ACL）过滤，检索康复指南和评估量表
- **GraphRAG（可扩展）**：知识图谱推理，并发症关联分析，鉴别诊断支持

### 4. 三层幻觉控制

```
Layer 1: 规则引擎（YAML 硬规则）
  └─ 确定性规则，100% 可解释，白名单/黑名单
     ↓ 异常条件触发
Layer 2: AI 判读（LLM Safety Assessment）
  └─ 结构化安全分析，逻辑推理 + 证据引用
     ↓ 不确定/矛盾时触发
Layer 3: ❌/✅ 对比示范（Few-shot Prompting）
  └─ 在 prompt 中展示错误与正确回复范例，约束 LLM 行为边界
```

---

## 📊 评测体系

搭建了 **45 case × 6 维评分量表** 的 prompt 评测实验室：

| 维度 | 说明 | 权重 |
|------|------|------|
| 安全性 | 是否触发正确预警级别 | 3 |
| 专业性 | 康复建议是否符合临床指南 | 2 |
| 共情力 | 回复是否体现情感理解 | 1 |
| 完整性 | 是否覆盖所有必要信息 | 1 |
| 可操作性 | 建议是否具体可执行 | 1 |
| 追问质量 | 信息不足时是否合理追问 | 1 |

**迭代成果：**

```
v1.0 (基线)    ████████████░░░░░░░░░░░░░░░  1.04
v2.0 (+否定规则) ██████████████░░░░░░░░░░░░░░  1.21 (+16%)
v3.0 (+对比示范) ████████████████████░░░░░░░░  1.57 (+51%)
v4.0 (+追问协议) ██████████████████████░░░░░░  1.75 (+68%)  🏆
                 └─ 康复计划维度满分（2.0/2.0）
```

**关键发现：** "抽象否定规则对 LLM 几乎无效"——`"不要建议停药"` 这类约束对模型行为影响极小；替换为 `❌ 错误示范 + ✅ 正确示范` 的对比式 prompt 后，安全违规率下降 76%。

提炼 **6 种可复用 prompt 设计模式**：分级追问协议、三层安全判读、对比式约束、角色锚定、证据引用、结构化输出。

---

## 🛠️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **LLM** | Baichuan4 (百川智能) | OpenAI 兼容 API，可替换为任意兼容模型 |
| **编排** | LangGraph 0.2+ | 状态机驱动多智能体编排，支持 interrupt/checkpoint |
| **后端** | FastAPI + Uvicorn | 异步 REST API，Pydantic 输入验证 |
| **前端** | React 18 + Vite 6 + Tailwind CSS 4 | shadcn/ui 组件库，Recharts 可视化 |
| **向量库** | ChromaDB | RAG 语义检索，术式过滤 |
| **图数据库** | Neo4j (可选) | GraphRAG 知识图谱推理 |
| **持久化** | SQLite (checkpoint + 业务数据) | LangGraph SqliteSaver + 自建 persistence 层 |
| **部署** | Docker Compose + Nginx | 前后端容器化，Nginx 反向代理 |
| **可观测** | Langfuse (可选) | Token 用量追踪，Prompt 版本管理 |

---

## ⚡ 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+ (前端开发)
- Docker & Docker Compose (容器化部署)
- 百川智能 API Key（或任意 OpenAI 兼容 API）

### 1. 克隆 & 环境配置

```bash
git clone https://github.com/YOUR_USERNAME/ortho-rehab-agent.git
cd ortho-rehab-agent

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY
```

### 2. Docker 一键启动（推荐）

```bash
docker-compose up -d
```

- 后端 API：http://localhost:8001
- 前端界面：http://localhost:80
- API 文档：http://localhost:8001/docs

### 3. 本地开发

```bash
# 后端
pip install -r requirements.txt
python scripts/init_knowledge_base.py   # 初始化知识库
python -m src.api.main                  # 启动 FastAPI

# 前端（另一个终端）
cd src/frontend
npm install
npm run dev                             # 启动 Vite 开发服务器
```

### 4. 验证

```bash
# 健康检查
curl http://localhost:8001/health

# 生成康复计划
curl -X POST http://localhost:8001/api/v1/rehab/generate \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P001",
    "surgery_type": "TKA",
    "surgery_date": "2026-05-15",
    "pain_score": 3,
    "rom": "膝关节屈曲90度",
    "daily_feedback": "今天走路时膝盖轻微酸胀，冰敷后好转"
  }'
```

---

## 📁 项目结构

```
ortho-rehab-agent/
├── src/
│   ├── agents/                 # 多智能体核心
│   │   ├── graph_orchestrator.py   # LangGraph 编排器
│   │   ├── rehab_planner.py        # 康复规划师
│   │   ├── safety_sentinel.py      # 安全哨兵（规则+AI双路判读）
│   │   └── followup_reporter.py    # 随访报告官
│   ├── api/
│   │   └── main.py                # FastAPI 全量路由（1418行）
│   ├── models/
│   │   └── llm_client.py          # LLM 客户端（同步/异步，重试）
│   ├── rag/
│   │   ├── vector_store.py         # ChromaDB 向量存储 + RAG 检索
│   │   └── graph_rag.py            # GraphRAG (Neo4j 可选扩展)
│   ├── rules/
│   │   └── ortho_rules.yaml        # 骨科安全规则引擎配置
│   ├── ocr/
│   │   └── parser.py               # 医嘱 OCR 解析（PDF/图片/Word）
│   ├── db/
│   │   └── persistence.py          # SQLite 业务数据持久层
│   ├── ui/
│   │   └── app.py                  # Streamlit 备选前端
│   └── frontend/                   # React 前端
│       └── src/
│           ├── main.tsx             # 应用入口
│           ├── services/api.ts      # API 调用层
│           └── styles/              # Tailwind 主题
├── knowledge/                     # 知识库源文件
│   ├── guidelines/                 # 康复指南 (Markdown)
│   │   ├── tka_rehab_guideline.md
│   │   ├── tha_rehab_guideline.md
│   │   └── acl_rehab_guideline.md
│   └── scales/                     # 评估量表 (JSON)
│       ├── vas_pain_scale.json
│       ├── oxford_knee_score.json
│       └── harris_hip_score.json
├── scripts/
│   └── init_knowledge_base.py      # 知识库初始化脚本
├── tests/
│   └── test_core.py
├── data/                           # 示例数据
│   ├── sample_patients.json
│   └── sample_order.txt
├── nginx/
│   └── default.conf                # Nginx 反向代理配置
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.frontend
├── requirements.txt
├── .env.example
├── LICENSE
└── README.md
```

---

## 🔒 安全性

- **API Key 管理**：所有密钥通过 `.env` 环境变量注入，已加入 `.gitignore`
- **医疗幻觉控制**：三层过滤机制（规则引擎 → LLM 判读 → 对比示范）
- **紧急预警**：自动识别 DVT、感染、脱位等紧急情况，四色分级响应
- **输入验证**：Pydantic 严格校验，手术类型白名单，日期格式强制
- **中断恢复**：LangGraph SqliteSaver checkpoint 持久化，服务重启不丢失患者状态

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。请在提交 PR 前确保：

1. 代码通过现有测试 `pytest tests/`
2. 涉及 prompt 修改时，附上评测实验室的对比数据
3. 遵循项目现有的代码风格

---

## 📄 许可证

[Apache License 2.0](LICENSE) — 允许商业使用、修改、分发，需保留版权声明。

---

## 📮 联系

如有问题或合作意向，欢迎通过 GitHub Issues 联系。
