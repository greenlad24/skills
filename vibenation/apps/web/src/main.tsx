import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { CamPage } from './cam/CamPage';
import './theme.css';

// /cam = phone camera page (no login, the QR invite is the key). Everything else = the app.
const isCam = location.pathname === '/cam' || location.pathname.startsWith('/cam/');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isCam ? <CamPage /> : <App />}
  </StrictMode>,
);
