const LOCAL_ENDPOINT = "http://127.0.0.1:8765/api/collect";

let currentTab = null;
let pageData = null;

const pageUrlEl = document.getElementById("pageUrl");
const candidatesEl = document.getElementById("candidates");
const manualPriceEl = document.getElementById("manualPrice");
const priceSourceEl = document.getElementById("priceSource");
const resultEl = document.getElementById("result");
const readPageBtn = document.getElementById("readPage");
const submitBtn = document.getElementById("submitData");

function localTimestamp() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function shortUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.host}${parsed.pathname}`.slice(0, 90);
  } catch (error) {
    return String(url || "").slice(0, 90);
  }
}

function detectPlatform(url) {
  const lower = String(url || "").toLowerCase();
  if (lower.includes("taobao.com") || lower.includes("tmall.com") || lower.includes("tmall.hk")) {
    return "淘宝";
  }
  if (lower.includes("douyin.com") || lower.includes("jinritemai.com")) {
    return "抖音";
  }
  return "";
}

function renderCandidates(candidates) {
  candidatesEl.innerHTML = "";
  if (!candidates || candidates.length === 0) {
    candidatesEl.className = "candidates empty";
    candidatesEl.textContent = "未识别到价格候选，可手动输入。";
    return;
  }
  candidatesEl.className = "candidates";
  candidates.slice(0, 20).forEach((candidate) => {
    const row = document.createElement("div");
    row.className = "candidate";
    const text = document.createElement("span");
    text.textContent = candidate.text || candidate.value || "";
    text.title = candidate.context || "";
    const button = document.createElement("button");
    button.textContent = "填入";
    button.addEventListener("click", () => {
      const value = String(candidate.value || candidate.text || "").match(/\d+(?:\.\d{1,2})?/);
      if (value) {
        manualPriceEl.value = value[0];
      }
    });
    row.append(text, button);
    candidatesEl.append(row);
  });
}

function showResult(payload) {
  resultEl.textContent = [
    `匹配商品名: ${payload.product_name || ""}`,
    `平台: ${payload.platform || ""}`,
    `当前价: ${payload.current_price ?? ""}`,
    `最终监控价: ${payload.final_price ?? ""}`,
    `心理价: ${payload.target_price ?? ""}`,
    `是否达到心理价: ${payload.meets_target_price ?? ""}`,
    `价格来源: ${payload.price_source || ""}`,
    `置信度: ${payload.confidence || ""}`,
    `提醒状态: ${payload.alert_sent ? "已提醒" : "未提醒"}`,
    `错误信息: ${payload.failure_reason || payload.error_message || ""}`,
    `消息: ${payload.message || ""}`
  ].join("\n");
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function collectCurrentPage() {
  currentTab = await getActiveTab();
  if (!currentTab || !currentTab.id) {
    throw new Error("未找到当前标签页");
  }
  try {
    return await chrome.tabs.sendMessage(currentTab.id, { type: "SKINCARE_COLLECT_PAGE" });
  } catch (error) {
    await chrome.scripting.executeScript({ target: { tabId: currentTab.id }, files: ["content.js"] });
    return await chrome.tabs.sendMessage(currentTab.id, { type: "SKINCARE_COLLECT_PAGE" });
  }
}

readPageBtn.addEventListener("click", async () => {
  readPageBtn.disabled = true;
  resultEl.textContent = "正在读取当前页...";
  try {
    pageData = await collectCurrentPage();
    pageData.platform = detectPlatform(pageData.url);
    pageUrlEl.textContent = shortUrl(pageData.url);
    renderCandidates(pageData.price_candidates);
    resultEl.textContent = "已读取当前页，可以确认价格后提交。";
  } catch (error) {
    resultEl.textContent = `读取失败: ${error.message}`;
  } finally {
    readPageBtn.disabled = false;
  }
});

submitBtn.addEventListener("click", async () => {
  submitBtn.disabled = true;
  resultEl.textContent = "正在提交到本地服务...";
  try {
    if (!pageData) {
      pageData = await collectCurrentPage();
      pageData.platform = detectPlatform(pageData.url);
    }
    const payload = {
      ...pageData,
      platform: detectPlatform(pageData.url),
      manual_price: manualPriceEl.value ? Number(manualPriceEl.value) : null,
      user_price_source: priceSourceEl.value,
      collected_at: localTimestamp()
    };
    const response = await fetch(LOCAL_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    showResult(result);
  } catch (error) {
    resultEl.textContent = `提交失败: ${error.message}\n请确认 local_collector.py 已启动。`;
  } finally {
    submitBtn.disabled = false;
  }
});

document.addEventListener("DOMContentLoaded", async () => {
  currentTab = await getActiveTab();
  pageUrlEl.textContent = shortUrl(currentTab && currentTab.url);
});
