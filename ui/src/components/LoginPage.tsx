import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Lock, User } from 'lucide-react';
import { setPanelToken } from '../lib/auth';

const FIXED_LOGIN = 'root@admin';

type Props = {
  onSuccess: () => void;
};

export function LoginPage({ onSuccess }: Props) {
  const [username, setUsername] = useState(FIXED_LOGIN);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error((data as { error?: string }).error || 'Ошибка входа');
      }
      const token = String((data as { token?: string }).token || '');
      if (!token) {
        throw new Error('Сервер не вернул токен');
      }
      setPanelToken(token);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка входа');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-dashboard-bg flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md p-10 rounded-[32px] bg-card-bg border border-border shadow-[0_0_60px_rgba(204,255,0,0.08)]"
      >
        <div className="inline-block px-3 py-1 border border-lime/30 rounded-full bg-lime/5 text-lime text-[10px] font-mono mb-6 tracking-widest uppercase">
          secure access
        </div>
        <h1 className="text-3xl font-black lowercase tracking-tighter mb-2">вход в панель</h1>
        <p className="text-text-muted text-sm font-mono lowercase mb-8">
          логин фиксированный · пароль задаётся на сервере
        </p>

        <form onSubmit={submit} className="space-y-5">
          <div>
            <label className="block text-[10px] font-mono text-lime lowercase tracking-widest mb-2 ml-1">
              логин
            </label>
            <div className="relative">
              <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="text"
                value={username}
                readOnly
                className="w-full h-12 pl-11 pr-4 rounded-xl bg-dashboard-bg border border-border text-main font-mono text-sm opacity-70 cursor-not-allowed"
              />
            </div>
          </div>
          <div>
            <label className="block text-[10px] font-mono text-lime lowercase tracking-widest mb-2 ml-1">
              пароль
            </label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
                className="w-full h-12 pl-11 pr-4 rounded-xl bg-dashboard-bg border border-border text-main font-mono text-sm focus:outline-none focus:ring-1 focus:ring-lime"
                placeholder="••••••••"
              />
            </div>
          </div>
          {error && (
            <p className="text-red-400 text-sm font-mono lowercase">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading || !password}
            className="w-full py-4 bg-lime text-black font-bold lowercase text-sm rounded-xl hover:bg-white disabled:opacity-50 transition-all"
          >
            {loading ? 'проверка…' : 'войти'}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
