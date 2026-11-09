// Router + live polling of incoming webhook leads.
import { api, h, state, toast } from "./ui.js";
import { flashLead, reloadBoard, renderBoard } from "./board.js";
import { closeLead, openLead } from "./lead.js";
import { renderStats } from "./stats.js";
import { markFresh, refreshWebhookLog, renderWebhook } from "./webhook.js";

const POLL_MS = 3000;
const VIEWS = { board: renderBoard, stats: renderStats, webhook: renderWebhook };
let lastLogId = 0;

function parseHash() {
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  return { view: VIEWS[path] ? path : "board", params: new URLSearchParams(query) };
}

async function route() {
  const { view, params } = parseHash();
  closeLead();
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("is-on", a.dataset.view === view));
  const container = document.getElementById("view");
  container.replaceChildren(h("div", { class: "loading" }, "Загрузка…"));
  await VIEWS[view](container);
  const leadId = Number(params.get("lead"));
  if (leadId) openLead(leadId, reloadBoard);
}

async function poll() {
  try {
    const rows = await api(`/api/webhook/log?after_id=${lastLogId}`);
    if (rows.length) {
      lastLogId = Math.max(lastLogId, ...rows.map((r) => r.id));
      markFresh(rows.map((r) => r.id));
      const created = rows.filter((r) => r.lead_id);
      created.forEach((r) => {
        const name = safeName(r.payload);
        toast("Новая заявка с сайта", `${name} · #${r.lead_id}`, "new", () => openLead(r.lead_id, reloadBoard));
        flashLead(r.lead_id);
      });
      await Promise.all([reloadBoard(), refreshWebhookLog()]);
    }
  } catch {
    document.getElementById("live-dot")?.classList.add("is-off");
    return;
  }
  document.getElementById("live-dot")?.classList.remove("is-off");
}

function safeName(payload) {
  try {
    return JSON.parse(payload).name || "без имени";
  } catch {
    return new URLSearchParams(payload).get("name") || "без имени";
  }
}

async function start() {
  try {
    state.meta = await api("/api/meta");
    const log = await api("/api/webhook/log");
    lastLogId = log.length ? log[0].id : 0;
  } catch (err) {
    toast("Сервер недоступен", err.message, "error");
  }
  window.addEventListener("hashchange", route);
  await route();
  setInterval(poll, POLL_MS);
}

start();
