import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ExternalLink, X, Copy, Check } from 'lucide-react';
import { fetchJson } from '../api';
import { cn } from '../lib/utils';

type AuthStatus = {
  status: string;
  user_code?: string | null;
  verification_uri?: string;
  message?: string;
};

type Props = {
  username: string;
  isOpen: boolean;
  force?: boolean;
  onClose: () => void;
  onComplete: () => void;
};

export function DeviceAuthModal({ username, isOpen, force = false, onClose, onComplete }: Props) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!isOpen || !username) return;

    let cancelled = false;

    const start = async () => {
      try {
        await fetchJson('/api/auth/device/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, force }),
        });
      } catch {
        /* ignore */
      }
    };

    const poll = async () => {
      try {
        const data = await fetchJson<AuthStatus>(
          `/api/auth/device/${encodeURIComponent(username)}`
        );
        if (cancelled) return;
        setStatus(data);
        if (data.status === 'complete') {
          onComplete();
        }
      } catch {
        /* ignore */
      }
    };

    start();
    poll();
    const t = window.setInterval(poll, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [isOpen, username, force, onComplete]);

  const code = status?.user_code || '';
  const uri = status?.verification_uri || 'https://www.twitch.tv/activate';

  const copyCode = () => {
    if (!code) return;
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[110] flex items-center justify-center p-6 bg-black/80 backdrop-blur-md">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0"
        />
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="relative w-full max-w-lg bg-card-bg border border-lime/30 rounded-[24px] shadow-[0_0_50px_rgba(204,255,0,0.15)] overflow-hidden"
        >
          <div className="p-8 border-b border-border flex justify-between items-center">
            <div>
              <h2 className="text-2xl font-black lowercase">авторизация twitch</h2>
              <p className="text-sm text-text-muted font-mono mt-1 lowercase">@{username}</p>
            </div>
            <button
              onClick={onClose}
              className="p-3 rounded-xl hover:bg-white/5 border border-transparent hover:border-border"
            >
              <X className="w-6 h-6 text-text-muted" />
            </button>
          </div>

          <div className="p-8 space-y-6">
            {status?.status === 'complete' ? (
              <p className="text-lime font-mono text-sm lowercase">cookie сохранён — аккаунт готов</p>
            ) : (
              <>
                {force && (
                  <p className="text-amber-400/90 text-xs font-mono lowercase border border-amber-500/30 rounded-xl px-4 py-2">
                    старый cookie удалён — введите новый код с этого twitch-аккаунта
                  </p>
                )}
                <p className="text-text-muted text-sm font-mono lowercase">
                  откройте twitch activate и введите 8-значный код:
                </p>
                <a
                  href={uri}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-lime font-mono text-sm hover:underline"
                >
                  <ExternalLink className="w-4 h-4" />
                  {uri.replace('https://', '')}
                </a>
                <div
                  className={cn(
                    'flex items-center justify-between p-6 rounded-2xl border',
                    code ? 'border-lime bg-lime/10' : 'border-border bg-dashboard-bg'
                  )}
                >
                  <span className="text-4xl font-black tracking-[0.35em] text-main">
                    {code || '········'}
                  </span>
                  {code && (
                    <button
                      type="button"
                      onClick={copyCode}
                      className="p-3 rounded-xl border border-lime/30 text-lime hover:bg-lime hover:text-black transition-all"
                    >
                      {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
                    </button>
                  )}
                </div>
                <p className="text-[10px] text-text-muted font-mono lowercase">
                  статус: {status?.status || 'ожидание…'}
                  {status?.message ? ` · ${status.message}` : ''}
                </p>
              </>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
