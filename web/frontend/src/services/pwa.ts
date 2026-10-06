/**
 * PWA Utilities for ST-EVA
 * Handles service worker registration, standalone detection, and installation prompt.
 */

export function registerServiceWorker(): void {
  if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js')
        .then((registration) => {
          // Check for periodic updates
          registration.onupdatefound = () => {
            const installingWorker = registration.installing;
            if (installingWorker) {
              installingWorker.onstatechange = () => {
                if (installingWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  // New version available
                  console.info('ST-EVA PWA: New version ready.');
                }
              };
            }
          };
        })
        .catch((error) => {
          console.warn('ST-EVA PWA: Service Worker registration failed:', error);
        });
    });
  }
}

export function isStandaloneMode(): boolean {
  if (typeof window === 'undefined') return false;
  const matchMediaStandalone =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(display-mode: standalone)').matches;
  return (
    Boolean(matchMediaStandalone) ||
    (window.navigator as any)?.standalone === true ||
    (typeof document !== 'undefined' && document.referrer.includes('android-app://'))
  );
}
