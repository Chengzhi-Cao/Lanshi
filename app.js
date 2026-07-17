const AGE_KEY = "lanshiAgeConfirmed";

const state = {
  videos: [],
  visible: 36,
  config: null,
  currentOrder: null,
  currentVideo: null,
  pollTimer: null,
};

const elements = {
  ageGate: document.querySelector("#ageGate"),
  ageConfirm: document.querySelector("#ageConfirm"),
  catalogGrid: document.querySelector("#catalogGrid"),
  cardTemplate: document.querySelector("#cardTemplate"),
  searchInput: document.querySelector("#searchInput"),
  seriesFilter: document.querySelector("#seriesFilter"),
  sortSelect: document.querySelector("#sortSelect"),
  loadMoreButton: document.querySelector("#loadMoreButton"),
  refreshButton: document.querySelector("#refreshButton"),
  videoCount: document.querySelector("#videoCount"),
  purchaseCount: document.querySelector("#purchaseCount"),
  resultSummary: document.querySelector("#resultSummary"),
  paymentNotice: document.querySelector("#paymentNotice"),
  paymentModal: document.querySelector("#paymentModal"),
  paymentTitle: document.querySelector("#paymentTitle"),
  paymentSubtitle: document.querySelector("#paymentSubtitle"),
  paymentAmount: document.querySelector("#paymentAmount"),
  paymentHelp: document.querySelector("#paymentHelp"),
  orderStatus: document.querySelector("#orderStatus"),
  mockPaidButton: document.querySelector("#mockPaidButton"),
  downloadAfterPayButton: document.querySelector("#downloadAfterPayButton"),
  payImage: document.querySelector("#payImage"),
  qrCanvas: document.querySelector("#qrCanvas"),
};

function formatDate(timestamp) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(timestamp * 1000));
}

function activeVideos() {
  const keyword = elements.searchInput.value.trim().toLowerCase();
  const series = elements.seriesFilter.value;
  const sort = elements.sortSelect.value;

  const filtered = state.videos.filter((video) => {
    const matchesKeyword =
      !keyword ||
      video.title.toLowerCase().includes(keyword) ||
      video.fileName.toLowerCase().includes(keyword) ||
      video.series.toLowerCase().includes(keyword);
    return matchesKeyword && (!series || video.series === series);
  });

  filtered.sort((a, b) => {
    if (sort === "newest") return b.updatedAt - a.updatedAt;
    if (sort === "sizeHigh") return b.size - a.size;
    return a.title.localeCompare(b.title, "zh-CN");
  });

  return filtered;
}

function renderSeriesFilter() {
  const current = elements.seriesFilter.value;
  const seriesList = [...new Set(state.videos.map((video) => video.series))].sort((a, b) =>
    a.localeCompare(b, "zh-CN"),
  );
  elements.seriesFilter.innerHTML = '<option value="">全部系列</option>';
  for (const series of seriesList) {
    const option = document.createElement("option");
    option.value = series;
    option.textContent = series;
    elements.seriesFilter.append(option);
  }
  elements.seriesFilter.value = current;
}

function updateStats(videos) {
  const purchased = state.videos.filter((video) => video.purchased).length;
  elements.videoCount.textContent = `${state.videos.length} 个素材`;
  elements.purchaseCount.textContent = `${purchased} 已购买`;
  elements.resultSummary.textContent = `当前显示 ${Math.min(videos.length, state.visible)} / ${videos.length} 个视频`;
}

function renderCatalog() {
  const videos = activeVideos();
  const visibleVideos = videos.slice(0, state.visible);
  elements.catalogGrid.innerHTML = "";

  if (!visibleVideos.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "没有找到匹配的视频";
    elements.catalogGrid.append(empty);
  }

  for (const video of visibleVideos) {
    const fragment = elements.cardTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".video-card");
    const image = fragment.querySelector(".thumb");
    const fallback = fragment.querySelector(".thumb-fallback");
    const badge = fragment.querySelector(".lock-badge");
    const title = fragment.querySelector("h3");
    const series = fragment.querySelector(".series");
    const size = fragment.querySelector(".size");
    const price = fragment.querySelector(".price");
    const action = fragment.querySelector(".card-action");

    card.classList.toggle("unlocked", video.purchased);
    image.src = video.thumb;
    image.alt = `${video.title} 预览图`;
    fallback.dataset.title = video.title;
    image.addEventListener("error", () => image.classList.add("is-hidden"), { once: true });
    badge.textContent = video.purchased ? "已购买" : "未购买";
    title.textContent = video.title;
    series.textContent = video.series;
    size.textContent = `${video.sizeLabel} · ${formatDate(video.updatedAt)}`;
    price.textContent = video.priceLabel;
    action.textContent = video.purchased ? "下载视频" : "微信购买";
    action.addEventListener("click", () => {
      if (video.purchased) {
        downloadVideo(video);
      } else {
        startPayment(video);
      }
    });

    elements.catalogGrid.append(fragment);
  }

  elements.loadMoreButton.hidden = videos.length <= state.visible;
  updateStats(videos);
}

async function loadConfig() {
  const response = await fetch("/api/config");
  state.config = await response.json();
  const mode = state.config.paymentMode;
  if (mode === "wechat" && state.config.wechatConfigured) {
    elements.paymentNotice.textContent = "已启用微信 Native 支付。付款成功依赖服务器回调确认。";
  } else if (mode === "manual" && state.config.manualPayReady) {
    elements.paymentNotice.textContent = "当前使用 pay.jpg 作为微信收款码。用户扫码付款后，由卖家后台确认收款并开放下载。";
  } else {
    elements.paymentNotice.textContent = "当前为本地支付测试模式。放入 pay.jpg 可显示微信收款码，配置微信商户参数后可切换正式支付。";
  }
}

async function loadVideos() {
  const response = await fetch("/api/videos");
  if (!response.ok) throw new Error("无法读取视频列表");
  const payload = await response.json();
  state.videos = payload.videos;
  renderSeriesFilter();
  renderCatalog();
}

async function refreshVideos() {
  await fetch("/api/refresh", { method: "POST" });
  await loadVideos();
}

async function startPayment(video) {
  state.currentVideo = video;
  elements.paymentTitle.textContent = video.title;
  elements.paymentSubtitle.textContent = "正在创建订单";
  elements.paymentAmount.textContent = video.priceLabel;
  elements.orderStatus.textContent = "正在创建订单...";
  elements.mockPaidButton.hidden = true;
  elements.downloadAfterPayButton.hidden = true;
  hidePayImage();
  drawFallbackQr("loading");
  showModal(elements.paymentModal);

  const response = await fetch("/api/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ videoId: video.id }),
  });
  const order = await response.json();
  if (!response.ok) {
    elements.orderStatus.textContent = order.detail || order.error || "创建订单失败";
    return;
  }

  state.currentOrder = order;
  elements.paymentSubtitle.textContent = `订单号：${order.orderId}`;
  elements.orderStatus.textContent = "等待微信扫码支付";
  elements.paymentHelp.textContent =
    order.paymentMode === "manual"
      ? "请用微信扫码支付 5 元。付款备注可填写订单号，卖家确认收款后会自动解锁下载。"
      : order.paymentMode === "mock"
        ? "本地演示二维码不会真实扣款。点击“本机确认已收款”即可测试购买后下载。"
        : "请使用微信扫码支付，支付回调成功后会解锁下载。";
  elements.mockPaidButton.hidden = !["mock", "wechat-mock"].includes(order.paymentMode);
  if (order.paymentMode === "manual") {
    showPayImage(order.codeUrl);
  } else {
    await drawQr(order.codeUrl);
  }
  startPolling(order.orderId);
}

function startPolling(orderId) {
  stopPolling();
  state.pollTimer = window.setInterval(async () => {
    const response = await fetch(`/api/orders/${orderId}`);
    if (!response.ok) return;
    const payload = await response.json();
    if (payload.status === "paid") {
      elements.orderStatus.textContent = "支付成功，可以下载";
      elements.downloadAfterPayButton.hidden = false;
      stopPolling();
      await loadVideos();
    }
  }, 2000);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function confirmMockPayment() {
  if (!state.currentOrder) return;
  elements.orderStatus.textContent = "正在确认支付...";
  const response = await fetch(`/api/orders/${state.currentOrder.orderId}/confirm-paid`, { method: "POST" });
  const payload = await response.json();
  if (!response.ok) {
    elements.orderStatus.textContent = payload.error || "确认失败";
    return;
  }
  elements.orderStatus.textContent = "支付成功，可以下载";
  elements.downloadAfterPayButton.hidden = false;
  stopPolling();
  await loadVideos();
}

function downloadVideo(video) {
  window.location.href = video.downloadUrl || `/api/videos/${video.id}/download`;
}

function downloadCurrentVideo() {
  const video = state.videos.find((item) => state.currentVideo && item.id === state.currentVideo.id) || state.currentVideo;
  if (video) downloadVideo(video);
}

async function drawQr(text) {
  hidePayImage();
  if (window.QRCode && window.QRCode.toCanvas) {
    await window.QRCode.toCanvas(elements.qrCanvas, text, {
      width: 220,
      margin: 1,
      color: { dark: "#111111", light: "#ffffff" },
    });
    return;
  }
  drawFallbackQr(text);
}

function drawFallbackQr(text) {
  hidePayImage();
  const canvas = elements.qrCanvas;
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  const cells = 21;
  const cell = Math.floor(size / cells);
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = "#111";

  function block(x, y, w, h) {
    ctx.fillRect(x * cell, y * cell, w * cell, h * cell);
  }
  function finder(x, y) {
    block(x, y, 7, 7);
    ctx.fillStyle = "#fff";
    block(x + 1, y + 1, 5, 5);
    ctx.fillStyle = "#111";
    block(x + 2, y + 2, 3, 3);
  }
  finder(1, 1);
  finder(13, 1);
  finder(1, 13);
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  for (let y = 1; y < 20; y += 1) {
    for (let x = 1; x < 20; x += 1) {
      const protectedCell = (x < 8 && y < 8) || (x > 12 && y < 8) || (x < 8 && y > 12);
      if (!protectedCell && (hash + x * 17 + y * 29 + x * y * 7) % 5 < 2) block(x, y, 1, 1);
    }
  }
}

function showPayImage(src) {
  elements.qrCanvas.hidden = true;
  elements.payImage.hidden = false;
  elements.payImage.src = src || "/pay.jpg";
}

function hidePayImage() {
  elements.payImage.hidden = true;
  elements.qrCanvas.hidden = false;
}

function showModal(modal) {
  modal.hidden = false;
}

function closeModal(modal) {
  modal.hidden = true;
  if (modal === elements.paymentModal) stopPolling();
}

function setupAgeGate() {
  if (localStorage.getItem(AGE_KEY) === "yes") {
    elements.ageGate.hidden = true;
  }
  elements.ageConfirm.addEventListener("click", () => {
    localStorage.setItem(AGE_KEY, "yes");
    elements.ageGate.hidden = true;
  });
}

function setupEvents() {
  for (const input of [elements.searchInput, elements.seriesFilter, elements.sortSelect]) {
    input.addEventListener("input", () => {
      state.visible = 36;
      renderCatalog();
    });
  }
  elements.loadMoreButton.addEventListener("click", () => {
    state.visible += 36;
    renderCatalog();
  });
  elements.refreshButton.addEventListener("click", refreshVideos);
  elements.mockPaidButton.addEventListener("click", confirmMockPayment);
  elements.downloadAfterPayButton.addEventListener("click", downloadCurrentVideo);
  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(document.querySelector(`#${button.dataset.close}`)));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal(elements.paymentModal);
  });
}

async function init() {
  setupAgeGate();
  setupEvents();
  await loadConfig();
  await loadVideos();
}

init().catch((error) => {
  elements.resultSummary.textContent = error.message;
});
