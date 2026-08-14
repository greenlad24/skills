#!/usr/bin/env node
// Vibration Poster Studio — local server shell. Zero dependencies, Node 18+.
// All API logic lives in lib/routes.js (shared with the Netlify deployment).
const http = require('http');
const fs = require('fs');
const path = require('path');

const store = require('./lib/store');
const { dispatch } = require('./lib/routes');
const auth = require('./lib/auth');

const PORT = process.env.PORT || 5713;
const PUBLIC_DIR = path.join(__dirname, 'public');
const DATA_DIR = path.join(__dirname, 'data');
const FILES_DIR = path.join(DATA_DIR, 'files');

// ---- local disk storage driver ----
fs.mkdirSync(FILES_DIR, { recursive: true });
store.setDriver({
  async getJson(key) {
    try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, key), 'utf8')); } catch { return null; }
  },
  async setJson(key, obj) {
    fs.writeFileSync(path.join(DATA_DIR, key), JSON.stringify(obj, null, 2));
  },
  async getFile(name) {
    try { return fs.readFileSync(path.join(FILES_DIR, name)); } catch { return null; }
  },
  async putFile(name, buf) {
    fs.writeFileSync(path.join(FILES_DIR, name), buf);
  },
});

const ctx = {
  origin: `http://localhost:${PORT}`,
  async loadAsset(relPath) {
    const resolved = path.resolve(PUBLIC_DIR, relPath);
    if (!resolved.startsWith(path.resolve(PUBLIC_DIR))) throw new Error('Bad asset path');
    return fs.readFileSync(resolved);
  },
};

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.webp': 'image/webp', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
};

function sendJson(res, status, obj, extraHeaders = {}) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body), ...extraHeaders });
  res.end(body);
}

function readBody(req, limitMb = 80) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => {
      size += c.length;
      if (size > limitMb * 1024 * 1024) { reject(new Error('Request too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      if (!chunks.length) return resolve({});
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
      catch { reject(new Error('Invalid JSON body')); }
    });
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, ctx.origin);
  const pathname = decodeURIComponent(url.pathname);

  try {
    const password = process.env.STUDIO_PASSWORD;

    if (pathname === '/api/login' && req.method === 'POST') {
      const body = await readBody(req);
      if (!password || auth.passwordMatches(body.password, password)) {
        return sendJson(res, 200, { ok: true }, password ? { 'Set-Cookie': auth.cookieHeader(password, false) } : {});
      }
      return sendJson(res, 401, { error: 'Wrong password' });
    }

    if (password && (pathname.startsWith('/api/') || pathname.startsWith('/files/'))) {
      if (!auth.verifyCookieHeader(req.headers.cookie, password)) {
        return sendJson(res, 401, { error: 'auth required' });
      }
    }

    if (pathname.startsWith('/api/') || pathname.startsWith('/files/')) {
      const body = ['POST', 'PUT', 'PATCH'].includes(req.method) ? await readBody(req) : {};
      const out = await dispatch(req.method, pathname, body, url.searchParams, ctx);
      if (!out) { res.writeHead(404); return res.end('Not found'); }
      if (out.file) {
        res.writeHead(200, { 'Content-Type': out.file.mime, 'Content-Length': out.file.buffer.length, 'Cache-Control': 'no-cache' });
        return res.end(out.file.buffer);
      }
      return sendJson(res, out.status, out.json);
    }

    // Static files from public/
    const staticPath = pathname === '/' ? '/index.html' : pathname;
    const resolved = path.resolve(PUBLIC_DIR, '.' + staticPath);
    if (resolved.startsWith(path.resolve(PUBLIC_DIR)) && fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
      res.writeHead(200, { 'Content-Type': MIME[path.extname(resolved).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
      return fs.createReadStream(resolved).pipe(res);
    }
    res.writeHead(404);
    res.end('Not found');
  } catch (e) {
    if (pathname.startsWith('/api/')) return sendJson(res, 500, { error: e.message });
    res.writeHead(500);
    res.end(e.message);
  }
});

if (parseInt(process.versions.node.split('.')[0], 10) < 18) {
  console.error(`\n  Node ${process.versions.node} is too old — please install Node 18 or newer from https://nodejs.org\n`);
  process.exit(1);
}

server.listen(PORT, () => {
  console.log('');
  console.log('  ██  Vibration Poster Studio');
  console.log(`  ██  Open  http://localhost:${PORT}  in your browser`);
  console.log('');
});
