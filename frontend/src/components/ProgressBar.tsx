export function ProgressBar({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div className="progress" title={`${clamped}%`}>
      <span style={{ width: `${clamped}%` }} />
    </div>
  );
}
