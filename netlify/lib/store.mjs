import { storage } from './blobs.mjs';
import { SEED_MENU } from './seed.mjs';
import { sanitiseLiveShows } from './shows.mjs';

const MENU_KEY = 'menu';

const store = () => storage('menu');

const str = (v) => (typeof v === 'string' ? v : '');

/**
 * Visibility is the one non-text thing the editor may set on the menu: a dish
 * that has run out comes off the published menu without deleting the page it
 * lives on, so putting it back is one tap rather than a rebuild.
 */
const isHidden = (v) => v === true;

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
    if ('hidden' in inSection) section.hidden = isHidden(inSection.hidden);

    const inEntries = Array.isArray(inSection.entries) ? inSection.entries : [];

    section.entries.forEach((entry, eIndex) => {
      const inEntry = inEntries[eIndex];
      if (!inEntry || typeof inEntry !== 'object') return;

      for (const field of TEXT_FIELDS[entry.type] || []) {
        if (field in inEntry) entry[field] = str(inEntry[field]);
      }

      if ('hidden' in inEntry) entry.hidden = isHidden(inEntry.hidden);

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
              // A fourth cell hides the line; the page renderer only reads 0–2.
              if (inRow.length > 3) row[3] = isHidden(inRow[3]);
            });
          });
        }
      }
    });
  });

  return next;
}

/**
 * The published view of the menu: everything marked hidden is removed here
 * rather than in the page, so a hidden dish is not merely invisible — it never
 * reaches the browser at all. The editor keeps reading the full stored menu.
 *
 * Emptied containers go too: a category with no lines left would print a
 * heading over nothing, and a section with no pages would open an empty book.
 */
export function withVisibleOnly(menu) {
  const visible = structuredClone(menu);

  visible.sections = visible.sections
    .filter((section) => !section.hidden)
    .map((section) => {
      section.entries = section.entries.filter((entry) => !entry.hidden);

      for (const entry of section.entries) {
        if (entry.type !== 'list') continue;
        for (const col of ['col1', 'col2']) {
          if (!Array.isArray(entry[col])) continue;
          entry[col] = entry[col]
            .map((block) => ({ ...block, rows: (block.rows || []).filter((row) => row[3] !== true) }))
            .filter((block) => block.rows.length);
        }
      }

      return section;
    })
    .filter((section) => section.entries.length);

  if (visible.liveShows?.hidden) delete visible.liveShows;

  return visible;
}

/** Reads the live menu, falling back to the bundled seed on an empty/failed store. */
export async function readMenu() {
  try {
    const stored = await store().getJSON(MENU_KEY);
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
