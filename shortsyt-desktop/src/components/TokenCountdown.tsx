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
  // Determine color and status
  // Czerwony gdy < 7 dni lub nieważny / brak
  const isExpiredOrMissing = !hasToken || !isValid;
  const isUrgent = isExpiredOrMissing || (daysRemaining !== null && daysRemaining < 7);
  const isCritical = isExpiredOrMissing || (daysRemaining !== null && daysRemaining <= 2);

  let theme = {
    border: 'border-[#2ECC71]/40',
    bg: 'bg-[#2ECC71]/10',
    text: 'text-[#55E88D]',
    badgeBg: 'bg-[#2ECC71]/20',
    iconColor: 'text-[#2ECC71]',
    badgeBorder: 'border-[#2ECC71]/50',
  };

  if (isCritical) {
    theme = {
      border: 'border-[#E84040]/40',
      bg: 'bg-[#E84040]/10',
      text: 'text-[#FF6060]',
      badgeBg: 'bg-[#E84040]/20',
      iconColor: 'text-[#E84040]',
      badgeBorder: 'border-[#E84040]/50',
    };
  } else if (isUrgent) {
    theme = {
      border: 'border-[#F0893A]/40',
      bg: 'bg-[#F0893A]/10',
      text: 'text-[#F0893A]',
      badgeBg: 'bg-[#F0893A]/20',
      iconColor: 'text-[#F0893A]',
      badgeBorder: 'border-[#F0893A]/50',
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
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold ${theme.bg} ${theme.border} ${theme.text}`}
      >
        {isUrgent ? <AlertTriangle className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
        <span>{getLabel()}</span>
      </div>
    );
  }

  return (
    <div className={`p-4 rounded-xl border transition-all ${theme.bg} ${theme.border}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-lg bg-[#0A0E1A]/60 border ${theme.border} ${theme.iconColor}`}>
            {isUrgent ? <ShieldAlert className="w-5 h-5" /> : <ShieldCheck className="w-5 h-5" />}
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-[#8B8FA8] font-semibold">
              YouTube OAuth Token
            </div>
            <div className={`text-base font-bold flex items-center gap-2 mt-0.5 ${theme.text}`}>
              {getLabel()}
            </div>
            {message && <div className="text-xs text-[#8B8FA8] mt-0.5">{message}</div>}
          </div>
        </div>

        {daysRemaining !== null && hasToken && (
          <div
            className={`flex flex-col items-center justify-center w-14 h-14 rounded-xl border font-bold ${theme.badgeBg} ${theme.badgeBorder} ${theme.text}`}
          >
            <span className="text-lg leading-none">{daysRemaining}</span>
            <span className="text-[10px] tracking-wide uppercase opacity-80">dni</span>
          </div>
        )}
      </div>

      {isUrgent && (
        <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
          <span className="text-xs text-[#FF6060] font-medium flex items-center gap-1">
            <AlertTriangle className="w-3.5 h-3.5" />
            {daysRemaining !== null && daysRemaining < 7
              ? 'Token wygasa za mniej niż 7 dni! Odnów go w ustawieniach.'
              : 'Wymagana ponowna autoryzacja YouTube.'}
          </span>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="text-xs bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] font-bold px-3 py-1 rounded-md transition-colors flex items-center gap-1"
            >
              <KeyRound className="w-3 h-3" />
              Autoryzuj
            </button>
          )}
        </div>
      )}
    </div>
  );
}
