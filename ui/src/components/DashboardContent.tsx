import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { ArrowUpRight, User } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchJson, type DashboardStats } from '../api';
import { CustomSelect } from './CustomSelect';

function formatPoints(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function DashboardContent() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<string>('__all__');

  useEffect(() => {
    const load = (force = false) =>
      fetchJson<DashboardStats>(`/api/dashboard${force ? '?refresh=1' : ''}`)
        .then((data) => {
          setStats(data);
          setSelectedAccount((prev) => {
            if (prev !== '__all__') return prev;
            if (data.accounts?.length === 1) return data.accounts[0].username;
            return prev;
          });
        })
        .catch(() => {});
    load(false);
    const delayed = window.setTimeout(() => load(true), 800);
    const t = window.setInterval(() => load(false), 30000);
    return () => {
      window.clearTimeout(delayed);
      window.clearInterval(t);
    };
  }, []);

  const perStreamerRows = useMemo(() => {
    if (!stats) return [];
    if (selectedAccount === '__all__') {
      return Object.entries(stats.per_streamer || {}).sort(([, a], [, b]) => b - a);
    }
    const acc = stats.accounts.find((a) => a.username === selectedAccount);
    if (!acc?.by_streamer) return [];
    return Object.entries(acc.by_streamer).sort(([, a], [, b]) => b - a);
  }, [stats, selectedAccount]);

  const totalForSelection = useMemo(() => {
    if (!stats) return 0;
    if (selectedAccount === '__all__') return stats.total_points;
    const acc = stats.accounts.find((a) => a.username === selectedAccount);
    return acc?.points ?? 0;
  }, [stats, selectedAccount]);

  const cards = [
    {
      label: selectedAccount === '__all__' ? 'Всего баллов' : `Баллы @${selectedAccount}`,
      value: stats ? formatPoints(totalForSelection) : '—',
      change: 'twitch gql',
    },
    {
      label: 'Активных сессий',
      value: stats ? String(stats.active_sessions) : '—',
      change: 'running',
    },
    {
      label: 'Онлайн стримеров',
      value: stats ? String(stats.online_streamers) : '—',
      change: 'live now',
    },
    {
      label: 'Аккаунтов в панели',
      value: stats ? String(stats.accounts.length) : '—',
      change: 'tracked',
    },
  ];

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative p-10 rounded-[32px] bg-card-bg border border-border overflow-hidden"
      >
        <div className="relative z-10 max-w-2xl">
          <div className="inline-block px-3 py-1 border border-lime/30 rounded-full bg-lime/5 text-lime text-[10px] font-mono mb-6 tracking-widest uppercase">
            production dashboard
          </div>
          <h1 className="text-4xl md:text-5xl font-black mb-4 tracking-tighter lowercase">
            twitch point miner
          </h1>
          <p className="text-gray-400 leading-relaxed text-lg font-light lowercase">
            единая панель: стримеры, аккаунты, сессии и логи. баллы — через twitch gql.
          </p>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {cards.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="p-6 rounded-3xl bg-card-bg border border-border hover:border-lime transition-all duration-300 group"
          >
            <span className="text-text-muted font-mono text-xs uppercase tracking-widest">
              {stat.label}
            </span>
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 mt-4">
              <h3 className="text-4xl font-black tracking-tighter group-hover:text-lime transition-colors">
                {stat.value}
              </h3>
              <div className="flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-lg bg-lime/10 text-lime border border-lime/20">
                <ArrowUpRight className="w-3 h-3" />
                {stat.change}
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {stats && stats.accounts.length > 0 && (
        <div className="rounded-3xl bg-card-bg border border-border p-6 space-y-6">
          <h3 className="text-sm font-mono text-lime lowercase">баллы по аккаунтам (twitch gql)</h3>
          <div className="space-y-2">
            {stats.accounts.map((a) => (
              <button
                key={a.username}
                type="button"
                onClick={() => setSelectedAccount(a.username)}
                className={cn(
                  'w-full flex justify-between text-sm font-mono border-b border-border/50 py-2 px-2 rounded-lg transition-colors text-left',
                  selectedAccount === a.username && 'bg-lime/10 border-lime/30'
                )}
              >
                <span className="text-text-muted">{a.username}</span>
                <span className="text-main">{formatPoints(a.points)} pts</span>
              </button>
            ))}
          </div>

          <div>
            <div className="flex flex-wrap items-end justify-between gap-4 mb-3">
              <h3 className="text-sm font-mono text-lime lowercase">баллы по стримерам</h3>
              <CustomSelect
                compact
                icon={User}
                value={selectedAccount}
                onChange={setSelectedAccount}
                options={[
                  { value: '__all__', label: 'все аккаунты (сумма)' },
                  ...stats.accounts.map((a) => ({
                    value: a.username,
                    label: a.username,
                  })),
                ]}
              />
            </div>
            {perStreamerRows.length === 0 ? (
              <p className="text-text-muted text-xs font-mono lowercase">
                нет данных — нужен cookie и стримеры в config
              </p>
            ) : (
              <div className="space-y-2">
                {perStreamerRows.map(([login, pts]) => (
                  <div
                    key={login}
                    className="flex justify-between text-sm font-mono border-b border-border/50 py-2"
                  >
                    <span className="text-text-muted">@{login}</span>
                    <span className="text-main">{formatPoints(pts)} pts</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
