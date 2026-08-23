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
    bg: 'bg-[#1E2438]/60',
    text: 'text-[#8B8FA8]',
    border: 'border-[#2D3550]',
    icon: <PauseCircle className="w-3.5 h-3.5" />,
    dotBg: 'bg-[#8B8FA8]',
  },
  running: {
    label: 'PRZETWARZANIE',
    bg: 'bg-[#2A7FD4]/15',
    text: 'text-[#4FA3F7]',
    border: 'border-[#2A7FD4]/40',
    icon: <Play className="w-3.5 h-3.5 fill-current animate-pulse" />,
    dotBg: 'bg-[#4FA3F7]',
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
    bg: 'bg-[#E84040]/15',
    text: 'text-[#FF6060]',
    border: 'border-[#E84040]/40',
    icon: <AlertCircle className="w-3.5 h-3.5" />,
    dotBg: 'bg-[#E84040]',
  },
};

export default function StatusBadge({ status, large = false, pulse = true }: StatusBadgeProps) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle;

  return (
    <div
      className={`inline-flex items-center gap-2 border rounded-full font-semibold transition-all ${
        cfg.bg
      } ${cfg.border} ${cfg.text} ${
        large ? 'px-4 py-2 text-sm tracking-wider' : 'px-3 py-1 text-xs tracking-wide'
      }`}
    >
      <span className="relative flex h-2 w-2">
        {status === 'running' && pulse && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
        )}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${cfg.dotBg}`}></span>
      </span>
      <span>{cfg.label}</span>
    </div>
  );
}
