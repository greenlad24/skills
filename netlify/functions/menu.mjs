import { readMenu } from '../lib/store.mjs';

/** Public menu feed. No auth: this is what diners see. */
export default async () => {
  const menu = await readMenu();
  return Response.json(menu, {
    headers: {
      // Short cache so a price change shows up promptly, with SWR to keep the
      // page instant for the next visitor while it revalidates.
      'Cache-Control': 'public, max-age=0, must-revalidate',
      'Netlify-CDN-Cache-Control': 'public, s-maxage=30, stale-while-revalidate=300',
    },
  });
};

export const config = { path: '/api/menu' };
