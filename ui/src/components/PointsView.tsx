import React from 'react';
import { Trophy } from 'lucide-react';
import { PointsRewardForm } from './PointsRewardForm';

/** Full-page «Баллы» tab (same form as former modal). */
export function PointsView() {
  return (
    <div className="p-8 max-w-[900px] mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <div className="p-3 rounded-2xl bg-lime/10 border border-lime/30">
          <Trophy className="w-8 h-8 text-lime" />
        </div>
        <div>
          <h1 className="text-3xl font-black lowercase tracking-tighter">баллы</h1>
          <p className="text-sm text-text-muted font-mono lowercase">
            активация наград за channel points
          </p>
        </div>
      </div>
      <PointsRewardForm variant="page" isOpen />
    </div>
  );
}
