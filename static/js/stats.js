// Dashboard: KPIs, weekly revenue chart, sources, funnel, managers. All numbers from /api/stats.
import { api, h, initials, money, moneyShort, num, pct, svg, toast } from "./ui.js";

export async function renderStats(container) {
  let s;
  try {
    s = await api("/api/stats?weeks=10");
  } catch (err) {
    toast("Сводка не загрузилась", err.message, "error");
    return;
  }
  const t = s.totals;
  container.replaceChildren(
    h("header", { class: "page-head" },
      h("h1", { class: "page-title" }, "Сводка"),
      h("p", { class: "page-sub" }, `Считается из базы при каждом открытии · ${num(t.leads)} заявок за всё время`)),
    h("div", { class: "kpis" },
      kpi("Заявок", num(t.leads), `${num(t.open)} в работе сейчас`),
      kpi("Конверсия в оплату", pct(t.conversion), `${num(t.paid)} из ${num(t.leads)} · среди закрытых ${pct(t.win_rate)}`),
      kpi("Выручка", money(t.revenue), "сумма оплаченных заявок", true),
      kpi("Средний чек", money(t.avg_check), "по оплаченным"),
      kpi("В воронке", money(t.pipeline), "потенциал открытых заявок")),
    h("div", { class: "grid-2" },
      panel("Выручка по неделям", "оплаченные заявки по дате оплаты", weekChart(s.revenue_by_week, chartWidth(container)), "panel-wide"),
      panel("Источники заявок", "сколько пришло и сколько оплатили", sourceTable(s.by_source)),
      panel("Воронка", "текущее распределение по статусам", funnel(s.by_status, t.leads)),
      panel("Менеджеры", "оплаты и открытые заявки", managerTable(s.by_manager), "panel-wide")));
}

function kpi(label, value, note, accent = false) {
  return h("div", { class: `kpi ${accent ? "kpi-accent" : ""}` },
    h("div", { class: "kpi-label" }, label),
    h("div", { class: "kpi-value" }, value),
    h("div", { class: "kpi-note" }, note));
}

function panel(title, sub, body, cls = "") {
  return h("section", { class: `panel ${cls}` },
    h("header", { class: "panel-head" }, h("h2", { class: "panel-title" }, title), h("span", { class: "panel-sub" }, sub)),
    body);
}

function niceMax(value) {
  if (value <= 0) return 100_000;
  const step = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / step / 2) * step * 2;
}

function chartWidth(container) {
  const panelPadding = 42;
  return Math.max(560, Math.round(container.clientWidth - 64 - panelPadding));
}

function weekChart(weeks, W) {
  const H = 380, padL = 70, padR = 12, padT = 28, padB = 56;
  const max = niceMax(Math.max(...weeks.map((w) => w.revenue)));
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const slot = innerW / weeks.length, barW = Math.min(56, slot * 0.58);
  const y = (v) => padT + innerH - (v / max) * innerH;
  const nodes = [];
  for (let i = 0; i <= 4; i++) {
    const v = (max / 4) * i;
    nodes.push(svg("line", { x1: padL, x2: W - padR, y1: y(v), y2: y(v), class: i ? "grid" : "axis" }));
    nodes.push(svg("text", { x: padL - 10, y: y(v) + 4, class: "tick", "text-anchor": "end" }, moneyShort(v)));
  }
  weeks.forEach((w, i) => {
    const cx = padL + slot * i + slot / 2;
    const current = i === weeks.length - 1;
    const d = new Date(w.week_start);
    const label = `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
    if (w.revenue > 0) {
      nodes.push(svg("rect", { x: cx - barW / 2, y: y(w.revenue), width: barW, height: Math.max(2, y(0) - y(w.revenue)), rx: 3,
        class: current ? "bar bar-current" : "bar" }, svg("title", {}, `${label}: ${money(w.revenue)}, оплат: ${w.paid}`)));
      nodes.push(svg("text", { x: cx, y: y(w.revenue) - 8, class: "bar-val", "text-anchor": "middle" }, moneyShort(w.revenue)));
    } else {
      nodes.push(svg("text", { x: cx, y: y(0) - 8, class: "bar-zero", "text-anchor": "middle" }, "0"));
    }
    nodes.push(svg("text", { x: cx, y: H - padB + 20, class: "tick", "text-anchor": "middle" }, current ? "эта нед." : label));
    nodes.push(svg("text", { x: cx, y: H - padB + 38, class: "tick tick-soft", "text-anchor": "middle" }, `${w.leads} заяв.`));
  });
  return h("div", { class: "chart" }, svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Выручка по неделям" }, nodes));
}

function sourceTable(rows) {
  const maxCount = Math.max(1, ...rows.map((r) => r.count));
  return h("div", { class: "src-list" }, rows.map((r) =>
    h("div", { class: "src-row" },
      h("div", { class: "src-name" }, h("i", { class: `dot dot-${r.source}` }), r.label),
      h("div", { class: "src-bar" },
        h("span", { class: `src-fill src-fill-${r.source}`, style: `width:${(r.count / maxCount) * 100}%` }),
        h("span", { class: `src-paid src-fill-${r.source}`, style: `width:${(r.paid / maxCount) * 100}%` })),
      h("div", { class: "src-nums" },
        h("b", {}, num(r.count)), h("span", {}, ` заявок · ${num(r.paid)} опл.`)),
      h("div", { class: "src-conv" }, pct(r.conversion)),
      h("div", { class: "src-rev" }, money(r.revenue)))),
    h("div", { class: "src-legend" },
      h("span", {}, h("i", { class: "lg lg-all" }), "все заявки"),
      h("span", {}, h("i", { class: "lg lg-paid" }), "оплачено"),
      h("span", { class: "src-legend-right" }, "конверсия · выручка")));
}

function funnel(byStatus, total) {
  return h("div", { class: "funnel" }, byStatus.map((s) =>
    h("div", { class: "fn-row" },
      h("span", { class: "fn-label" }, s.label),
      h("div", { class: "fn-track" }, h("span", { class: `fn-fill fn-${s.status}`, style: `width:${total ? (s.count / total) * 100 : 0}%` })),
      h("span", { class: "fn-count" }, num(s.count)),
      h("span", { class: "fn-share" }, pct(total ? s.count / total : 0)))));
}

function managerTable(rows) {
  return h("table", { class: "table" },
    h("thead", {}, h("tr", {}, ["Менеджер", "Заявок", "Открыто", "Оплачено", "Конверсия", "Выручка"].map((c) => h("th", {}, c)))),
    h("tbody", {}, rows.map((r) => h("tr", {},
      h("td", {}, h("span", { class: "mgr" }, h("span", { class: "avatar" }, initials(r.manager)), r.manager)),
      h("td", { class: "num" }, num(r.count)),
      h("td", { class: "num" }, num(r.open)),
      h("td", { class: "num" }, num(r.paid)),
      h("td", { class: "num" }, pct(r.count ? r.paid / r.count : 0)),
      h("td", { class: "num strong" }, money(r.revenue))))));
}
