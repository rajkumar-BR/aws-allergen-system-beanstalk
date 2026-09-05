const MENU_ID = "kiwi-cafe-queenstown";
let allItems = [];
let allCategories = [];
let activeFilters = new Set();
let currentLang = "en";

// icon shown in the small circular badge on each allergen/diet chip.
// emoji where a clear one-to-one match exists, otherwise a short monogram.
const CHIP_ICON = {
  "Contains Wheat/Gluten": "🌾",
  "Contains Crustacea": "🦐",
  "Contains Egg": "🥚",
  "Contains Fish": "🐟",
  "Contains Milk": "🥛",
  "Contains Peanuts": "🥜",
  "Contains Soy": "🫘",
  "Contains Tree Nuts": "🌰",
  "Contains Sesame": "Se",
  "Contains Lupin": "Lu",
  "Contains Sulphites": "SO₂",
  "Gluten-Free": "GF",
  "Dairy-Free": "DF",
};
function chipIcon(label) {
  return CHIP_ICON[label] || label.slice(0, 2);
}

// Pick a colourful food emoji + gradient for each dish based on keywords in
// its name/description, so every card gets a nice visual banner even without
// real photos (works fully offline). First match wins; falls back to a plate.
const DISH_VISUALS = [
  { kw: ["steak", "ribeye", "beef", "burger"],               emoji: "🥩", grad: "linear-gradient(135deg,#b45309,#7c2d12)" },
  { kw: ["chowder", "soup", "bisque"],                       emoji: "🍲", grad: "linear-gradient(135deg,#f59e0b,#b45309)" },
  { kw: ["prawn", "shrimp", "crab", "tempura", "lobster"],   emoji: "🍤", grad: "linear-gradient(135deg,#fb7185,#be123c)" },
  { kw: ["salmon", "snapper", "tuna", "seafood", "fish"],    emoji: "🐟", grad: "linear-gradient(135deg,#0ea5e9,#0369a1)" },
  { kw: ["chicken", "satay", "skewer"],                       emoji: "🍗", grad: "linear-gradient(135deg,#f97316,#c2410c)" },
  { kw: ["risotto", "rice", "quinoa", "bowl"],                emoji: "🍚", grad: "linear-gradient(135deg,#84cc16,#4d7c0f)" },
  { kw: ["mushroom", "truffle"],                              emoji: "🍄", grad: "linear-gradient(135deg,#a16207,#713f12)" },
  { kw: ["salad", "rocket", "greens", "kumara", "halloumi", "fig"], emoji: "🥗", grad: "linear-gradient(135deg,#22c55e,#15803d)" },
  { kw: ["brownie", "chocolate"],                             emoji: "🍫", grad: "linear-gradient(135deg,#78350f,#451a03)" },
  { kw: ["tart", "cake", "meringue", "dessert", "sweet"],    emoji: "🍰", grad: "linear-gradient(135deg,#ec4899,#be185d)" },
  { kw: ["pasta", "noodle", "spaghetti"],                     emoji: "🍝", grad: "linear-gradient(135deg,#f43f5e,#9f1239)" },
  { kw: ["egg", "brunch", "toast", "benedict"],               emoji: "🍳", grad: "linear-gradient(135deg,#fbbf24,#d97706)" },
  { kw: ["vegan", "vegetable", "buddha", "tofu"],             emoji: "🥑", grad: "linear-gradient(135deg,#10b981,#047857)" },
];
function dishVisual(item) {
  const hay = `${item.name} ${item.description}`.toLowerCase();
  for (const v of DISH_VISUALS) {
    if (v.kw.some(k => hay.includes(k))) return v;
  }
  return { emoji: "🍽️", grad: "linear-gradient(135deg,#64748b,#334155)" };
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

async function loadCategories() {
  const data = await api("/api/allergen-categories");
  allCategories = data.categories;
  const el = document.getElementById("categoryList");
  el.innerHTML = allCategories.map(c =>
    `<span class="chip"><span class="icon-badge">${chipIcon(c).slice(0, 2)}</span>${c}</span>`
  ).join("");
}

async function loadItems() {
  const data = await api(`/api/menus/${MENU_ID}/items`);
  allItems = data.items || [];
  renderGrid();
}

function translatedView(item) {
  if (currentLang === "en" || !item.translations || !item.translations[currentLang]) {
    return { name: item.name, description: item.description };
  }
  const trans = item.translations[currentLang];
  
  // 美化离线翻译显示
  let name = trans.name || item.name;
  let desc = trans.description || item.description;
  
  // 移除离线占位符前缀
  const langNames = {
    es: 'Spanish', de: 'German', ja: 'Japanese', zh: 'Mandarin Chinese (Simplified)'
  };
  const langName = langNames[currentLang] || currentLang;
  
  const offlinePrefix = `[${langName} - offline] `;
  if (name.startsWith(offlinePrefix)) {
    name = name.slice(offlinePrefix.length);
  }
  
  const descPrefix = `[${langName} translation unavailable offline] `;
  if (desc.startsWith(descPrefix)) {
    desc = desc.slice(descPrefix.length);
  }
  
  return { name, description: desc };
}

function passesFilters(item) {
  if (activeFilters.size === 0) return true;
  // OR logic: show dishes that have ANY of the selected diet tags.
  // E.g. checking both "Gluten-Free" and "Dairy-Free" shows all dishes
  // that are gluten-free OR dairy-free (not just ones that are both).
  const dietTags = new Set(item.diet_tags || []);
  for (const f of activeFilters) {
    if (dietTags.has(f)) return true;
  }
  return false;
}

function renderGrid() {
  const grid = document.getElementById("dishGrid");
  const visible = allItems.filter(passesFilters);

  // Update the count shown next to the heading
  const countEl = document.getElementById("dishCount");
  if (countEl) {
    countEl.textContent = activeFilters.size > 0
      ? `${visible.length} of ${allItems.length} dishes match`
      : `${allItems.length} dishes`;
  }

  if (allItems.length === 0) {
    grid.innerHTML = `<p class="muted">No dishes yet - load the sample menu, upload a file, or add one manually.</p>`;
    return;
  }
  if (visible.length === 0) {
    grid.innerHTML = `<p class="muted">No dishes match the selected diet filters. Try unchecking one.</p>`;
    return;
  }
  grid.innerHTML = visible.map(item => {
    const view = translatedView(item);
    const tags = (item.allergens?.display_tags || []).map(t =>
      `<span class="chip warn"><span class="icon-badge">${chipIcon(t)}</span>${t}</span>`
    ).join("");
    const diet = (item.diet_tags || []).map(t =>
      `<span class="chip diet"><span class="icon-badge">${chipIcon(t)}</span>${t}</span>`
    ).join("");
    const disagree = item.allergens?.disagreements;
    const hasDisagreement = disagree && (disagree.llm_only?.length || disagree.rule_only?.length);
    const vis = dishVisual(item);
    return `
      <div class="dish-card" data-id="${item.item_id}">
        <div class="dish-photo" style="background:${vis.grad}">
          <span class="dish-photo-emoji" aria-hidden="true">${vis.emoji}</span>
        </div>
        <div class="dish-body">
          <h4>${escapeHtml(view.name)}</h4>
          ${currentLang !== "en" ? `<div class="translated-name">🇬🇧 English: ${escapeHtml(item.name)}</div>` : ""}
          <p>${escapeHtml(view.description)}</p>
          <div class="tags">${tags}${diet}</div>
          <div class="status-badge">${item.status}${hasDisagreement ? " · needs review" : ""}</div>
        </div>
      </div>`;
  }).join("");

  grid.querySelectorAll(".dish-card").forEach(card => {
    card.addEventListener("click", () => openModal(card.dataset.id));
  });
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------- modal (human-in-the-loop review) ----------------
function openModal(itemId) {
  const item = allItems.find(i => i.item_id === itemId);
  if (!item) return;
  document.getElementById("modalTitle").textContent = item.name;
  const confirmed = new Set(item.allergens?.confirmed || []);
  const checks = allCategories.map(c => `
    <label><input type="checkbox" value="${c}" ${confirmed.has(c) ? "checked" : ""}/> ${c}</label>
  `).join("");

  const disagree = item.allergens?.disagreements || { llm_only: [], rule_only: [] };
  const disagreeHtml = (disagree.llm_only?.length || disagree.rule_only?.length)
    ? `<p class="muted">⚠ AI-only flagged: ${disagree.llm_only.join(", ") || "none"} · Rules-only flagged: ${disagree.rule_only.join(", ") || "none"}${disagree.rag_only?.length ? ` · RAG-only flagged: ${disagree.rag_only.join(", ")}` : ""}</p>`
    : `<p class="muted">AI extraction and rules-engine scan agreed on all allergens.</p>`;

  const engine = item.allergens?.compliance?.engine || "";
  const cites = item.allergens?.rag_citations || [];
  const complianceHtml = cites.length
    ? `<div class="rag-sources">
        <strong>Compliance engine: <span class="engine-badge">${escapeHtml(engine)}</span></strong>
        <ul>${cites.map(c => `<li><em>${escapeHtml(c.category)}</em> — ${escapeHtml(c.section || c.source)}</li>`).join("")}</ul>
      </div>`
    : "";

  document.getElementById("modalBody").innerHTML = `
    <p class="muted">${escapeHtml(item.description)}</p>
    ${disagreeHtml}
    ${complianceHtml}
    <label>Confirmed allergens (human-in-the-loop override)</label>
    <div class="allergen-checks">${checks}</div>
    <div class="modal-actions">
      <button class="btn primary" id="saveReviewBtn">Save as Human-Verified</button>
      <button class="btn" id="deleteItemBtn">Delete dish</button>
    </div>
  `;
  document.getElementById("editModal").classList.remove("hidden");

  document.getElementById("saveReviewBtn").onclick = async () => {
    const selected = Array.from(document.querySelectorAll("#modalBody .allergen-checks input:checked")).map(i => i.value);
    await api(`/api/menus/${MENU_ID}/items/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed_allergens: selected }),
    });
    closeModal();
    await loadItems();
  };
  document.getElementById("deleteItemBtn").onclick = async () => {
    await api(`/api/menus/${MENU_ID}/items/${itemId}`, { method: "DELETE" });
    closeModal();
    await loadItems();
  };
}
function closeModal() { document.getElementById("editModal").classList.add("hidden"); }
document.getElementById("modalClose").onclick = closeModal;
document.getElementById("editModal").addEventListener("click", e => {
  if (e.target.id === "editModal") closeModal();
});

// ---------------- language + filters ----------------
document.getElementById("langSelect").addEventListener("change", e => {
  currentLang = e.target.value;
  renderGrid();
});
document.getElementById("filters").addEventListener("change", e => {
  const val = e.target.value;
  if (e.target.checked) activeFilters.add(val); else activeFilters.delete(val);
  renderGrid();
});
document.getElementById("refreshBtn").addEventListener("click", loadItems);

// ---------------- seed sample menu ----------------
document.getElementById("seedBtn").addEventListener("click", async () => {
  const status = document.getElementById("seedStatus");
  status.textContent = "Running OCR-skip → allergen analysis → compliance verify → translation for 16 dishes...";
  try {
    await api(`/api/menus/${MENU_ID}/seed`, { method: "POST" });
    status.textContent = "Sample menu loaded.";
    await loadItems();
  } catch (err) {
    status.textContent = `Failed: ${err.message}`;
  }
});

// ---------------- manual add ----------------
document.getElementById("manualForm").addEventListener("submit", async e => {
  e.preventDefault();
  const name = document.getElementById("dishName").value.trim();
  const description = document.getElementById("dishDesc").value.trim();
  const status = document.getElementById("manualStatus");
  status.textContent = "Analyzing...";
  try {
    await api(`/api/menus/${MENU_ID}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    status.textContent = "Added.";
    document.getElementById("manualForm").reset();
    await loadItems();
  } catch (err) {
    status.textContent = `Failed: ${err.message}`;
  }
});

// ---------------- file upload ----------------
document.getElementById("uploadBtn").addEventListener("click", async () => {
  const fileInput = document.getElementById("fileInput");
  const progress = document.getElementById("uploadProgress");
  if (!fileInput.files.length) {
    progress.innerHTML = `<div>Select a file first.</div>`;
    return;
  }
  const steps = ["Uploading to S3...", "Running Textract OCR...", "Analyzing allergens (Bedrock + rules engine)...", "Translating (4 languages)...", "Saving to DynamoDB..."];
  progress.innerHTML = steps.map(s => `<div>${s}</div>`).join("");

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  try {
    const result = await api(`/api/menus/${MENU_ID}/upload`, { method: "POST", body: formData });
    progress.innerHTML += `<div>Done - ${result.items.length} dish(es) extracted.</div>`;
    await loadItems();
  } catch (err) {
    progress.innerHTML += `<div>Failed: ${err.message}</div>`;
  }
});

// ---------------- init ----------------
(async function init() {
  await loadCategories();
  await loadItems();
})();
