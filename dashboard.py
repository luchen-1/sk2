from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import BACKUPS_DIR, PRICE_HISTORY_DB, PRODUCTS_PATH, REPORTS_DIR, configure_console, ensure_runtime_dirs
from local_collector import handle_collect, is_promo_period
from main import generate_report_no_email, send_alerts_and_generate_report
from notify.email_notifier import annotate_email_decisions, send_test_email
from parsers.price_parser import to_float
from product_io import load_products
from storage.db import get_connection, init_db, insert_price_record
from storage.reporter import label_for, latest_by_product


HOST = "127.0.0.1"
PORT = 8765
EMAIL_REQUIRED_KEYS = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>护肤品价格监控助手</title>
  <style>
    :root {
      --bg: #fbfcfb;
      --panel: #ffffff;
      --ink: #1b2522;
      --muted: #697873;
      --line: #dfe7e3;
      --green: #174d42;
      --green-soft: #e9f5f1;
      --amber-soft: #fff5df;
      --amber: #946b1d;
      --red-soft: #fff0ed;
      --red: #a03a2d;
      --shadow: 0 12px 28px rgba(31, 45, 40, .07);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.55 "Microsoft YaHei", "Segoe UI", sans-serif;
    }
    header {
      background: #f3f7f5;
      border-bottom: 1px solid var(--line);
      padding: 24px 28px 20px;
    }
    header h1 { margin: 0; font-size: 26px; font-weight: 800; }
    header p { margin: 7px 0 0; color: var(--muted); }
    main { max-width: 1220px; margin: 0 auto; padding: 22px; display: grid; gap: 16px; }
    .status-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
    .status-card, .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .status-card { padding: 14px; min-height: 86px; }
    .status-card span { display: block; color: var(--muted); font-size: 13px; }
    .status-card strong { display: block; margin-top: 8px; font-size: 23px; }
    .status-card small { color: var(--muted); }
    .card { padding: 16px; }
    .grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 16px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    h2 { margin: 0 0 12px; font-size: 17px; }
    label { display: block; margin: 10px 0; color: #35443f; font-weight: 700; }
    input, select, textarea {
      width: 100%;
      margin-top: 5px;
      padding: 9px 10px;
      border: 1px solid #cbd7d2;
      border-radius: 6px;
      font: inherit;
      background: #fff;
      color: var(--ink);
    }
    textarea { min-height: 72px; resize: vertical; }
    button {
      border: 1px solid var(--green);
      border-radius: 6px;
      padding: 9px 13px;
      background: var(--green);
      color: #fff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary { background: #eef6f3; color: var(--green); }
    button.warning { background: var(--amber-soft); color: var(--amber); border-color: #e2c77f; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; }
    .info { display: grid; grid-template-columns: 128px 1fr; gap: 6px 10px; margin-top: 10px; }
    .info div:nth-child(odd) { color: var(--muted); }
    .url { word-break: break-all; }
    .result, .notice {
      padding: 12px;
      border-radius: 8px;
      background: #f3f6f5;
      border: 1px solid var(--line);
    }
    .result.hit { background: #eaf8ef; border-color: #9bd5ad; }
    .result.miss { background: var(--amber-soft); border-color: #e4cd8c; }
    .notice.error { background: var(--red-soft); border-color: #e6aaa2; color: var(--red); }
    .muted { color: var(--muted); }
    table { width: 100%; border-collapse: collapse; background: #fff; }
    th, td { padding: 8px 7px; border-bottom: 1px solid #edf2f0; text-align: left; vertical-align: top; }
    th { color: #52615e; font-weight: 800; background: #f8fbfa; }
    .pill { display: inline-block; padding: 2px 7px; border-radius: 999px; background: #e8f1ee; white-space: nowrap; }
    .pill.hit { background: #dff5e7; color: #126b35; }
    .pill.no { background: #f3ece1; color: #795822; }
    .pill.warn { background: var(--red-soft); color: var(--red); }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 430px;
      overflow: auto;
      margin: 0;
      padding: 12px;
      background: #13211d;
      color: #eff8f5;
      border-radius: 8px;
    }
    .check-list { display: grid; gap: 8px; }
    .check-item { display: grid; grid-template-columns: 160px 92px 1fr; gap: 10px; align-items: start; padding: 9px; border: 1px solid #edf2f0; border-radius: 6px; }
    @media (max-width: 980px) { .status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .grid { grid-template-columns: 1fr; } }
    @media (max-width: 640px) { main { padding: 14px; } .row, .check-item { grid-template-columns: 1fr; } .status-grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>护肤品价格监控助手</h1>
    <p>本地录入淘宝/抖音真实到手价，统一生成报告和发送提醒。</p>
  </header>

  <main>
    <section class="status-grid" id="statusCards">
      <div class="status-card"><span>总商品数</span><strong>--</strong></div>
      <div class="status-card"><span>今日已采集</span><strong>--</strong></div>
      <div class="status-card"><span>达到心理价</span><strong>--</strong></div>
      <div class="status-card"><span>今日已提醒</span><strong>--</strong></div>
      <div class="status-card"><span>邮件配置状态</span><strong>--</strong></div>
    </section>

    <section class="grid">
      <div class="card">
        <h2>价格录入区</h2>
        <div class="row">
          <label>平台筛选
            <select id="platformFilter">
              <option value="">全部</option>
              <option value="淘宝">淘宝</option>
              <option value="抖音">抖音</option>
            </select>
          </label>
          <label>商品搜索
            <input id="searchInput" placeholder="输入商品名关键词" />
          </label>
        </div>
        <label>商品
          <select id="productSelect"></select>
        </label>
        <div id="productInfo" class="info"></div>
      </div>

      <div class="card">
        <h2>手动录入</h2>
        <label>当前真实到手价 / 券后价
          <input id="manualPrice" type="number" step="0.01" min="0" placeholder="例如 119.42" />
        </label>
        <label>价格来源
          <select id="priceSource">
            <option value="手动确认价">手动确认价</option>
            <option value="页面明确券后价/到手价">页面明确券后价/到手价</option>
            <option value="根据优惠估算价">根据优惠估算价</option>
            <option value="普通页面价">普通页面价</option>
          </select>
        </label>
        <label>备注，可选
          <textarea id="noteInput" placeholder="例如：手机抖音 App 看到的到手价；测试数据请写“测试”"></textarea>
        </label>
        <button id="saveBtn">保存并判断</button>
      </div>
    </section>

    <section class="card">
      <h2>保存结果区</h2>
      <div id="saveResult" class="result muted">还没有保存本次价格。</div>
    </section>

    <section class="card">
      <h2>操作按钮区</h2>
      <div class="actions">
        <button id="reportBtn">生成报告</button>
        <button id="alertBtn">发送提醒邮件</button>
        <button id="testEmailBtn" class="secondary">测试邮件</button>
        <button id="latestReportBtn" class="secondary">查看最新报告</button>
        <button id="selfCheckBtn" class="secondary">系统自检</button>
        <button id="backupBtn" class="secondary">备份数据库</button>
        <button id="clearBtn" class="warning">清空测试数据</button>
      </div>
      <p id="actionStatus" class="muted"></p>
    </section>

    <section class="card">
      <h2>系统自检</h2>
      <div id="selfCheckResult" class="notice muted">点击“系统自检”查看商品清单、邮件配置、数据库和报告目录状态。</div>
    </section>

    <section class="card">
      <h2>最近采集记录</h2>
      <div id="recentRecords"></div>
    </section>

    <section class="card">
      <h2>最新报告</h2>
      <pre id="latestReport">点击“查看最新报告”查看。</pre>
    </section>
  </main>

  <script>
    let products = [];

    const labelMap = {
      manual_confirmed: "手动确认价",
      explicit_final_price: "页面明确券后价/到手价",
      estimated_after_discount: "根据优惠估算价",
      current_page_price_fallback: "普通页面价",
      high: "高可信",
      medium: "中可信",
      low: "低可信",
      sent: "已发送邮件提醒",
      already_sent_today: "今日已提醒，避免重复发送",
      not_meets_target_price: "未达到心理价",
      stale_data: "数据已过期，未提醒",
      low_confidence: "价格可信度较低，未正式提醒",
      confidence_not_allowed: "价格可信度较低，未正式提醒",
      email_disabled_no_email_mode: "本次只生成报告，未发送邮件",
      email_config_incomplete: "邮件配置不完整，未发送",
      require_final_price_blocks_fallback: "要求明确券后价，普通页面价未提醒",
      missing_final_price: "没有可用价格，未提醒"
    };

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[char]));
    }

    function label(value) {
      if (value === null || value === undefined || value === "") return "暂无数据";
      return labelMap[value] || String(value);
    }

    function money(value) {
      if (value === null || value === undefined || value === "") return "暂无数据";
      const number = Number(value);
      return Number.isFinite(number) ? `${number.toFixed(2)} 元` : String(value);
    }

    function yesNo(value) {
      return value ? "是" : "否";
    }

    function targetText(value) {
      return value ? "已达到心理价" : "未达到心理价";
    }

    function currentProduct() {
      const id = document.getElementById("productSelect").value;
      return products.find((item) => String(item.id) === String(id));
    }

    function filteredProducts() {
      const platform = document.getElementById("platformFilter").value;
      const keyword = document.getElementById("searchInput").value.trim().toLowerCase();
      return products.filter((item) => {
        const platformOk = !platform || item.platform === platform;
        const text = `${item.name} ${item.platform}`.toLowerCase();
        const keywordOk = !keyword || text.includes(keyword);
        return platformOk && keywordOk;
      });
    }

    function renderStatus(status) {
      const cards = document.getElementById("statusCards");
      const emailClass = status.email_config_ok ? "hit" : "warn";
      cards.innerHTML = `
        <div class="status-card"><span>总商品数</span><strong>${status.total_products ?? "--"}</strong></div>
        <div class="status-card"><span>今日已采集</span><strong>${status.today_collected ?? "--"}</strong></div>
        <div class="status-card"><span>达到心理价</span><strong>${status.meets_target ?? "--"}</strong></div>
        <div class="status-card"><span>今日已提醒</span><strong>${status.today_alerted ?? "--"}</strong></div>
        <div class="status-card"><span>邮件配置状态</span><strong><span class="pill ${emailClass}">${escapeHtml(status.email_config_status || "--")}</span></strong></div>
      `;
    }

    function renderProductSelect() {
      const select = document.getElementById("productSelect");
      const current = select.value;
      const list = filteredProducts();
      select.innerHTML = "";
      list.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = `${item.platform} - ${item.name}（心理价 ${money(item.target_price)}）`;
        select.appendChild(option);
      });
      if (list.some((item) => String(item.id) === String(current))) {
        select.value = current;
      }
      renderProductInfo();
    }

    function renderProductInfo() {
      const item = currentProduct();
      const box = document.getElementById("productInfo");
      if (!item) {
        box.innerHTML = "<div>提示</div><div>没有匹配商品</div>";
        return;
      }
      box.innerHTML = `
        <div>商品名</div><div>${escapeHtml(item.name)}</div>
        <div>平台</div><div>${escapeHtml(item.platform)}</div>
        <div>心理价</div><div>${money(item.target_price)}</div>
        <div>原始链接</div><div class="url">${escapeHtml(item.url)}</div>
        <div>最近采集价格</div><div>${money(item.latest_final_price)}</div>
        <div>最近采集时间</div><div>${escapeHtml(item.latest_collected_at || "未采集")}</div>
        <div>最近是否达到心理价</div><div>${item.latest_meets_target_price === null ? "未采集" : targetText(item.latest_meets_target_price)}</div>
      `;
    }

    function renderSaveResult(result) {
      const box = document.getElementById("saveResult");
      if (!result || !result.ok) {
        box.className = "result miss";
        box.textContent = result && result.message ? result.message : "保存失败";
        return;
      }
      box.className = `result ${result.meets_target_price ? "hit" : "miss"}`;
      box.innerHTML = `
        <div><strong>${escapeHtml(result.message || targetText(result.meets_target_price))}</strong></div>
        <div>当前价：${money(result.final_price)}</div>
        <div>心理价：${money(result.target_price)}</div>
        <div>是否达到心理价：${targetText(result.meets_target_price)}</div>
        <div>价格来源：${escapeHtml(result.price_source_label || label(result.price_source))}</div>
        <div>价格可信度：${escapeHtml(result.confidence_label || label(result.confidence))}</div>
        <div>是否可提醒：${result.email_eligible ? "可提醒" : "暂不可提醒"}</div>
        <div>邮件处理原因：${escapeHtml(result.email_skip_reason_label || label(result.email_skip_reason))}</div>
      `;
    }

    function renderRecent(records) {
      const box = document.getElementById("recentRecords");
      if (!records || records.length === 0) {
        box.innerHTML = '<p class="muted">还没有采集记录。</p>';
        return;
      }
      const rows = records.map((record) => `
        <tr>
          <td>${escapeHtml(record.product_name || "")}</td>
          <td>${escapeHtml(record.platform || "")}</td>
          <td>${money(record.final_price)}</td>
          <td>${money(record.target_price)}</td>
          <td><span class="pill ${record.meets_target_price ? "hit" : "no"}">${targetText(record.meets_target_price)}</span></td>
          <td>${escapeHtml(record.price_source_label || label(record.price_source || record.confidence))}</td>
          <td>${escapeHtml(record.collected_at || "")}</td>
          <td>${record.alert_sent ? "已提醒" : "未提醒"}</td>
        </tr>
      `).join("");
      box.innerHTML = `<table><thead><tr><th>商品</th><th>平台</th><th>当前价</th><th>心理价</th><th>判断结果</th><th>价格来源</th><th>采集时间</th><th>邮件状态</th></tr></thead><tbody>${rows}</tbody></table>`;
    }

    function renderSelfCheck(result) {
      const box = document.getElementById("selfCheckResult");
      if (!result || !result.ok) {
        box.className = "notice error";
      } else {
        box.className = "notice";
      }
      const checks = result.checks || [];
      if (!checks.length) {
        box.textContent = result.message || "自检没有返回结果。";
        return;
      }
      box.innerHTML = `<div class="check-list">${checks.map((item) => `
        <div class="check-item">
          <strong>${escapeHtml(item.name)}</strong>
          <span class="pill ${item.ok ? "hit" : "warn"}">${item.ok ? "正常" : "异常"}</span>
          <span>${escapeHtml(item.message || "")}</span>
        </div>
      `).join("")}</div>`;
    }

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.failure_reason || "请求失败");
      return data;
    }

    async function loadStatus() {
      const data = await fetchJson("/api/status");
      renderStatus(data.status || {});
    }

    async function loadProducts() {
      const data = await fetchJson("/api/products");
      products = data.products || [];
      renderProductSelect();
    }

    async function loadRecent() {
      const data = await fetchJson("/api/recent");
      renderRecent(data.records || []);
    }

    async function refreshAll() {
      await loadStatus();
      await loadProducts();
      await loadRecent();
    }

    document.getElementById("platformFilter").addEventListener("change", renderProductSelect);
    document.getElementById("searchInput").addEventListener("input", renderProductSelect);
    document.getElementById("productSelect").addEventListener("change", renderProductInfo);

    document.getElementById("saveBtn").addEventListener("click", async () => {
      const item = currentProduct();
      const price = Number(document.getElementById("manualPrice").value);
      if (!item) return renderSaveResult({ ok: false, message: "请先选择商品" });
      if (!Number.isFinite(price) || price <= 0) return renderSaveResult({ ok: false, message: "请输入有效价格" });
      try {
        const result = await fetchJson("/api/manual-collect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            selected_product_id: item.id,
            manual_price: price,
            user_price_source: document.getElementById("priceSource").value,
            note: document.getElementById("noteInput").value
          })
        });
        renderSaveResult(result);
        await refreshAll();
      } catch (error) {
        renderSaveResult({ ok: false, message: error.message });
      }
    });

    document.getElementById("reportBtn").addEventListener("click", async () => {
      const status = document.getElementById("actionStatus");
      status.textContent = "正在生成报告...";
      try {
        const result = await fetchJson("/api/generate-report", { method: "POST" });
        status.textContent = `报告已生成：${result.report_path}`;
        await loadStatus();
      } catch (error) {
        status.textContent = `生成报告失败：${error.message}`;
      }
    });

    document.getElementById("alertBtn").addEventListener("click", async () => {
      const status = document.getElementById("actionStatus");
      status.textContent = "正在发送提醒邮件...";
      try {
        const result = await fetchJson("/api/send-alerts", { method: "POST" });
        status.textContent = `${result.message} 报告：${result.report_path}`;
        await refreshAll();
      } catch (error) {
        status.textContent = `发送提醒失败：${error.message}`;
      }
    });

    document.getElementById("testEmailBtn").addEventListener("click", async () => {
      const status = document.getElementById("actionStatus");
      const confirmed = confirm("将发送一封测试邮件到 .env 配置的接收邮箱。继续吗？");
      if (!confirmed) return;
      status.textContent = "正在发送测试邮件...";
      try {
        const result = await fetchJson("/api/test-email", { method: "POST" });
        status.textContent = result.message;
      } catch (error) {
        status.textContent = `测试邮件发送失败：${error.message}`;
      }
    });

    document.getElementById("latestReportBtn").addEventListener("click", async () => {

    document.getElementById("latestReportBtn").addEventListener("click", async () => {
      const report = document.getElementById("latestReport");
      try {
        const result = await fetchJson("/api/latest-report");
        report.textContent = result.content || `最新报告：${result.report_path}`;
      } catch (error) {
        report.textContent = `读取最新报告失败：${error.message}`;
      }
    });

    document.getElementById("selfCheckBtn").addEventListener("click", async () => {
      const status = document.getElementById("actionStatus");
      status.textContent = "正在执行系统自检...";
      try {
        const result = await fetchJson("/api/self-check");
        renderSelfCheck(result);
        status.textContent = result.ok ? "系统自检完成。" : "系统自检发现异常，请查看详情。";
        await loadStatus();
      } catch (error) {
        status.textContent = `系统自检失败：${error.message}`;
      }
    });

    document.getElementById("backupBtn").addEventListener("click", async () => {
      const status = document.getElementById("actionStatus");
      status.textContent = "正在备份数据库...";
      try {
        const result = await fetchJson("/api/backup-db", { method: "POST" });
        status.textContent = `数据库已备份：${result.backup_path}`;
      } catch (error) {
        status.textContent = `备份失败：${error.message}`;
      }
    });

    document.getElementById("clearBtn").addEventListener("click", async () => {
      const first = confirm("清理会删除备注中标记为测试/test/dashboard_validation 的采集记录，并同步删除关联提醒记录。建议先备份数据库。继续吗？");
      if (!first) return;
      const second = confirm("请再次确认：不会删除 products.xlsx、.env 或代码，但清理后的测试历史不可直接恢复。确认清理？");
      if (!second) return;
      const status = document.getElementById("actionStatus");
      status.textContent = "正在清理测试数据...";
      try {
        const result = await fetchJson("/api/clear-test-data", { method: "POST" });
        status.textContent = result.message;
        await refreshAll();
      } catch (error) {
        status.textContent = `清理失败：${error.message}`;
      }
    });

    refreshAll().catch((error) => {
      document.getElementById("actionStatus").textContent = `初始化失败：${error.message}`;
    });
  </script>
</body>
</html>
"""


def json_ready(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


def compact_error(exc: BaseException | str, max_length: int = 240) -> str:
    text = str(exc).replace("\r", " ").replace("\n", " ")
    return " ".join(text.split())[:max_length]


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def env_config_presence() -> dict[str, Any]:
    present = {key: bool(os.getenv(key)) for key in EMAIL_REQUIRED_KEYS}
    env_path = PRODUCTS_PATH.parent / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in present and value.strip().strip('"').strip("'"):
                present[key] = True
    missing = [key for key in EMAIL_REQUIRED_KEYS if not present.get(key)]
    return {
        "ok": not missing,
        "missing": missing,
        "status": "正常" if not missing else "缺失字段",
        "message": "正常" if not missing else f"缺失字段：{', '.join(missing)}",
    }


def today_collected_count() -> int:
    today = date.today().isoformat()
    with get_connection() as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT product_id) AS count
            FROM price_history
            WHERE source_type IN ('chrome_extension', 'manual_input')
              AND substr(COALESCE(collected_at, checked_at, created_at), 1, 10) = ?
            """,
            (today,),
        ).fetchone()
    return int(row["count"] or 0) if row else 0


def today_alerted_count() -> int:
    today = date.today().isoformat()
    with get_connection() as conn:
        init_db(conn)
        row = conn.execute(
            "SELECT COUNT(DISTINCT product_id) AS count FROM sent_alerts WHERE alert_date = ?",
            (today,),
        ).fetchone()
    return int(row["count"] or 0) if row else 0


def status_payload() -> dict[str, Any]:
    products = load_products(PRODUCTS_PATH)
    records = latest_by_product(products)
    email_status = env_config_presence()
    return json_ready(
        {
            "ok": True,
            "status": {
                "total_products": len(products),
                "today_collected": today_collected_count(),
                "meets_target": sum(1 for record in records if record.get("meets_target_price")),
                "today_alerted": today_alerted_count(),
                "email_config_ok": email_status["ok"],
                "email_config_status": email_status["status"],
            },
        }
    )


def latest_products_payload() -> list[dict]:
    products = load_products(PRODUCTS_PATH)
    records = latest_by_product(products)
    latest_by_id = {str(record.get("product_id") or ""): record for record in records if record.get("collected")}
    payload: list[dict] = []
    for product in products.to_dict("records"):
        product_id = str(product.get("id") or "")
        latest = latest_by_id.get(product_id, {})
        payload.append(
            {
                "id": product_id,
                "name": product.get("name"),
                "platform": product.get("platform"),
                "target_price": product.get("target_price"),
                "url": product.get("url"),
                "item_id": product.get("item_id"),
                "normalized_url": product.get("normalized_url"),
                "latest_final_price": latest.get("final_price"),
                "latest_collected_at": latest.get("collected_at"),
                "latest_meets_target_price": latest.get("meets_target_price") if latest else None,
            }
        )
    return json_ready(payload)


def recent_records(limit: int = 10) -> list[dict]:
    with get_connection() as conn:
        init_db(conn)
        rows = conn.execute(
            """
            SELECT product_name, name, platform, final_price, target_price, meets_target_price,
                   price_source, confidence, collected_at, alert_sent, source_type
            FROM price_history
            WHERE source_type IN ('chrome_extension', 'manual_input')
            ORDER BY COALESCE(collected_at, checked_at, created_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return json_ready(
        [
            {
                "product_name": row["product_name"] or row["name"],
                "platform": row["platform"],
                "final_price": row["final_price"],
                "target_price": row["target_price"],
                "meets_target_price": bool(row["meets_target_price"]),
                "price_source": row["price_source"],
                "price_source_label": label_for(row["price_source"] or row["confidence"]),
                "confidence": row["confidence"],
                "collected_at": row["collected_at"],
                "alert_sent": bool(row["alert_sent"]),
                "source_type": row["source_type"],
            }
            for row in rows
        ]
    )


def product_by_id(product_id: str) -> dict | None:
    products = load_products(PRODUCTS_PATH)
    matched = products[products["id"].astype(str) == str(product_id)]
    if matched.empty:
        return None
    return matched.iloc[0].to_dict()


def handle_manual_collect(payload: dict[str, Any]) -> dict[str, Any]:
    product = product_by_id(str(payload.get("selected_product_id") or ""))
    if product is None:
        return {"ok": False, "failure_reason": "product_not_found", "message": "未找到选中的商品。"}
    manual_price = to_float(payload.get("manual_price"))
    if manual_price is None:
        return {"ok": False, "failure_reason": "invalid_manual_price", "message": "请输入有效价格。"}

    now = datetime.now().isoformat(timespec="seconds")
    target_price = to_float(product.get("target_price"))
    meets_target = target_price is not None and manual_price <= target_price
    note = str(payload.get("note") or "").strip()
    user_price_source = str(payload.get("user_price_source") or "").strip()
    raw_price_text = f"manual_price={manual_price}"
    if user_price_source:
        raw_price_text += f"; user_price_source={user_price_source}"
    if note:
        raw_price_text += f"; note={note}"

    record = {
        "product_id": str(product.get("id") or ""),
        "product_name": product.get("name") or "",
        "category": product.get("category") or "",
        "brand": product.get("brand") or "",
        "platform": product.get("platform") or "",
        "url": product.get("url") or "",
        "normalized_url": product.get("normalized_url") or "",
        "item_id": product.get("item_id") or "",
        "page_title": "",
        "current_price": manual_price,
        "final_price": manual_price,
        "target_price": target_price,
        "price_source": "manual_confirmed",
        "confidence": "manual_confirmed",
        "meets_target_price": meets_target,
        "require_final_price": bool(product.get("require_final_price")),
        "is_promo_period": is_promo_period(product),
        "promo_name": product.get("promo_name") or "",
        "raw_price_text": raw_price_text,
        "discount_text": f"用户选择来源：{user_price_source}" if user_price_source else "",
        "selected_text": note,
        "manual_price": manual_price,
        "source_type": "manual_input",
        "failure_reason": None,
        "error_message": None,
        "collected_at": now,
        "created_at": now,
        "checked_at": now,
        "stale": False,
        "alert_sent": False,
    }
    with get_connection() as conn:
        init_db(conn)
        insert_price_record(conn, record)
    annotate_email_decisions([record], email_enabled=True)
    message = "已达到心理价" if meets_target else "未达到心理价"
    return json_ready(
        {
            "ok": True,
            "product_name": record["product_name"],
            "platform": record["platform"],
            "final_price": record["final_price"],
            "target_price": record["target_price"],
            "meets_target_price": record["meets_target_price"],
            "price_source": record["price_source"],
            "price_source_label": label_for(record["price_source"]),
            "confidence": record["confidence"],
            "confidence_label": label_for(record["confidence"]),
            "email_eligible": record.get("email_eligible"),
            "email_skip_reason": record.get("email_skip_reason"),
            "email_skip_reason_label": label_for(record.get("email_skip_reason")),
            "message": message,
        }
    )


def report_payload(send_email: bool) -> dict[str, Any]:
    result = send_alerts_and_generate_report() if send_email else generate_report_no_email()
    target_decisions = [
        {
            "product_name": record.get("product_name") or record.get("name"),
            "platform": record.get("platform"),
            "email_eligible": record.get("email_eligible"),
            "email_skip_reason": record.get("email_skip_reason"),
            "email_skip_reason_label": label_for(record.get("email_skip_reason")),
            "alert_sent": record.get("alert_sent"),
        }
        for record in result["records"]
        if record.get("meets_target_price")
    ]
    if send_email:
        sent_count = result.get("sent_count", 0)
        if sent_count:
            message = f"已发送 {sent_count} 封提醒邮件。"
        elif target_decisions:
            reasons = "；".join(
                f"{item['platform']} - {item['product_name']}：{item.get('email_skip_reason_label') or '未发送'}"
                for item in target_decisions
            )
            message = f"未发送新邮件：{reasons}"
        else:
            message = "没有达到心理价的商品需要提醒。"
    else:
        message = "报告已生成，未发送邮件。"
    return json_ready(
        {
            "ok": True,
            "sent_count": result.get("sent_count", 0),
            "report_path": str(result["report_path"]),
            "summary": result["summary"],
            "message": message,
            "target_decisions": target_decisions,
        }
    )


def latest_report_payload() -> dict[str, Any]:
    reports = sorted(REPORTS_DIR.glob("price_check_report_*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports:
        return {"ok": False, "failure_reason": "report_not_found", "message": "还没有生成报告。"}
    path = reports[0]
    return {"ok": True, "report_path": str(path), "content": path.read_text(encoding="utf-8")}


def test_email_payload() -> dict[str, Any]:
    ok = send_test_email()
    if ok:
        return {"ok": True, "message": "测试邮件已发送，请检查收件箱。"}
    return {"ok": False, "failure_reason": "test_email_failed", "message": "测试邮件发送失败，请检查邮箱配置、授权码、网络和 SMTP 设置。"}


def product_check() -> dict[str, Any]:
    if not PRODUCTS_PATH.exists():
        return {"name": "商品清单", "ok": False, "message": "products.xlsx 不存在。"}
    try:
        products = load_products(PRODUCTS_PATH)
    except Exception as exc:
        return {"name": "商品清单", "ok": False, "message": f"products.xlsx 加载失败：{compact_error(exc)}"}
    counts = products["platform"].value_counts().to_dict()
    ok = len(products) == 22 and int(counts.get("淘宝", 0)) == 11 and int(counts.get("抖音", 0)) == 11
    message = f"已加载 {len(products)} 条，淘宝 {int(counts.get('淘宝', 0))}，抖音 {int(counts.get('抖音', 0))}。"
    return {"name": "商品清单", "ok": ok, "message": message}


def database_check() -> dict[str, Any]:
    try:
        with get_connection() as conn:
            init_db(conn)
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        return {"name": "数据库", "ok": False, "message": f"price_history.db 连接失败：{compact_error(exc)}"}
    return {"name": "数据库", "ok": True, "message": "price_history.db 可连接。"}


def reports_dir_check() -> dict[str, Any]:
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        probe = REPORTS_DIR / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        return {"name": "报告目录", "ok": False, "message": f"reports/ 不可写：{compact_error(exc)}"}
    return {"name": "报告目录", "ok": True, "message": "reports/ 存在且可写。"}


def email_check() -> dict[str, Any]:
    status = env_config_presence()
    return {"name": "邮件配置", "ok": status["ok"], "message": status["message"]}


def report_generation_check() -> dict[str, Any]:
    try:
        result = generate_report_no_email()
    except Exception as exc:
        return {"name": "报告生成", "ok": False, "message": f"报告生成失败：{compact_error(exc)}"}
    return {"name": "报告生成", "ok": True, "message": f"可正常生成报告：{result['report_path']}"}


def self_check_payload() -> dict[str, Any]:
    checks = [product_check(), email_check(), database_check(), reports_dir_check(), report_generation_check()]
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def backup_db_payload() -> dict[str, Any]:
    ensure_runtime_dirs()
    if not PRICE_HISTORY_DB.exists():
        return {"ok": False, "failure_reason": "database_not_found", "message": "price_history.db 不存在，无法备份。"}
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUPS_DIR / f"price_history_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(PRICE_HISTORY_DB, backup_path)
    return {"ok": True, "backup_path": str(backup_path), "message": "数据库备份完成。"}


def clear_test_data_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    force_all = truthy(payload.get("confirm_clear_all")) and str(payload.get("confirm_text") or "") == "清空全部历史记录"
    with get_connection() as conn:
        init_db(conn)
        if force_all:
            deleted_alerts = conn.execute("DELETE FROM sent_alerts").rowcount
            deleted_history = conn.execute("DELETE FROM price_history").rowcount
            conn.commit()
            return {
                "ok": True,
                "cleared_price_history": deleted_history,
                "cleared_alerts": deleted_alerts,
                "message": f"已清空全部历史记录 {deleted_history} 条、提醒记录 {deleted_alerts} 条。",
            }

        rows = conn.execute(
            """
            SELECT id
            FROM price_history
            WHERE source_type = 'manual_input'
              AND (
                lower(COALESCE(selected_text, '')) LIKE '%test%'
                OR COALESCE(selected_text, '') LIKE '%测试%'
                OR COALESCE(selected_text, '') LIKE '%dashboard_validation%'
                OR lower(COALESCE(raw_price_text, '')) LIKE '%test%'
                OR COALESCE(raw_price_text, '') LIKE '%测试%'
                OR COALESCE(raw_price_text, '') LIKE '%dashboard_validation%'
              )
            """
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        if not ids:
            return {
                "ok": True,
                "cleared_price_history": 0,
                "cleared_alerts": 0,
                "message": "当前无法区分测试数据和真实数据，请先备份数据库。没有清理任何历史记录。",
            }
        placeholders = ", ".join("?" for _ in ids)
        deleted_alerts = conn.execute(f"DELETE FROM sent_alerts WHERE price_history_id IN ({placeholders})", ids).rowcount
        deleted_history = conn.execute(f"DELETE FROM price_history WHERE id IN ({placeholders})", ids).rowcount
        conn.commit()
    return {
        "ok": True,
        "cleared_price_history": deleted_history,
        "cleared_alerts": deleted_alerts,
        "message": f"已清理测试采集记录 {deleted_history} 条、关联提醒记录 {deleted_alerts} 条。",
    }


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "SkincareDashboard/2.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(json_ready(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_OPTIONS(self) -> None:
        self.send_json(200, {"ok": True})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/":
                self.send_html(HTML)
            elif path == "/health":
                self.send_json(200, {"ok": True})
            elif path == "/api/status":
                self.send_json(200, status_payload())
            elif path == "/api/products":
                self.send_json(200, {"ok": True, "products": latest_products_payload()})
            elif path == "/api/recent":
                self.send_json(200, {"ok": True, "records": recent_records()})
            elif path == "/api/self-check":
                payload = self_check_payload()
                self.send_json(200, payload)
            elif path == "/api/latest-report":
                payload = latest_report_payload()
                self.send_json(200 if payload.get("ok") else 404, payload)
            else:
                self.send_json(404, {"ok": False, "message": "Not found"})
        except Exception as exc:
            self.send_json(500, {"ok": False, "message": compact_error(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json_body()
            if path == "/api/collect":
                result = handle_collect(payload)
                self.send_json(200 if result.get("ok") else 400, result)
            elif path == "/api/manual-collect":
                result = handle_manual_collect(payload)
                self.send_json(200 if result.get("ok") else 400, result)
            elif path == "/api/generate-report":
                self.send_json(200, report_payload(send_email=False))
            elif path == "/api/send-alerts":
                self.send_json(200, report_payload(send_email=True))
            elif path == "/api/test-email":
                result = test_email_payload()
                self.send_json(200 if result.get("ok") else 400, result)
            elif path == "/api/backup-db":
                result = backup_db_payload()
                self.send_json(200 if result.get("ok") else 400, result)
            elif path == "/api/clear-test-data":
                self.send_json(200, clear_test_data_payload(payload))
            else:
                self.send_json(404, {"ok": False, "message": "Not found"})
        except Exception as exc:
            self.send_json(500, {"ok": False, "message": compact_error(exc)})


def run_server(host: str = HOST, port: int = PORT) -> None:
    ensure_runtime_dirs()
    try:
        server = ThreadingHTTPServer((host, port), DashboardHandler)
    except OSError as exc:
        print(f"端口 {port} 已被占用，无法启动价格助手。请关闭正在占用 8765 的程序后再试。")
        raise SystemExit(1) from exc
    print(f"护肤品价格监控助手已启动: http://{host}:{port}")
    print("请在浏览器打开上面的地址，按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("价格助手已停止。")
    finally:
        server.server_close()


def main() -> None:
    configure_console()
    parser = argparse.ArgumentParser(description="Local skincare price dashboard.")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
