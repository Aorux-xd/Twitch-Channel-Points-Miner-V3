import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { MessageSquare, Send, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchJson, type Account, type Streamer } from '../api';
import { CustomSelect } from './CustomSelect';
import { chatDebug, chatError, chatWarn } from '../lib/chatDebug';
import { authHeaders, clearPanelToken } from '../lib/auth';

const CHAT_LAYOUT = {
  selectCol: 'minmax(0,160px)',
  sendBtn: 'w-11 shrink-0',
} as const;

type ChatBadge = {
  type: string;
  version: string;
  label: string;
};

type ChatMessage = {
  id: string;
  streamer: string;
  user: string;
  text: string;
  ts: number;
  display_name?: string;
  badges?: ChatBadge[];
  color?: string;
};

type ChatDebugInfo = {
  reader?: string | null;
  reader_alive?: boolean;
  reader_joined?: boolean;
  buffer_messages?: number;
};

type ChatPollResponse = {
  streamer?: string;
  messages: ChatMessage[];
  reader?: string | null;
  error?: string;
  debug?: ChatDebugInfo;
};

type ChatSendResult = {
  account: string;
  ok: boolean;
  error?: string | null;
  method?: string;
  code?: string;
};

type ChatSendResponse = {
  ok: boolean;
  partial?: boolean;
  ok_count?: number;
  fail_count?: number;
  total?: number;
  error?: string;
  results?: ChatSendResult[];
  streamer?: string;
  session?: string;
  accounts?: string[];
  debug?: ChatDebugInfo;
};

const CHAT_SEND_TIMEOUT_MS = 120_000;

const BADGE_STYLES: Record<string, string> = {
  broadcaster: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
  moderator: 'bg-green-500/20 text-green-300 border-green-500/40',
  vip: 'bg-pink-500/20 text-pink-300 border-pink-500/40',
  lead_moderator: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  founder: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  subscriber: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40',
};

function dedupeMessages(list: ChatMessage[]): ChatMessage[] {
  const out: ChatMessage[] = [];
  for (const m of list) {
    const prev = out[out.length - 1];
    if (
      prev &&
      prev.user === m.user &&
      prev.text === m.text &&
      Math.abs(m.ts - prev.ts) < 3
    ) {
      continue;
    }
    out.push(m);
  }
  return out;
}

function formatSendSummary(data: ChatSendResponse): string {
  const failed = (data.results || []).filter((r) => !r.ok);
  if (!failed.length) return '';
  return failed
    .map((r) => {
      const code = r.code ? ` [${r.code}]` : '';
      return `${r.account}${code}: ${r.error || 'ошибка'}`;
    })
    .join('; ');
}

export function ChatView() {
  const [streamers, setStreamers] = useState<Streamer[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedStreamer, setSelectedStreamer] = useState('');
  const [selectedSession, setSelectedSession] = useState('Все сессии');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [sendStatus, setSendStatus] = useState<
    'idle' | 'sending' | 'sent' | 'partial' | 'failed' | 'rate_limited'
  >('idle');
  const [error, setError] = useState<string | null>(null);
  const [lastDebug, setLastDebug] = useState<ChatDebugInfo | null>(null);
  const [readerAccount, setReaderAccount] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pollCountRef = useRef(0);

  const cookieAccounts = useMemo(
    () => accounts.filter((a) => a.has_cookie),
    [accounts]
  );

  const sessionOptions = useMemo(
    () => ['Все сессии', ...cookieAccounts.map((a) => a.username)],
    [cookieAccounts]
  );

  const pollMessages = useCallback(async (reason: string) => {
    if (!selectedStreamer) return;
    const q = new URLSearchParams({
      streamer: selectedStreamer,
      limit: '150',
    });
    const url = `/api/chat?${q}`;
    pollCountRef.current += 1;
    chatDebug('poll:start', {
      reason,
      poll: pollCountRef.current,
      url,
      streamer: selectedStreamer,
    });

    try {
      const data = await fetchJson<ChatPollResponse>(url);
      const list = dedupeMessages(data.messages || []);
      setMessages(list);
      setReaderAccount(data.reader ?? null);
      setLastDebug(data.debug ?? null);
      setError(data.error || null);

      chatDebug('poll:ok', {
        reason,
        messageCount: list.length,
        reader: data.reader,
        debug: data.debug,
        lastMessage: list.length
          ? {
              user: list[list.length - 1].user,
              text: list[list.length - 1].text?.slice(0, 60),
            }
          : null,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'ошибка чата';
      setError(msg);
      chatError('poll:fail', { reason, message: msg });
    }
  }, [selectedStreamer]);

  useEffect(() => {
    chatDebug('mount');
    Promise.all([
      fetchJson<{ streamers: Streamer[] }>('/api/streamers'),
      fetchJson<{ accounts: Account[] }>('/api/accounts'),
    ])
      .then(([st, acc]) => {
        const list = st.streamers || [];
        const accs = acc.accounts || [];
        setStreamers(list);
        setAccounts(accs);
        chatDebug('init:data', {
          streamers: list.map((s) => s.login),
          cookieAccounts: accs.filter((a) => a.has_cookie).map((a) => a.username),
        });
        if (list.length) setSelectedStreamer(list[0].login);
      })
      .catch((e) => chatError('init:fail', e));
  }, []);

  useEffect(() => {
    if (!selectedStreamer) return;
    let cancelled = false;

    const poll = async () => {
      if (cancelled) return;
      await pollMessages('interval');
    };

    chatDebug('poll:subscribe', { streamer: selectedStreamer });
    poll();
    const id = setInterval(poll, 2500);
    return () => {
      cancelled = true;
      clearInterval(id);
      chatDebug('poll:unsubscribe', { streamer: selectedStreamer });
    };
  }, [selectedStreamer, pollMessages]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    const text = draft.trim();
    if (!text || !selectedStreamer) return;

    const payload = {
      streamer: selectedStreamer,
      text,
      session: selectedSession,
    };

    chatDebug('send:start', {
      ...payload,
      cookieAccounts: cookieAccounts.map((a) => a.username),
    });

    setSending(true);
    setSendStatus('sending');
    setError(null);

    try {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(
        () => controller.abort(),
        CHAT_SEND_TIMEOUT_MS
      );

      const headers = new Headers({ 'Content-Type': 'application/json' });
      Object.entries(authHeaders() as Record<string, string>).forEach(([k, v]) =>
        headers.set(k, v)
      );

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      window.clearTimeout(timeoutId);

      if (res.status === 401) {
        clearPanelToken();
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }

      const data = (await res.json()) as ChatSendResponse & { error?: string };
      if (!res.ok) {
        throw new Error(data.error || res.statusText);
      }

      chatDebug('send:response', data);

      if (data.debug) {
        setLastDebug(data.debug);
        setReaderAccount(data.debug.reader ?? data.reader ?? null);
      }

      const failed = (data.results || []).filter((r) => !r.ok);

      if (data.ok) {
        setDraft('');
        if (data.partial) {
          setSendStatus('partial');
          const summary = `частично: ${data.ok_count}/${data.total} отправлено`;
          const details = formatSendSummary(data);
          setError(details ? `${summary}. ${details}` : summary);
          chatWarn('send:partial', {
            ok_count: data.ok_count,
            fail_count: data.fail_count,
            failed,
          });
        } else {
          setSendStatus('sent');
          setError(null);
          chatDebug('send:success', {
            ok_count: data.ok_count,
            total: data.total,
          });
        }
        void pollMessages('after-send');
      } else {
        const rateLimited = (data.results || []).some(
          (r) => r.code === 'RATE_LIMIT' || (r.error || '').includes('too quickly')
        );
        setSendStatus(rateLimited ? 'rate_limited' : 'failed');
        const detail = formatSendSummary(data) || data.error || 'не удалось отправить';
        setError(detail);
        chatWarn('send:failed', {
          error: data.error,
          results: data.results,
          debug: data.debug,
        });
      }
    } catch (e) {
      let msg = e instanceof Error ? e.message : 'ошибка отправки';
      if (e instanceof Error && e.name === 'AbortError') {
        msg =
          'таймаут отправки (много аккаунтов). проверьте лог api_server — часть могла уйти';
      }
      setSendStatus('failed');
      setError(msg);
      chatError('send:exception', { message: msg, payload });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="p-8 max-w-[1400px] mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <div className="p-3 rounded-2xl bg-lime/10 border border-lime/30">
          <MessageSquare className="w-8 h-8 text-lime" />
        </div>
        <div>
          <h1 className="text-3xl font-black lowercase tracking-tighter">чат</h1>
          <p className="text-sm text-text-muted font-mono lowercase">
            irc #{selectedStreamer || '—'} · reader: {readerAccount || '—'} · консоль:
            TwitchPanel:Chat
          </p>
        </div>
      </div>

      <div className="rounded-[24px] border border-border bg-card-bg flex flex-col h-[calc(100vh-280px)] min-h-[420px] overflow-hidden">
        <div className="px-6 py-3 border-b border-border bg-dashboard-bg/50 shrink-0 space-y-1">
          <p className="text-[10px] font-mono text-text-muted lowercase">
            канал #{selectedStreamer || '—'}
            {readerAccount ? ` · irc reader: ${readerAccount}` : ''}
            {lastDebug?.reader_joined === false ? ' · reader не в канале (join…)' : ''}
            {sendStatus !== 'idle' && sendStatus !== 'sent' ? ` · send: ${sendStatus}` : ''}
            {sendStatus === 'sent' ? ' · отправлено' : ''}
            {error ? ` · ${error}` : ''}
          </p>
          {lastDebug && (
            <p className="text-[9px] font-mono text-text-muted/80">
              debug: joined={String(lastDebug.reader_joined)} alive=
              {String(lastDebug.reader_alive)} buf={lastDebug.buffer_messages}
            </p>
          )}
        </div>

        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-6 space-y-2 custom-scrollbar bg-dashboard-bg/30 font-mono text-sm min-h-0"
        >
          {messages.length === 0 ? (
            <p className="text-text-muted text-center py-16 lowercase">
              сообщений пока нет — подключение к чату канала…
            </p>
          ) : (
            messages.map((m) => {
              const name = m.display_name || m.user;
              return (
                <div
                  key={m.id}
                  className="flex flex-wrap items-baseline gap-x-2 gap-y-1 hover:bg-white/[0.02] rounded-lg px-2 py-1"
                >
                  <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
                    {(m.badges || []).map((b) => (
                      <span
                        key={`${m.id}-${b.type}-${b.version}`}
                        title={b.label}
                        className={cn(
                          'text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border',
                          BADGE_STYLES[b.type] ||
                            'bg-white/5 text-text-muted border-border'
                        )}
                      >
                        {b.label}
                      </span>
                    ))}
                    <span
                      className="font-bold shrink-0"
                      style={m.color ? { color: m.color } : { color: 'var(--color-lime, #ccff00)' }}
                    >
                      {name}
                    </span>
                  </div>
                  <span className="text-text-main break-words min-w-0 flex-1">
                    {m.text}
                  </span>
                  <span className="text-[10px] text-text-muted shrink-0 w-full sm:w-auto sm:ml-auto text-right">
                    {new Date(m.ts * 1000).toLocaleTimeString()}
                  </span>
                </div>
              );
            })
          )}
        </div>

        <div className="relative z-30 shrink-0 p-3 sm:p-4 border-t border-border bg-card-bg overflow-visible">
          <div className="grid grid-cols-1 gap-2 items-center sm:grid-cols-[1fr_160px_160px_44px]">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="введите текст..."
              className="w-full min-w-0 h-11 px-4 rounded-xl bg-dashboard-bg border border-border font-mono text-sm lowercase"
            />
            <CustomSelect
              compact
              dropUp
              ariaLabel="стример"
              className="w-full min-w-0 !space-y-0"
              options={streamers.map((s) => s.login)}
              value={selectedStreamer || '—'}
              onChange={(v) => {
                chatDebug('select:streamer', { streamer: v });
                setSelectedStreamer(v);
              }}
            />
            <CustomSelect
              compact
              dropUp
              ariaLabel="сессия"
              className="w-full min-w-0 !space-y-0"
              options={
                sessionOptions.length > 1 ? sessionOptions : ['нет cookie']
              }
              value={selectedSession}
              onChange={(v) => {
                chatDebug('select:session', { session: v });
                setSelectedSession(v);
              }}
            />
            <button
              type="button"
              disabled={!draft.trim() || sending || cookieAccounts.length === 0}
              onClick={handleSend}
              className={cn(
                'h-11 rounded-xl font-bold lowercase flex items-center justify-center justify-self-end sm:justify-self-auto',
                CHAT_LAYOUT.sendBtn,
                draft.trim() && !sending
                  ? 'bg-lime text-black hover:bg-white'
                  : 'bg-dashboard-bg text-text-muted border border-border cursor-not-allowed'
              )}
            >
              {sending ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
