import React from 'react';
import { Play, CheckCircle2, AlertCircle, PauseCircle } from 'lucide-react';

export type PipelineStatusType = 'idle' | 'running' | 'done' | 'error';

interface StatusBadgeProps {
  status: PipelineStatusType;
  large?: boolean;
  pulse?: boolean;
}

const STATUS_CONFIG: Record<
  PipelineStatusType,
  { label: string; bg: string; text: string; border: string; icon: React.ReactNode; dotBg: string }
> = {
  idle: {
    label: 'BEZCZYNNY',
    bg: 'bg-[#17191C]',
    text: 'text-[#A0A7B1]',
    border: 'border-[#272A2F]',
    icon: <PauseCircle className="w-3.5 h-3.5" />,
    dotBg: 'bg-[#A0A7B1]',
  },
  running: {
    label: 'PRZETWARZANIE',
    bg: 'bg-[#C8FF3A]/15',
    text: 'text-[#C8FF3A]',
    border: 'border-[#C8FF3A]/45',
    icon: <Play className="w-3.5 h-3.5 fill-current animate-pulse" />,
    dotBg: 'bg-[#C8FF3A]',
  },
  done: {
    label: 'UKOŃCZONO',
    bg: 'bg-[#2ECC71]/15',
    text: 'text-[#55E88D]',
    border: 'border-[#2ECC71]/40',
    icon: <CheckCircle2 className="w-3.5 h-3.5" />,
    dotBg: 'bg-[#2ECC71]',
  },
  error: {
    label: 'BŁĄD',
    bg: 'bg-[#FF5C5C]/15',
    text: 'text-[#FF5C5C]',
    border: 'border-[#FF5C5C]/40',
    icon: <AlertCircle className="w-3.5 h-3.5" />,
    dotBg: 'bg-[#FF5C5C]',
  },
};

export default function StatusBadge({ status, large = false, pulse = true }: StatusBadgeProps) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle;

  return (
    <div
      className={`fk-tag inline-flex items-center gap-2 border font-extrabold transition-all ${
        cfg.bg
      } ${cfg.border} ${cfg.text} ${
        large ? 'px-4 py-2 text-xs tracking-wider' : 'px-3 py-1 text-[11px] tracking-wider'
      }`}
    >
      <span className="relative flex h-2 w-2">
        {status === 'running' && pulse && (
          <span className="animate-ping absolute inline-flex h-full w-full bg-[#C8FF3A] opacity-75"></span>
        )}
        <span className={`relative inline-flex h-2 w-2 ${cfg.dotBg}`}></span>
      </span>
      <span>{cfg.label}</span>
    </div>
  );
}
