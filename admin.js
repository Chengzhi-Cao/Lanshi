const ADMIN_TOKEN_KEY = "lanshiAdminToken";

const adminState = {
  orders: [],
};

const adminElements = {
  token: document.querySelector("#adminToken"),
  status: document.querySelector("#adminStatus"),
  refresh: document.querySelector("#adminRefresh"),
  summary: document.querySelector("#adminSummary"),
  orders: document.querySelector("#adminOrders"),
  template: document.querySelector("#adminOrderTemplate"),
};

function formatAdminDate(timestamp) {
  if (!timestamp) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp * 1000));
}

function adminHeaders() {
  return { "X-Admin-Token": adminElements.token.value.trim() };
}

function renderOrders() {
  adminElements.orders.innerHTML = "";
  adminElements.summary.textContent = `当前 ${adminState.orders.length} 个订单`;

  if (!adminState.orders.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "没有符合条件的订单";
    adminElements.orders.append(empty);
    return;
  }

  for (const order of adminState.orders) {
    const fragment = adminElements.template.content.cloneNode(true);
    const card = fragment.querySelector(".admin-order");
    const id = fragment.querySelector(".order-id");
    const time = fragment.querySelector(".order-time");
    const title = fragment.querySelector("h3");
    const file = fragment.querySelector(".order-file");
    const price = fragment.querySelector(".price");
    const pill = fragment.querySelector(".order-status-pill");
    const button = fragment.querySelector(".confirm-order");

    id.textContent = order.orderId;
    time.textContent = formatAdminDate(order.createdAt);
    title.textContent = order.title;
    file.textContent = order.fileName;
    price.textContent = order.amountLabel;
    pill.textContent = order.status === "paid" ? "已支付" : "待确认";
    card.classList.toggle("is-paid", order.status === "paid");
    button.hidden = order.status === "paid";
    button.addEventListener("click", () => confirmOrder(order.orderId));

    adminElements.orders.append(fragment);
  }
}

async function loadOrders() {
  const token = adminElements.token.value.trim();
  if (!token) {
    adminElements.summary.textContent = "请输入卖家确认码";
    return;
  }
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
  const params = new URLSearchParams();
  if (adminElements.status.value) params.set("status", adminElements.status.value);
  const response = await fetch(`/api/admin/orders?${params}`, { headers: adminHeaders() });
  const payload = await response.json();
  if (!response.ok) {
    adminElements.summary.textContent = payload.error || "读取订单失败";
    adminState.orders = [];
    renderOrders();
    return;
  }
  adminState.orders = payload.orders;
  renderOrders();
}

async function confirmOrder(orderId) {
  const response = await fetch(`/api/admin/orders/${orderId}/confirm`, {
    method: "POST",
    headers: adminHeaders(),
  });
  const payload = await response.json();
  if (!response.ok) {
    adminElements.summary.textContent = payload.error || "确认失败";
    return;
  }
  adminElements.summary.textContent = `${payload.orderId} 已确认收款`;
  await loadOrders();
}

function setupAdmin() {
  adminElements.token.value = localStorage.getItem(ADMIN_TOKEN_KEY) || "";
  adminElements.refresh.addEventListener("click", loadOrders);
  adminElements.status.addEventListener("change", loadOrders);
  adminElements.token.addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadOrders();
  });
  if (adminElements.token.value) loadOrders();
}

setupAdmin();
