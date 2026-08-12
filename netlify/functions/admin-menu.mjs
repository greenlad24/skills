import { isAuthenticated, hasCsrfHeader, unauthorized } from '../lib/auth.mjs';
import { readMenu, writeMenu } from '../lib/store.mjs';

/**
 * Authenticated read/write of the whole menu document.
 *
 * GET  -> current menu, uncached
 * PUT  -> replace the menu; rejected if someone else saved since this editor loaded
 */
export default async (request) => {
  if (!isAuthenticated(request)) return unauthorized();

  if (request.method === 'GET') {
    const menu = await readMenu();
    return Response.json(menu, { headers: { 'Cache-Control': 'no-store' } });
  }

  if (!hasCsrfHeader(request)) {
    return Response.json({ error: 'Bad request' }, { status: 400 });
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: 'Could not read the submitted menu' }, { status: 400 });
  }

  const incoming = body?.menu;
  if (!incoming || !Array.isArray(incoming.sections)) {
    return Response.json({ error: 'Menu must contain a list of sections' }, { status: 400 });
  }

  // Last-writer-wins is the wrong default when two phones are open on the same
  // menu. The editor sends the updatedAt it loaded; if the stored copy has moved
  // on, refuse rather than silently discard the other person's edit.
  const current = await readMenu();
  if (body.baseUpdatedAt !== undefined && current.updatedAt !== body.baseUpdatedAt) {
    return Response.json(
      {
        error: 'This menu was changed somewhere else since you opened it. Reload to get the latest version.',
        conflict: true,
        current,
      },
      { status: 409 },
    );
  }

  const saved = await writeMenu(incoming);
  return Response.json(saved, { headers: { 'Cache-Control': 'no-store' } });
};

export const config = { path: '/api/admin/menu', method: ['GET', 'PUT'] };
