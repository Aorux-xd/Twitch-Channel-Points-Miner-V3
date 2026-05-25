import { DashboardContent } from './components/DashboardContent';
import { StreamersView } from './components/StreamersView';
import { LogsView } from './components/LogsView';
import { SystemView } from './components/SystemView';
import { AccountsView } from './components/AccountsView';
import { ActiveStreamsView } from './components/ActiveStreamsView';
import { ChatView } from './components/ChatView';
import { PointsView } from './components/PointsView';

export const ROUTES = [
  { path: '/', label: 'Обзор', element: <DashboardContent /> },
  { path: '/streams', label: 'Активные стримы', element: <ActiveStreamsView /> },
  { path: '/streamers', label: 'Стримеры', element: <StreamersView /> },
  { path: '/accounts', label: 'Аккаунты', element: <AccountsView /> },
  { path: '/chat', label: 'Чат', element: <ChatView /> },
  { path: '/logs', label: 'Консоль логов', element: <LogsView /> },
  { path: '/points', label: 'Баллы', element: <PointsView /> },
  { path: '/system', label: 'Система', element: <SystemView /> },
] as const;

export function pathForLabel(label: string): string {
  const row = ROUTES.find((r) => r.label === label);
  return row?.path ?? '/';
}

export function labelForPath(pathname: string): string {
  const row = ROUTES.find((r) => r.path === pathname);
  return row?.label ?? 'Обзор';
}
