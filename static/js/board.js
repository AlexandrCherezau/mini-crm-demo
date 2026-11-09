// Kanban board with HTML5 drag-and-drop status changes.
import { STATUS_ORDER, ago, api, h, initials, money, sourceTag, state, toast } from "./ui.js";
import { openLead } from "./lead.js";
import { openNewLeadForm } from "./newlead.js";

const filters = { q: "", source: "", manager: "" };
let leads = [];
let highlightId = null;
let root = null;

export async function renderBoard(container) {
  root = container;
  container.replaceChildren(boardHeader(), h("div", { class: "board", id: "board" }));
  await reloadBoard();
}

export function flashLead(id) {
  highlightId = id;
}

export async function reloadBoard() {
  if (!root || !document.getElementById("board")) return;
  const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
  try {
    leads = await api(`/api/leads?${params}`);
  } catch (err) {
    toast("Не удалось загрузить заявки", err.message, "error");
    return;
  }
  drawColumns();
}

function boardHeader() {
  const search = h("input", {
    class: "input search",
    type: "search",
    placeholder: "Имя, телефон или запрос",
    value: filters.q,
    "aria-label": "Поиск",
  });
  let timer = null;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { filters.q = search.value.trim(); reloadBoard(); }, 250);
  });

  const sourceChips = h("div", { class: "chips", role: "group", "aria-label": "Источник" },
    [["", "Все источники"], ...Object.entries(state.meta.sources)].map(([key, label]) =>
      h("button", {
        class: `chip ${filters.source === key ? "is-on" : ""}`,
        type: "button",
        onclick: (e) => {
          filters.source = key;
          e.currentTarget.parentElement.querySelectorAll(".chip").forEach((c) => c.classList.remove("is-on"));
          e.currentTarget.classList.add("is-on");
          reloadBoard();
        },
      }, key ? h("i", { class: `dot dot-${key}` }) : null, label)));

  const managerSelect = h("select", { class: "input select", "aria-label": "Менеджер",
    onchange: (e) => { filters.manager = e.target.value; reloadBoard(); } },
    h("option", { value: "" }, "Все менеджеры"),
    state.meta.managers.map((m) => h("option", { value: m, selected: filters.manager === m }, m)));

  return h("header", { class: "page-head" },
    h("div", { class: "page-title-row" },
      h("div", {},
        h("h1", { class: "page-title" }, "Доска заявок"),
        h("p", { class: "page-sub" }, "Перетащите карточку в другую колонку, чтобы сменить статус")),
      h("button", { class: "btn btn-primary", type: "button", onclick: () => openNewLeadForm(onCreated) }, "+ Новая заявка")),
    h("div", { class: "toolbar" }, search, sourceChips, managerSelect));
}

function onCreated(lead) {
  flashLead(lead.id);
  reloadBoard();
}

function drawColumns() {
  const board = document.getElementById("board");
  board.replaceChildren(...STATUS_ORDER.map((status) => column(status, leads.filter((l) => l.status === status))));
  if (highlightId) {
    const card = board.querySelector(`[data-id="${highlightId}"]`);
    card?.classList.add("is-new");
    card?.scrollIntoView({ block: "nearest" });
    highlightId = null;
  }
}

function column(status, items) {
  const total = items.reduce((sum, l) => sum + l.amount, 0);
  const list = h("div", { class: "col-list" }, items.length ? items.map(card) : h("div", { class: "col-empty" }, "Пусто"));
  const col = h("section", { class: `col col-${status}`, dataset: { status }, "aria-label": state.meta.statuses[status] },
    h("header", { class: "col-head" },
      h("span", { class: "col-name" }, state.meta.statuses[status]),
      h("span", { class: "col-count" }, items.length),
      h("span", { class: "col-sum" }, money(total))),
    list);
  col.addEventListener("dragover", (e) => { e.preventDefault(); col.classList.add("is-target"); });
  col.addEventListener("dragleave", (e) => { if (!col.contains(e.relatedTarget)) col.classList.remove("is-target"); });
  col.addEventListener("drop", (e) => {
    e.preventDefault();
    col.classList.remove("is-target");
    const id = Number(e.dataTransfer.getData("text/plain"));
    if (id) moveLead(id, status);
  });
  return col;
}

function card(lead) {
  const el = h("article", { class: "card", draggable: "true", tabindex: "0", dataset: { id: lead.id },
      onclick: () => openLead(lead.id, reloadBoard),
      onkeydown: (e) => { if (e.key === "Enter") openLead(lead.id, reloadBoard); } },
    h("div", { class: "card-top" },
      h("span", { class: "card-name" }, lead.name),
      h("span", { class: "card-age", title: lead.created_at }, ago(lead.created_at))),
    lead.request ? h("p", { class: "card-req" }, lead.request) : null,
    h("div", { class: "card-foot" },
      sourceTag(lead.source),
      h("span", { class: "card-amount" }, lead.amount ? money(lead.amount) : "—"),
      h("span", { class: "avatar", title: lead.manager || "Не назначен" }, initials(lead.manager))));
  el.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", String(lead.id));
    e.dataTransfer.effectAllowed = "move";
    el.classList.add("is-drag");
  });
  el.addEventListener("dragend", () => el.classList.remove("is-drag"));
  return el;
}

async function moveLead(id, status) {
  const lead = leads.find((l) => l.id === id);
  if (!lead || lead.status === status) return;
  const previous = lead.status;
  leads = leads.map((l) => (l.id === id ? { ...l, status } : l));
  drawColumns();
  try {
    await api(`/api/leads/${id}/status`, { method: "PATCH", body: { status, author: lead.manager || "Менеджер" } });
    toast(`${lead.name}: ${state.meta.statuses[status]}`, `Было: ${state.meta.statuses[previous]}`, "ok");
  } catch (err) {
    leads = leads.map((l) => (l.id === id ? { ...l, status: previous } : l));
    drawColumns();
    toast("Статус не сохранён", err.message, "error");
  }
}
