/** White "YOU" lock badge: this control is held by a human for the rest of the stream. */
export function YouBadge() {
  return (
    <span aria-label="Held by you" title="Held by you for the rest of the stream"
      style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: 'var(--text-1)', filter: 'drop-shadow(0 0 6px rgba(245,238,230,0.7))' }}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
      <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: '0.04em' }}>YOU</span>
    </span>
  );
}
