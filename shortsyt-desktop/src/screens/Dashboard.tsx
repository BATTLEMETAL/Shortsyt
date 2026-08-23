import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  apiGetStatus,
  apiGetYtTokenStatus,
  apiHealthCheck,
  apiStopPipeline,
  PipelineStateResponse,
  YtTokenStatusResponse,
} from '../lib/api';
import StatusBadge, { PipelineStatusType } from '../components/StatusBadge';
import TokenCountdown from '../components/TokenCountdown';
import {
  RefreshCw,
  Square,
  Settings,
  Terminal,
  Activity,
  Film,
  Sparkles,
  Server,
  Layers,
  ArrowUpRight,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react';

interface DashboardProps {
  onStatusChange?: (status: PipelineStatusType, connected: boolean) => void;
}

export default function Dashboard({ onStatusChange }: DashboardProps) {
  const navigate = useNavigate();

  // State
  const [backendOk, setBackendOk] = useState<boolean>(false);
  const [pipelineState, setPipelineState] = useState<PipelineStateResponse>({
    status: 'idle',
    progress: 0,
    current_step: '',
    output_path: null,
    error: null,
    started_at: null,
    finished_at: null,
    logs: [],
  });
  const [ytStatus, setYtStatus] = useState<YtTokenStatusResponse>({
    has_token: false,
    is_valid: false,
    can_refresh: false,
    expires_at: null,
    days_remaining: null,
    message: 'Ładowanie statusu...',
  });
  const [isStopping, setIsStopping] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [autoScroll, setAutoScroll] = useState<boolean>(true);

  const logsContainerRef = useRef<HTMLDivElement>(null);

  // Fetch all dashboard data
  const fetchData = async (silent = false) => {
    if (!silent) setIsRefreshing(true);
    try {
      // 1. Health check
      const health = await apiHealthCheck();
      setBackendOk(health.ok);

      if (health.ok) {
        // 2. Pipeline status
        try {
          const st = await apiGetStatus();
          setPipelineState(st);
          if (onStatusChange) onStatusChange(st.status as PipelineStatusType, true);
        } catch {
          // If auth or status fails
        }

        // 3. YouTube token status
        try {
          const yt = await apiGetYtTokenStatus();
          setYtStatus(yt);
        } catch {
          // YT status fetch error
        }
      } else {
        if (onStatusChange) onStatusChange('idle', false);
      }
    } catch {
      setBackendOk(false);
      if (onStatusChange) onStatusChange('idle', false);
    } finally {
      if (!silent) setIsRefreshing(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchData();
  }, []);

  // Polling /status and /health co 1.5s
  useEffect(() => {
    const interval = setInterval(() => {
      fetchData(true);
    }, 1500);

    return () => clearInterval(interval);
  }, []);

  // Auto scroll logs to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [pipelineState.logs, autoScroll]);

  // Handle Stop Pipeline
  const handleStop = async () => {
    if (isStopping) return;
    setIsStopping(true);
    try {
      await apiStopPipeline();
      await fetchData(true);
    } catch (err) {
      console.error('Stop error:', err);
    } finally {
      setIsStopping(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      {/* Top Bar Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2438]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-3">
            <span>Studio Dashboard</span>
            <StatusBadge status={pipelineState.status as PipelineStatusType} large />
          </h1>
          <p className="text-xs text-[#8B8FA8] mt-1 font-medium">
            Zarządzanie pipeline publikacji YouTube Shorts z klipów League of Legends
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchData()}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#121624] hover:bg-[#1A1E30] border border-[#1E2438] text-xs font-semibold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors"
            title="Odśwież stan"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-[#C89B3C]' : ''}`} />
            <span>Odśwież</span>
          </button>

          {pipelineState.status === 'running' && (
            <button
              onClick={handleStop}
              disabled={isStopping}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#E84040]/20 hover:bg-[#E84040]/30 border border-[#E84040]/40 text-xs font-bold text-[#FF6060] transition-colors shadow-lg shadow-[#E84040]/10"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              <span>{isStopping ? 'Zatrzymywanie...' : 'Stop Pipeline'}</span>
            </button>
          )}

          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#C89B3C]/15 hover:bg-[#C89B3C]/25 border border-[#C89B3C]/40 text-xs font-bold text-[#C89B3C] transition-colors"
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Settings</span>
          </button>
        </div>
      </div>

      {/* Grid: 3 Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Card 1: Backend Connection */}
        <div className="p-5 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-md flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#8B8FA8]">Backend Status</span>
            <div className={`p-2 rounded-lg ${backendOk ? 'bg-[#2ECC71]/10 text-[#2ECC71]' : 'bg-[#E84040]/10 text-[#E84040]'}`}>
              <Server className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${backendOk ? 'bg-[#2ECC71] shadow-lg shadow-[#2ECC71]/50 animate-pulse' : 'bg-[#E84040]'}`} />
              <span className={`text-lg font-black ${backendOk ? 'text-[#55E88D]' : 'text-[#FF6060]'}`}>
                {backendOk ? 'ONLINE (Port 8765)' : 'OFFLINE'}
              </span>
            </div>
            <p className="text-xs text-[#8B8FA8] mt-1">
              {backendOk
                ? 'FastAPI serwer odpowiada prawidłowo'
                : 'Uruchom lol_agent/api/start_server.bat'}
            </p>
          </div>
        </div>

        {/* Card 2: Pipeline State */}
        <div className="p-5 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-md flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#8B8FA8]">Pipeline Progress</span>
            <div className="p-2 rounded-lg bg-[#2A7FD4]/10 text-[#4FA3F7]">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline justify-between">
              <span className="text-2xl font-black text-[#E4D6B5]">
                {pipelineState.progress}%
              </span>
              <span className="text-xs text-[#C89B3C] font-semibold truncate max-w-[150px]">
                {pipelineState.current_step || (pipelineState.status === 'idle' ? 'Oczekiwanie' : 'Gotowy')}
              </span>
            </div>
            {/* Progress bar */}
            <div className="w-full bg-[#1E2438] h-2 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-[#2A7FD4] via-[#C89B3C] to-[#55E88D] h-full transition-all duration-500 rounded-full"
                style={{ width: `${Math.max(pipelineState.progress, 0)}%` }}
              />
            </div>
          </div>
        </div>

        {/* Card 3: YouTube Token Status */}
        <TokenCountdown
          daysRemaining={ytStatus.days_remaining}
          isValid={ytStatus.is_valid}
          hasToken={ytStatus.has_token}
          message={ytStatus.message}
          onRefresh={() => navigate('/settings')}
        />
      </div>

      {/* Error alert if any */}
      {pipelineState.error && (
        <div className="p-4 rounded-xl bg-[#E84040]/10 border border-[#E84040]/30 text-[#FF6060] text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 flex-shrink-0" />
            <span className="font-semibold">Ostatni błąd renderowania: {pipelineState.error}</span>
          </div>
        </div>
      )}

      {/* Live Logs Terminal Viewer */}
      <div className="flex-1 min-h-[280px] flex flex-col rounded-2xl bg-[#070A12] border border-[#1E2438] overflow-hidden shadow-xl">
        {/* Terminal Header */}
        <div className="px-4 py-3 bg-[#121624] border-b border-[#1E2438] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Terminal className="w-4 h-4 text-[#C89B3C]" />
            <span className="text-xs font-bold uppercase tracking-wider text-[#E4D6B5]">Live Pipeline Logs</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#1E2438] text-[#8B8FA8] font-mono">
              polling 1.5s
            </span>
          </div>

          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-[#8B8FA8] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="rounded border-[#1E2438] bg-[#0A0E1A] text-[#C89B3C] focus:ring-0"
              />
              <span>Auto-scroll</span>
            </label>
            <button
              onClick={() => navigate('/render')}
              className="text-xs text-[#C89B3C] hover:text-[#E5C269] flex items-center gap-1 font-semibold"
            >
              <span>Pełny monitor</span>
              <ArrowUpRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Terminal Content */}
        <div
          ref={logsContainerRef}
          className="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-1 bg-[#070A12] text-[#8B8FA8] leading-relaxed selection:bg-[#C89B3C]/30"
          style={{ minHeight: '180px', maxHeight: '360px' }}
        >
          {pipelineState.logs && pipelineState.logs.length > 0 ? (
            pipelineState.logs.map((log, index) => {
              const isInfo = log.includes('[INFO]') || log.includes('✅');
              const isWarn = log.includes('[WARN]') || log.includes('⚠');
              const isError = log.includes('[ERROR]') || log.includes('❌') || log.includes('Traceback');
              const isStep = log.includes('[STEP') || log.includes('[1/7]') || log.includes('[2/7]') || log.includes('[7/7]');

              let colorClass = 'text-[#8B8FA8]';
              if (isError) colorClass = 'text-[#FF6060] font-semibold';
              else if (isWarn) colorClass = 'text-[#F0893A]';
              else if (isStep) colorClass = 'text-[#C89B3C] font-bold';
              else if (isInfo) colorClass = 'text-[#55E88D]';

              return (
                <div key={index} className={`flex items-start gap-2 ${colorClass}`}>
                  <span className="text-[#50546A] select-none text-[10px] pt-0.5">{String(index + 1).padStart(2, '0')}</span>
                  <span className="break-all whitespace-pre-wrap">{log}</span>
                </div>
              );
            })
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-[#50546A] py-12">
              <Terminal className="w-8 h-8 mb-2 opacity-40" />
              <p>Brak aktywnych logów w buforze.</p>
              <p className="text-[11px] mt-1 opacity-70">Uruchom render klipu w zakładce &apos;Klipy&apos; lub przez API.</p>
            </div>
          )}
        </div>
      </div>

      {/* Quick Launch & Status Highlights Banner */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
        <div
          onClick={() => navigate('/clips')}
          className="p-4 rounded-xl bg-[#121624] hover:bg-[#1A1E30] border border-[#1E2438] hover:border-[#C89B3C]/40 cursor-pointer transition-all flex items-center justify-between group"
        >
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-lg bg-[#C89B3C]/10 text-[#C89B3C] group-hover:scale-105 transition-transform">
              <Film className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-[#E4D6B5] group-hover:text-[#C89B3C] transition-colors">
                Przeglądaj nowe klipy Outplayed
              </div>
              <div className="text-xs text-[#8B8FA8]">Auto-skan nagrań i ranking pre-analizy</div>
            </div>
          </div>
          <ArrowUpRight className="w-4 h-4 text-[#8B8FA8] group-hover:text-[#C89B3C] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
        </div>

        <div
          onClick={() => navigate('/outputs')}
          className="p-4 rounded-xl bg-[#121624] hover:bg-[#1A1E30] border border-[#1E2438] hover:border-[#2ECC71]/40 cursor-pointer transition-all flex items-center justify-between group"
        >
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-lg bg-[#2ECC71]/10 text-[#2ECC71] group-hover:scale-105 transition-transform">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-[#E4D6B5] group-hover:text-[#55E88D] transition-colors">
                Biblioteka wyrenderowanych Shortów
              </div>
              <div className="text-xs text-[#8B8FA8]">Podgląd wideo i 1-click publikacja na YouTube</div>
            </div>
          </div>
          <ArrowUpRight className="w-4 h-4 text-[#8B8FA8] group-hover:text-[#55E88D] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
        </div>
      </div>
    </div>
  );
}
