// Modal form for creating a lead manually.
import { api, h, state, toast } from "./ui.js";

export function openNewLeadForm(onCreated) {
  const root = document.getElementById("drawer-root");
  const close = () => root.replaceChildren();
  const field = (label, input) => h("label", { class: "field" }, h("span", { class: "field-label" }, label), input);

  const form = h("form", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": "Новая заявка" },
    h("header", { class: "modal-head" },
      h("h2", { class: "drawer-title" }, "Новая заявка"),
      h("button", { class: "icon-btn", type: "button", "aria-label": "Закрыть", onclick: close }, "✕")),
    h("div", { class: "modal-grid" },
      field("Имя клиента", h("input", { class: "input", name: "name", required: true, minlength: "2", maxlength: "120" })),
      field("Телефон", h("input", { class: "input", name: "phone", maxlength: "40", placeholder: "+7 900 000-00-00" })),
      field("Источник", h("select", { class: "input", name: "source" },
        Object.entries(state.meta.sources).map(([k, v]) => h("option", { value: k }, v)))),
      field("Менеджер", h("select", { class: "input", name: "manager" },
        state.meta.managers.map((m) => h("option", { value: m }, m)))),
      field("Сумма, ₽", h("input", { class: "input", name: "amount", type: "number", min: "0", step: "1000", value: "0" })),
      field("E-mail", h("input", { class: "input", name: "email", type: "email", maxlength: "160" })),
      h("label", { class: "field field-wide" }, h("span", { class: "field-label" }, "Что нужно"),
        h("textarea", { class: "input textarea", name: "request", rows: "3", maxlength: "2000" }))),
    h("footer", { class: "modal-foot" },
      h("button", { class: "btn", type: "button", onclick: close }, "Отмена"),
      h("button", { class: "btn btn-primary", type: "submit" }, "Создать")));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    data.amount = Number(data.amount) || 0;
    try {
      const lead = await api("/api/leads", { method: "POST", body: data });
      close();
      toast("Заявка создана", lead.name, "ok");
      onCreated(lead);
    } catch (err) {
      toast("Не удалось создать", err.message, "error");
    }
  });

  root.replaceChildren(h("div", { class: "scrim", onclick: close }), form);
  form.querySelector("input").focus();
}
