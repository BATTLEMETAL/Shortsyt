import React from 'react';
import { ShieldCheck, ShieldAlert, KeyRound, AlertTriangle } from 'lucide-react';

interface TokenCountdownProps {
  daysRemaining: number | null;
  isValid: boolean;
  hasToken: boolean;
  message?: string;
  onRefresh?: () => void;
  compact?: boolean;
}

export default function TokenCountdown({
  daysRemaining,
  isValid,
  hasToken,
  message,
  onRefresh,
  compact = false,
}: TokenCountdownProps) {
  const isExpiredOrMissing = !hasToken || !isValid;
  const isUrgent = isExpiredOrMissing || (daysRemaining !== null && daysRemaining < 7);
  const isCritical = isExpiredOrMissing || (daysRemaining !== null && daysRemaining <= 2);

  let theme = {
    border: 'border-[#2ECC71]/40',
    bg: 'bg-[#0E0F11]',
    text: 'text-[#55E88D]',
    badgeBg: 'bg-[#2ECC71]/15',
    iconColor: 'text-[#2ECC71]',
    badgeBorder: 'border-[#2ECC71]/45',
  };

  if (isCritical) {
    theme = {
      border: 'border-[#FF5C5C]/45',
      bg: 'bg-[#0E0F11]',
      text: 'text-[#FF5C5C]',
      badgeBg: 'bg-[#FF5C5C]/15',
      iconColor: 'text-[#FF5C5C]',
      badgeBorder: 'border-[#FF5C5C]/50',
    };
  } else if (isUrgent) {
    theme = {
      border: 'border-[#FFB84D]/45',
      bg: 'bg-[#0E0F11]',
      text: 'text-[#FFB84D]',
      badgeBg: 'bg-[#FFB84D]/15',
      iconColor: 'text-[#FFB84D]',
      badgeBorder: 'border-[#FFB84D]/50',
    };
  }

  function getLabel(): string {
    if (!hasToken) return 'Brak tokenu';
    if (!isValid) return 'Token wygasł';
    if (daysRemaining === null) return 'Token aktywny';
    if (daysRemaining === 0) return 'Wygasa dzisiaj!';
    if (daysRemaining === 1) return 'Wygasa jutro!';
    return `${daysRemaining} dni ważności`;
  }

  if (compact) {
    return (
      <div
        className={`fk-tag inline-flex items-center gap-1.5 px-2.5 py-1 border text-xs font-bold tabular-nums ${theme.bg} ${theme.border} ${theme.text}`}
      >
        {isUrgent ? <AlertTriangle className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
        <span>{getLabel()}</span>
      </div>
    );
  }

  return (
    <div className={`fk-cut-sm p-4 border transition-all ${theme.bg} ${theme.border}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 fk-cut-sm bg-[#17191C] border ${theme.border} ${theme.iconColor}`}>
            {isUrgent ? <ShieldAlert className="w-5 h-5" /> : <ShieldCheck className="w-5 h-5" />}
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-[#A0A7B1] font-bold">
              YouTube OAuth Token
            </div>
            <div className={`text-base font-extrabold flex items-center gap-2 mt-0.5 ${theme.text}`}>
              {getLabel()}
            </div>
            {message && <div className="text-xs text-[#A0A7B1] mt-0.5">{message}</div>}
          </div>
        </div>

        {daysRemaining !== null && hasToken && (
          <div
            className={`fk-cut-sm flex flex-col items-center justify-center w-14 h-14 border font-extrabold tabular-nums ${theme.badgeBg} ${theme.badgeBorder} ${theme.text}`}
          >
            <span className="text-lg leading-none">{daysRemaining}</span>
            <span className="text-[10px] tracking-wide uppercase opacity-80">dni</span>
          </div>
        )}
      </div>

      {isUrgent && (
        <div className="mt-3 pt-3 border-t border-[#272A2F] flex items-center justify-between gap-2">
          <span className="min-w-0 text-xs text-[#FF5C5C] font-semibold flex items-center gap-1.5 leading-snug">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            <span>
              {daysRemaining !== null && daysRemaining < 7
                ? 'Token wygasa za mniej niż 7 dni! Odnów go w ustawieniach.'
                : 'Wymagana ponowna autoryzacja YouTube.'}
            </span>
          </span>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="fk-btn shrink-0 whitespace-nowrap text-xs bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] font-extrabold px-3.5 py-1.5 transition-colors flex items-center gap-1"
            >
              <KeyRound className="w-3 h-3 shrink-0" />
              Autoryzuj
            </button>
          )}
        </div>
      )}
    </div>
  );
}
