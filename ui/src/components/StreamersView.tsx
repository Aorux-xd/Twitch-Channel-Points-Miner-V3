import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Plus, Trash2, ExternalLink, ShieldCheck, Star, X } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchJson, type Streamer } from '../api';

export function StreamersView() {
  const [showForm, setShowForm] = React.useState(false);
  const [streamers, setStreamers] = React.useState<Streamer[]>([]);
  const [newLogin, setNewLogin] = React.useState('');
  const [claimDrops, setClaimDrops] = React.useState(true);
  const [highPriority, setHighPriority] = React.useState(false);

  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = async (force = false) => {
    try {
      setError(null);
      const url = force ? '/api/streamers?refresh=1' : '/api/streamers';
      const data = await fetchJson<{ streamers: Streamer[] }>(url);
      setStreamers(data.streamers || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    refresh(false);
    const t = window.setInterval(() => refresh(false), 45000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <div className="p-8 space-y-6 max-w-[1600px] mx-auto relative text-main">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-black lowercase flex items-center gap-4">
            <span className="w-12 h-1 bg-lime"></span> управление стримерами
          </h2>
          <p className="text-text-muted text-sm mt-1 lowercase font-mono">глобальный список каналов для всех аккаунтов</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => refresh(true)}
            className="px-4 py-3 rounded-xl border border-border font-mono text-xs hover:border-lime"
          >
            обновить twitch
          </button>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-6 py-3 bg-lime text-black font-bold rounded-xl hover:shadow-[0_0_30px_-5px_rgba(204,255,0,0.5)] transition-all lowercase"
          >
            <Plus className="w-5 h-5" /> добавить канал
          </button>
        </div>
      </div>

      {error && (
        <p className="text-red-400 font-mono text-sm">{error}</p>
      )}
      {loading && streamers.length === 0 && (
        <p className="text-text-muted font-mono text-sm">загрузка из кэша...</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {streamers.map((s, i) => (
          <motion.div
            key={s.login}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.05 }}
            className="p-6 rounded-[24px] bg-card-bg border border-border group hover:border-lime transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_10px_40px_-10px_rgba(204,255,0,0.1)] relative overflow-hidden"
          >
            <div className="flex items-start justify-between mb-4 relative z-10">
              <div className="flex items-center gap-4">
                <div className="relative">
                  <div className="w-14 h-14 rounded-xl bg-dashboard-bg border border-border overflow-hidden">
                    <img
                      src={s.avatar_url || `https://api.dicebear.com/7.x/avataaars/svg?seed=${s.login}`}
                      alt={s.login}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  {s.is_live && (
                    <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-lime rounded-full border-[3px] border-card-bg" />
                  )}
                </div>
                <div>
                  <h3 className="font-bold group-hover:text-lime transition-colors text-lg tracking-tight lowercase">
                    {s.display_name || s.login}
                  </h3>
                  <p className="text-xs text-text-muted font-mono">@{s.login}</p>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    await fetchJson(`/api/streamers/${encodeURIComponent(s.login)}`, {
                      method: 'DELETE',
                    });
                    refresh();
                  }}
                  className="p-2 rounded-xl hover:bg-dashboard-bg text-text-muted hover:text-red-500 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
                <a
                  href={`https://twitch.tv/${s.login}`}
                  target="_blank"
                  rel="noreferrer"
                  className="p-2 rounded-xl hover:bg-dashboard-bg text-text-muted hover:text-lime transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 mb-4 relative z-10">
              {s.claim_drops && (
                <span className="px-2 py-1 bg-lime/5 border border-lime/30 text-lime text-[10px] font-mono lowercase rounded">
                  авто-сбор
                </span>
              )}
              {s.high_priority && (
                <span className="px-2 py-1 bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-mono lowercase rounded">
                  приоритет
                </span>
              )}
              <span className={cn(
                "px-2 py-1 text-[10px] font-mono lowercase rounded border",
                s.is_live ? "text-lime border-lime/30 bg-lime/5" : "text-text-muted border-border"
              )}>
                {s.is_live ? 'online' : 'offline'}
              </span>
            </div>
          </motion.div>
        ))}
      </div>

      <AnimatePresence>
        {showForm && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 sm:p-0">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowForm(false)}
              className="absolute inset-0 bg-black/80 backdrop-blur-md"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="relative w-full max-w-lg bg-card-bg border border-lime/30 rounded-[24px] p-8 shadow-[0_0_50px_rgba(204,255,0,0.1)]"
            >
              <div className="flex justify-between items-center mb-6 text-main">
                <h3 className="text-2xl font-black lowercase tracking-tighter">добавить канал</h3>
                <button onClick={() => setShowForm(false)} className="p-2 rounded-xl hover:bg-white/5">
                  <X className="w-5 h-5 text-text-muted" />
                </button>
              </div>

              <form className="space-y-6" onSubmit={(e) => e.preventDefault()}>
                <div>
                  <label className="block text-[10px] font-mono text-lime lowercase tracking-widest mb-2">login</label>
                  <input
                    type="text"
                    placeholder="напр. esl_csgo"
                    value={newLogin}
                    onChange={(e) => setNewLogin(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-dashboard-bg border border-border text-main font-mono text-sm focus:outline-none focus:ring-1 focus:ring-lime"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <button
                    type="button"
                    onClick={() => setClaimDrops(!claimDrops)}
                    className={cn(
                      "flex items-center gap-3 p-4 rounded-xl border transition-colors",
                      claimDrops ? "border-lime/50 bg-lime/5" : "border-border bg-dashboard-bg"
                    )}
                  >
                    <ShieldCheck className={cn("w-6 h-6", claimDrops ? "text-lime" : "text-text-muted")} />
                    <span className="text-[10px] font-mono lowercase">авто-сбор</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setHighPriority(!highPriority)}
                    className={cn(
                      "flex items-center gap-3 p-4 rounded-xl border transition-colors",
                      highPriority ? "border-lime/50 bg-lime/5" : "border-border bg-dashboard-bg"
                    )}
                  >
                    <Star className={cn("w-6 h-6", highPriority ? "text-lime" : "text-text-muted")} />
                    <span className="text-[10px] font-mono lowercase">приоритет</span>
                  </button>
                </div>
                <button
                  onClick={async () => {
                    const login = newLogin.trim();
                    if (!login) return;
                    await fetchJson('/api/streamers', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ login, claim_drops: claimDrops, high_priority: highPriority }),
                    });
                    setNewLogin('');
                    setClaimDrops(true);
                    setHighPriority(false);
                    setShowForm(false);
                    await refresh(false);
                    fetchJson('/api/streamers?refresh=1').catch(() => {});
                  }}
                  className="w-full py-4 bg-lime text-black font-bold rounded-xl hover:bg-white lowercase"
                >
                  добавить в список
                </button>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
