const BOOKMARK_KEY = "newsclipping_saved_v1";
const KEYWORDS_DRAFT_KEY = "newsclipping_keywords_draft_v1";

const state = {
  economy: null,
  domestic: null,
  global: null,
  industry: { selectedCategory: null, source: "domestic" },
  business: { selectedCategory: null, source: "domestic" },
  economySelectedGroup: null,
  saved: { kindFilter: "all", subFilter: null },
  keywords: null,
  keywordsOriginal: null,
  keywordsIsDraft: false,
  keywordsView: { kind: "industry", selectedCategory: null },
};

const KIND_LABELS = { economy: "경제", industry: "산업군", business: "Business" };

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function highlightInsight(text) {
  const escaped = escapeHtml(text);
  return escaped.replace(/(추정|가능성)/g, '<span class="badge-tag">$1</span>');
}

function timeAgo(isoString) {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const hours = Math.max(0, Math.round(diffMs / 3600000));
  if (hours < 1) return "방금 전";
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.round(hours / 24)}일 전`;
}

// ---------- Bookmarks (localStorage) ----------

function getSaved() {
  try {
    return JSON.parse(localStorage.getItem(BOOKMARK_KEY)) || {};
  } catch {
    return {};
  }
}

function isSaved(id) {
  return Object.prototype.hasOwnProperty.call(getSaved(), id);
}

function toggleSaved(article, meta) {
  const saved = getSaved();
  if (saved[article.id]) {
    delete saved[article.id];
  } else {
    saved[article.id] = { ...article, ...meta, saved_at: new Date().toISOString() };
  }
  localStorage.setItem(BOOKMARK_KEY, JSON.stringify(saved));
}

// ---------- Article card ----------

function createArticleCard(article, meta) {
  const card = document.createElement("div");
  card.className = "article-card";

  const bookmarked = isSaved(article.id);

  card.innerHTML = `
    <div class="article-head">
      <div class="article-title">
        <a href="${escapeHtml(article.url)}" target="_blank" rel="noopener">${escapeHtml(article.title)}</a>
        <div class="article-meta">${escapeHtml(meta.categoryLabel || article.category)} · ${timeAgo(article.published_at)}${meta.sourceLabel ? " · " + meta.sourceLabel : ""}</div>
      </div>
      <button class="icon-btn bookmark ${bookmarked ? "active" : ""}" title="저장">${bookmarked ? "★" : "☆"}</button>
      <span class="chevron">▾</span>
    </div>
    <div class="article-body">
      <ul class="article-bullets">
        ${article.bullets.map((b) => `<li>${escapeHtml(b)}</li>`).join("")}
      </ul>
      <div class="insight-block">
        <span class="insight-label">INSIGHT</span>
        ${highlightInsight(article.insight)}
      </div>
    </div>
  `;

  const head = card.querySelector(".article-head");
  head.addEventListener("click", (e) => {
    if (e.target.closest(".bookmark") || e.target.closest("a")) return;
    card.classList.toggle("expanded");
  });

  const bookmarkBtn = card.querySelector(".bookmark");
  bookmarkBtn.addEventListener("click", () => {
    toggleSaved(article, meta);
    const nowSaved = isSaved(article.id);
    bookmarkBtn.classList.toggle("active", nowSaved);
    bookmarkBtn.textContent = nowSaved ? "★" : "☆";
    if (state.currentTab === "saved") renderSaved();
  });

  return card;
}

// ---------- Summary box ----------

function renderSummaryBox(summary) {
  const headlines = summary.headlines
    .map((h) => `<li class="headline-chip"><b>${escapeHtml(h.category)}</b> · ${escapeHtml(h.headline)}</li>`)
    .join("");
  return `
    <div class="summary-box">
      <h2>오늘의 핵심 요약</h2>
      <ul class="summary-bullets">
        ${summary.overall_bullets.map((b) => `<li>${escapeHtml(b)}</li>`).join("")}
      </ul>
      <ul class="headline-list">${headlines}</ul>
    </div>
  `;
}

// ---------- Economy tab ----------

const INDICATOR_META = [
  { key: "policy_rate", region: "kr", label: "기준금리 — 한국", unit: "%" },
  { key: "policy_rate", region: "us", label: "기준금리 — 미국", unit: "%" },
  { key: "cpi", region: "kr", label: "소비자물가(CPI) — 한국", unit: "" },
  { key: "cpi", region: "us", label: "소비자물가(CPI) — 미국", unit: "" },
  { key: "fx_usd_krw", region: null, label: "환율 — 원/달러", unit: "원" },
];

function renderIndicatorCard(container, meta) {
  const data = meta.region ? state.economy.indicators[meta.key][meta.region] : state.economy.indicators[meta.key];

  const card = document.createElement("div");
  card.className = "indicator-card";
  card.innerHTML = `
    <div class="indicator-title">${meta.label}</div>
    <div class="indicator-numbers">
      <div><div class="label">오늘</div><div class="value today">${data.latest}${meta.unit}</div></div>
      <div><div class="label">1달 평균</div><div class="value">${data.avg_1m}${meta.unit}</div></div>
      <div><div class="label">1년 평균</div><div class="value">${data.avg_1y}${meta.unit}</div></div>
    </div>
    <div class="indicator-chart"><canvas></canvas></div>
  `;
  container.appendChild(card);

  const ctx = card.querySelector("canvas").getContext("2d");
  new Chart(ctx, {
    type: "line",
    data: {
      labels: data.history_5y.map((p) => p.date),
      datasets: [
        {
          data: data.history_5y.map((p) => p.value),
          borderColor: "#1f3c63",
          backgroundColor: "rgba(31,60,99,0.08)",
          fill: true,
          pointRadius: 0,
          borderWidth: 1.5,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
    },
  });
}

function renderEconomyGroupButtons(container, groups) {
  const grid = document.createElement("div");
  grid.className = "category-grid";
  Object.entries(groups).forEach(([name, block]) => {
    const btn = document.createElement("button");
    btn.className = "category-btn" + (state.economySelectedGroup === name ? " active" : "");
    btn.innerHTML = `${escapeHtml(name)} <span class="count">${block.articles.length}</span>`;
    btn.addEventListener("click", () => {
      state.economySelectedGroup = name;
      renderEconomy();
    });
    grid.appendChild(btn);
  });
  container.appendChild(grid);
}

function renderEconomy() {
  const view = document.getElementById("view-economy");
  view.innerHTML = "";

  const economy = state.economy;

  const title = document.createElement("div");
  title.className = "block-title";
  title.textContent = "경제 지표";
  view.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "indicator-grid";
  view.appendChild(grid);
  INDICATOR_META.forEach((m) => renderIndicatorCard(grid, m));

  const newsTitle = document.createElement("div");
  newsTitle.className = "block-title";
  newsTitle.textContent = "경제 뉴스클리핑";
  view.appendChild(newsTitle);

  view.insertAdjacentHTML("beforeend", renderSummaryBox(economy.news.summary));

  renderEconomyGroupButtons(view, economy.news.keyword_groups);

  const detail = document.createElement("div");
  detail.className = "category-detail";
  view.appendChild(detail);

  if (!state.economySelectedGroup) {
    detail.innerHTML = `<div class="empty-state">위에서 키워드 그룹을 선택하면 관련 뉴스가 표시됩니다.</div>`;
    return;
  }

  const block = economy.news.keyword_groups[state.economySelectedGroup];
  renderCategoryDetail(detail, block, { categoryLabel: state.economySelectedGroup, kind: "economy" });
}

// ---------- Industry / Business tabs ----------

function renderCategoryDetail(container, block, meta) {
  if (block.sub_summary_bullets.length) {
    const subSummary = document.createElement("ul");
    subSummary.className = "sub-summary";
    subSummary.innerHTML = block.sub_summary_bullets.map((b) => `<li>${escapeHtml(b)}</li>`).join("");
    container.appendChild(subSummary);
  }

  if (!block.articles.length) {
    container.insertAdjacentHTML("beforeend", `<div class="empty-state">오늘은 이 카테고리에 표시할 기사가 없습니다.</div>`);
    return;
  }

  block.articles.forEach((article) => {
    container.appendChild(createArticleCard(article, meta));
  });

  if (block.extra_topics && block.extra_topics.length) {
    const extra = document.createElement("div");
    extra.className = "extra-topics";
    extra.textContent = "그 외: " + block.extra_topics.join(" · ");
    container.appendChild(extra);
  }
}

function renderCategoryTab(kind) {
  const view = document.getElementById(`view-${kind}`);
  view.innerHTML = "";

  const s = state[kind];
  const dataset = state[s.source];
  const categories = dataset.categories[kind];

  const title = document.createElement("div");
  title.className = "block-title";
  title.textContent = kind === "industry" ? "산업군" : "Business";
  view.appendChild(title);

  view.insertAdjacentHTML("beforeend", renderSummaryBox(dataset.summary));

  const grid = document.createElement("div");
  grid.className = "category-grid";
  view.appendChild(grid);

  Object.entries(categories).forEach(([name, block]) => {
    const btn = document.createElement("button");
    btn.className = "category-btn" + (s.selectedCategory === name ? " active" : "");
    btn.innerHTML = `${escapeHtml(name)} <span class="count">${block.articles.length}</span>`;
    btn.addEventListener("click", () => {
      s.selectedCategory = name;
      renderCategoryTab(kind);
    });
    grid.appendChild(btn);
  });

  const detail = document.createElement("div");
  detail.className = "category-detail";
  view.appendChild(detail);

  if (!s.selectedCategory) {
    detail.innerHTML = `<div class="empty-state">위에서 카테고리를 선택하면 관련 뉴스가 표시됩니다.</div>`;
    return;
  }

  const toggle = document.createElement("div");
  toggle.className = "source-toggle";
  toggle.innerHTML = `
    <button data-src="domestic" class="${s.source === "domestic" ? "active" : ""}">국내</button>
    <button data-src="global" class="${s.source === "global" ? "active" : ""}">글로벌</button>
  `;
  toggle.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => {
      s.source = b.dataset.src;
      renderCategoryTab(kind);
    });
  });
  detail.appendChild(toggle);

  const currentDataset = state[s.source];
  const block = currentDataset.categories[kind][s.selectedCategory];
  const sourceLabel = s.source === "domestic" ? "국내" : "글로벌";
  renderCategoryDetail(detail, block, { categoryLabel: s.selectedCategory, sourceLabel, kind });
}

// ---------- Saved tab ----------

function renderSaved() {
  const view = document.getElementById("view-saved");
  view.innerHTML = "";

  const title = document.createElement("div");
  title.className = "block-title";
  title.textContent = "저장됨";
  view.appendChild(title);

  const all = Object.values(getSaved()).sort((a, b) => new Date(b.saved_at) - new Date(a.saved_at));

  if (!all.length) {
    view.insertAdjacentHTML(
      "beforeend",
      `<div class="empty-state">저장한 기사가 없습니다. 기사 카드의 ☆ 아이콘을 눌러 저장해보세요.</div>`
    );
    return;
  }

  const s = state.saved;

  // 대분류(경제/산업군/Business) 필터 칩
  const kindGrid = document.createElement("div");
  kindGrid.className = "kind-filter-grid";
  const kindCounts = { economy: 0, industry: 0, business: 0 };
  all.forEach((a) => {
    if (kindCounts[a.kind] !== undefined) kindCounts[a.kind] += 1;
  });

  const allBtn = document.createElement("button");
  allBtn.className = "kind-filter-btn" + (s.kindFilter === "all" ? " active" : "");
  allBtn.innerHTML = `전체 <span class="count">${all.length}</span>`;
  allBtn.addEventListener("click", () => {
    s.kindFilter = "all";
    s.subFilter = null;
    renderSaved();
  });
  kindGrid.appendChild(allBtn);

  Object.entries(KIND_LABELS).forEach(([kind, label]) => {
    const btn = document.createElement("button");
    btn.className = "kind-filter-btn" + (s.kindFilter === kind ? " active" : "");
    btn.innerHTML = `${escapeHtml(label)} <span class="count">${kindCounts[kind]}</span>`;
    btn.addEventListener("click", () => {
      s.kindFilter = kind;
      s.subFilter = null;
      renderSaved();
    });
    kindGrid.appendChild(btn);
  });
  view.appendChild(kindGrid);

  let filtered = s.kindFilter === "all" ? all : all.filter((a) => a.kind === s.kindFilter);

  // 하위 카테고리 필터 칩 (대분류를 선택했을 때만) — 대분류와 다른 모양(알약형 칩)으로 구분
  if (s.kindFilter !== "all") {
    const subCounts = {};
    filtered.forEach((a) => {
      subCounts[a.categoryLabel] = (subCounts[a.categoryLabel] || 0) + 1;
    });

    const subGrid = document.createElement("div");
    subGrid.className = "category-grid sub-filter-grid";

    const subAllBtn = document.createElement("button");
    subAllBtn.className = "category-btn" + (!s.subFilter ? " active" : "");
    subAllBtn.innerHTML = `전체 <span class="count">${filtered.length}</span>`;
    subAllBtn.addEventListener("click", () => {
      s.subFilter = null;
      renderSaved();
    });
    subGrid.appendChild(subAllBtn);

    Object.entries(subCounts).forEach(([label, count]) => {
      const btn = document.createElement("button");
      btn.className = "category-btn" + (s.subFilter === label ? " active" : "");
      btn.innerHTML = `${escapeHtml(label)} <span class="count">${count}</span>`;
      btn.addEventListener("click", () => {
        s.subFilter = label;
        renderSaved();
      });
      subGrid.appendChild(btn);
    });
    view.appendChild(subGrid);

    if (s.subFilter) {
      filtered = filtered.filter((a) => a.categoryLabel === s.subFilter);
    }
  }

  const list = document.createElement("div");
  list.className = "category-detail";
  view.appendChild(list);

  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state">이 분류에 저장된 기사가 없습니다.</div>`;
    return;
  }

  filtered.forEach((article) => {
    list.appendChild(
      createArticleCard(article, { categoryLabel: article.categoryLabel, sourceLabel: article.sourceLabel, kind: article.kind })
    );
  });
}

// ---------- 키워드 설정 ----------

function saveKeywordsDraft() {
  state.keywordsIsDraft = true;
  localStorage.setItem(KEYWORDS_DRAFT_KEY, JSON.stringify(state.keywords));
}

function downloadKeywordsJson() {
  const blob = new Blob([JSON.stringify(state.keywords, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "keywords.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function renderKeywordEditor(kind, category, lang, label) {
  const wrap = document.createElement("div");
  wrap.className = "keyword-editor";

  const words = state.keywords[kind][category][lang];

  const chipRow = document.createElement("div");
  chipRow.className = "keyword-chip-row";
  words.forEach((word, i) => {
    const chip = document.createElement("span");
    chip.className = "keyword-chip";
    chip.innerHTML = `${escapeHtml(word)} <button type="button" aria-label="삭제">×</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      words.splice(i, 1);
      saveKeywordsDraft();
      renderKeywords();
    });
    chipRow.appendChild(chip);
  });

  const addForm = document.createElement("form");
  addForm.className = "keyword-add-form";
  addForm.innerHTML = `<input type="text" placeholder="새 키워드" /><button type="submit">+ 추가</button>`;
  addForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = addForm.querySelector("input");
    const value = input.value.trim();
    if (value && !words.includes(value)) {
      words.push(value);
      saveKeywordsDraft();
      renderKeywords();
    }
  });

  wrap.innerHTML = `<div class="keyword-editor-label">${escapeHtml(label)}</div>`;
  wrap.appendChild(chipRow);
  wrap.appendChild(addForm);
  return wrap;
}

function renderKeywords() {
  const view = document.getElementById("view-keywords");
  view.innerHTML = "";

  const title = document.createElement("div");
  title.className = "block-title";
  title.textContent = "키워드 설정";
  view.appendChild(title);

  view.insertAdjacentHTML(
    "beforeend",
    `<p class="keywords-help">카테고리별 검색 키워드를 추가·삭제할 수 있습니다. 이 화면 편집은 실제 파이프라인에 자동 반영되지 않으니,
    수정 후 <b>keywords.json 다운로드</b>로 파일을 받아 <code>docs/data/keywords.json</code>에 덮어쓰고 커밋·푸시하세요.</p>`
  );

  if (state.keywordsIsDraft) {
    view.insertAdjacentHTML(
      "beforeend",
      `<p class="keywords-draft-notice">이 브라우저에 저장된 임시 편집 내용을 보여주는 중입니다.</p>`
    );
  }

  const toolbar = document.createElement("div");
  toolbar.className = "keywords-toolbar";
  const downloadBtn = document.createElement("button");
  downloadBtn.className = "primary-btn";
  downloadBtn.textContent = "⬇ keywords.json 다운로드";
  downloadBtn.addEventListener("click", downloadKeywordsJson);
  const resetBtn = document.createElement("button");
  resetBtn.className = "ghost-btn";
  resetBtn.textContent = "편집 내용 되돌리기";
  resetBtn.addEventListener("click", () => {
    localStorage.removeItem(KEYWORDS_DRAFT_KEY);
    state.keywords = JSON.parse(JSON.stringify(state.keywordsOriginal));
    state.keywordsIsDraft = false;
    renderKeywords();
  });
  toolbar.appendChild(downloadBtn);
  toolbar.appendChild(resetBtn);
  view.appendChild(toolbar);

  const kindGrid = document.createElement("div");
  kindGrid.className = "kind-filter-grid";
  [
    ["economy", "경제"],
    ["industry", "산업군"],
    ["business", "Business"],
  ].forEach(([kind, label]) => {
    const btn = document.createElement("button");
    btn.className = "kind-filter-btn" + (state.keywordsView.kind === kind ? " active" : "");
    btn.textContent = label;
    btn.addEventListener("click", () => {
      state.keywordsView.kind = kind;
      state.keywordsView.selectedCategory = null;
      renderKeywords();
    });
    kindGrid.appendChild(btn);
  });
  view.appendChild(kindGrid);

  const kind = state.keywordsView.kind;
  const categoryNames = Object.keys(state.keywords[kind]);

  const catGrid = document.createElement("div");
  catGrid.className = "category-grid";
  categoryNames.forEach((name) => {
    const btn = document.createElement("button");
    btn.className = "category-btn" + (state.keywordsView.selectedCategory === name ? " active" : "");
    btn.textContent = name;
    btn.addEventListener("click", () => {
      state.keywordsView.selectedCategory = name;
      renderKeywords();
    });
    catGrid.appendChild(btn);
  });
  view.appendChild(catGrid);

  const detail = document.createElement("div");
  detail.className = "category-detail";
  view.appendChild(detail);

  const selected = state.keywordsView.selectedCategory;
  if (!selected) {
    detail.innerHTML = `<div class="empty-state">위에서 카테고리를 선택하면 키워드를 편집할 수 있습니다.</div>`;
    return;
  }

  detail.appendChild(renderKeywordEditor(kind, selected, "ko", "국내 검색 키워드 (한국어)"));
  detail.appendChild(renderKeywordEditor(kind, selected, "en", "글로벌 검색 키워드 (영어)"));
}

// ---------- Tabs ----------

function switchTab(tab) {
  state.currentTab = tab;
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${tab}`));

  if (tab === "economy") renderEconomy();
  if (tab === "industry") renderCategoryTab("industry");
  if (tab === "business") renderCategoryTab("business");
  if (tab === "saved") renderSaved();
  if (tab === "keywords") renderKeywords();
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// ---------- Init ----------

async function init() {
  const [economy, domestic, global, keywords] = await Promise.all([
    fetch("data/economy.json").then((r) => r.json()),
    fetch("data/domestic.json").then((r) => r.json()),
    fetch("data/global.json").then((r) => r.json()),
    fetch("data/keywords.json").then((r) => r.json()),
  ]);
  state.economy = economy;
  state.domestic = domestic;
  state.global = global;
  state.keywordsOriginal = keywords;

  let draft = null;
  try {
    draft = JSON.parse(localStorage.getItem(KEYWORDS_DRAFT_KEY));
  } catch {
    draft = null;
  }
  state.keywords = draft || JSON.parse(JSON.stringify(keywords));
  state.keywordsIsDraft = Boolean(draft);

  document.getElementById("header-date").textContent = `${economy.date} 기준`;
  switchTab("economy");
}

init().catch((err) => {
  document.querySelector("main").innerHTML = `<div class="empty-state">데이터를 불러오지 못했습니다: ${escapeHtml(err.message)}</div>`;
  console.error(err);
});
