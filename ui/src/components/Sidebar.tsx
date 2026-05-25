import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  BarChart3,
  LayoutDashboard,
  Users,
  Wallet,
  Terminal,
  Activity,
  MessageSquare,
  ChevronLeft,
  Menu,
  Trophy,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { motion, AnimatePresence } from 'motion/react';
import { ROUTES } from '../routes';

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  Обзор: LayoutDashboard,
  'Активные стримы': Activity,
  Стримеры: Users,
  Аккаунты: Wallet,
  Чат: MessageSquare,
  'Консоль логов': Terminal,
  Баллы: Trophy,
  Система: BarChart3,
};

interface SidebarProps {
  isCollapsed: boolean;
  setIsCollapsed: (value: boolean) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export function Sidebar({
  isCollapsed,
  setIsCollapsed,
  activeTab,
  setActiveTab,
}: SidebarProps) {
  return (
    <motion.aside
      initial={false}
      animate={{
        width: isCollapsed ? 88 : 260,
      }}
      className={cn(
        'fixed left-6 top-6 z-50 bg-sidebar-bg border border-border rounded-[32px] shadow-2xl overflow-hidden flex flex-col transition-all duration-300 ease-in-out h-fit max-h-[calc(100vh-48px)]'
      )}
    >
      <div className="p-4 flex flex-col h-full">
        <div className="flex items-center justify-end mb-4 px-2">
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-2 rounded-xl hover:bg-dashboard-bg text-text-muted transition-colors"
          >
            {isCollapsed ? <Menu className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
          </button>
        </div>

        <div className="overflow-y-auto custom-scrollbar pr-1">
          <nav className="space-y-1">
            {ROUTES.map((item) => {
              const Icon = ICONS[item.label] || LayoutDashboard;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  title={isCollapsed ? item.label : undefined}
                  onClick={() => setActiveTab(item.label)}
                  className={({ isActive }) =>
                    cn(
                      'w-full flex items-center gap-3 px-3 py-3 rounded-2xl transition-all duration-200 group relative truncate',
                      isActive || activeTab === item.label
                        ? 'bg-lime text-white shadow-lg shadow-lime/20'
                        : 'text-text-muted hover:bg-lime/10 hover:text-lime'
                    )
                  }
                >
                  <Icon
                    className={cn(
                      'w-6 h-6 shrink-0',
                      activeTab === item.label ? 'text-white' : 'group-hover:text-lime'
                    )}
                  />
                  <AnimatePresence mode="wait">
                    {!isCollapsed && (
                      <motion.span
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -10 }}
                        className="font-bold text-sm whitespace-nowrap"
                      >
                        {item.label}
                      </motion.span>
                    )}
                  </AnimatePresence>
                </NavLink>
              );
            })}
          </nav>
        </div>
      </div>
    </motion.aside>
  );
}
