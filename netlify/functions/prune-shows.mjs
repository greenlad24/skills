import { getStore } from '@netlify/blobs';
import { venueToday } from '../lib/shows.mjs';

const KEEP_DAYS = 30;

/**
 * Daily tidy-up of the Live Shows list.
 *
 * Past shows already never reach the public page — /api/menu filters them out
 * the moment their date passes, so nothing lingers for a day waiting on this.
 * This exists only so the stored list cannot grow forever, and it deliberately
 * keeps a month of history: a show that finished last night is still useful to
 * the person editing, and deleting it the next morning would be surprising.
 */
export default async () => {
  const store = getStore({ name: 'vibration-menu', consistency: 'strong' });

  let menu;
  try {
    menu = await store.get('menu', { type: 'json' });
  } catch (error) {
    console.error('prune-shows: could not read menu', error);
    return new Response('read failed', { status: 500 });
  }

  // Nothing saved yet means the site is still serving the bundled seed.
  if (!menu?.liveShows?.events?.length) {
    return Response.json({ pruned: 0, reason: 'nothing stored' });
  }

  const cutoff = new Date(`${venueToday()}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - KEEP_DAYS);
  const cutoffDay = cutoff.toISOString().slice(0, 10);

  const before = menu.liveShows.events.length;
  menu.liveShows.events = menu.liveShows.events.filter((e) => !e.on || e.on >= cutoffDay);
  const pruned = before - menu.liveShows.events.length;

  if (pruned === 0) return Response.json({ pruned: 0, cutoff: cutoffDay });

  try {
    await store.setJSON('menu', menu);
  } catch (error) {
    console.error('prune-shows: could not write menu', error);
    return new Response('write failed', { status: 500 });
  }

  console.log(`prune-shows: removed ${pruned} show(s) older than ${cutoffDay}`);
  return Response.json({ pruned, cutoff: cutoffDay });
};

// 19:00 UTC is 02:00 in Koh Samui — after closing, before anyone is editing.
export const config = { schedule: '0 19 * * *' };
