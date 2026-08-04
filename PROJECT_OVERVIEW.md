# 途策必达留学 — 智能选校 Agent

## 项目简介

为留学顾问业务构建的 **AI 智能选校推荐系统**。基于已有的 27,000+ 条内部知识库（覆盖 20+ 所国内国际学校画像、藤校信息、课程体系、历史录取案例），通过 DeepSeek 大模型 + 向量检索（RAG），将顾问经验转化为可复用的智能选校能力。

**一句话**：输入学生画像 → AI 输出带分级的选校推荐报告，每条建议有历史案例做依据。

## 技术栈

- **LLM**: DeepSeek API（OpenAI 兼容）
- **Embedding**: BGE-large-zh（1024 维）
- **后端**: FastAPI（Python, async, SSE 流式输出）
- **向量库**: ChromaDB（已有 27,064 chunks，1024 维）
- **前端**: 单页 HTML + vanilla JS（响应式）

## 能实现的功能

1. **学生画像智能解析** — 支持自然语言描述或分字段填写，自动结构化
2. **智能选校推荐** — RAG 检索 + LLM 生成，每所学校附匹配理由和历史案例
3. **冲刺/匹配/保底三档分级** — 基于 GPA + 标化 vs 录取数据自动分档
4. **报告流式输出** — SSE 实时推送，打字机效果
5. **Web 交互界面** — 三步流程（填写 → 确认 → 查看报告）

## 项目结构

```
途策必达留学/
├── agent/
│   ├── config.py           # API keys, 模型配置, 路径
│   ├── profile.py          # 学生画像结构化提取 (LLM)
│   ├── retriever.py        # 多路检索 (向量 + 元数据过滤)
│   ├── matcher.py          # 匹配打分 + 冲刺/匹配/保底 分级
│   └── reporter.py         # 生成选校报告 (LLM RAG)
├── web/
│   ├── app.py              # FastAPI 主入口 + API 路由
│   └── static/
│       ├── index.html      # 前端主页面
│       └── style.css       # 样式
├── data/
│   └── universities.json   # Top 50 大学结构化数据
├── chroma_db/              # 已有向量库
├── requirements.txt
└── PROJECT_OVERVIEW.md
```

## 数据流

```
前端表单 → POST /api/profile
  ├─ 自然语言描述 → DeepSeek 提取结构化画像
  └─ 返回结构化 profile JSON

用户确认 → POST /api/match
  ├─ retriever: 向量检索 + 元数据过滤 → 相关案例/学校
  ├─ matcher: 多维度打分 → 排序 + 分级
  └─ reporter: RAG prompt → DeepSeek 流式生成报告

SSE 实时推送报告给前端
```

## 14 天排期

### 第一周：核心链路

| 天 | 任务 | 产出 |
|---|------|------|
| D1 | 项目骨架 + API 调通 | config, DeepSeek + ChromaDB 验证 |
| D2 | 学生画像提取 | profile.py, FastAPI 端点, 前端表单 |
| D3 | 向量检索 | retriever.py, 画像 → 相似案例 |
| D4 | 多路融合 | 结构化过滤 + 向量结果合并 |
| D5 | RAG 选校生成 | reporter.py, 检索结果 → 推荐列表 |
| D6 | 冲刺/匹配/保底分级 | matcher.py, 三档打分 |
| D7 | MVP 里程碑 | 端到端走通，浏览器可演示 |

### 第二周：打磨

| 天 | 任务 | 产出 |
|---|------|------|
| D8 | 补充大学数据 | Top 50 美本结构化数据 |
| D9 | 案例对标优化 | 推荐附带历史案例引用 |
| D10 | 报告质量打磨 | prompt 精调, 模板美化 |
| D11 | Web 界面完善 | 多步流程, SSE 流式, 错误处理 |
| D12 | 真实案例测试 | 历史 case 验证效果 |
| D13 | 边界情况 | 输入校验, 降级策略, 日志 |
| D14 | 收尾 | README, 代码清理 |

## 后续迭代方向

- 多轮对话（顾问追问、调整偏好）
- 用户反馈闭环（采纳/不采纳 → 调权）
- 文书写作辅助
- 更多数据源（录取数据实时更新、暑校/科研机会）
- 多账号 + 权限管理
