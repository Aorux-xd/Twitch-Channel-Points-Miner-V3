import React from 'react';
import { Bell } from 'lucide-react';
import { RunnerHealthBadge } from './RunnerHealthBadge';

export function Header() {
  return (
    <header className="h-20 border border-border bg-sidebar-bg/80 backdrop-blur-md rounded-3xl sticky top-6 z-40 px-8 flex items-center justify-between mb-6 shadow-sm">
      <div className="flex-1">
        <p className="text-xs font-mono text-text-muted lowercase tracking-widest">
          twitch channel points miner · production dashboard
        </p>
      </div>

      <div className="flex items-center gap-4">
        <RunnerHealthBadge />
        <button
          type="button"
          className="p-2.5 rounded-xl border border-border hover:bg-dashboard-bg transition-colors relative"
          title="Уведомления"
        >
          <Bell className="w-5 h-5 text-text-muted" />
        </button>

        <div className="h-10 w-[1px] bg-border mx-2" />

        <div className="flex items-center gap-3 pl-2">
          <div className="text-right hidden sm:block">
            <p className="text-sm font-bold leading-none">root@admin</p>
            <p className="text-xs text-text-muted mt-1">Система активна</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-lime/10 flex items-center justify-center border-2 border-lime overflow-hidden shadow-lg shadow-lime/20">
            <img
              src="https://api.dicebear.com/7.x/avataaars/svg?seed=Admin"
              alt="Avatar"
              className="w-full h-full object-cover"
              referrerPolicy="no-referrer"
            />
          </div>
        </div>
      </div>
    </header>
  );
}
