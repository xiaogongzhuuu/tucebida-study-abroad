const $ = (sel) => document.querySelector(sel);

let currentProfile = null;

// Tab 切换
$(".tab-bar").addEventListener("click", (e) => {
  if (!e.target.classList.contains("tab")) return;
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  e.target.classList.add("active");

  const panel = e.target.dataset.tab;
  document.querySelectorAll(".tab-panel").forEach((p) => (p.style.display = "none"));
  $(`#tab-${panel}`).style.display = "";
});

// 提交按钮 — 提取画像
$("#submit-btn").addEventListener("click", async () => {
  const activeTab = document.querySelector(".tab.active").dataset.tab;

  let text;
  if (activeTab === "free") {
    text = $("#free-input").value.trim();
  } else {
    text = buildFieldsText();
  }

  if (!text) {
    alert("请输入学生信息");
    return;
  }

  const btn = $("#submit-btn");
  const loading = $("#loading");

  btn.disabled = true;
  loading.style.display = "";
  $("#result-section").style.display = "none";
  $("#report-section").style.display = "none";

  try {
    const resp = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    currentProfile = data.profile;
    renderProfile(data.profile);
    $("#result-section").style.display = "";
  } catch (err) {
    alert(`解析失败: ${err.message}`);
  } finally {
    btn.disabled = false;
    loading.style.display = "none";
  }
});

// 开始选校匹配按钮
$("#match-btn").addEventListener("click", () => doMatch(false));

// 流式匹配按钮 (预留接口)
$("#match-btn-stream").addEventListener("click", () => doMatch(true));

async function doMatch(useStream) {
  if (!currentProfile) return;

  const btn = $("#match-btn");
  const btnStream = $("#match-btn-stream");
  const loading = $("#match-loading");

  btn.disabled = true;
  if (btnStream) btnStream.disabled = true;
  loading.style.display = "";
  $("#report-section").style.display = "";
  $("#report-content").innerHTML = '<p class="loading-text">AI 正在分析案例并生成选校报告...</p>';
  $("#search-summary").innerHTML = "";
  $("#classify-summary").style.display = "none";
  $("#classify-summary").innerHTML = "";
  $("#classify-table").style.display = "none";
  $("#classify-table").innerHTML = "";

  try {
    if (useStream) {
      await matchStream();
    } else {
      await matchNormal();
    }
  } catch (err) {
    $("#report-content").innerHTML = `<p class="error-text">匹配失败: ${escapeHtml(err.message)}</p>`;
  } finally {
    btn.disabled = false;
    if (btnStream) btnStream.disabled = false;
    loading.style.display = "none";
  }
}

async function matchNormal() {
  const resp = await fetch("/api/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile: currentProfile,
      filters: { doc_types: ["录取结果", "顾问笔记", "school_profile"] },
    }),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  const data = await resp.json();
  renderReport(data);
}

async function matchStream() {
  const resp = await fetch("/api/match/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile: currentProfile,
      filters: { doc_types: ["录取结果", "顾问笔记", "school_profile"] },
    }),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let reportText = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6);
      if (data === "[DONE]") continue;

      try {
        const parsed = JSON.parse(data);
        if (parsed.classification) {
          renderClassification(parsed.classification);
          continue;
        }
        if (parsed.content) {
          reportText += parsed.content;
          $("#report-content").innerHTML = parseMarkdown(reportText);
        }
      } catch (e) {
        // skip malformed chunks
      }
    }
  }
}

function buildFieldsText() {
  const parts = [];
  const add = (label, value) => {
    if (value) parts.push(`${label}: ${value}`);
  };

  add("课程体系", $("#f-curriculum").value);
  add("GPA", $("#f-gpa").value);
  add("TOEFL", $("#f-toefl").value);
  add("IELTS", $("#f-ielts").value);
  add("SAT", $("#f-sat").value);
  add("ACT", $("#f-act").value);
  add("AP成绩", $("#f-ap").value);
  add("专业意向", $("#f-major").value);
  add("意向国家", $("#f-country").value);
  add("预算", $("#f-budget").value);
  add("当前年级", $("#f-grade").value);
  add("活动经历", $("#f-activities").value);
  add("补充信息", $("#f-notes").value);

  return parts.join("\n");
}

function renderProfile(p) {
  const container = $("#profile-result");
  container.innerHTML = "";

  const items = [
    ["课程体系", p.curriculum],
    ["GPA / 预估分", p.gpa],
    ["TOEFL", p.toefl],
    ["IELTS", p.ielts],
    ["SAT", p.sat],
    ["ACT", p.act],
    ["AP 成绩", p.ap_scores],
    ["当前年级", p.grade_level],
    ["预算", p.budget],
  ];

  const grid = document.createElement("div");
  grid.className = "profile-grid";

  items.forEach(([label, value]) => {
    const div = document.createElement("div");
    div.className = "profile-item";
    div.innerHTML = `<span class="label">${label}</span><span class="value${value ? "" : " empty"}">${value || "未提供"}</span>`;
    grid.appendChild(div);
  });

  // 专业意向
  const majorDiv = document.createElement("div");
  majorDiv.className = "profile-item full";
  majorDiv.innerHTML = '<span class="label">专业意向</span>';
  if (p.major_interest?.length) {
    const tags = document.createElement("div");
    tags.className = "tags";
    p.major_interest.forEach((m) => {
      const span = document.createElement("span");
      span.className = "tag";
      span.textContent = m;
      tags.appendChild(span);
    });
    majorDiv.appendChild(tags);
  } else {
    majorDiv.innerHTML += '<span class="value empty">未提供</span>';
  }
  grid.appendChild(majorDiv);

  // 意向国家
  const countryDiv = document.createElement("div");
  countryDiv.className = "profile-item full";
  countryDiv.innerHTML = '<span class="label">意向国家</span>';
  if (p.country_pref?.length) {
    const tags = document.createElement("div");
    tags.className = "tags";
    p.country_pref.forEach((c) => {
      const span = document.createElement("span");
      span.className = "tag";
      span.textContent = c;
      tags.appendChild(span);
    });
    countryDiv.appendChild(tags);
  } else {
    countryDiv.innerHTML += '<span class="value empty">未提供</span>';
  }
  grid.appendChild(countryDiv);

  // 活动经历
  if (p.activities?.length) {
    const div = document.createElement("div");
    div.className = "profile-item full";
    div.innerHTML = '<span class="label">活动 / 竞赛</span>';
    const tags = document.createElement("div");
    tags.className = "tags";
    p.activities.forEach((a) => {
      const span = document.createElement("span");
      span.className = "tag";
      span.textContent = a;
      tags.appendChild(span);
    });
    div.appendChild(tags);
    grid.appendChild(div);
  }

  // 补充说明
  if (p.notes) {
    const div = document.createElement("div");
    div.className = "profile-item full";
    div.innerHTML = `<span class="label">补充说明</span><span class="value">${escapeHtml(p.notes)}</span>`;
    grid.appendChild(div);
  }

  container.appendChild(grid);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// 选校报告渲染
function renderReport(data) {
  // 检索摘要
  const summary = data.search_summary;
  const summaryDiv = $("#search-summary");
  let summaryHTML = `<span class="search-meta">检索命中 <strong>${summary.total_hits}</strong> 条相关案例`;
  if (summary.by_doc_type) {
    const types = Object.entries(summary.by_doc_type)
      .map(([k, v]) => `${k}(${v})`)
      .join(", ");
    summaryHTML += ` | 类型: ${types}`;
  }
  summaryHTML += "</span>";
  summaryDiv.innerHTML = summaryHTML;

  // 分级结果
  if (data.classification) {
    renderClassification(data.classification);
  }

  // Markdown 报告
  const contentDiv = $("#report-content");
  contentDiv.innerHTML = parseMarkdown(data.report);
}

// 渲染三级分级结果
function renderClassification(cls) {
  const summary = cls.summary || {};
  const schools = cls.schools || [];
  const studentScores = cls.student_scores || {};

  // 统计卡片
  const statDiv = $("#classify-summary");
  statDiv.style.display = "";
  const tierLabels = { reach: "冲刺", match: "匹配", safety: "保底" };
  let statHTML = "";
  for (const [key, label] of Object.entries(tierLabels)) {
    statHTML += `<div class="classify-stat ${key}">
      <span class="stat-num">${summary[key] || 0}</span>
      <span class="stat-label">${label}</span>
    </div>`;
  }
  statHTML += `<div class="classify-stat total">
    <span class="stat-num">${summary.total || schools.length}</span>
    <span class="stat-label">总计</span>
  </div>`;
  statDiv.innerHTML = statHTML;

  // 学生成绩条
  const scoreParts = [];
  if (studentScores.gpa) scoreParts.push(`GPA ${studentScores.gpa}`);
  if (studentScores.toefl) scoreParts.push(`TOEFL ${studentScores.toefl}`);
  if (studentScores.ielts) scoreParts.push(`IELTS ${studentScores.ielts}`);
  if (studentScores.sat) scoreParts.push(`SAT ${studentScores.sat}`);
  if (studentScores.act) scoreParts.push(`ACT ${studentScores.act}`);
  if (scoreParts.length) {
    statDiv.innerHTML += `<div style="font-size:12px;color:#888;margin-top:4px">学生成绩: ${scoreParts.join(" / ")}</div>`;
  }

  // 详情表格
  if (schools.length === 0) return;

  const tableDiv = $("#classify-table");
  tableDiv.style.display = "";
  let tableHTML = '<table class="classify-table"><thead><tr>';
  tableHTML += '<th>学校</th><th>分级</th><th>匹配分</th><th>数据来源</th><th>关键指标对比</th>';
  tableHTML += '</tr></thead><tbody>';

  schools.forEach((s) => {
    const tier = s.tier || "match";
    const label = tierLabels[tier] || tier;
    const score = s.match_score != null ? (s.match_score * 100).toFixed(0) + "%" : "N/A";
    const docCount = s.doc_count || 0;

    // 关键指标对比
    const metricParts = [];
    const metrics = s.metrics || {};
    const metricOrder = ["gpa", "toefl", "ielts", "sat", "act"];
    const metricNames = { gpa: "GPA", toefl: "托福", ielts: "雅思", sat: "SAT", act: "ACT" };
    for (const key of metricOrder) {
      const m = metrics[key];
      if (m && m.result) {
        const resultLabel = { above_range: "↑", in_range: "≈", below_range: "↓", no_data: "?" }[m.result] || m.result;
        metricParts.push(`${metricNames[key]}: ${m.student}${resultLabel}(${m.school_median})`);
      }
    }

    tableHTML += `<tr>
      <td><strong>${escapeHtml(s.name)}</strong></td>
      <td><span class="tier-badge ${tier}">${label}</span></td>
      <td>${score}</td>
      <td>${docCount} 条</td>
      <td style="font-size:12px;color:#666">${metricParts.join("<br>") || "数据不足"}</td>
    </tr>`;
  });

  tableHTML += "</tbody></table>";
  tableDiv.innerHTML = tableHTML;
}

// Markdown → HTML 解析器
function parseMarkdown(md) {
  if (!md) return '<p class="empty-text">暂无报告内容</p>';

  let html = escapeHtml(md);

  // ── 代码块（必须在行内代码之前处理） ──
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code>${code.trim()}</code></pre>`;
  });

  // ── 行内代码 ──
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // ── 标题 ──
  html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // ── 粗体 / 斜体 ──
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // ── 水平线 ──
  html = html.replace(/^---+$/gm, "<hr>");

  // ── 无序列表 ──
  html = html.replace(/^[\*\-] (.+)$/gm, "<li>$1</li>");

  // ── 有序列表 ──
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // ── 按行组装段落和列表 ──
  const lines = html.split("\n");
  const result = [];
  let inList = false;
  let listType = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    if (!line) {
      if (inList) {
        result.push(listType === "ul" ? "</ul>" : "</ol>");
        inList = false;
        listType = null;
      }
      continue;
    }

    // 已经是块级元素
    if (/^<(h[1-4]|pre|hr|ul|ol|table|blockquote)/.test(line)) {
      if (inList) {
        result.push(listType === "ul" ? "</ul>" : "</ol>");
        inList = false;
        listType = null;
      }
      result.push(line);
      continue;
    }

    if (line.startsWith("<li>")) {
      if (!inList) {
        // 判断是否无序列表（原始行以 * 或 - 开头）
        listType = "ul";
        result.push("<ul>");
        inList = true;
      }
      result.push(line);
      continue;
    }

    if (inList) {
      result.push(listType === "ul" ? "</ul>" : "</ol>");
      inList = false;
      listType = null;
    }

    // 默认段落
    result.push(`<p>${line}</p>`);
  }

  if (inList) {
    result.push(listType === "ul" ? "</ul>" : "</ol>");
  }

  return result.join("\n");
}
