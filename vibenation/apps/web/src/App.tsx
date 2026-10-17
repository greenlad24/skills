import { useEffect, useState } from 'react';
import { connect, useShow, useStatus } from './store';
import { useRoute } from './route';
import { Header } from './components/Header';
import { Login } from './screens/Login';
import { ShowScreen } from './screens/Show';
import { MixScreen } from './screens/Mix';
import { FxScreen } from './screens/Fx';
import { GoLiveScreen } from './screens/GoLive';
import { SlateScreen } from './screens/Slate';
import { AppsScreen } from './screens/Apps';

export function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const status = useStatus();
  const show = useShow();
  const route = useRoute();

  useEffect(() => {
    fetch('/api/me').then((r) => r.json()).then((m) => setAuthed(!!m.authed)).catch(() => setAuthed(false));
  }, []);
  useEffect(() => { if (authed) connect(); }, [authed]);
  useEffect(() => { if (status === 'unauthorized') setAuthed(false); }, [status]);

  if (authed === null) return null;
  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  if (!show) return <div className="vn-app" style={{ alignItems: 'center', justifyContent: 'center', color: 'var(--text-meta)' }}>Connecting to the show…</div>;

  return (
    <div className="vn-app">
      <Header />
      {status !== 'open' && (
        <div role="alert" style={{ padding: '10px 22px', background: 'var(--error-fill)', color: '#fff', fontWeight: 700 }}>Lost connection to the server — reconnecting…</div>
      )}
      {route === 'show' && <ShowScreen />}
      {route === 'mix' && <MixScreen />}
      {route === 'fx' && <FxScreen />}
      {route === 'golive' && <GoLiveScreen />}
      {route === 'slate' && <SlateScreen />}
      {route === 'apps' && <AppsScreen />}
    </div>
  );
}
