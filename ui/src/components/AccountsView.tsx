import React, { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Plus, Trash2, User, X, Play, Square, Check, Monitor, UserPlus } from 'lucide-react';
import { FollowModal } from './FollowModal';
import { cn } from '../lib/utils';
import { fetchJson, type Account, type AccountField, type Streamer } from '../api';
import { CustomSelect } from './CustomSelect';
import { DeviceAuthModal } from './DeviceAuthModal';

const BET_FIELD_KEYS = new Set(['bet_max_points', 'bet_percentage', 'bet_strategy']);

export function AccountsView() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [streamers, setStreamers] = useState<Streamer[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showStartModal, setShowStartModal] = useState(false);
  const [showStopModal, setShowStopModal] = useState(false);
  const [showFollowModal, setShowFollowModal] = useState(false);

  // Selection states for Modals
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
  const [schema, setSchema] = useState<AccountField[]>([]);
  const [formValues, setFormValues] = useState<Record<string, string | number | boolean>>({});
  const [authUsername, setAuthUsername] = useState<string | null>(null);
  const [authForce, setAuthForce] = useState(false);

  const makePredictions = Boolean(formValues.make_predictions);

  const visibleSchema = useMemo(
    () =>
      schema.filter(
        (field) => makePredictions || !BET_FIELD_KEYS.has(field.key)
      ),
    [schema, makePredictions]
  );

  const activeAccounts = useMemo(() => accounts.filter((a) => a.status === 'Active'), [accounts]);
  const startableAccounts = useMemo(
    () => accounts.filter((a) => a.status !== 'Active'),
    [accounts]
  );

  const toggleAccount = (username: string) => {
    setSelectedAccounts(prev => prev.includes(username) ? prev.filter(u => u !== username) : [...prev, username]);
  };

  const refresh = async () => {
    try {
      const [accRes, stRes] = await Promise.all([
        fetchJson<{ accounts: Account[] }>('/api/accounts'),
        fetchJson<{ streamers: Streamer[] }>('/api/streamers'),
      ]);
      setAccounts(accRes.accounts || []);
      setStreamers(stRes.streamers || []);
    } catch {
      /* 401 → redirect to /login via fetchJson */
    }
  };

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 5000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (!showAddForm) return;
    fetchJson<{ fields: AccountField[] }>('/api/accounts/schema').then((d) => {
      setSchema(d.fields || []);
      const defaults: Record<string, string | number | boolean> = {};
      for (const f of d.fields || []) {
        if (f.default !== undefined) defaults[f.key] = f.default;
      }
      setFormValues(defaults);
    });
  }, [showAddForm]);

  return (
    <div className="p-8 space-y-6 max-w-[1600px] mx-auto relative text-main">
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-6">
        <div>
          <h2 className="text-2xl font-black lowercase flex items-center gap-4">
            <span className="w-12 h-1 bg-lime"></span> управление аккаунтами
          </h2>
          <p className="text-text-muted text-sm mt-1 lowercase font-mono">config/accounts.json · multi_session_runner</p>
        </div>
        
        <div className="flex flex-wrap items-center gap-3">
          <button 
            onClick={() => {
              setSelectedAccounts([]);
              setShowStartModal(true);
            }}
            className="flex items-center gap-2 px-6 py-3 bg-white/5 border border-lime/30 text-lime hover:bg-lime hover:text-black font-bold rounded-xl transition-all shadow-[0_0_15px_rgba(204,255,0,0.1)] group lowercase"
          >
            <Play className="w-4 h-4" /> запустить
          </button>
          <button 
            onClick={() => {
              setSelectedAccounts([]);
              setShowStopModal(true);
            }}
            className="flex items-center gap-2 px-6 py-3 bg-white/5 border border-red-500/30 text-red-500 hover:bg-red-500 hover:text-white font-bold rounded-xl transition-all shadow-[0_0_15px_rgba(239,68,68,0.1)] group lowercase"
          >
            <Square className="w-4 h-4" /> остановить
          </button>
          <button
            type="button"
            onClick={() => setShowFollowModal(true)}
            className="flex items-center gap-2 px-6 py-3 bg-white/5 border border-border text-text-main hover:border-lime/50 font-bold rounded-xl transition-all lowercase"
          >
            <UserPlus className="w-4 h-4" /> фоловнуться
          </button>
          <div className="hidden sm:block w-px h-8 bg-border mx-2" />
          <button 
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 px-6 py-3 bg-lime hover:bg-white text-black font-bold rounded-xl transition-all shadow-[0_0_30px_-5px_rgba(204,255,0,0.5)] lowercase"
          >
            <Plus className="w-5 h-5" /> добавить аккаунт
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {accounts.length === 0 && (
          <p className="col-span-full text-text-muted font-mono text-sm lowercase py-12 text-center border border-dashed border-border rounded-3xl">
            нет аккаунтов — добавьте бота или авторизуйте twitch (cookie в cookies/)
          </p>
        )}
        {accounts.map((acc, i) => (
          <motion.div
            key={acc.username}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="p-6 rounded-[24px] bg-card-bg border border-border hover:border-lime transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_10px_40px_-10px_rgba(204,255,0,0.1)] group relative overflow-hidden"
          >
            <div className="flex items-center justify-between mb-4 relative z-10">
              <div className="w-12 h-12 rounded-xl bg-dashboard-bg flex items-center justify-center border border-border">
                <User className="w-6 h-6 text-lime" />
              </div>
              <span className={cn(
                "px-3 py-1 rounded text-[10px] font-mono lowercase tracking-widest",
                acc.status === 'Active' ? "bg-lime/10 text-lime border border-lime/30" : "bg-white/5 text-text-muted border border-border"
              )}>
                {acc.status}
              </span>
            </div>

            <h3 className="font-bold text-lg mb-1 truncate lowercase relative z-10">{acc.username}</h3>
            <div className="flex items-center gap-2 text-text-muted mb-4 relative z-10 font-mono text-xs flex-wrap">
              <span className="truncate">
                {acc.has_config === false ? 'нет в accounts.json' : acc.file || '—'}
              </span>
              {acc.screen && (
                <span className="px-2 py-0.5 rounded border border-lime/30 text-lime">
                  {acc.screen}
                </span>
              )}
              <span
                className={cn(
                  'px-2 py-0.5 rounded border',
                  acc.has_cookie ? 'border-lime/30 text-lime' : 'border-border text-text-muted'
                )}
              >
                {acc.has_cookie ? 'cookie ok' : 'нет cookie'}
              </span>
            </div>

            <div className="flex gap-3 relative z-10 flex-wrap">
              {acc.has_config === false && acc.has_cookie && (
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await fetchJson(`/api/accounts/${encodeURIComponent(acc.username)}/restore-config`, {
                        method: 'POST',
                      });
                      refresh();
                    } catch (e) {
                      alert(e instanceof Error ? e.message : 'Ошибка');
                    }
                  }}
                  className="flex-1 py-2 rounded-xl bg-lime/10 border border-lime/30 text-xs font-mono lowercase text-lime hover:bg-lime transition-all hover:text-black"
                >
                  восстановить .py
                </button>
              )}
              {!acc.has_cookie ? (
                <button
                  type="button"
                  onClick={() => {
                    setAuthForce(false);
                    setAuthUsername(acc.username);
                  }}
                  className="flex-1 py-2 rounded-xl bg-dashboard-bg border border-lime/30 text-xs font-mono lowercase text-lime hover:bg-lime/10 transition-all"
                >
                  авторизовать
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    if (
                      !window.confirm(
                        `Переавторизовать ${acc.username}? Старый cookie будет удалён, нужен новый код с twitch.tv/activate.`
                      )
                    ) {
                      return;
                    }
                    setAuthForce(true);
                    setAuthUsername(acc.username);
                  }}
                  className="flex-1 py-2 rounded-xl bg-dashboard-bg border border-amber-500/40 text-xs font-mono lowercase text-amber-400 hover:bg-amber-500/10 transition-all"
                >
                  переавторизовать
                </button>
              )}
              <button
                type="button"
                onClick={async () => {
                  if (
                    !window.confirm(
                      `Удалить аккаунт ${acc.username}? Сессия будет остановлена.`
                    )
                  ) {
                    return;
                  }
                  try {
                    await fetchJson(`/api/accounts/${encodeURIComponent(acc.username)}`, {
                      method: 'DELETE',
                    });
                    refresh();
                  } catch (e) {
                    alert(e instanceof Error ? e.message : 'Ошибка удаления');
                  }
                }}
                className={cn(
                  'p-2 rounded-xl bg-dashboard-bg text-text-muted border border-border hover:border-red-500/50 hover:text-red-500 transition-all',
                  acc.has_cookie ? 'flex-1 flex items-center justify-center gap-2' : ''
                )}
              >
                <Trash2 className="w-4 h-4" />
                {acc.has_cookie && (
                  <span className="text-xs font-mono lowercase">удалить</span>
                )}
              </button>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Start Mining Modal */}
      <AnimatePresence>
        {showStartModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/80 backdrop-blur-md">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setShowStartModal(false)} className="absolute inset-0" />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              onClick={(e) => e.stopPropagation()}
              className="relative w-full max-w-2xl bg-card-bg border border-lime/30 rounded-[24px] shadow-[0_0_50px_rgba(204,255,0,0.1)] overflow-hidden"
            >
              <div className="p-8 border-b border-border flex justify-between items-center bg-gradient-to-r from-lime/5 to-transparent">
                <div>
                  <h2 className="text-2xl font-black lowercase tracking-tighter">запустить сессии</h2>
                  <p className="text-sm text-text-muted font-mono mt-1 lowercase">
                    стримеры берутся из общего списка ({streamers.length} каналов)
                  </p>
                </div>
                <button onClick={() => setShowStartModal(false)} className="p-3 rounded-xl hover:bg-white/5 transition-colors border border-transparent hover:border-border"><X className="w-6 h-6 text-text-muted" /></button>
              </div>
              
              <div className="p-8 space-y-8">
                {/* Account Selection */}
                <div className="space-y-4">
                  <div className="flex justify-between items-baseline">
                    <label className="text-[10px] font-mono lowercase tracking-widest text-lime ml-1">
                      аккаунты для запуска
                    </label>
                    <button 
                      type="button"
                      onClick={() =>
                        setSelectedAccounts(
                          selectedAccounts.length === startableAccounts.length
                            ? []
                            : startableAccounts.map((a) => a.username)
                        )
                      }
                      className="text-xs font-mono text-text-muted hover:text-white transition-colors"
                    >
                      выбрать все
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[200px] overflow-y-auto pr-2 custom-scrollbar">
                    {startableAccounts.map(acc => (
                      <button
                        type="button"
                        key={acc.username}
                        onClick={() => toggleAccount(acc.username)}
                        className={cn(
                          "p-4 rounded-xl border transition-all flex items-center justify-between group text-left",
                          selectedAccounts.includes(acc.username) ? "border-lime bg-lime/10" : "border-border bg-dashboard-bg hover:border-lime/50"
                        )}
                      >
                        <div className="flex items-center gap-3">
                          <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center border transition-colors", selectedAccounts.includes(acc.username) ? "bg-lime border-lime text-black" : "bg-card-bg border-border text-text-muted group-hover:border-lime/50 group-hover:text-lime")}>
                            <User className="w-5 h-5" />
                          </div>
                          <div>
                            <p className="text-sm font-bold truncate max-w-[120px] lowercase">{acc.username}</p>
                            <p className="text-[10px] text-text-muted font-mono lowercase">
                              {acc.has_config === false ? 'нужен .py' : acc.status}
                            </p>
                          </div>
                        </div>
                        {selectedAccounts.includes(acc.username) && <Check className="w-5 h-5 text-lime" />}
                      </button>
                    ))}
                    {startableAccounts.length === 0 && (
                      <div className="col-span-full py-8 text-center bg-dashboard-bg rounded-xl border border-dashed border-border text-text-muted">
                        <Monitor className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p className="text-[10px] font-mono lowercase tracking-widest">все аккаунты уже в сети</p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex gap-4 pt-4">
                  <button onClick={() => setShowStartModal(false)} className="flex-1 py-4 bg-dashboard-bg border border-border text-xs font-mono lowercase rounded-xl hover:bg-white/5 hover:text-white transition-colors">отмена</button>
                  <button
                    type="button"
                    disabled={selectedAccounts.length === 0 || streamers.length === 0}
                    onClick={async () => {
                      try {
                        for (const username of selectedAccounts) {
                          const acc = accounts.find((a) => a.username === username);
                          if (acc && acc.has_config === false && acc.has_cookie) {
                            await fetchJson(
                              `/api/accounts/${encodeURIComponent(username)}/restore-config`,
                              { method: 'POST' }
                            );
                          }
                        }
                        const result = await fetchJson<{
                          started: { username: string }[];
                          skipped: { username: string; reason: string }[];
                        }>('/api/sessions/start', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ accounts: selectedAccounts }),
                        });
                        const started = result.started || [];
                        const skipped = result.skipped || [];
                        const messages: string[] = [];
                        if (started.length) {
                          messages.push(
                            started
                              .map((s) => `${s.username}: screen ${s.screen ?? '—'}, pid ${s.pid ?? 0}`)
                              .join('\n')
                          );
                        }
                        if (skipped.length) {
                          messages.push(
                            skipped
                              .map((s) => {
                                const detail = 'detail' in s && s.detail ? `\n  ${String(s.detail)}` : '';
                                return `${s.username}: ${s.reason}${detail}`;
                              })
                              .join('\n')
                          );
                        }
                        if (!started.length && selectedAccounts.length) {
                          messages.push('ни одна сессия не запущена — проверьте screen -ls и logs/<user>.log');
                        }
                        if (messages.length) {
                          alert(messages.join('\n\n'));
                        }
                        setShowStartModal(false);
                        setSelectedAccounts([]);
                        refresh();
                      } catch (e) {
                        alert(e instanceof Error ? e.message : 'Ошибка запуска');
                      }
                    }}
                    className={cn(
                      'flex-[2] py-4 rounded-xl font-bold lowercase text-sm transition-all',
                      selectedAccounts.length > 0 && streamers.length > 0
                        ? 'bg-lime text-black hover:bg-white shadow-[0_0_20px_rgba(204,255,0,0.3)]'
                        : 'bg-dashboard-bg border border-border text-text-muted cursor-not-allowed'
                    )}
                  >
                    запустить {selectedAccounts.length > 0 && `(${selectedAccounts.length})`}
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Stop Mining Modal */}
      <AnimatePresence>
        {showStopModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/80 backdrop-blur-md">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setShowStopModal(false)} className="absolute inset-0" />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="relative w-full max-w-lg bg-card-bg border border-red-500/30 rounded-[24px] shadow-[0_0_50px_rgba(239,68,68,0.1)] overflow-hidden">
              <div className="p-8 border-b border-border flex justify-between items-center bg-gradient-to-r from-red-600/5 to-transparent">
                <h2 className="text-2xl font-black lowercase tracking-tighter">остановить аккаунты</h2>
                <button onClick={() => setShowStopModal(false)} className="p-3 rounded-xl hover:bg-white/5 transition-colors border border-transparent hover:border-border"><X className="w-6 h-6 text-text-muted" /></button>
              </div>
              
              <div className="p-8 space-y-6">
                <div>
                  <div className="flex justify-between items-baseline mb-4">
                    <label className="text-[10px] font-mono lowercase tracking-widest text-red-500 ml-1">активные сессии</label>
                    <button 
                      onClick={() => setSelectedAccounts(selectedAccounts.length === activeAccounts.length ? [] : activeAccounts.map(a => a.username))}
                      className="text-xs font-mono text-text-muted hover:text-white transition-colors"
                    >
                      {selectedAccounts.length === activeAccounts.length ? 'сбросить всех' : 'выбрать всех'}
                    </button>
                  </div>
                  <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                    {activeAccounts.map(acc => (
                      <button
                        key={acc.username}
                        onClick={() => toggleAccount(acc.username)}
                        className={cn(
                          "w-full p-4 rounded-xl border transition-all flex items-center justify-between group text-left",
                          selectedAccounts.includes(acc.username) ? "border-red-500 bg-red-500/10" : "border-border bg-dashboard-bg hover:border-red-500/50"
                        )}
                      >
                        <div className="flex items-center gap-4">
                          <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center border transition-colors", selectedAccounts.includes(acc.username) ? "bg-red-500 border-red-500 text-white" : "bg-card-bg border-border text-text-muted group-hover:border-red-500/50 group-hover:text-white")}>
                            <User className="w-5 h-5" />
                          </div>
                          <div>
                            <p className="font-bold text-main tracking-tight lowercase">{acc.username}</p>
                            <p className="text-[10px] text-lime font-mono lowercase">active</p>
                          </div>
                        </div>
                        {selectedAccounts.includes(acc.username) ? (
                          <div className="text-red-500">
                            <Check className="w-4 h-4" />
                          </div>
                        ) : (
                          <div className="w-4 h-4 rounded border border-border group-hover:border-red-500/50" />
                        )}
                      </button>
                    ))}
                    {activeAccounts.length === 0 && (
                      <p className="text-center py-10 text-[10px] font-mono lowercase tracking-widest bg-dashboard-bg rounded-xl border border-dashed border-border text-text-muted">нет активных сессий</p>
                    )}
                  </div>
                </div>

                <div className="flex gap-4 pt-4">
                  <button onClick={() => setShowStopModal(false)} className="flex-1 py-4 bg-dashboard-bg border border-border text-xs font-mono lowercase rounded-xl hover:bg-white/5 transition-colors text-text-muted hover:text-white">отмена</button>
                  <button 
                    disabled={selectedAccounts.length === 0}
                    onClick={async () => {
                      try {
                        await fetchJson('/api/sessions/stop', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ accounts: selectedAccounts }),
                        });
                      } catch (e) {
                        alert(e instanceof Error ? e.message : 'Ошибка остановки');
                      }
                      setShowStopModal(false);
                      setSelectedAccounts([]);
                      refresh();
                    }}
                    className={cn(
                      "flex-[2] py-4 rounded-xl font-bold lowercase text-sm transition-all",
                      selectedAccounts.length > 0 ? "bg-red-500 text-white hover:bg-red-400 shadow-[0_0_20px_rgba(239,68,68,0.3)]" : "bg-dashboard-bg border border-border text-text-muted cursor-not-allowed"
                    )}
                  >
                    остановить {selectedAccounts.length > 0 && `(${selectedAccounts.length})`}
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Add Account Modal Overlay */}
      <AnimatePresence>
        {showAddForm && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 sm:p-0">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setShowAddForm(false)} className="absolute inset-0 bg-black/80 backdrop-blur-md" />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-card-bg border border-lime/30 rounded-[24px] p-8 shadow-[0_0_50px_rgba(204,255,0,0.1)] custom-scrollbar">
              <div className="flex justify-between items-center mb-6">
                <h3 className="text-2xl font-black lowercase tracking-tighter">новый аккаунт</h3>
                <button onClick={() => setShowAddForm(false)} className="p-2 rounded-xl hover:bg-white/5"><X className="w-5 h-5 text-text-muted" /></button>
              </div>

              <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
                {visibleSchema.map((field) => (
                  <div key={field.key}>
                    <label className="block text-[10px] font-mono text-lime lowercase tracking-widest mb-2 ml-1">
                      {field.label}
                    </label>
                    {field.type === 'boolean' ? (
                      <button
                        type="button"
                        onClick={() => setFormValues((v) => ({ ...v, [field.key]: !v[field.key] }))}
                        className={cn(
                          'w-full py-3 rounded-xl border font-mono text-sm lowercase',
                          formValues[field.key] ? 'border-lime bg-lime/10 text-lime' : 'border-border bg-dashboard-bg text-text-muted'
                        )}
                      >
                        {formValues[field.key] ? 'да' : 'нет'}
                      </button>
                    ) : field.type === 'select' ? (
                      <CustomSelect
                        value={String(formValues[field.key] ?? field.default ?? '')}
                        options={field.options || []}
                        onChange={(value) =>
                          setFormValues((v) => ({ ...v, [field.key]: value }))
                        }
                      />
                    ) : (
                      <input
                        type={field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'}
                        value={String(formValues[field.key] ?? '')}
                        onChange={(e) =>
                          setFormValues((v) => ({
                            ...v,
                            [field.key]: field.type === 'number' ? Number(e.target.value) : e.target.value,
                          }))
                        }
                        className="w-full h-[48px] px-4 rounded-xl bg-dashboard-bg border border-border text-main font-mono text-sm focus:outline-none focus:ring-1 focus:ring-lime"
                      />
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const payload = { ...formValues };
                      if (!makePredictions) {
                        for (const key of BET_FIELD_KEYS) {
                          delete payload[key];
                        }
                      }
                      const created = await fetchJson<{ username: string }>('/api/accounts', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                      });
                      setShowAddForm(false);
                      refresh();
                      setAuthUsername(created.username);
                    } catch (e) {
                      alert(e instanceof Error ? e.message : 'Ошибка создания');
                    }
                  }}
                  className="w-full py-4 bg-lime text-black font-bold lowercase text-sm rounded-xl hover:bg-white"
                >
                  создать accounts/&lt;user&gt;.py
                </button>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <FollowModal isOpen={showFollowModal} onClose={() => setShowFollowModal(false)} />

      {authUsername && (
        <DeviceAuthModal
          username={authUsername}
          force={authForce}
          isOpen={Boolean(authUsername)}
          onClose={() => {
            setAuthUsername(null);
            setAuthForce(false);
          }}
          onComplete={() => {
            refresh();
            setAuthUsername(null);
            setAuthForce(false);
          }}
        />
      )}
    </div>
  );
}
