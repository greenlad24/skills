// Cookie-based password gate for the hosted deployment. The password lives in
// the STUDIO_PASSWORD environment variable (set it in Netlify → Site settings
// → Environment variables). When the variable is unset (typical local use),
// auth is disabled entirely.
const crypto = require('crypto');

const COOKIE_NAME = 'studio_auth';
const MAX_AGE_S = 30 * 24 * 3600; // 30 days

function hmac(password, payload) {
  return crypto.createHmac('sha256', `vps:${password}`).update(payload).digest('hex');
}

function makeCookieValue(password) {
  const exp = String(Date.now() + MAX_AGE_S * 1000);
  return `${exp}.${hmac(password, exp)}`;
}

function cookieHeader(password, secure) {
  return `${COOKIE_NAME}=${makeCookieValue(password)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${MAX_AGE_S}${secure ? '; Secure' : ''}`;
}

function verifyCookieHeader(cookies, password) {
  const m = new RegExp(`(?:^|;\\s*)${COOKIE_NAME}=([^;]+)`).exec(cookies || '');
  if (!m) return false;
  const [exp, sig] = m[1].split('.');
  if (!exp || !sig) return false;
  if (Number(exp) < Date.now()) return false;
  const expected = hmac(password, exp);
  return sig.length === expected.length && crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected));
}

function passwordMatches(given, password) {
  const a = Buffer.from(String(given || ''));
  const b = Buffer.from(String(password));
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

module.exports = { COOKIE_NAME, cookieHeader, verifyCookieHeader, passwordMatches };
