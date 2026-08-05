# 途策必达留学 — 智能选校 Agent

基于 AI 的智能选校推荐系统，覆盖本科 + 研究生，为留学顾问业务提供数据驱动的选校决策支持。

## 功能

- **学生画像智能解析** — 支持自然语言描述或分字段填写，自动结构化提取
- **智能选校推荐** — RAG 检索 + LLM 生成，每所学校附匹配理由
- **冲刺/匹配/保底三档分级** — 基于 GPA + 标化 vs 录取数据自动分档
- **报告流式输出** — SSE 实时推送，打字机效果
- **Web 交互界面** — 三步流程（填写 → 确认 → 查看报告）
- **研究生项目数据** — 116 个项目已结构化入库，覆盖英港新 33 所院校

## 技术栈

| 组件 | 技术 |
|---|---|
| LLM | DeepSeek API（OpenAI 兼容） |
| Embedding | BAAI/bge-m3（1024 维） |
| 后端 | FastAPI + SSE 流式输出 |
| 向量库 | ChromaDB |
| 数据 | JSON Schema 统一结构，支持 xlsx 解析 |

## 项目结构

```
├── agent/
│   ├── config.py           # API 配置、模型参数
│   ├── profile.py          # 学生画像结构化提取
│   ├── retriever.py        # 多路检索（向量 + 元数据过滤）
│   ├── matcher.py          # 匹配打分 + 三档分级
│   ├── reporter.py         # RAG 选校报告生成
│   └── grad_schema.py      # 研究生项目统一 Schema + 数据清洗 + 打标
├── web/
│   ├── app.py              # FastAPI 入口 + API 路由
│   └── static/
│       ├── index.html      # 前端页面
│       ├── app.js          # 前端逻辑
│       └── style.css       # 样式
├── Analytics/              # 100 个研究生项目 JSON（英港院校）
├── SMU/                    # 16 个 SMU 项目 JSON + 元数据 xlsx
├── output/
│   ├── grad_programs_enriched.json  # 116 项目打标后统一数据
│   └── D1_data_quality_report.md    # 数据质量报告
├── chroma_db/              # 向量数据库
├── data/
│   └── universities.json   # 本科院校数据
├── requirements.txt
├── NEXT_PHASE_PLAN.md      # 下一阶段实施计划（D1-D14）
├── IMPLEMENTATION_PLAN.md  # 原始实施方案
└── PROJECT_OVERVIEW.md     # 项目概览
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key
# 编辑 .env 文件，填入 DeepSeek API Key
# DEEPSEEK_API_KEY=your_key_here

# 启动服务
cd web
python app.py
```

访问 `http://localhost:8000` 使用 Web 界面。

## 数据流

```
前端表单 → /api/profile → DeepSeek 提取结构化画像
       ↓
用户确认 → /api/match
       ├─ retriever: 向量检索 + 元数据过滤
       ├─ matcher: 多维度打分 + 分级
       └─ reporter: RAG → DeepSeek 流式生成报告
       ↓
SSE 实时推送报告给前端
```

## 研究生数据

当前已整理 116 个研究生项目，数据质量报告见 `output/D1_data_quality_report.md`。

| 维度 | 数据 |
|---|---|
| 国家 | 英国 72、新加坡 26、香港 18 |
| 院校 | 33 所（Imperial, LSE, UCL, NUS, HKU, SMU 等） |
| 专业方向 | 17 类（Analytics 57 个为主） |
| 学位类型 | 20 种（MSc 占 93 个） |
| 字段 | 13 个标准字段（申请材料、语言要求、费用等） |

运行数据校验：

```bash
python agent/grad_schema.py
```

## 下一阶段

详见 `NEXT_PHASE_PLAN.md`：

- **P1** 研究生数据入库 + 检索 + 报告 + 前端模块
- **P2** 飞书文档对接（报告同步、知识库浏览）
- **P3** 知识库扩展（DataSource 插件机制、批量摄入管线）
- **P4** 体验优化（PDF 导出、收藏夹、Docker 部署）+ 文件拖拽上传 + LLM 自动结构化
