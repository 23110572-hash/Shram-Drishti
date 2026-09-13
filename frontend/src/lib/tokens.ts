/** Token storage.
 *
 *  Deliberate split:
 *
 *  - **Access token lives in memory only.** Never written to storage, so an XSS
 *    payload cannot read a usable API credential out of localStorage. It is
 *    re-derived from the refresh token on page load.
 *  - **Refresh token lives in localStorage.** It has to survive a reload, and
 *    it is single-use with rotation, so a stolen one is detectable server-side
 *    the moment either party uses it twice.
 *
 *  Production upgrade: move the refresh token to an httpOnly, Secure,
 *  SameSite=Strict cookie so it is unreadable from JavaScript entirely. That
 *  needs a backend change (set-cookie on login, read cookie on refresh), which
 *  is why it is not done here.
 */

const REFRESH_KEY = "sd.refresh";

let accessToken: string | null = null;

/** Subscribers notified when the session appears or disappears, so React can
 *  re-render without polling. */
type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    // Private browsing modes can throw on storage access. Treat as no session
    // rather than crashing the app shell.
    return null;
  }
}

export function setTokens(access: string, refresh: string): void {
  accessToken = access;
  try {
    localStorage.setItem(REFRESH_KEY, refresh);
  } catch {
    /* session becomes tab-scoped; acceptable degradation */
  }
  notify();
}

export function clearTokens(): void {
  accessToken = null;
  try {
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* nothing to do */
  }
  notify();
}

export function hasStoredSession(): boolean {
  return getRefreshToken() !== null;
}
