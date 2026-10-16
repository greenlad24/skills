import { useEffect, useState } from 'react';
import { CHANNELS, type HealthResponse } from '@vibenation/shared';

// Milestone 1 placeholder: proves web ↔ server wiring. The real screens arrive in milestone 2.
export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  useEffect(() => {
    fetch('/api/health').then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
  }, []);
  return (
    <main style={{ padding: 32 }}>
      <h1 style={{ fontFamily: 'var(--font-display)', margin: 0 }}>VibeNation</h1>
      <p style={{ color: 'var(--text-2)' }}>
        Server: {health ? `OK · v${health.version} · up ${health.uptimeS}s` : 'not reachable'} · {CHANNELS.length} channels
      </p>
    </main>
  );
}
