// Webhook page: endpoint docs, a test form that posts to the real public endpoint, live request log.
import { api, dateTime, h, toast } from "./ui.js";
import { openLead } from "./lead.js";

let logBox = null;
let fresh = new Set();

export function markFresh(ids) {
  fresh = new Set([...fresh, ...ids]);
}

export async function renderWebhook(container) {
  const url = `${location.origin}/api/webhook/lead`;
  logBox = h("div", { class: "log", id: "wh-log" });
  container.replaceChildren(
    h("header", { class: "page-head" },
      h("h1", { class: "page-title" }, "Webhook с сайта"),
      h("p", { class: "page-sub" }, "Форма на сайте, Tilda или бот отправляют POST — заявка сразу попадает в колонку «Новая»")),
    h("div", { class: "grid-wh" },
      h("section", { class: "panel" },
        h("header", { class: "panel-head" }, h("h2", { class: "panel-title" }, "Адрес приёма"), h("span", { class: "panel-sub" }, "JSON или form-urlencoded")),
        h("div", { class: "endpoint" }, h("span", { class: "method" }, "POST"), h("code", {}, url)),
        h("pre", { class: "code" }, curlExample(url)),
        h("p", { class: "hint" }, "Поля: name (обязательно), phone, email, message, source (site | telegram | avito), budget. "
          + "Если задать переменную WEBHOOK_TOKEN, нужен заголовок X-Webhook-Token. Лимит — 30 запросов в минуту с одного IP."),
        testForm()),
      h("section", { class: "panel panel-log" },
        h("header", { class: "panel-head" },
          h("h2", { class: "panel-title" }, h("span", { class: "live" }), "Входящие запросы"),
          h("span", { class: "panel-sub" }, "обновляется автоматически")),
        logBox)));
  await refreshWebhookLog();
}

function curlExample(url) {
  return `curl -X POST ${url} \\
  -H 'Content-Type: application/json' \\
  -d '{"name": "Алиса Пробникова",
       "phone": "+7 900 000-12-34",
       "message": "Кухня 2,8 м, нужен замер",
       "budget": 210000}'`;
}

function testForm() {
  const form = h("form", { class: "wh-form" },
    h("div", { class: "wh-form-title" }, "Проверить вручную — как будто с сайта"),
    h("input", { class: "input", name: "name", required: true, minlength: "2", value: "Нина Условнова", "aria-label": "Имя" }),
    h("input", { class: "input", name: "phone", value: "+7 900 000-55-01", "aria-label": "Телефон" }),
    h("input", { class: "input wh-wide", name: "message", value: "Шкаф-купе в спальню, 2 м", "aria-label": "Сообщение" }),
    h("button", { class: "btn btn-primary", type: "submit" }, "Отправить на webhook"));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    try {
      await api("/api/webhook/lead", { method: "POST", body });
    } catch (err) {
      toast("Webhook вернул ошибку", err.message, "error");
    }
  });
  return form;
}

export async function refreshWebhookLog() {
  if (!logBox || !document.body.contains(logBox)) return;
  const rows = await api("/api/webhook/log").catch(() => []);
  logBox.replaceChildren(...(rows.length ? rows.map(logRow) : [h("div", { class: "log-empty" }, "Пока ни одного запроса. Отправьте curl из примера слева.")]));
}

function prettyPayload(raw) {
  try {
    return JSON.stringify(JSON.parse(raw), null, 0).replace(/","/g, '", "').replace(/":/g, '": ');
  } catch {
    const form = Object.fromEntries(new URLSearchParams(raw));
    return Object.keys(form).length ? `form: ${JSON.stringify(form).replace(/","/g, '", "').replace(/":/g, '": ')}` : raw;
  }
}

function logRow(r) {
  const ok = r.http_status < 300;
  return h("div", { class: `log-row ${ok ? "" : "log-err"} ${fresh.has(r.id) ? "is-fresh" : ""}` },
    h("div", { class: "log-line" },
      h("span", { class: `code-badge ${ok ? "ok" : "bad"}` }, r.http_status),
      h("time", { class: "log-time" }, dateTime(r.received_at)),
      h("span", { class: "log-ip" }, r.remote_ip),
      ok && r.lead_id
        ? h("button", { class: "link", type: "button", onclick: () => openLead(r.lead_id) }, `→ заявка #${r.lead_id}`)
        : h("span", { class: "log-error" }, r.error || "")),
    h("code", { class: "log-payload" }, prettyPayload(r.payload)));
}
