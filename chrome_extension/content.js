(function () {
  const priceRegex = /[¥￥]\s*(\d+(?:\.\d{1,2})?|\?{2,3})(?:\s*起)?|(?:到手价|券后价|预估到手|优惠后|实付|活动价)[^\d¥￥]{0,18}(\d+(?:\.\d{1,2})?)/gi;

  function compact(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function collectCandidates(text) {
    const candidates = [];
    const seen = new Set();
    let match;
    while ((match = priceRegex.exec(text || "")) !== null && candidates.length < 40) {
      const raw = compact(match[0]);
      if (!raw || seen.has(raw)) {
        continue;
      }
      seen.add(raw);
      const start = Math.max(0, match.index - 24);
      const end = Math.min(text.length, match.index + raw.length + 24);
      candidates.push({
        text: raw,
        context: compact(text.slice(start, end)),
        value: raw
      });
    }
    return candidates;
  }

  function localTimestamp() {
    const date = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  window.__skincareCollectPage = function () {
    const visibleText = document.body ? document.body.innerText || "" : "";
    const selectedText = window.getSelection ? String(window.getSelection()) : "";
    return {
      platform: "",
      url: location.href,
      page_title: document.title || "",
      visible_text: visibleText,
      selected_text: selectedText,
      price_candidates: collectCandidates(`${selectedText}\n${visibleText}`),
      collected_at: localTimestamp()
    };
  };

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message && message.type === "SKINCARE_COLLECT_PAGE") {
      sendResponse(window.__skincareCollectPage());
    }
    return true;
  });
})();
