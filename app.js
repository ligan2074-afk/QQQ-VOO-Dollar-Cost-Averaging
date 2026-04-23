const fallbackHistory = {
  generated_at: "2026-04-23T00:00:00Z",
  mode: "sample",
  items: [
    { date: "2026-04-17", price: 26672.43, pe: 36.19, ma200: 24589.00, vix: 17.48, pePercentile: 0.843, bias: 8.473, peScore: 4.7, maScore: 3.1, vixScore: 5.0, total: 12.8, gradeLetter: "D", gradeNote: "偏高，控制节奏" },
    { date: "2026-04-16", price: 26333.00, pe: 35.64, ma200: 24570.73, vix: 17.94, pePercentile: 0.807, bias: 7.172, peScore: 5.8, maScore: 5.7, vixScore: 5.9, total: 17.4, gradeLetter: "D", gradeNote: "偏高，控制节奏" }
  ]
};

const fallbackLatest = {
  generated_at: "2026-04-23T00:00:00Z",
  as_of: "2026-04-17",
  mode: "sample",
  meta: { index_source: "sample", vol_source: "sample", pe_source: "sample" },
  record: fallbackHistory.items[0]
};

const fallbackConfig = {
  title: "纳指100自动定投打分系统",
  subtitle: "Auto Daily Update · GitHub Pages + GitHub Actions",
  series: { index_label: "NASDAQ-100", vol_label: "VIX", pe_label: "纳指100 PE" },
  weights: { pe: 30, ma: 40, vol: 30 },
  pe: { fallback_min: 4.7, fallback_max: 36.7, label: "PE 十年百分位" },
  ma: { target_bias: -10, bias_range: 20, label: "价格 VS MA200" },
  vol: { floor: 15, cap: 30, label: "VIX 恐慌指数" },
  grades: [
    { letter: "A", min: 80, note: "极具吸引力，可提高定投" },
    { letter: "B", min: 60, note: "估值偏合理，可积极定投" },
    { letter: "C", min: 40, note: "中性区间，正常定投" },
    { letter: "D", min: 0, note: "偏高，控制节奏" }
  ]
};

let config = fallbackConfig;
let historyData = fallbackHistory;
let latestData = fallbackLatest;
let history = [...fallbackHistory.items];

const $ = (id) => document.getElementById(id);
const round1 = (value) => Math.round(value * 10) / 10;
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

function formatPct(value) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${Number(value).toFixed(2)}%`;
}

function formatDateTime(text) {
  if (!text) return "--";
  const d = new Date(text);
  if (Number.isNaN(d.getTime())) return text;
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}

function gradeClass(letter) {
  return { A: "tag-a", B: "tag-b", C: "tag-c", D: "tag-d" }[letter] || "tag-d";
}

function getGrade(total) {
  const grades = config.grades || fallbackConfig.grades;
  return grades.find(item => total >= item.min) || grades[grades.length - 1];
}

function scoreRecord(record) {
  const pePercentile = record.pePercentile !== undefined && record.pePercentile !== null
    ? Number(record.pePercentile)
    : clamp((record.pe - config.pe.fallback_min) / (config.pe.fallback_max - config.pe.fallback_min), 0, 1);

  const bias = record.bias !== undefined && record.bias !== null
    ? Number(record.bias)
    : ((record.price - record.ma200) / record.ma200) * 100;

  const peScore = record.peScore !== undefined && record.peScore !== null
    ? Number(record.peScore)
    : (1 - pePercentile) * config.weights.pe;

  const maScore = record.maScore !== undefined && record.maScore !== null
    ? Number(record.maScore)
    : clamp(config.weights.ma * (1 - Math.abs(bias - config.ma.target_bias) / config.ma.bias_range), 0, config.weights.ma);

  const vixScore = record.vixScore !== undefined && record.vixScore !== null
    ? Number(record.vixScore)
    : clamp(((record.vix - config.vol.floor) / (config.vol.cap - config.vol.floor)) * config.weights.vol, 0, config.weights.vol);

  const total = record.total !== undefined && record.total !== null
    ? Number(record.total)
    : peScore + maScore + vixScore;

  const grade = record.gradeLetter
    ? { letter: record.gradeLetter, note: record.gradeNote || getGrade(total).note }
    : getGrade(total);

  return { ...record, pePercentile, bias, peScore, maScore, vixScore, total, grade };
}

function renderSelectOptions() {
  const select = $("dateSelect");
  select.innerHTML = history
    .map(item => `<option value="${item.date}">${item.date}</option>`)
    .join("");
  if (history[0]) select.value = history[0].date;
}

function fillInput(record) {
  $("inputDate").value = record.date || "";
  $("inputPrice").value = record.price ?? "";
  $("inputPe").value = record.pe ?? "";
  $("inputMa200").value = record.ma200 ?? "";
  $("inputVix").value = record.vix ?? "";
}

function renderHeaderMeta() {
  $("siteTitle").textContent = config.title || fallbackConfig.title;
  $("siteSubtitle").textContent = config.subtitle || fallbackConfig.subtitle;
  $("updatedAt").textContent = formatDateTime(latestData.generated_at);
  $("autoSource").textContent = `${latestData.meta?.index_source || "--"} / ${latestData.meta?.vol_source || "--"} / ${latestData.meta?.pe_source || "--"}`;
}

function renderSummary(scored) {
  $("pePercentileLabel").textContent = `${config.pe.label}（满分 ${config.weights.pe}）`;
  $("maLabel").textContent = `${config.ma.label}（满分 ${config.weights.ma}）`;
  $("volLabel").textContent = `${config.vol.label}（满分 ${config.weights.vol}）`;
  $("seriesVolLabel").textContent = config.series?.vol_label || "VIX";

  $("pePercentileCard").textContent = `${(scored.pePercentile * 100).toFixed(1)}%`;
  $("peDesc").textContent = `${config.series.pe_label || "PE"}: ${Number(scored.pe).toFixed(2)} · 数据日期 ${scored.date}`;

  $("biasCard").textContent = formatPct(scored.bias);
  $("maDesc").textContent = `MA200: ${Number(scored.ma200).toFixed(2)} · 得分 ${round1(scored.maScore).toFixed(1)} / ${config.weights.ma}`;

  $("vixCard").textContent = Number(scored.vix).toFixed(2);
  $("vixDesc").textContent = `${config.series.vol_label || "VIX"} 得分: ${round1(scored.vixScore).toFixed(1)} / ${config.weights.vol}`;

  $("gradeLetter").textContent = scored.grade.letter;
  $("totalScore").textContent = round1(scored.total).toFixed(1);
  $("gradeNote").textContent = scored.grade.note;

  $("barPe").style.width = `${(scored.peScore / config.weights.pe) * 100}%`;
  $("barMa").style.width = `${(scored.maScore / config.weights.ma) * 100}%`;
  $("barVix").style.width = `${(scored.vixScore / config.weights.vol) * 100}%`;
  $("barTotal").style.width = `${clamp(scored.total, 0, 100)}%`;

  $("barPeText").textContent = `${round1(scored.peScore).toFixed(1)} / ${config.weights.pe}`;
  $("barMaText").textContent = `${round1(scored.maScore).toFixed(1)} / ${config.weights.ma}`;
  $("barVixText").textContent = `${round1(scored.vixScore).toFixed(1)} / ${config.weights.vol}`;
  $("barTotalText").textContent = `${round1(scored.total).toFixed(1)} / 100`;

  drawRadar(scored);
}

function renderTable() {
  const tbody = $("historyTableBody");
  tbody.innerHTML = history
    .map(scoreRecord)
    .map(scored => `
      <tr>
        <td>${scored.date}</td>
        <td class="num">${Number(scored.price).toFixed(2)}</td>
        <td class="num">${Number(scored.pe).toFixed(2)}</td>
        <td class="num">${(Number(scored.pePercentile) * 100).toFixed(1)}%</td>
        <td class="num">${Number(scored.ma200).toFixed(2)}</td>
        <td class="num">${formatPct(Number(scored.bias))}</td>
        <td class="num">${Number(scored.vix).toFixed(2)}</td>
        <td class="num">${round1(scored.peScore).toFixed(1)}</td>
        <td class="num">${round1(scored.maScore).toFixed(1)}</td>
        <td class="num">${round1(scored.vixScore).toFixed(1)}</td>
        <td class="num"><strong>${round1(scored.total).toFixed(1)}</strong></td>
        <td><span class="tag ${gradeClass(scored.grade.letter)}">${scored.grade.letter}</span></td>
      </tr>
    `)
    .join("");
}

function drawRadar(scored) {
  const canvas = $("radarCanvas");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const centerX = w / 2;
  const centerY = h / 2;
  const radius = 108;
  const axes = [
    { label: `MA ${round1(scored.maScore)}`, value: scored.maScore / config.weights.ma, angle: -Math.PI / 2 },
    { label: `${config.series.vol_label || "VIX"} ${round1(scored.vixScore)}`, value: scored.vixScore / config.weights.vol, angle: (Math.PI * 5) / 6 },
    { label: `PE ${round1(scored.peScore)}`, value: scored.peScore / config.weights.pe, angle: Math.PI / 6 }
  ];

  for (let level = 1; level <= 5; level += 1) {
    ctx.beginPath();
    axes.forEach((axis, i) => {
      const r = radius * (level / 5);
      const x = centerX + Math.cos(axis.angle) * r;
      const y = centerY + Math.sin(axis.angle) * r;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.strokeStyle = "#d8e0ea";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  axes.forEach(axis => {
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(centerX + Math.cos(axis.angle) * radius, centerY + Math.sin(axis.angle) * radius);
    ctx.strokeStyle = "#d8e0ea";
    ctx.stroke();
  });

  ctx.beginPath();
  axes.forEach((axis, i) => {
    const r = radius * axis.value;
    const x = centerX + Math.cos(axis.angle) * r;
    const y = centerY + Math.sin(axis.angle) * r;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.fillStyle = "rgba(79, 124, 255, 0.18)";
  ctx.strokeStyle = "#4f7cff";
  ctx.lineWidth = 3;
  ctx.fill();
  ctx.stroke();

  ctx.font = "14px sans-serif";
  ctx.fillStyle = "#6b7280";
  axes.forEach(axis => {
    const x = centerX + Math.cos(axis.angle) * (radius + 24);
    const y = centerY + Math.sin(axis.angle) * (radius + 24);
    ctx.textAlign = x < centerX - 10 ? "right" : x > centerX + 10 ? "left" : "center";
    ctx.fillText(axis.label, x, y);
  });
}

function renderAllByDate(date) {
  const record = history.find(item => item.date === date) || history[0];
  if (!record) return;
  fillInput(record);
  renderSummary(scoreRecord(record));
  renderTable();
}

function exportJson() {
  const payload = {
    exportedAt: new Date().toISOString(),
    config,
    latest: latestData,
    history: history
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "nasdaq100_auto_scoring_export.json";
  a.click();
  URL.revokeObjectURL(url);
}

function upsertCurrentInput() {
  const record = {
    date: $("inputDate").value,
    price: Number($("inputPrice").value),
    pe: Number($("inputPe").value),
    ma200: Number($("inputMa200").value),
    vix: Number($("inputVix").value)
  };

  if (!record.date || [record.price, record.pe, record.ma200, record.vix].some(v => Number.isNaN(v))) {
    alert("请先把日期、价格、PE、MA200、VIX 填完整。");
    return;
  }

  const idx = history.findIndex(item => item.date === record.date);
  if (idx >= 0) history[idx] = record;
  else history.unshift(record);
  history.sort((a, b) => b.date.localeCompare(a.date));
  renderSelectOptions();
  $("dateSelect").value = record.date;
  renderAllByDate(record.date);
}

async function loadRemoteJson(path, fallbackValue) {
  try {
    const res = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`加载 ${path} 失败，使用本地兜底样例。`, err);
    return fallbackValue;
  }
}

async function init() {
  [config, historyData, latestData] = await Promise.all([
    loadRemoteJson("./data/config.json", fallbackConfig),
    loadRemoteJson("./data/history.json", fallbackHistory),
    loadRemoteJson("./data/latest.json", fallbackLatest)
  ]);
  history = Array.isArray(historyData.items) ? historyData.items : fallbackHistory.items;

  renderHeaderMeta();
  renderSelectOptions();
  renderAllByDate((latestData.record && latestData.record.date) || (history[0] && history[0].date));

  $("dateSelect").addEventListener("change", (e) => renderAllByDate(e.target.value));
  $("calcBtn").addEventListener("click", upsertCurrentInput);
  $("exportBtn").addEventListener("click", exportJson);
  $("resetBtn").addEventListener("click", () => {
    history = Array.isArray(historyData.items) ? [...historyData.items] : [...fallbackHistory.items];
    renderSelectOptions();
    renderAllByDate((latestData.record && latestData.record.date) || (history[0] && history[0].date));
  });
}

document.addEventListener("DOMContentLoaded", init);
