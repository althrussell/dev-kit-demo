import type { RiskBand } from '../types';

export function RiskPill({ band }: { band: RiskBand }) {
  const cls =
    band === 'critical'
      ? 'pill pill-critical'
      : band === 'high'
        ? 'pill pill-high'
        : band === 'medium'
          ? 'pill pill-medium'
          : 'pill pill-low';
  return <span className={cls}>{band}</span>;
}
