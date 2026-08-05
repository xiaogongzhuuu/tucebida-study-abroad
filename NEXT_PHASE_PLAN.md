# 途策必达留学 — 下一阶段实施计划

## 状态总览

| 天数 | 阶段 | 状态 |
|---|---|---|
| D1 | 项目骨架 + LLM调通 | ✅ |
| D2 | 学生画像提取 | ✅ |
| D3 | 向量检索链路 | ✅ |
| D4 | 元数据过滤 + 多路融合 | ✅ |
| D5 | RAG选校生成 | ✅ |
| D6 | 冲刺/匹配/保底分级 | ✅ |
| D7 | 端到端走通 (MVP里程碑) | ✅ |
| D8 | 补充大学数据 | ❌ |
| D9 | 案例对标优化 | ✅ |
| D10 | 报告质量打磨 | ⚠️ |
| D11 | Web界面完善 | ✅ |
| D12 | 真实案例测试 | ❌ |
| D13 | 边界情况 + 鲁棒性 | ⚠️ |
| D14 | 收尾 | ⚠️ |

---

## 下一阶段计划

```
+------+------+---------------------------------------------------------------------------+
| 阶段 | 天数 | 内容                                                                      |
+------+------+---------------------------------------------------------------------------+
| D1 | 研究生数据结构化 — 统一Schema + 数据清洗 + 打标 (国家/学校/专业方向)      | ✅ |
| P1   | D2   | 研究生数据入库 — ChromaDB新collection + embedding + 元数据索引             |
| P1   | D3   | 研究生检索模块 — GradProgramRetriever + /api/grad/search + 筛选API         |
| P1   | D4   | 研究生报告生成 — GradReporter (申请要求/截止日期/费用/课程 四维分析)       |
| P1   | D5   | 前端研究生模块 — 专业搜索页 + 详情卡片 (申请材料/语言/标化/费用/奖学金)    |
| P2   | D6   | 飞书开放接口对接 — tenant_access_token + 文档创建/写入API                  |
| P2   | D7   | 报告一键同步飞书 — 选校报告→飞书文档 + 研究生专业详情→飞书多维表格        |
| P2   | D8   | 飞书知识库浏览 — 飞书小程序/H5 嵌入 + 前端适配移动端                       |
| P3   | D9   | 知识库扩展架构 — DataSource基类 + Plugin机制 + 标准化metadata schema       |
| P3   | D10  | 批量摄入管线 — 文件夹监听 + 自动chunk → embed → 入库 + 去重策略           |
| P4   | D11  | 体验优化 — 报告PDF导出 + 学校对比功能 + 多轮追问优化                       |
| P4   | D12  | 功能增强 — 截止日期提醒 + 选校收藏夹 + 顾问协作分享                        |
| P4   | D13  | 性能与鲁棒性 — 检索缓存 + API重试 + embedding本地化批处理 + 日志告警       |
| P4   | D14  | 测试与文档 — 端到端测试用例 + 接口文档 + 部署脚本 (Docker)                 |
+------+------+---------------------------------------------------------------------------+
```

---

## P1 — 研究生数据并入 (D1-D5)

### 背景
当前 `Analytics/` 目录有 100 个研究生项目 JSON，`SMU/` 目录有 16 个 SMU 项目 JSON + 1 个 xlsx。
覆盖院校包括英国 (Imperial, LSE, Warwick, Edinburgh, Manchester, Leeds, Liverpool, Exeter, Cardiff, QUB, QMUL)、
香港 (HKU, CUHK, PolyU, HKLU)、新加坡 (NUS, NTU, SMU) 等。
所有 JSON 字段结构统一：

| 字段 | 内容 |
|---|---|
| Application Materials | 申请材料清单 |
| Interview Requirements | 面试要求 |
| Application Deadlines | 申请截止日期 |
| Academic Requirements | 学术背景要求 |
| GRE GMAT Requirements | GRE/GMAT 分数要求 |
| English Proficiency Requirements | 语言成绩要求 (IELTS/TOEFL) |
| Program Overview | 项目概述 |
| Curriculum | 课程设置 |
| Cost of Attendance | 费用 |
| Financial Aid | 奖学金/资助 |
| Multiple Applications | 多项目申请政策 |
| Deferral Admission Policy | 延期入学政策 |
| Conditional Admission Policy | 条件录取政策 |

### D1 — 研究生数据结构化 ✅
- [x] 统一 Schema 定义 (`agent/grad_schema.py`)
  - 国家: 从文件名/URL 自动提取 + 人工校验
  - 学校: Imperial, LSE, Warwick, Edinburgh, Manchester, HKU, NUS, SMU ...
  - 专业方向: Analytics, Finance, Accounting, Management, CS, Law, Economics ...
  - 学位类型: MSc, MA, MSA, MBA, MBAI, LLM, JD, MiM ...
- [x] 数据清洗
  - 去重检查 (同名项目合并)
  - 缺失字段标注 (SMU 部分项目的 Multiple Applications / Deferral 字段为 "Not Mentioned")
  - URL 有效性校验
- [x] SMU.xlsx 解析并转换为统一 JSON Schema

### D2 — 研究生数据入库
- [ ] 为每个项目的每个字段生成独立 chunk
  - `{学校} - {专业} - {字段名}` 作为文档标题
  - 保留原始 URL 作为元数据 source_url
- [ ] 创建 ChromaDB 新 collection: `grad_programs`
- [ ] 批量 embedding 入 BAAI/bge-m3
- [ ] 元数据索引字段:
  - `country`, `school`, `program_name`, `degree`, `field` (字段类型)
  - `major_direction` (专业方向标签)
- [ ] 验证: 按学校/国家/专业方向查询均返回正确结果

### D3 — 研究生检索模块
- [ ] `agent/grad_retriever.py` — `GradProgramRetriever`
  - `search_programs(query, filters)`: 通用搜索
  - `search_by_school(school)`: 按学校查所有专业
  - `search_by_field(field_type)`: 按信息类型查 (如只看"申请截止日期")
  - 结构化筛选: 国家、学校、专业方向、学位类型
- [ ] API 端点:
  - `POST /api/grad/search` — 语义搜索研究生项目
  - `GET /api/grad/programs/{school}` — 按学校列出专业
  - `GET /api/grad/program/{id}` — 单个专业完整信息
  - `POST /api/grad/compare` — 多专业对比

### D4 — 研究生报告生成
- [ ] `agent/grad_reporter.py` — `GradReporter`
  - 四维分析报告: 申请要求 / 截止日期 / 费用 / 课程匹配度
  - 基于学生画像匹配: 标化成绩 vs 项目要求 → 可行性评估
  - LLM 生成择校建议 (基于检索到的项目信息)
- [ ] `POST /api/grad/report` — 研究生选专业报告
- [ ] `POST /api/grad/report/stream` — SSE 流式报告

### D5 — 前端研究生模块
- [ ] 新增"研究生选专业"Tab
- [ ] 专业搜索页: 搜索框 + 筛选器 (国家/学校/方向/学位)
- [ ] 专业详情卡片: 折叠面板展示各字段
- [ ] 申请要求对比组件: 学生标化 vs 项目要求的差距可视化
- [ ] 截止日期时间线展示

---

## P2 — 飞书文档连接 (D6-D8)

### D6 — 飞书开放接口对接
- [ ] 飞书企业自建应用创建
  - 获取 App ID / App Secret
  - 配置权限: `doc:document`, `docx:document`, `bitable:app`, `drive:drive`
- [ ] `agent/feishu_client.py` — 飞书 SDK 封装
  - `get_tenant_access_token()`: token 管理 + 自动刷新
  - `create_doc(title, content)`: 创建飞书文档
  - `append_doc_content(doc_id, content)`: 追加内容
  - `create_bitable_record(app_token, table_id, record)`: 写入多维表格
- [ ] 配置项: `FEISHU_APP_ID`, `FEISHU_APP_SECRET` 加入 `.env`

### D7 — 报告一键同步飞书
- [ ] 选校报告 → 飞书文档
  - Markdown → 飞书文档 Block 格式转换
  - "导出到飞书"按钮 (前端 + API)
  - `POST /api/export/feishu/doc` — 选校报告导出
- [ ] 研究生专业数据 → 飞书多维表格
  - 以学校/专业/国家/学位/语言要求/GRE要求/费用 为列
  - 批量导入脚本: 117 条数据一键写入
  - `POST /api/export/feishu/bitable` — 数据同步
- [ ] 飞书文档权限: 支持设置查看/编辑权限 (分享给顾问/学生)

### D8 — 飞书知识库浏览
- [ ] 飞书小程序前端适配
  - 响应式移动端优化
  - 飞书 JSSDK 集成 (身份认证)
- [ ] 知识库内容页: 在飞书内浏览选校报告 + 研究生专业详情
- [ ] 飞书消息卡片: 报告生成完成通知

---

## P3 — 知识库扩展架构 (D9-D10)

### D9 — DataSource 插件机制
- [ ] `agent/datasource/` 目录结构
  ```
  agent/datasource/
  ├── __init__.py
  ├── base.py              # DataSource 基类
  ├── json_source.py       # JSON 数据源 (研究生项目)
  ├── pdf_source.py        # PDF 数据源 (招生简章等)
  ├── web_source.py        # 网页爬取数据源
  ├── feishu_source.py     # 飞书文档数据源
  └── registry.py          # 数据源注册中心
  ```
- [ ] `DataSource` 基类接口:
  - `name`: 数据源名称
  - `load()`: 加载原始数据
  - `chunk()`: 分割为 chunk
  - `metadata()`: 提取元数据
  - `validate()`: 数据校验
- [ ] 标准化 Metadata Schema:
  ```json
  {
    "source_type": "json|pdf|web|feishu",
    "source_path": "原始文件路径或URL",
    "country": "US|UK|HK|SG|...",
    "school": "学校名称",
    "program_name": "专业名称 (如适用)",
    "degree": "本科|硕士|博士",
    "doc_type": "program_info|admission_case|school_profile|...",
    "year": "数据年份",
    "language": "zh|en",
    "tags": ["标签数组"],
    "ingested_at": "摄入时间"
  }
  ```

### D10 — 批量摄入管线
- [ ] `agent/ingest.py` — 数据摄入入口
  - 扫描指定目录 → 自动识别数据源类型 → chunk → embed → 入库
  - 支持增量更新 (对比已入库内容, 跳过重复)
  - 去重策略: 基于 content hash + metadata 匹配
- [ ] CLI 工具: `python -m agent.ingest --source ./new_data/`
- [ ] 文件夹监听 (可选): 监控 `data/` 目录新增文件自动摄入
- [ ] 摄入日志 + 失败重试

---

## P4 — 体验与功能增强 (D11-D14)

### D11 — 体验优化
- [ ] 报告 PDF 导出
  - Markdown → HTML → PDF (WeasyPrint 或 Playwright)
  - 含封面、目录、分级表格、图表
  - `GET /api/report/pdf?session_id=xxx`
- [ ] 学校对比功能
  - 可勾选多所学校/专业并排对比
  - 对比维度: 排名、费用、录取要求、截止日期、课程
- [ ] 多轮追问优化
  - 报告生成后支持追问 (如"能否推荐更多保底学校?")
  - 会话上下文保持

### D12 — 功能增强
- [ ] 截止日期提醒
  - 从研究生数据提取截止日期
  - 前端展示倒计时 + 近期待办
- [ ] 选校收藏夹
  - 学生可收藏感兴趣的学校/专业
  - localStorage 持久化
- [ ] 顾问协作分享
  - 生成分享链接 (含只读报告)
  - 可选密码保护

### D13 — 性能与鲁棒性
- [ ] 检索缓存
  - 相同查询参数缓存结果 (TTL 5分钟)
  - 减少 embedding 调用
- [ ] API 重试机制
  - DeepSeek API 调用失败自动重试 (最多3次, 指数退避)
  - 前端展示重试状态
- [ ] embedding 本地化批处理
  - 批量 embedding 请求合并
  - GPU 加速 (如可用)
- [ ] 日志告警
  - 结构化日志 (JSON format)
  - API 错误率监控

### D14 — 测试与文档
- [ ] 端到端测试用例
  - 完整链路: 画像输入 → 选校报告
  - 研究生链路: 搜索 → 详情 → 对比
  - 边界情况: 空输入、缺字段、无匹配
- [ ] API 接口文档
  - OpenAPI/Swagger 完善
- [ ] Docker 部署
  - `Dockerfile` + `docker-compose.yml`
  - 含 ChromaDB 持久化卷
  - `.env.example` 模板
