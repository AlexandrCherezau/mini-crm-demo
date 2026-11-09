// Lead drawer: details, status switch, amount/manager edit, history and comments.
import { STATUS_ORDER, api, dateTime, h, initials, sourceTag, state, statusPill, toast } from "./ui.js";

let onChange = () => {};

export function closeLead() {
  document.getElementById("drawer-root").replaceChildren();
  document.removeEventListener("keydown", escClose);
}

function escClose(e) {
  if (e.key === "Escape") closeLead();
}

export async function openLead(id, changed = () => {}) {
  onChange = changed;
  let lead;
  try {
    lead = await api(`/api/leads/${id}`);
  } catch (err) {
    toast("Заявка не открылась", err.message, "error");
    return;
  }
  draw(lead);
  document.addEventListener("keydown", escClose);
}

function draw(lead) {
  const panel = h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": `Заявка ${lead.name}` },
    drawerHead(lead),
    h("div", { class: "drawer-body" },
      statusSwitch(lead),
      facts(lead),
      h("h3", { class: "section-title" }, "История"),
      commentForm(lead),
      timeline(lead.history)));
  document.getElementById("drawer-root").replaceChildren(
    h("div", { class: "scrim", onclick: closeLead }), panel);
}

function drawerHead(lead) {
  return h("header", { class: "drawer-head" },
    h("div", {},
      h("div", { class: "drawer-kicker" }, `Заявка #${lead.id}`, " · ", sourceTag(lead.source)),
      h("h2", { class: "drawer-title" }, lead.name),
      lead.request ? h("p", { class: "drawer-req" }, lead.request) : null),
    h("button", { class: "icon-btn", type: "button", "aria-label": "Закрыть", onclick: closeLead }, "✕"));
}

function statusSwitch(lead) {
  return h("div", { class: "seg", role: "group", "aria-label": "Статус" },
    STATUS_ORDER.map((status) => h("button", {
      type: "button",
      class: `seg-btn seg-${status} ${lead.status === status ? "is-on" : ""}`,
      "aria-pressed": lead.status === status ? "true" : "false",
      onclick: () => setStatus(lead, status),
    }, state.meta.statuses[status])));
}

async function setStatus(lead, status) {
  if (lead.status === status) return;
  try {
    await api(`/api/leads/${lead.id}/status`, { method: "PATCH", body: { status, author: lead.manager || "Менеджер" } });
    await refresh(lead.id);
  } catch (err) {
    toast("Статус не сохранён", err.message, "error");
  }
}

async function refresh(id) {
  draw(await api(`/api/leads/${id}`));
  onChange();
}

function facts(lead) {
  const amount = h("input", { class: "input input-amount", type: "number", min: "0", step: "1000", value: lead.amount, "aria-label": "Сумма" });
  amount.addEventListener("change", () => patch(lead, { amount: Math.max(0, Number(amount.value) || 0) }));
  const manager = h("select", { class: "input", "aria-label": "Ответственный",
      onchange: (e) => patch(lead, { manager: e.target.value }) },
    lead.manager ? null : h("option", { value: "" }, "Не назначен"),
    state.meta.managers.map((m) => h("option", { value: m, selected: m === lead.manager }, m)));
  return h("dl", { class: "facts" },
    fact("Телефон", lead.phone ? h("a", { href: `tel:${lead.phone.replace(/[^\d+]/g, "")}` }, lead.phone) : "—"),
    fact("E-mail", lead.email || "—"),
    fact("Сумма, ₽", amount),
    fact("Ответственный", manager),
    fact("Создана", dateTime(lead.created_at)),
    fact("Статус", statusPill(lead.status)));
}

const fact = (label, value) => h("div", { class: "fact" }, h("dt", {}, label), h("dd", {}, value));

async function patch(lead, body) {
  try {
    await api(`/api/leads/${lead.id}`, { method: "PATCH", body: { ...body, author: lead.manager || "Менеджер" } });
    await refresh(lead.id);
  } catch (err) {
    toast("Не сохранилось", err.message, "error");
  }
}

const KIND_LABEL = { created: "Создана", status: "Статус", comment: "Комментарий", amount: "Сумма", manager: "Ответственный" };

function timeline(events) {
  return h("ol", { class: "timeline" }, [...events].reverse().map((e) =>
    h("li", { class: `tl tl-k-${e.kind} ${e.to_status ? `tl-to-${e.to_status}` : ""}` },
      h("span", { class: "tl-dot", "aria-hidden": "true" }),
      h("div", { class: "tl-meta" },
        h("span", { class: "tl-kind" }, KIND_LABEL[e.kind] || e.kind),
        h("span", { class: "tl-author" }, h("span", { class: "avatar avatar-xs" }, initials(e.author)), e.author),
        h("time", { class: "tl-time", datetime: e.created_at }, dateTime(e.created_at))),
      e.kind === "status"
        ? h("div", { class: "tl-status" }, statusPill(e.from_status), h("span", { class: "tl-arrow" }, "→"), statusPill(e.to_status))
        : h("div", { class: e.kind === "comment" ? "tl-text tl-quote" : "tl-text" }, e.text))));
}

function commentForm(lead) {
  const area = h("textarea", { class: "input textarea", rows: "2", maxlength: "2000", placeholder: "Комментарий: о чём договорились, когда перезвонить…", "aria-label": "Комментарий" });
  const form = h("form", { class: "comment-form" }, area,
    h("button", { class: "btn btn-primary", type: "submit" }, "Добавить"));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = area.value.trim();
    if (!text) return;
    try {
      await api(`/api/leads/${lead.id}/comments`, { method: "POST", body: { text, author: lead.manager || "Менеджер" } });
      await refresh(lead.id);
    } catch (err) {
      toast("Комментарий не добавлен", err.message, "error");
    }
  });
  return form;
}

