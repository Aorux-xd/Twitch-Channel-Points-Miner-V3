export type Streamer = {
  login: string;
  claim_drops: boolean;
  high_priority: boolean;
  display_name?: string;
  avatar_url?: string;
  is_live?: boolean;
};

export type Account = {
  username: string;
  file: string | null;
  status: 'Active' | 'Offline';
  has_config?: boolean;
  has_cookie: boolean;
  pid?: number;
  startedAt?: number;
};

export type AccountField = {
  key: string;
  label: string;
  type: 'text' | 'password' | 'boolean' | 'number' | 'select';
  required?: boolean;
  default?: string | number | boolean;
  options?: string[];
};

export type ActiveStream = {
  login: string;
  display_name?: string;
  avatar_url?: string;
  channel_points: number;
  accounts: string[];
};

export type DashboardStats = {
  total_points: number;
  active_sessions: number;
  online_streamers: number;
  accounts: {
    username: string;
    points: number;
    streamers_online: number;
    by_streamer?: Record<string, number>;
  }[];
  per_streamer?: Record<string, number>;
  from_cache?: boolean;
};

import { authHeaders, clearPanelToken } from './lib/auth';

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const auth = authHeaders() as Record<string, string>;
  Object.entries(auth).forEach(([k, v]) => headers.set(k, v));
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(url, { ...init, headers });
  if (res.status === 401) {
    clearPanelToken();
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { error?: string }).error || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type SystemInfo = {
  cpu: string;
  cpu_percent: number;
  ram: string;
  ram_used_gb: number;
  ram_total_gb: number;
  ram_free_gb: number;
  ram_percent: number;
  disk_percent: number;
  uptime: string;
  uptime_seconds: number;
  status: string;
  active_sessions: number;
  python_version: string;
  platform: string;
  hostname: string;
  os_name: string;
  twitch_online: boolean;
  api_version: string;
};

export type DeviceAuthStatus = {
  status: string;
  user_code?: string | null;
  verification_uri?: string;
  message?: string;
};
