import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Cpu, HardDrive, Globe, Layers, Server } from 'lucide-react';
import { fetchJson, type SystemInfo } from '../api';

const SysStat = ({
  label,
  value,
  sub,
  icon: Icon,
  color,
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}) => (
  <div className="p-6 rounded-[24px] bg-card-bg border border-border flex items-center gap-4 hover:border-lime transition-all duration-300 hover:-translate-y-1">
    <div className={`w-12 h-12 rounded-2xl ${color} flex items-center justify-center`}>
      <Icon className="w-6 h-6 text-black" />
    </div>
    <div>
      <p className="text-xs text-text-muted font-bold uppercase tracking-widest mb-0.5">{label}</p>
      <p className="text-xl font-bold tracking-tight">{value}</p>
      <p className="text-[10px] text-text-muted font-medium">{sub}</p>
    </div>
  </div>
);

export function SystemView() {
  const [sysData, setSysData] = useState<SystemInfo | null>(null);

  useEffect(() => {
    const fetchSystemData = async () => {
      try {
        const data = await fetchJson<SystemInfo>('/api/system');
        setSysData(data);
      } catch (error) {
        console.error('Failed to fetch system stats', error);
      }
    };
    fetchSystemData();
    const interval = setInterval(fetchSystemData, 5000);
    return () => clearInterval(interval);
  }, []);

  const ramSub = sysData
    ? `Свободно ${sysData.ram_free_gb} GB (${100 - sysData.ram_percent}% свободно)`
    : 'загрузка…';

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto">
      <div>
        <h2 className="text-2xl font-black lowercase flex items-center gap-4">
          <span className="w-12 h-1 bg-lime"></span> информация о системе
        </h2>
        <p className="text-text-muted text-sm mt-1 lowercase font-mono">
          хост, нагрузка и статус майнера
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <SysStat
          label="Процессор"
          value={sysData?.cpu || '—'}
          sub={sysData ? `загрузка ${sysData.cpu_percent}%` : ''}
          icon={Cpu}
          color="bg-lime"
        />
        <SysStat
          label="Память RAM"
          value={sysData?.ram || '—'}
          sub={ramSub}
          icon={Layers}
          color="bg-lime opacity-80"
        />
        <SysStat
          label="ОС"
          value={sysData?.os_name || '—'}
          sub={sysData?.platform || ''}
          icon={HardDrive}
          color="bg-white"
        />
        <SysStat
          label="Twitch API"
          value={sysData?.twitch_online ? 'online' : 'offline'}
          sub={sysData?.twitch_online ? 'gql доступен' : 'кэш / офлайн режим'}
          icon={Globe}
          color={sysData?.twitch_online ? 'bg-lime' : 'bg-gray-400'}
        />
      </div>

      <div className="p-8 rounded-[32px] bg-card-bg border border-border shadow-soft relative overflow-hidden group hover:border-lime transition-all duration-300">
        <div className="absolute top-0 right-0 bg-lime/10 border border-b border-lime/20 text-lime text-[10px] font-bold px-3 py-1 rounded-bl-xl uppercase tracking-widest">
          host
        </div>
        <h3 className="font-bold mb-6 lowercase flex items-center gap-2">
          <Server className="w-5 h-5 text-lime" />
          сервер и майнер
        </h3>
        <div className="space-y-4 font-mono text-sm">
          <div className="flex justify-between py-3 border-b border-border/50">
            <span className="text-text-muted">hostname</span>
            <span className="font-bold">{sysData?.hostname || '—'}</span>
          </div>
          <div className="flex justify-between py-3 border-b border-border/50">
            <span className="text-text-muted">uptime</span>
            <span className="font-bold">{sysData?.uptime || '—'}</span>
          </div>
          <div className="flex justify-between py-3 border-b border-border/50">
            <span className="text-text-muted">python</span>
            <span className="font-bold">{sysData?.python_version || '—'}</span>
          </div>
          <div className="flex justify-between py-3 border-b border-border/50">
            <span className="text-text-muted">api version</span>
            <span className="font-bold">{sysData?.api_version || '—'}</span>
          </div>
          <div className="flex justify-between py-3 border-b border-border/50">
            <span className="text-text-muted">диск /</span>
            <span className="font-bold">
              {sysData ? `${sysData.disk_percent}% занято` : '—'}
            </span>
          </div>
          <div className="flex justify-between py-3 border-b border-border/50">
            <span className="text-text-muted">активные сессии</span>
            <span className="font-bold">{sysData?.active_sessions ?? '—'}</span>
          </div>
          <div className="flex justify-between py-3">
            <span className="text-text-muted">статус</span>
            <span className="text-lime font-bold uppercase text-xs">
              {sysData?.status === 'Healthy' ? 'healthy' : 'unknown'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
