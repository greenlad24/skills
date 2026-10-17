import { useSyncExternalStore } from 'react';

export type Route = 'show' | 'mix' | 'fx' | 'golive' | 'slate' | 'apps' | 'keys';
const ROUTES: Route[] = ['show', 'mix', 'fx', 'golive', 'slate', 'apps', 'keys'];

const read = (): Route => {
  const r = location.hash.replace(/^#\/?/, '') as Route;
  return ROUTES.includes(r) ? r : 'show';
};

export function useRoute() {
  return useSyncExternalStore((f) => { addEventListener('hashchange', f); return () => removeEventListener('hashchange', f); }, read);
}

export const go = (r: Route) => { location.hash = `/${r}`; };
