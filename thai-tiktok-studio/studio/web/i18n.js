/* Tiny i18n runtime (vanilla JS, Safari 15+).
 * Dictionaries live in /static/lang/th.json and /static/lang/en.json (flat "dotted.key": "text").
 * Usage: t("home.title")  ·  t("upload.count", { n: 3 })  → "{n}" placeholders, values are HTML-escaped.
 * Strings may contain simple HTML (<b>, <br>) — they come from our own files, never from users.
 * To add a string: add the same key to BOTH json files, then call t("your.key") in app.js.
 * tests/test_i18n.py checks that both files have identical keys and that every t("…") key exists.
 */
const I18N = { dict: { th: {}, en: {} }, lang: "th", LANGS: ["th", "en"] };

function escHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function t(key, vars) {
  let s = I18N.dict[I18N.lang][key];
  if (s == null) s = I18N.dict.th[key];
  if (s == null) { if (window.console) console.warn("i18n: missing key", key); return key; }
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (Object.prototype.hasOwnProperty.call(vars, k) ? escHtml(vars[k]) : m));
  return s;
}
/* Translate a key that is built at runtime (e.g. "status." + value); falls back to a readable value. */
function tOr(key, fallback) {
  const s = I18N.dict[I18N.lang][key] != null ? I18N.dict[I18N.lang][key] : I18N.dict.th[key];
  return s != null ? s : escHtml(fallback);
}
/* Plain text version (for title/aria-label/placeholder attributes and toasts). */
function tt(key, vars) { return t(key, vars).replace(/<[^>]+>/g, ""); }

async function loadI18n() {
  const get = (l) => fetch(`/static/lang/${l}.json`, { cache: "no-cache" }).then((r) => r.json());
  const [th, en] = await Promise.all([get("th"), get("en")]);
  I18N.dict = { th, en };
}
function storedLang() {
  try { const l = localStorage.getItem("tts_lang"); return I18N.LANGS.indexOf(l) >= 0 ? l : null; } catch (e) { return null; }
}
function applyLang(lang) {
  I18N.lang = I18N.LANGS.indexOf(lang) >= 0 ? lang : "th";
  document.documentElement.lang = I18N.lang;
  try { localStorage.setItem("tts_lang", I18N.lang); } catch (e) { /* private mode */ }
  document.cookie = "tts_lang=" + I18N.lang + ";path=/;max-age=31536000;samesite=lax";
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.innerHTML = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", tt(el.dataset.i18nAria)); el.title = tt(el.dataset.i18nAria); });
  document.querySelectorAll("select.lang-sel").forEach((s) => { s.value = I18N.lang; });
}
