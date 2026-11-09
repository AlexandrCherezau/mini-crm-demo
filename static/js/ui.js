// Shared helpers: safe DOM builder, formatting, API client, toasts.

export const STATUS_ORDER = ["new", "in_progress", "paid", "lost"];

export const state = {
  meta: { statuses: {}, sources: {}, managers: [] },
};

/** Build a DOM element. Strings become text nodes, so user data is never parsed as HTML. */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") el.style.cssText = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  appendChildren(el, children);
  return el;
}

function appendChildren(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

const SVG_NS = "http://www.w3.org/2000/svg";
export function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) el.setAttribute(key, String(value));
  }
  appendChildren(el, children);
  return el;
}

const rub = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
export const money = (n) => `${rub.format(n || 0)} ₽`;
export const num = (n) => rub.format(n || 0);
export const pct = (x) => `${(x * 100).toFixed(x > 0 && x < 0.1 ? 1 : 0)}%`;

export function moneyShort(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1).replace(".", ",")} млн`;
  if (n >= 1000) return `${Math.round(n / 1000)} тыс`;
  return String(n);
}

const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

export function dateShort(iso) {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function dateTime(iso) {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${dateShort(iso)}, ${hh}:${mm}`;
}

export function ago(iso) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} дн`;
  return dateShort(iso);
}

export const initials = (name) =>
  (name || "—").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();

export async function api(path, options = {}) {
  const init = { headers: { "content-type": "application/json" }, ...options };
  if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail[0]?.msg : data.detail || data.error;
    throw new Error(detail || `Ошибка ${res.status}`);
  }
  return data;
}

export function toast(title, text = "", kind = "info", onClick = null) {
  const node = h(
    "div",
    { class: `toast toast-${kind}`, role: "status", onclick: onClick },
    h("div", { class: "toast-title" }, title),
    text ? h("div", { class: "toast-text" }, text) : null,
  );
  document.getElementById("toasts").append(node);
  setTimeout(() => node.classList.add("toast-out"), 5200);
  setTimeout(() => node.remove(), 5600);
}

export function sourceTag(source) {
  return h("span", { class: `tag tag-${source}` }, h("i", { "aria-hidden": "true" }), state.meta.sources[source] || source);
}

export function statusPill(status) {
  return h("span", { class: `pill pill-${status}` }, state.meta.statuses[status] || status);
}
