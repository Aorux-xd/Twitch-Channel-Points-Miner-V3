import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '../lib/utils';

export type SelectOption = { value: string; label: string };

type Props = {
  label?: string;
  value: string;
  options: string[] | SelectOption[];
  onChange: (value: string) => void;
  icon?: React.ComponentType<{ className?: string }>;
  className?: string;
  compact?: boolean;
  /** Open dropdown above the trigger (e.g. bottom toolbar). */
  dropUp?: boolean;
  /** Accessible name when label is omitted. */
  ariaLabel?: string;
};

export function CustomSelect({
  label,
  value,
  options,
  onChange,
  icon: Icon,
  className,
  compact = false,
  dropUp = false,
  ariaLabel,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const normalized: SelectOption[] = options.map((o) =>
    typeof o === 'string' ? { value: o, label: o } : o
  );
  const selected = normalized.find((o) => o.value === value);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className={cn('space-y-2 relative', className)} ref={containerRef}>
      {label && (
        <label className="text-[10px] font-mono lowercase tracking-widest text-lime ml-1">
          {label}
        </label>
      )}
      <button
        type="button"
        aria-label={ariaLabel || label}
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'w-full rounded-xl bg-dashboard-bg border border-border flex items-center justify-between hover:border-lime/50 transition-all font-mono text-sm text-main',
          compact ? 'h-10 px-4 min-w-[200px]' : 'h-14 px-5'
        )}
      >
        <span className="flex items-center gap-2 truncate">
          {Icon && <Icon className="w-4 h-4 text-lime shrink-0" />}
          <span className="truncate">{selected?.label ?? value}</span>
        </span>
        <ChevronDown
          className={cn('w-5 h-5 text-text-muted transition-transform shrink-0', isOpen && 'rotate-180')}
        />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: dropUp ? -8 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: dropUp ? -8 : 8 }}
            className={cn(
              'absolute z-[110] w-full min-w-[200px] bg-card-bg border border-border rounded-xl shadow-xl overflow-hidden py-1 max-h-48 overflow-y-auto',
              dropUp ? 'bottom-full mb-2' : 'top-full mt-2'
            )}
          >
            {normalized.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  onChange(opt.value);
                  setIsOpen(false);
                }}
                className={cn(
                  'w-full px-5 py-3 text-left text-sm font-mono lowercase transition-colors flex items-center justify-between hover:text-white',
                  opt.value === value ? 'text-lime bg-lime/10' : 'text-text-muted hover:bg-white/5'
                )}
              >
                <span className="truncate">{opt.label}</span>
                {opt.value === value && <Check className="w-4 h-4 shrink-0" />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
