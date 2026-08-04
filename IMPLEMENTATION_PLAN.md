# 途策必达留学 — 智能选校 Agent 实施计划

## Context

为"途策必达留学"业务构建一个 AI 驱动的智能选校 Agent，帮助顾问/学生根据学生画像
自动推荐匹配的海外大学。项目已有 27,064 条 chunk 的 ChromaDB 向量知识库（1024 维
embedding），覆盖 20+ 所国内国际学校信息、藤校 profile、课程体系说明和历史录取案例。

## 技术栈

- **LLM**: DeepSeek API（OpenAI 兼容）
- **Embedding**: BGE-large-zh（1024 维，需确认与现有 chroma_db 一致）
- **后端**: FastAPI（Python, async, SSE 流式输出）
- **向量库**: ChromaDB（已有，直接复用）
- **前端**: 单页 HTML + vanilla JS（响应式，干净 UI）
- **部署**: 本地开发运行，后续可打 Docker

## 项目结构

```
途策必达留学/
├── agent/
│   ├── __init__.py
│   ├── config.py            # API keys, 模型配置, 路径
│   ├── profile.py           # 学生画像结构化提取 (LLM)
│   ├── retriever.py         # 多路检索 (向量 + 元数据过滤)
│   ├── matcher.py           # 匹配打分 + 冲刺/匹配/保底 分级
│   └── reporter.py          # 生成选校报告 (LLM RAG)
├── web/
│   ├── app.py               # FastAPI 主入口 + API 路由
│   ├── static/
│   │   ├── index.html       # 前端主页面
│   │   └── style.css        # 样式
│   └── templates/           # (预留, SSE 事件模板)
├── data/                    # 大学录取数据补充目录
│   └── universities.json    # Top 50 大学结构化数据
├── requirements.txt
└── chroma_db/               # 已有，不动
```

## 核心数据流

```
1. 前端表单 → POST /api/profile
   ├─ 自然语言描述 → DeepSeek 提取结构化画像
   └─ 返回 {gpa, tests, curriculum, major, preferences, ...}

2. 用户确认画像 → POST /api/match
   ├─ retriever: 向量检索 + 元数据过滤 → 相关案例/学校
   ├─ matcher: 多维度打分 → 排序 + 分级
   └─ reporter: RAG prompt → DeepSeek 流式生成报告

3. SSE 实时推送报告给前端
```

## 分天实施计划

### D1 — 项目骨架 + LLM 调通

- [ ] 创建项目目录结构
- [ ] `requirements.txt`（fastapi, uvicorn, chromadb, openai, sentence-transformers）
- [ ] `agent/config.py` — DeepSeek API key / base_url / 模型名 配置
- [ ] 验证：DeepSeek API 调通（chat + embedding 都测）
- [ ] 验证：ChromaDB 查询能返回正确结果

### D2 — 学生画像提取

- [ ] `agent/profile.py` — `ProfileExtractor`
  - Prompt: 将非结构化描述转为 JSON（GPA/标化/课程/专业意向/偏好）
  - 输出 schema: `{curriculum, gpa, toefl, sat, major_interest, activities, country_pref, budget, ...}`
- [ ] `web/app.py` — FastAPI 骨架 + `POST /api/profile` 端点
- [ ] `web/static/index.html` — 输入表单（两个入口：自然语言 or 分字段填写）

### D3 — 向量检索链路

- [ ] `agent/retriever.py` — `Retriever`
  - `search_similar_cases(profile)`: 用画像文本 → embedding → ChromaDB 查 top_k 相似案例
  - `search_schools(query)`: 查学校信息
  - 结果去重 + 按 source 分类
- [ ] 验证：输入一个学生描述 → 返回相关历史案例 chunk

### D4 — 元数据过滤 + 多路融合

- [ ] 扩展 `retriever.py`:
  - 结构化过滤：按 `curriculum`、`doc_type`、`school` 字段精确筛选
  - 高校信息补充检索
- [ ] 融合策略：向量结果权重 0.6 + 规则匹配权重 0.4

### D5 — RAG 选校生成（第一版）

- [ ] `agent/reporter.py` — `ReportGenerator`
  - System prompt + 检索上下文 → DeepSeek chat
  - 输出：推荐学校列表 + 每所理由
- [ ] `POST /api/match` — 完整链路：检索 → 排序 → 生成
- [ ] 前端展示 Markdown 报告

### D6 — 冲刺/匹配/保底 分级

- [ ] `agent/matcher.py` — `Matcher`
  - 基于 GPA + 标化 vs 学校录取区间 做三档分级
  - 结合历史案例：同校相似画像录了哪类学校
  - 输出带 tier 标注的学校列表
- [ ] 报告模板格式化（分级表格 + 分析段落）

### D7 — 端到端走通

- [ ] 全链路测试：输入一个完整学生画像 → 输出带分级选校报告
- [ ] 前端交互打磨：表单 → 加载态 → 报告展示
- [ ] 日志 + 错误处理基础
- [ ] **里程碑：可演示的 MVP**

### D8 — 补充大学数据

- [ ] `data/universities.json` — Top 50 美本高校结构化信息
  - 录取率、SAT/TOEFL 中位数、GPA 区间、热门专业、学费
  - 来源：公开数据 + 人工整理
- [ ] `agent/config.py` 增加大学数据加载
- [ ] 更新 retriever 支持结构化大学数据匹配

### D9 — 案例对标优化

- [ ] 报告增强：每所推荐学校附带"相似历史案例"
  - 展示同校/同课程体系学生的录取案例
- [ ] DeepSeek prompt 优化：要求引用具体案例来源
- [ ] retriever 增加案例溯源元数据

### D10 — 报告质量打磨

- [ ] Prompt 精调（system prompt + few-shot examples）
- [ ] 输出格式标准化（Markdown 模板，含：个人画像概述、推荐学校分级表、每校分析、风险提示）
- [ ] 前端 Markdown 渲染美化

### D11 — Web 界面完善

- [ ] 前端：多步流程（填写 → 确认画像 → 等待报告 → 展示）
- [ ] SSE 流式展示（打字机效果）
- [ ] 响应式适配
- [ ] 错误状态处理（API 超时、无匹配结果等）

### D12 — 真实案例测试

- [ ] 用历史数据中的真实案例做验证
  - 例如：取深国交某学生数据 → 看推荐是否合理
- [ ] 调整匹配权重和 prompt
- [ ] 记录 bad case，标注后续优化方向

### D13 — 边界情况 + 鲁棒性

- [ ] 输入校验（缺少关键字段时的降级策略）
- [ ] API 超时/失败重试
- [ ] ChromaDB 空结果降级（纯 LLM 推理）
- [ ] 异常日志

### D14 — 收尾

- [ ] 代码清理 + 注释关键逻辑
- [ ] README：如何启动、配置、使用
- [ ] 后续迭代方向记录（多轮对话、用户反馈闭环、更多数据源）

## 技术要点

### Embedding 对齐
ChromaDB 现有 1024 维向量，需要在 `agent/config.py` 中确认并复用同一个
embedding 模型（大概率 BGE-large-zh）。先在 D1 验证。

### DeepSeek API 格式
```python
from openai import OpenAI
client = OpenAI(
    api_key="sk-xxx",
    base_url="https://api.deepseek.com"
)
# chat
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[...],
    stream=True
)
```

### 检索策略细节
向量检索 query 构造：
```
f"学生画像: {curriculum}课程体系, GPA {gpa}, "
f"TOEFL {toefl}, SAT {sat}, 专业意向 {major}. "
f"寻找录取案例和匹配学校"
```

### 分级逻辑（matcher）
- **冲刺**: 学生 GPA/标化 < 学校录取中位数，但差距在 10% 内
- **匹配**: 学生 GPA/标化 ≈ 学校录取中位数 ±5%
- **保底**: 学生 GPA/标化 > 学校录取 75 分位数

## 验证方式

1. D1: `python -c "from agent.config import ..."` 验证配置加载
2. D2: `curl -X POST localhost:8000/api/profile -d '{"text":"IB 42分, TOEFL 108, 想学CS"}'`
3. D5: 同样 curl 测 `/api/match`，检查返回 Markdown 报告
4. D7: 浏览器打开页面，完整走通
5. D12: 取 summary.csv 中已知案例，对比推荐结果与真实录取
