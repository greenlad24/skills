import { getStore } from '@netlify/blobs';
import { randomUUID } from 'node:crypto';
import { SEED_MENU } from './seed.mjs';

const STORE_NAME = 'vibration-menu';
const MENU_KEY = 'menu';

// Strong consistency: after the editor hits Save, the very next read of the
// public menu must show the new price rather than a stale cached one.
function store() {
  return getStore({ name: STORE_NAME, consistency: 'strong' });
}

function id() {
  return randomUUID().slice(0, 8);
}

function cleanString(value, fallback = '') {
  return typeof value === 'string' ? value.trim() : fallback;
}

/**
 * Coerces whatever is in the store (or came from the editor) into the shape the
 * rest of the app relies on. Prices stay strings on purpose so "14", "9 / 12"
 * and "market price" are all expressible.
 */
export function normalizeMenu(input) {
  const raw = input && typeof input === 'object' ? input : {};
  const sections = Array.isArray(raw.sections) ? raw.sections : [];

  return {
    restaurant: {
      name: cleanString(raw.restaurant?.name, SEED_MENU.restaurant.name),
      tagline: cleanString(raw.restaurant?.tagline),
      note: cleanString(raw.restaurant?.note),
    },
    currency: cleanString(raw.currency, '$'),
    sections: sections
      .filter((section) => section && typeof section === 'object')
      .map((section) => ({
        id: cleanString(section.id) || id(),
        name: cleanString(section.name, 'Untitled section'),
        description: cleanString(section.description),
        items: (Array.isArray(section.items) ? section.items : [])
          .filter((item) => item && typeof item === 'object')
          .map((item) => ({
            id: cleanString(item.id) || id(),
            name: cleanString(item.name, 'Untitled item'),
            description: cleanString(item.description),
            price: cleanString(item.price),
            available: item.available !== false,
          })),
      })),
    updatedAt: cleanString(raw.updatedAt) || null,
  };
}

/** Reads the live menu, falling back to the bundled seed on an empty/failed store. */
export async function readMenu() {
  try {
    const stored = await store().get(MENU_KEY, { type: 'json' });
    if (stored && Array.isArray(stored.sections)) return normalizeMenu(stored);
  } catch (error) {
    console.error('Blobs read failed, serving bundled fallback menu:', error);
  }
  return normalizeMenu(SEED_MENU);
}

export async function writeMenu(menu) {
  const normalized = normalizeMenu(menu);
  normalized.updatedAt = new Date().toISOString();
  await store().setJSON(MENU_KEY, normalized);
  return normalized;
}
