import React, { useEffect, useState } from 'react';
import { fetchJson } from '../api';
import { cn } from '../lib/utils';

type SystemResponse = {
  runner_health?: string;
  status?: string;
  multi_session?: { runner_health?: string };
};

const STYLES: Record<string, string> = {
  Healthy: 'bg-lime/15 text-lime border-lime/40',
  Degraded: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  Stopped: 'bg-red-500/15 text-red-300 border-red-500/40',
};

export function RunnerHealthBadge() {
  const [health, setHealth] = useState<string>('—');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await fetchJson<SystemResponse>('/api/system');
        if (cancelled) return;
        const h =
          data.runner_health ||
          data.multi_session?.runner_health ||
          data.status ||
          'Stopped';
        setHealth(h);
      } catch {
        if (!cancelled) setHealth('Stopped');
      }
    };
    load();
    const id = setInterval(load, 12_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const label = health === 'Healthy' ? 'runner ok' : health === 'Degraded' ? 'runner degraded' : 'runner stopped';

  return (
    <span
      className={cn(
        'text-[10px] font-mono lowercase px-2.5 py-1 rounded-lg border',
        STYLES[health] || STYLES.Stopped
      )}
      title={`multi_session_runner: ${health}`}
    >
      {label}
    </span>
  );
}
