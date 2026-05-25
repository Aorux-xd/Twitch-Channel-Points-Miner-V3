import React, { useEffect, useRef, useState, useMemo } from 'react';
import { Terminal as TerminalIcon, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchJson } from '../api';

type LogLine = {
  id: string;
  ts: number;
  level: string;
  category: string;
  text: string;
};

const FILTERS = [
  { id: 'all', label: 'все' },
  { id: 'auth', label: 'авторизация' },
  { id: 'session', label: 'сессии' },
  { id: 'streamer', label: 'стримеры' },
  { id: 'points', label: 'баллы' },
  { id: 'reward', label: 'награды' },
  { id: 'error', label: 'ошибки' },
];

function parseMinerLine(line: string, username: string): Partial<LogLine> {
  const m = line.match(/^(\d{2}\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2}) - (\w+) -/);
  const level = m ? m[2].toLowerCase() : 'info';
  let category = 'miner';
  if (line.includes('Offline') || line.includes('Online')) category = 'streamer';
  if (line.includes('points') || line.includes('Points') || line.includes('🚀')) category = 'points';
  if (level === 'error') category = 'error';
  if (line.includes('Join IRC') || line.includes('session')) category = 'session';
  if (
    line.includes('twitch.tv/activate') ||
    line.includes('enter this code') ||
    /code:\s*[A-Z0-9]{4,10}/i.test(line)
  ) {
    category = 'auth';
  }
  return { level, category, text: `[${username}] ${line}` };
}

export function LogsView() {
  const [lines, setLines] = useState<LogLine[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const offsetsRef = useRef<Record<string, number>>({});
  const [filter, setFilter] = useState('all');
  const [usernames, setUsernames] = useState<string[]>([]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines, filter]);

  useEffect(() => {
    fetchJson<{ accounts: { username: string }[] }>('/api/accounts')
      .then((d) => {
        const names = (d.accounts || []).map((a) => a.username);
        setUsernames(names);
        offsetsRef.current = Object.fromEntries(names.map((u) => [u, 0]));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      try {
        const merged: LogLine[] = [];

        const events = await fetchJson<{ events: Array<Record<string, unknown>> }>(
          '/api/events'
        ).catch(() => ({ events: [] }));

        for (const ev of events.events || []) {
          const parts = [String(ev.message || '')];
          if (ev.account) parts.push(`[${ev.account}]`);
          if (ev.streamer) parts.push(`@${ev.streamer}`);
          if (ev.points) parts.push(`+${ev.points}`);
          merged.push({
            id: `ev-${ev.ts}-${String(ev.message).slice(0, 24)}`,
            ts: Number(ev.ts) || 0,
            level: String(ev.level || 'info'),
            category: String(ev.category || 'platform'),
            text: parts.join(' '),
          });
        }

        for (const username of usernames) {
          const offset = offsetsRef.current[username] ?? 0;
          const data = await fetchJson<{ chunk: string; nextOffset: number }>(
            `/api/logs?username=${encodeURIComponent(username)}&offset=${offset}`
          ).catch(() => null);
          if (!data?.chunk) continue;
          offsetsRef.current[username] = Number(data.nextOffset ?? offset);
          data.chunk.split(/\r?\n/).forEach((line, i) => {
            if (!line.trim()) return;
            const parsed = parseMinerLine(line, username);
            merged.push({
              id: `log-${username}-${offset}-${i}`,
              ts: 0,
              level: parsed.level || 'info',
              category: parsed.category || 'miner',
              text: parsed.text || line,
            });
          });
        }

        if (!cancelled) {
          merged.sort((a, b) => (a.ts !== b.ts ? a.ts - b.ts : a.text.localeCompare(b.text)));
          setLines(merged.slice(-5000));
        }
      } catch {
        /* ignore */
      }
    };

    tick();
    const t = window.setInterval(tick, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [usernames]);

  const filtered = useMemo(() => {
    return lines.filter((l) => {
      if (filter === 'all') return true;
      if (filter === 'error') return l.level === 'error' || l.level === 'warning';
      return l.category === filter;
    });
  }, [lines, filter]);

  return (
    <div className="p-8 space-y-6 max-w-[1600px] mx-auto h-[calc(100vh-140px)] flex flex-col text-main">
      <div className="flex justify-between items-center flex-wrap gap-4">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-3">
            <TerminalIcon className="w-6 h-6 text-lime" /> консоль
          </h2>
          <p className="text-text-muted text-sm mt-1">
            события панели и логи всех ботов ({usernames.length})
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setLines([]);
            offsetsRef.current = Object.fromEntries(usernames.map((u) => [u, 0]));
          }}
          className="p-2 rounded-xl border border-border text-text-muted hover:text-red-500"
          title="Очистить экран"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-mono lowercase border',
              filter === f.id ? 'border-lime text-lime bg-lime/10' : 'border-border text-text-muted'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="flex-1 bg-[#0d0e12] rounded-[32px] border border-[#1e202a] overflow-hidden flex flex-col min-h-0 font-mono">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-1 custom-scrollbar text-xs">
          {filtered.length === 0 && (
            <p className="text-zinc-500">нет записей — запустите бота или дождитесь событий</p>
          )}
          {filtered.map((line) => (
            <div key={line.id} className="flex gap-3 leading-relaxed">
              <span
                className={cn(
                  'w-14 shrink-0 font-bold uppercase',
                  line.level === 'error' && 'text-red-400',
                  line.level === 'warning' && 'text-amber-400',
                  line.level === 'success' && 'text-emerald-400',
                  line.level === 'info' && 'text-blue-400'
                )}
              >
                {line.level}
              </span>
              <span className="text-zinc-500 w-16 shrink-0">{line.category}</span>
              <span
                className={cn(
                  'flex-1 whitespace-pre-wrap break-words',
                  line.category === 'auth' ? 'text-lime font-bold' : 'text-zinc-300'
                )}
              >
                {line.text}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
