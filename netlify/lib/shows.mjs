import { randomUUID } from 'node:crypto';

const str = (v) => (typeof v === 'string' ? v.trim() : '');
const newId = () => randomUUID().slice(0, 8);

/**
 * Image paths the editor may set. Uploads live under /api/img/, seeded assets
 * under /img/ — anything else (an external URL, a javascript: payload) is
 * dropped rather than stored.
 */
function safeImage(value) {
  const v = str(value);
  if (!v) return '';
  return /^\/(api\/img|img)\/[A-Za-z0-9._-]+$/.test(v) ? v : '';
}

const MAX_EVENTS = 60;
const MAX_WEEKLY = 12;

/**
 * Unlike the menu, Live Shows is fully editable: events and weekly slots can be
 * added, renamed, reordered and removed. So this rebuilds the section from the
 * payload rather than merging onto stored structure — but every field is
 * coerced, capped and validated on the way through.
 */
export function sanitiseLiveShows(incoming, current) {
  const src = incoming && typeof incoming === 'object' ? incoming : {};
  const base = current && typeof current === 'object' ? current : {};

  const events = (Array.isArray(src.events) ? src.events : [])
    .filter((e) => e && typeof e === 'object')
    .slice(0, MAX_EVENTS)
    .map((e) => ({
      id: str(e.id) || newId(),
      // ISO date drives ordering and the drop-off of past shows.
      on: /^\d{4}-\d{2}-\d{2}$/.test(str(e.on)) ? str(e.on) : '',
      date: str(e.date),
      day: str(e.day),
      name: str(e.name),
      genre: str(e.genre),
      poster: safeImage(e.poster),
      description: str(e.description),
    }));

  const weeklySrc = src.weekly && typeof src.weekly === 'object' ? src.weekly : {};
  const weekly = {
    title: str(weeklySrc.title) || base.weekly?.title || 'Every Week',
    items: (Array.isArray(weeklySrc.items) ? weeklySrc.items : [])
      .filter((w) => w && typeof w === 'object')
      .slice(0, MAX_WEEKLY)
      .map((w) => ({
        id: str(w.id) || newId(),
        name: str(w.name),
        when: str(w.when),
        image: safeImage(w.image),
      })),
  };

  return {
    key: 'live',
    hidden: src.hidden === true,
    title: str(src.title) || base.title || 'Live Shows',
    sub: str(src.sub),
    thumb: safeImage(src.thumb),
    heading: str(src.heading),
    eyebrow: str(src.eyebrow),
    foot: str(src.foot),
    events,
    weekly,
  };
}

/** Today in Koh Samui, as YYYY-MM-DD. A show runs into the evening, so the venue's
    own calendar day is what decides whether it has passed — not the server's. */
export function venueToday(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now);
}

/**
 * Upcoming shows, soonest first. Past shows are hidden rather than deleted, so
 * nothing is lost and the editor can still see them. Events without a date are
 * always kept — an undated entry is unfinished, not expired.
 */
export function withUpcomingOnly(shows, today = venueToday()) {
  if (!shows || !Array.isArray(shows.events)) return shows;
  const events = shows.events
    .filter((e) => !e.on || e.on >= today)
    .sort((a, b) => (a.on || '9999').localeCompare(b.on || '9999'));
  return { ...shows, events };
}
