import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, Users, MessageSquare, Zap, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchJson, type Account, type Streamer } from '../api';
import { CustomSelect } from './CustomSelect';

interface PointsRewardFormProps {
  isOpen: boolean;
  onClose?: () => void;
  /** modal — overlay; page — embedded on /points tab */
  variant?: 'modal' | 'page';
}

type Reward = {
  id: string;
  name: string;
  cost: number;
  requiresText: boolean;
  inStock?: boolean;
  isEnabled?: boolean;
};

type ActivateResult = {
  account: string;
  ok: boolean;
  error?: string;
  code?: string;
  redemption_id?: string;
  status?: string;
};

type ActivateResponse = {
  ok: boolean;
  partial?: boolean;
  ok_count?: number;
  fail_count?: number;
  total?: number;
  error?: string;
  results?: ActivateResult[];
};

export function PointsRewardForm({
  isOpen,
  onClose,
  variant = 'modal',
}: PointsRewardFormProps) {
  const isPage = variant === 'page';
  const [streamers, setStreamers] = useState<Streamer[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [rewards, setRewards] = useState<Reward[]>([]);
  const [loadingRewards, setLoadingRewards] = useState(false);
  const [activating, setActivating] = useState(false);
  const [lastResult, setLastResult] = useState<ActivateResponse | null>(null);

  const [selectedStreamer, setSelectedStreamer] = useState('');
  const [selectedSession, setSelectedSession] = useState('Все сессии');
  const [selectedReward, setSelectedReward] = useState<string | null>(null);
  const [rewardText, setRewardText] = useState('');

  const cookieAccounts = useMemo(
    () => accounts.filter((a) => a.has_cookie),
    [accounts]
  );

  const sessionOptions = useMemo(
    () => ['Все сессии', ...cookieAccounts.map((a) => a.username)],
    [cookieAccounts]
  );

  useEffect(() => {
    if (!isOpen && !isPage) return;
    setLastResult(null);
    Promise.all([
      fetchJson<{ streamers: Streamer[] }>('/api/streamers'),
      fetchJson<{ accounts: Account[] }>('/api/accounts'),
    ])
      .then(([st, acc]) => {
        const list = st.streamers || [];
        setStreamers(list);
        setAccounts(acc.accounts || []);
        if (list.length) setSelectedStreamer(list[0].login);
        setSelectedSession('Все сессии');
      })
      .catch(console.error);
  }, [isOpen, isPage]);

  useEffect(() => {
    if ((!isOpen && !isPage) || !selectedStreamer) return;
    const account =
      selectedSession !== 'Все сессии'
        ? selectedSession
        : cookieAccounts[0]?.username;

    setLoadingRewards(true);
    setRewards([]);
    setSelectedReward(null);

    const q = new URLSearchParams({ streamer: selectedStreamer });
    if (account) q.set('account', account);

    fetchJson<{ rewards: Reward[] }>(`/api/rewards?${q}`)
      .then((d) => setRewards(d.rewards || []))
      .catch(() => setRewards([]))
      .finally(() => setLoadingRewards(false));
  }, [isOpen, isPage, selectedStreamer, selectedSession, cookieAccounts]);

  const activeReward = rewards.find((r) => r.id === selectedReward);

  const handleActivate = async () => {
    if (!selectedReward || !selectedStreamer) return;
    setActivating(true);
    setLastResult(null);
    try {
      const data = await fetchJson<ActivateResponse>('/api/activate-reward', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          streamer: selectedStreamer,
          session: selectedSession,
          rewardId: selectedReward,
          rewardName: activeReward?.name,
          text: activeReward?.requiresText ? rewardText.trim() : null,
          textInput: activeReward?.requiresText ? rewardText.trim() : null,
        }),
      });
      setLastResult(data);
      if (data.ok) {
        setRewardText('');
        setSelectedReward(null);
      }
    } catch (error) {
      if (error instanceof Error && error.message !== 'Unauthorized') {
        setLastResult({ ok: false, error: error.message, results: [] });
      }
    } finally {
      setActivating(false);
    }
  };

  const enabledCount = rewards.filter((r) => r.isEnabled !== false).length;

  const canActivate =
    Boolean(selectedReward) &&
    cookieAccounts.length > 0 &&
    activeReward?.isEnabled !== false &&
    activeReward?.inStock !== false &&
    !(activeReward?.requiresText && !rewardText.trim());

  const inner = (
            <div className={cn('space-y-6', isPage ? 'p-0' : 'p-8')}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <CustomSelect
                  label="стример"
                  options={streamers.map((s) => s.login)}
                  value={selectedStreamer || '—'}
                  onChange={setSelectedStreamer}
                />
                <CustomSelect
                  label="сессия (боты)"
                  options={sessionOptions.length > 1 ? sessionOptions : ['нет cookie']}
                  value={selectedSession}
                  onChange={setSelectedSession}
                  icon={Users}
                />
              </div>

              <div className="space-y-3">
                <label className="text-[10px] font-mono lowercase tracking-widest text-lime ml-1">
                  доступные награды
                  {rewards.length > 0 && (
                    <span className="text-text-muted ml-2">
                      ({enabledCount} активных / {rewards.length} всего)
                    </span>
                  )}
                </label>
                {loadingRewards ? (
                  <div className="flex items-center gap-2 text-text-muted font-mono text-sm py-8 justify-center">
                    <Loader2 className="w-5 h-5 animate-spin" /> загрузка с twitch...
                  </div>
                ) : rewards.length === 0 ? (
                  <p className="text-sm text-text-muted font-mono py-6 text-center">
                    нет наград или нет cookie у выбранного бота
                  </p>
                ) : (
                  <div className="grid grid-cols-1 gap-2 max-h-[220px] overflow-y-auto pr-2 custom-scrollbar">
                    {rewards.map((reward) => {
                      const disabled = reward.isEnabled === false;
                      const outOfStock = reward.inStock === false;
                      return (
                      <button
                        key={reward.id}
                        type="button"
                        onClick={() => setSelectedReward(reward.id)}
                        className={cn(
                          'flex items-center justify-between p-4 rounded-xl border transition-all text-left',
                          selectedReward === reward.id
                            ? 'bg-lime border-lime text-black'
                            : 'bg-dashboard-bg border-border hover:border-lime/50',
                          disabled && 'opacity-50'
                        )}
                      >
                        <div className="flex items-center gap-4">
                          <div
                            className={cn(
                              'w-10 h-10 rounded-lg flex items-center justify-center border',
                              selectedReward === reward.id
                                ? 'bg-black text-lime'
                                : 'bg-card-bg'
                            )}
                          >
                            {reward.requiresText ? (
                              <MessageSquare className="w-5 h-5" />
                            ) : (
                              <Zap className="w-5 h-5" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <p className="font-bold text-sm lowercase truncate">{reward.name}</p>
                            <p className="text-[10px] font-mono opacity-70 truncate">
                              {disabled
                                ? 'отключена на канале · '
                                : ''}
                              {reward.requiresText
                                ? 'нужен текст · '
                                : ''}
                              {outOfStock ? 'нет в наличии' : disabled ? '' : 'доступна'}
                            </p>
                          </div>
                        </div>
                        <span className="text-xs font-mono">
                          {reward.cost.toLocaleString()} xp
                        </span>
                      </button>
                    );})}
                  </div>
                )}
              </div>

              <AnimatePresence>
                {activeReward?.requiresText && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="space-y-2"
                  >
                    <label className="text-[10px] font-mono text-lime ml-1">сообщение</label>
                    <input
                      type="text"
                      value={rewardText}
                      onChange={(e) => setRewardText(e.target.value)}
                      className="w-full h-[52px] px-5 rounded-xl bg-dashboard-bg border border-border font-mono text-sm"
                      placeholder="текст для награды"
                    />
                  </motion.div>
                )}
              </AnimatePresence>

              {lastResult && (
                <div className="rounded-xl border border-border bg-dashboard-bg p-4 space-y-2 font-mono text-xs">
                  <p
                    className={cn(
                      'font-bold lowercase',
                      lastResult.ok ? 'text-lime' : 'text-red-400'
                    )}
                  >
                    {lastResult.ok
                      ? lastResult.partial
                        ? `частично: ${lastResult.ok_count ?? 0} / ${lastResult.total ?? 0}`
                        : `успешно: ${lastResult.ok_count ?? 0} / ${lastResult.total ?? 0}`
                      : lastResult.error || 'все попытки неудачны'}
                  </p>
                  {(lastResult.results || []).map((r) => (
                    <div key={r.account} className="flex justify-between gap-2 border-t border-border/50 pt-2">
                      <span className="text-text-muted shrink-0">{r.account}</span>
                      <span className={cn('text-right', r.ok ? 'text-lime' : 'text-red-400')}>
                        {r.ok
                          ? r.status || 'ok'
                          : `${r.code ? `[${r.code}] ` : ''}${r.error || 'ошибка'}`}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex gap-4 pt-4">
                {!isPage && onClose && (
                  <button
                    type="button"
                    onClick={onClose}
                    className="flex-1 py-4 bg-dashboard-bg border border-border text-xs font-mono rounded-xl"
                  >
                    закрыть
                  </button>
                )}
                <button
                  type="button"
                  disabled={!canActivate || activating}
                  onClick={handleActivate}
                  className={cn(
                    isPage ? 'w-full' : 'flex-[2]',
                    'py-4 rounded-xl font-bold lowercase text-sm flex items-center justify-center gap-2',
                    canActivate && !activating
                      ? 'bg-lime text-black hover:bg-white'
                      : 'bg-dashboard-bg text-text-muted cursor-not-allowed border border-border'
                  )}
                >
                  {activating && <Loader2 className="w-4 h-4 animate-spin" />}
                  {activating ? 'активация…' : 'активировать'}
                </button>
              </div>
            </div>
  );

  if (isPage) {
    return (
      <div className="rounded-[24px] border border-border bg-card-bg p-8">
        {inner}
      </div>
    );
  }

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
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-card-bg border border-lime/30 rounded-[24px] shadow-[0_0_50px_rgba(204,255,0,0.1)]"
          >
            <div className="p-8 border-b border-border flex justify-between items-center bg-gradient-to-r from-lime/5 to-transparent sticky top-0 bg-card-bg z-10">
              <div>
                <h2 className="text-2xl font-black lowercase tracking-tighter text-main">
                  активация наград
                </h2>
                <p className="text-sm text-text-muted font-mono mt-1 lowercase">
                  twitch gql · redeemCommunityPointsCustomReward
                </p>
              </div>
              {onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  className="p-3 rounded-xl hover:bg-white/5 border border-transparent hover:border-border"
                >
                  <X className="w-6 h-6 text-text-muted" />
                </button>
              )}
            </div>
            {inner}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
