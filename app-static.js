const STORAGE_KEY = "lanshiUnlockedVideos";
const AGE_KEY = "lanshiAgeConfirmed";

const state = {
  videos: Array.isArray(window.VIDEO_CATALOG) ? window.VIDEO_CATALOG : [],
  visible: 36,
  unlocked: new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]")),
  currentVideo: null,
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
  resetButton: document.querySelector("#resetButton"),
  videoCount: document.querySelector("#videoCount"),
  unlockCount: document.querySelector("#unlockCount"),
  resultSummary: document.querySelector("#resultSummary"),
  paymentModal: document.querySelector("#paymentModal"),
  paymentTitle: document.querySelector("#paymentTitle"),
  paymentSubtitle: document.querySelector("#paymentSubtitle"),
  paymentAmount: document.querySelector("#paymentAmount"),
  mockPaidButton: document.querySelector("#mockPaidButton"),
  qrCanvas: document.querySelector("#qrCanvas"),
  playerModal: document.querySelector("#playerModal"),
  playerTitle: document.querySelector("#playerTitle"),
  playerHint: document.querySelector("#playerHint"),
  videoPlayer: document.querySelector("#videoPlayer"),
};

function saveUnlocked() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...state.unlocked]));
}

function formatDate(timestamp) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(timestamp * 1000));
}

function isUnlocked(video) {
  return state.unlocked.has(video.id);
}

function videoUrl(video) {
  return `../${encodeURIComponent(video.fileName)}`;
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
    const matchesSeries = !series || video.series === series;
    return matchesKeyword && matchesSeries;
  });

  filtered.sort((a, b) => {
    if (sort === "newest") return b.updatedAt - a.updatedAt;
    if (sort === "priceHigh") return b.priceCents - a.priceCents;
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
  elements.videoCount.textContent = `${state.videos.length} 个素材`;
  elements.unlockCount.textContent = `${state.unlocked.size} 已解锁`;
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
    const unlocked = isUnlocked(video);

    card.classList.toggle("unlocked", unlocked);
    image.src = video.thumb;
    image.alt = `${video.title} 预览图`;
    fallback.dataset.title = video.title;
    image.addEventListener("error", () => image.classList.add("is-hidden"), { once: true });
    badge.textContent = unlocked ? "已解锁" : "未解锁";
    title.textContent = video.title;
    series.textContent = video.series;
    size.textContent = `${video.sizeLabel} · ${formatDate(video.updatedAt)}`;
    price.textContent = unlocked ? "已购买" : video.priceLabel;
    action.textContent = unlocked ? "立即播放" : "微信支付";
    action.addEventListener("click", () => {
      if (unlocked) {
        openPlayer(video);
      } else {
        startPayment(video);
      }
    });

    elements.catalogGrid.append(fragment);
  }

  elements.loadMoreButton.hidden = videos.length <= state.visible;
  updateStats(videos);
}

function startPayment(video) {
  state.currentVideo = video;
  const orderId = `LS${Date.now().toString(36).toUpperCase()}${video.id.slice(0, 4).toUpperCase()}`;
  elements.paymentTitle.textContent = video.title;
  elements.paymentSubtitle.textContent = `演示订单：${orderId}`;
  elements.paymentAmount.textContent = video.priceLabel;
  drawPseudoQr(`weixin://wxpay/lanshi-preview?order=${orderId}&video=${video.id}`);
  showModal(elements.paymentModal);
}

function confirmPayment() {
  if (!state.currentVideo) return;
  state.unlocked.add(state.currentVideo.id);
  saveUnlocked();
  closeModal(elements.paymentModal);
  renderCatalog();
  openPlayer(state.currentVideo);
}

function openPlayer(video) {
  elements.playerTitle.textContent = video.title;
  elements.playerHint.textContent =
    video.ext === ".mp4" || video.ext === ".mov"
      ? "静态预览会直接读取本地视频文件。"
      : "该格式可能不被浏览器直接播放，可换成 mp4 或用正式服务端转码。";
  elements.videoPlayer.src = videoUrl(video);
  elements.videoPlayer.load();
  showModal(elements.playerModal);
}

function showModal(modal) {
  modal.hidden = false;
}

function closeModal(modal) {
  modal.hidden = true;
  if (modal === elements.playerModal) {
    elements.videoPlayer.pause();
    elements.videoPlayer.removeAttribute("src");
    elements.videoPlayer.load();
  }
}

function drawPseudoQr(text) {
  const canvas = elements.qrCanvas;
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  const cells = 21;
  const cellSize = Math.floor(size / cells);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = "#111111";

  function block(x, y, w, h) {
    ctx.fillRect(x * cellSize, y * cellSize, w * cellSize, h * cellSize);
  }

  function finder(x, y) {
    block(x, y, 7, 7);
    ctx.fillStyle = "#ffffff";
    block(x + 1, y + 1, 5, 5);
    ctx.fillStyle = "#111111";
    block(x + 2, y + 2, 3, 3);
  }

  finder(1, 1);
  finder(13, 1);
  finder(1, 13);

  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  }

  for (let y = 1; y < 20; y += 1) {
    for (let x = 1; x < 20; x += 1) {
      const inFinder = (x < 8 && y < 8) || (x > 12 && y < 8) || (x < 8 && y > 12);
      if (inFinder) continue;
      const bit = (hash + x * 17 + y * 29 + x * y * 7) % 5;
      if (bit === 0 || bit === 3) block(x, y, 1, 1);
    }
  }

  ctx.fillStyle = "#111111";
  ctx.font = "12px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("演示支付码", size / 2, size - 8);
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

  elements.resetButton.addEventListener("click", () => {
    state.unlocked.clear();
    saveUnlocked();
    renderCatalog();
  });

  elements.mockPaidButton.addEventListener("click", confirmPayment);

  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => {
      closeModal(document.querySelector(`#${button.dataset.close}`));
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal(elements.paymentModal);
      closeModal(elements.playerModal);
    }
  });
}

function init() {
  setupAgeGate();
  setupEvents();
  renderSeriesFilter();
  renderCatalog();
}

init();
