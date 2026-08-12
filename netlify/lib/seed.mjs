// Fallback menu, compiled into the functions bundle.
//
// This is only ever served when the Blobs store is empty or unreachable, so the
// public menu degrades to something sane instead of an error page. It is
// deliberately free of invented dishes and prices: showing a placeholder price
// on a real restaurant's menu is worse than showing nothing. Once the menu has
// been saved once from /admin, the stored version always wins.

export const SEED_MENU = {
  restaurant: {
    name: 'Vibration',
    tagline: '',
    note: '',
  },
  currency: '$',
  sections: [],
  updatedAt: null,
};
