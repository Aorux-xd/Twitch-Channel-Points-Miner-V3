import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { fetchJson, type ActiveStream } from '../api';

export function ActiveStreamsView() {
  const [streams, setStreams] = useState<ActiveStream[]>([]);

  useEffect(() => {
    const load = () =>
      fetchJson<{ streams: ActiveStream[] }>('/api/active-streams')
        .then((d) => setStreams(d.streams || []))
        .catch(() => setStreams([]));
    load();
    const t = window.setInterval(load, 10000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <div className="p-8 space-y-6 max-w-[1600px] mx-auto text-main">
      <div>
        <h2 className="text-2xl font-black lowercase flex items-center gap-4">
          <span className="w-12 h-1 bg-lime"></span> активные стримы
        </h2>
        <p className="text-text-muted text-sm mt-1 font-mono lowercase">
          каналы в эфире, которые сейчас смотрят запущенные сессии
        </p>
      </div>

      {streams.length === 0 ? (
        <div className="p-12 rounded-[32px] bg-card-bg border border-dashed border-border text-center text-text-muted font-mono text-sm">
          нет активных трансляций — запустите сессии и дождитесь онлайн-стримеров
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {streams.map((s) => (
            <div key={s.login} className="p-8 rounded-[32px] bg-card-bg border border-border">
              <div className="flex justify-between items-center mb-6">
                <div className="flex items-center gap-4">
                  <img
                    src={s.avatar_url || `https://api.dicebear.com/7.x/avataaars/svg?seed=${s.login}`}
                    className="w-12 h-12 rounded-xl bg-dashboard-bg border border-border object-cover"
                    alt={s.login}
                  />
                  <div>
                    <p className="font-bold lowercase">{s.display_name || s.login}</p>
                    <p className="text-xs text-lime font-mono">{s.accounts.length} бот(ов)</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-lg font-bold">{s.channel_points.toLocaleString()}</p>
                  <p className="text-xs text-text-muted">баллов на канале</p>
                </div>
              </div>
              <p className="text-[10px] font-mono text-text-muted truncate">
                {s.accounts.join(', ')}
              </p>
              <div className="mt-4 w-full h-2 bg-dashboard-bg rounded-full overflow-hidden border border-border">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: '100%' }}
                  className="h-full bg-gradient-to-r from-lime/80 to-lime"
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
