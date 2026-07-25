/* WhatsApp Message Scheduler — popup
 * Lists pending/sent/failed messages and lets the user send-now or cancel. */

const listEl = document.getElementById("list");
const emptyEl = document.getElementById("empty");
const bannerEl = document.getElementById("weekend-banner");

function fmt(ts) {
  return new Date(ts).toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function send(type, extra = {}) {
  return new Promise((resolve) => chrome.runtime.sendMessage({ type, ...extra }, resolve));
}

function showWeekendBanner() {
  const day = new Date().getDay();
  if (day === 0 || day === 6) {
    bannerEl.textContent = "It's the weekend — schedule messages for Monday so they don't get lost.";
    bannerEl.hidden = false;
  }
}

function render(items) {
  listEl.innerHTML = "";
  const sorted = [...items].sort((a, b) => a.when - b.when);
  if (!sorted.length) {
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  for (const item of sorted) {
    const li = document.createElement("li");
    li.className = "item item-" + item.status;

    const info = document.createElement("div");
    info.className = "item-info";
    info.innerHTML = `
      <div class="item-top">
        <span class="item-chat"></span>
        <span class="badge badge-${item.status}">${item.status}</span>
      </div>
      <div class="item-text"></div>
      <div class="item-when">${fmt(item.when)}</div>
      ${item.error ? `<div class="item-error"></div>` : ""}`;
    info.querySelector(".item-chat").textContent = item.chatName;
    info.querySelector(".item-text").textContent = item.text;
    if (item.error) info.querySelector(".item-error").textContent = item.error;

    const actions = document.createElement("div");
    actions.className = "item-actions";

    if (item.status === "pending" || item.status === "failed") {
      const sendBtn = document.createElement("button");
      sendBtn.className = "btn btn-send";
      sendBtn.textContent = "Send now";
      sendBtn.addEventListener("click", async () => {
        sendBtn.disabled = true;
        sendBtn.textContent = "Sending…";
        await send("SEND_NOW", { id: item.id });
        refresh();
      });
      actions.appendChild(sendBtn);
    }

    const del = document.createElement("button");
    del.className = "btn btn-del";
    del.textContent = item.status === "pending" ? "Cancel" : "Remove";
    del.addEventListener("click", async () => {
      await send("CANCEL_MESSAGE", { id: item.id });
      refresh();
    });
    actions.appendChild(del);

    li.appendChild(info);
    li.appendChild(actions);
    listEl.appendChild(li);
  }
}

async function refresh() {
  const res = await send("GET_SCHEDULED");
  render((res && res.items) || []);
}

showWeekendBanner();
refresh();
