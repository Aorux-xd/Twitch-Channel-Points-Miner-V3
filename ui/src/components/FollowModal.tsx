import React, { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, UserPlus, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchJson, type Account } from '../api';
import { CustomSelect } from './CustomSelect';

type FollowResult = {
  account: string;
  ok: boolean;
  skipped?: boolean;
  error?: string | null;
};

type FollowResponse = {
  ok: boolean;
  ok_count?: number;
  skipped?: number;
  total?: number;
  error?: string;
  results?: FollowResult[];
};

interface FollowModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function FollowModal({ isOpen, onClose }: FollowModalProps) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [targetLogin, setTargetLogin] = useState('');
  const [selectedSession, setSelectedSession] = useState('Все сессии');
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<FollowResponse | null>(null);

  const cookieAccounts = useMemo(
    () => accounts.filter((a) => a.has_cookie),
    [accounts]
  );

  const sessionOptions = useMemo(
    () => ['Все сессии', ...cookieAccounts.map((a) => a.username)],
    [cookieAccounts]
  );

  useEffect(() => {
    if (!isOpen) return;
    setLastResult(null);
    fetchJson<{ accounts: Account[] }>('/api/accounts')
      .then((d) => setAccounts(d.accounts || []))
      .catch(console.error);
  }, [isOpen]);

  const handleFollow = async () => {
    const login = targetLogin.trim().toLowerCase();
    if (!login) return;
    setRunning(true);
    setLastResult(null);
    try {
      const data = await fetchJson<FollowResponse>('/api/follow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ login, session: selectedSession }),
      });
      setLastResult(data);
    } catch (e) {
      setLastResult({
        ok: false,
        error: e instanceof Error ? e.message : 'ошибка',
        results: [],
      });
    } finally {
      setRunning(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/80 backdrop-blur-md">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 16 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-lg bg-card-bg border border-lime/30 rounded-[24px] shadow-[0_0_50px_rgba(204,255,0,0.1)]"
          >
            <div className="p-6 border-b border-border flex justify-between items-center">
              <div>
                <h2 className="text-xl font-black lowercase">фоловнуться</h2>
                <p className="text-xs text-text-muted font-mono mt-1">
                  helix · пропуск если уже в подписках
                </p>
              </div>
              <button type="button" onClick={onClose} className="p-2 rounded-xl hover:bg-white/5">
                <X className="w-5 h-5 text-text-muted" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <CustomSelect
                label="сессия"
                options={sessionOptions.length > 1 ? sessionOptions : ['нет cookie']}
                value={selectedSession}
                onChange={setSelectedSession}
              />
              <div className="space-y-2">
                <label className="text-[10px] font-mono text-lime ml-1">ник стримера</label>
                <input
                  type="text"
                  value={targetLogin}
                  onChange={(e) => setTargetLogin(e.target.value)}
                  placeholder="channel_login"
                  className="w-full h-11 px-4 rounded-xl bg-dashboard-bg border border-border font-mono text-sm lowercase"
                />
              </div>

              {lastResult && (
                <div className="rounded-xl border border-border bg-dashboard-bg p-4 space-y-2 font-mono text-xs">
                  <p className={cn('font-bold', lastResult.ok ? 'text-lime' : 'text-red-400')}>
                    {lastResult.ok
                      ? `новых: ${lastResult.ok_count ?? 0}, пропущено: ${lastResult.skipped ?? 0} / ${lastResult.total ?? 0}`
                      : lastResult.error || 'ошибка'}
                  </p>
                  {(lastResult.results || []).map((r) => (
                    <div
                      key={r.account}
                      className="flex justify-between gap-2 border-t border-border/50 pt-2"
                    >
                      <span className="text-text-muted">{r.account}</span>
                      <span className={cn('text-right max-w-[70%]', r.ok ? 'text-lime' : 'text-red-400')}>
                        {r.skipped ? 'уже подписан' : r.ok ? 'ok' : r.error}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              <button
                type="button"
                disabled={!targetLogin.trim() || running || cookieAccounts.length === 0}
                onClick={handleFollow}
                className={cn(
                  'w-full py-4 rounded-xl font-bold lowercase flex items-center justify-center gap-2',
                  targetLogin.trim() && !running
                    ? 'bg-lime text-black hover:bg-white'
                    : 'bg-dashboard-bg text-text-muted border border-border cursor-not-allowed'
                )}
              >
                {running ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <UserPlus className="w-4 h-4" />
                )}
                {running ? 'подписка…' : 'подписаться'}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
