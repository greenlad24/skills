import { getStore } from '@netlify/blobs';
import { SEED_MENU } from './seed.mjs';
import { sanitiseLiveShows } from './shows.mjs';

const STORE_NAME = 'vibration-menu';
const MENU_KEY = 'menu';

// Strong consistency: after Save, the next read of the public menu must show the
// new price rather than a stale cached one.
function store() {
  return getStore({ name: STORE_NAME, consistency: 'strong' });
}

const str = (v) => (typeof v === 'string' ? v : '');

/**
 * Text fields the editor is allowed to change, per entry type. Everything else
 * — images, layout, entry types, the number of sections/entries/rows — is
 * structural and stays exactly as designed.
 */
const TEXT_FIELDS = {
  item: ['eyebrow', 'name', 'story', 'build', 'serve', 'price', 'priceHtml'],
  back: ['kicker', 'quote', 'attrib', 'fine'],
  list: ['eyebrow', 'title'],
};

/**
 * Applies incoming text onto the stored structure.
 *
 * The merge is deliberately one-directional: we walk the *stored* menu and pull
 * matching text across, so a malformed or hostile payload cannot add, remove or
 * reorder anything, and cannot touch an image path. Anything the payload omits
 * keeps its current value.
 */
export function applyTextEdits(stored, incoming) {
  const next = structuredClone(stored);
  const src = incoming && typeof incoming === 'object' ? incoming : {};

  if (src.brand && typeof src.brand === 'object') {
    if ('tag' in src.brand) next.brand.tag = str(src.brand.tag);
    if ('foot' in src.brand) next.brand.foot = str(src.brand.foot);
  }

  const srcSections = Array.isArray(src.sections) ? src.sections : [];

  next.sections.forEach((section, sIndex) => {
    const inSection = srcSections[sIndex];
    if (!inSection || typeof inSection !== 'object') return;

    if ('title' in inSection) section.title = str(inSection.title);
    if ('sub' in inSection) section.sub = str(inSection.sub);

    const inEntries = Array.isArray(inSection.entries) ? inSection.entries : [];

    section.entries.forEach((entry, eIndex) => {
      const inEntry = inEntries[eIndex];
      if (!inEntry || typeof inEntry !== 'object') return;

      for (const field of TEXT_FIELDS[entry.type] || []) {
        if (field in inEntry) entry[field] = str(inEntry[field]);
      }

      // List pages carry their own nested rows of name / price / size.
      if (entry.type === 'list') {
        for (const col of ['col1', 'col2']) {
          if (!Array.isArray(entry[col])) continue;
          const inCol = Array.isArray(inEntry[col]) ? inEntry[col] : [];

          entry[col].forEach((block, bIndex) => {
            const inBlock = inCol[bIndex];
            if (!inBlock || typeof inBlock !== 'object') return;
            if ('cat' in inBlock) block.cat = str(inBlock.cat);

            if (!Array.isArray(block.rows)) return;
            const inRows = Array.isArray(inBlock.rows) ? inBlock.rows : [];

            block.rows.forEach((row, rIndex) => {
              const inRow = inRows[rIndex];
              if (!Array.isArray(inRow)) return;
              // [name, price, size] — each cell optional, order fixed.
              for (let c = 0; c < 3; c += 1) {
                if (typeof inRow[c] === 'string') row[c] = inRow[c];
              }
            });
          });
        }
      }
    });
  });

  return next;
}

/** Reads the live menu, falling back to the bundled seed on an empty/failed store. */
export async function readMenu() {
  try {
    const stored = await store().get(MENU_KEY, { type: 'json' });
    if (stored && Array.isArray(stored.sections) && stored.sections.length) {
      // Menus saved before Live Shows existed have no such key.
      if (!stored.liveShows) stored.liveShows = structuredClone(SEED_MENU.liveShows);
      return stored;
    }
  } catch (error) {
    console.error('Blobs read failed, serving bundled seed menu:', error);
  }
  return structuredClone(SEED_MENU);
}

/**
 * Persists an edit.
 *
 * The menu and Live Shows have deliberately different rules: the menu is
 * text-only because its pages, photography and framing are designed, while Live
 * Shows is fully editable because events come and go every month.
 */
export async function saveEdits(incoming) {
  const current = await readMenu();
  const next = applyTextEdits(current, incoming);
  next.liveShows = sanitiseLiveShows(incoming?.liveShows, current.liveShows);
  next.updatedAt = new Date().toISOString();
  await store().setJSON(MENU_KEY, next);
  return next;
}
