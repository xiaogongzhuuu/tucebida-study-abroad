# 途策必达留学 — 智能选校 Agent

基于 AI 的智能选校推荐系统，为留学顾问业务提供数据驱动的选校决策支持。

## 功能

- **学生画像智能解析** — 支持自然语言描述或分字段填写，自动结构化提取
- **智能选校推荐** — RAG 检索 + LLM 生成，每所学校附匹配理由和历史案例
- **冲刺/匹配/保底三档分级** — 基于 GPA + 标化 vs 录取数据自动分档
- **报告流式输出** — SSE 实时推送，打字机效果
- **Web 交互界面** — 三步流程（填写 → 确认 → 查看报告）

## 技术栈

| 组件 | 技术 |
|------|------|
| LLM | DeepSeek API（OpenAI 兼容） |
| Embedding | BGE-large-zh（1024 维） |
| 后端 | FastAPI + SSE 流式输出 |
| 向量库 | ChromaDB（27,000+ chunks） |
| 前端 | 原生 HTML/CSS/JS |

## 项目结构

```
├── agent/
│   ├── config.py        # API 配置、模型参数
│   ├── profile.py       # 学生画像结构化提取
│   ├── retriever.py     # 多路检索（向量 + 元数据过滤）
│   ├── matcher.py       # 匹配打分 + 三档分级
│   └── reporter.py      # RAG 选校报告生成
├── web/
│   ├── app.py           # FastAPI 入口 + API 路由
│   └── static/
│       ├── index.html   # 前端页面
│       ├── app.js       # 前端逻辑
│       └── style.css    # 样式
├── data/
│   └── universities.json
├── chroma_db/           # 向量数据库
└── requirements.txt
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
