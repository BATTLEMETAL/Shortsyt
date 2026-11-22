import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  apiGetStatus,
  apiGetYtTokenStatus,
  apiHealthCheck,
  apiStopPipeline,
  apiGetLatestOvernight,
  apiGetOvernightStatus,
  apiGetOutputUrl,
  apiGetBackendBaseUrl,
  apiGetSocialAnalytics,
  OvernightBatchManifest,
  OvernightStatusResponse,
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
  Moon,
  Trophy,
  Play,
  Share2,
  Loader2,
  Star,
  X,
  ArrowRight,
  Image as ImageIcon,
  FolderOpen,
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
  const [overnightStatus, setOvernightStatus] = useState<OvernightStatusResponse | null>(null);
  const [latestBatch, setLatestBatch] = useState<OvernightBatchManifest | null>(null);
  const [previewVideoUrl, setPreviewVideoUrl] = useState<string | null>(null);
  const [previewFilename, setPreviewFilename] = useState<string | null>(null);
  const [backendUrl, setBackendUrl] = useState<string>('http://localhost:8765');
  const [brokenThumbs, setBrokenThumbs] = useState<Record<string, boolean>>({});
  const [ttTopTags, setTtTopTags] = useState<string[]>([]);

  const logsContainerRef = useRef<HTMLDivElement>(null);
  const mountedRef = useRef<boolean>(true);
  const lastLoadedBatchIdRef = useRef<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const handlePreviewShort = async (filename: string) => {
    try {
      const url = await apiGetOutputUrl(filename);
      if (mountedRef.current) {
        setPreviewVideoUrl(url);
        setPreviewFilename(filename);
      }
    } catch { }
  };

  // Fetch all dashboard data
  const fetchData = async (silent = false) => {
    if (!silent && mountedRef.current) setIsRefreshing(true);
    try {
      // 1. Health check
      const health = await apiHealthCheck();
      if (!mountedRef.current) return;
      setBackendOk(health.ok);

      if (health.ok) {
        // 2. Pipeline status
        try {
          const st = await apiGetStatus();
          if (!mountedRef.current) return;
          setPipelineState(st);
          if (onStatusChange) onStatusChange(st.status as PipelineStatusType, true);
        } catch {
          // If auth or status fails
        }

        // 3. YouTube token status
        try {
          const yt = await apiGetYtTokenStatus();
          if (mountedRef.current) setYtStatus(yt);
        } catch {
          // YT status fetch error
        }

        // 4. Overnight status & ready batch showcase
        try {
          const onSt = await apiGetOvernightStatus();
          if (!mountedRef.current) return;
          setOvernightStatus(onSt);
          const shouldLoadLatest =
            !silent ||
            lastLoadedBatchIdRef.current === null ||
            (onSt.batch_id && onSt.status === 'done' && onSt.batch_id !== lastLoadedBatchIdRef.current);
          if (shouldLoadLatest) {
            const latestRes = await apiGetLatestOvernight();
            if (mountedRef.current && latestRes?.batch) {
              setLatestBatch(latestRes.batch);
              lastLoadedBatchIdRef.current = latestRes.batch.batch_id;
            }
          }
        } catch {
          // Overnight endpoints optional
        }
      } else {
        if (onStatusChange) onStatusChange('idle', false);
      }
    } catch {
      if (mountedRef.current) setBackendOk(false);
      if (onStatusChange) onStatusChange('idle', false);
    } finally {
      if (!silent && mountedRef.current) setIsRefreshing(false);
    }
  };

  // Initial load
  useEffect(() => {
    apiGetBackendBaseUrl().then((u) => {
      if (mountedRef.current && u) setBackendUrl(u.replace(/\/$/, ''));
    }).catch(() => {});
    apiGetSocialAnalytics('tiktok', false)
      .then((res) => {
        const rec = res?.tiktok_learning?.recommended_hashtags;
        if (mountedRef.current && Array.isArray(rec)) {
          setTtTopTags(rec.map((t: any) => String(t).replace(/^#/, '').toLowerCase()).filter(Boolean).slice(0, 4));
        }
      })
      .catch(() => {});
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
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#050505] p-6 lg:p-8 space-y-6 text-[#FFFFFF]">
      {/* Top Bar Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#272A2F]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#FFFFFF] flex items-center gap-3">
            <span>Studio Dashboard</span>
            <StatusBadge status={pipelineState.status as PipelineStatusType} large />
          </h1>
          <p className="text-xs text-[#A0A7B1] mt-1 font-medium">
            Zarządzanie pipeline publikacji YouTube Shorts z klipów League of Legends
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchData()}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3.5 py-2 fk-cut-sm bg-[#0E0F11] hover:bg-[#17191C] border border-[#272A2F] text-xs font-semibold text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors"
            title="Odśwież stan"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-[#C8FF3A]' : ''}`} />
            <span>Odśwież</span>
          </button>

          {pipelineState.status === 'running' && (
            <button
              onClick={handleStop}
              disabled={isStopping}
              className="flex items-center gap-1.5 px-4 py-2 fk-cut-sm bg-[#FF5C5C]/20 hover:bg-[#FF5C5C]/30 border border-[#FF5C5C]/40 text-xs font-bold text-[#FF5C5C] transition-colors"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              <span>{isStopping ? 'Zatrzymywanie...' : 'Stop Pipeline'}</span>
            </button>
          )}

          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-1.5 px-3.5 py-2 fk-cut-sm bg-[#C8FF3A]/15 hover:bg-[#C8FF3A]/25 border border-[#C8FF3A]/40 text-xs font-bold text-[#C8FF3A] transition-colors"
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Settings</span>
          </button>
        </div>
      </div>

      {/* LIVE OVERNIGHT PROGRESS BANNER */}
      {overnightStatus && ['scanning', 'rendering', 'evaluating'].includes(overnightStatus.status) && (
        <div className="p-4 fk-cut bg-[#0E0F11] border border-indigo-400/50 space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="font-bold text-indigo-200 flex items-center gap-2 min-w-0 truncate">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-300 flex-shrink-0" />
              <span className="truncate">Tryb Nocny w toku: {overnightStatus.phase}</span>
            </span>
            <span className="font-mono text-[#C8FF3A] font-black">{overnightStatus.progress}%</span>
          </div>
          <div className="w-full h-1.5 bg-[#17191C] rounded-full overflow-hidden">
            <div className="h-full bg-indigo-400 transition-all duration-300" style={{ width: `${Math.min(100, Math.max(2, overnightStatus.progress || 0))}%` }} />
          </div>
          <div className="flex items-center justify-between text-[11px] text-[#A0A7B1] flex-wrap gap-2">
            <span>Skan: {overnightStatus.scanned_clips}/{overnightStatus.total_clips} • Mocne: {overnightStatus.qualified_count} • Zmontowano: {overnightStatus.rendered_count}/{overnightStatus.selected_count || 5}</span>
            <button onClick={() => navigate('/clips')} className="text-indigo-300 hover:text-white font-semibold flex items-center gap-1">
              Szczegóły w Przeglądarce Klipów <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      )}

      {/* GOTOWE NAJLEPSZE MONTAŻE Z NOCY (OD RAZU PO ODPALENIU APLIKACJI) */}
      {latestBatch && latestBatch.items && latestBatch.items.length > 0 && (
        <div className="p-5 fk-cut bg-[#0E0F11] border border-[#C8FF3A]/45 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-black text-[#FFFFFF] flex items-center gap-2 flex-wrap">
                <Moon className="w-4 h-4 text-[#C8FF3A]" />
                Gotowe Najlepsze Montaże z Nocy — Top {latestBatch.items.length} Synapsy
                <span className="text-[9px] px-2 py-0.5 rounded bg-indigo-500/20 border border-indigo-400/35 text-indigo-200 font-bold">
                  {latestBatch.champion_name || 'Katarina'} • ZERO AUTO-UPLOADU
                </span>
              </div>
              <div className="text-[11px] text-[#A0A7B1] mt-1">
                Skan: {latestBatch.scan_stats?.scanned_unpublished ?? 0} nieopubl. (znaleziono {latestBatch.scan_stats?.total_clips_found ?? 0}) • Mocne: {latestBatch.scan_stats?.qualified_count ?? 0} • Odrzucone: {latestBatch.scan_stats?.rejected_count ?? 0}
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {latestBatch.recommended_filename && (
                <button
                  onClick={() => handlePreviewShort(latestBatch.recommended_filename!)}
                  className="px-3.5 py-2 fk-cut-sm bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] font-black text-xs flex items-center gap-1.5"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />Odtwórz #1 Synapsy
                </button>
              )}
              <button
                onClick={() => navigate('/outputs')}
                className="px-3 py-2 fk-cut-sm bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] flex items-center gap-1.5"
              >
                Wszystkie Wyjścia <ArrowRight className="w-3.5 h-3.5 text-[#C8FF3A]" />
              </button>
            </div>
          </div>

          {latestBatch.summary_pl && (
            <div className="p-3 fk-cut-sm bg-[#C8FF3A]/10 border border-[#C8FF3A]/40 text-xs text-[#FFFFFF] flex items-start gap-2.5">
              <Trophy className="w-4 h-4 text-[#C8FF3A] flex-shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1 break-words">{latestBatch.summary_pl}</div>
            </div>
          )}

          {previewVideoUrl && (
            <div className="p-3 fk-cut-sm bg-[#050505] border border-[#C8FF3A]/50 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-[#C8FF3A] truncate">Podgląd montażu: {previewFilename}</span>
                <button
                  onClick={() => { setPreviewVideoUrl(null); setPreviewFilename(null); }}
                  className="p-1 text-[#A0A7B1] hover:text-white"
                  title="Zamknij podgląd"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex justify-center bg-black rounded-lg overflow-hidden">
                <video src={previewVideoUrl} controls autoPlay className="max-h-[420px] w-auto" />
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {latestBatch.items.map(item => {
              const isWinner = item.overnight_rank === 1 && item.verdict === 'PICK_WINNER';
              const isPlayingThis = previewFilename === item.output_filename;
              const thumbParts = item.thumbnail_path ? item.thumbnail_path.split(/[\\/]/).filter(Boolean) : [];
              const thumbName = item.thumbnail_filename || (thumbParts.length > 0 ? thumbParts[thumbParts.length - 1] : null);
              const thumbUrl = thumbName && !brokenThumbs[item.output_filename]
                ? `${backendUrl}/thumbnails/${encodeURIComponent(thumbName)}`
                : null;
              return (
                <div
                  key={item.output_filename}
                  className={`p-3.5 fk-cut-sm bg-[#050505] border flex flex-col justify-between gap-2.5 ${
                    isWinner
                      ? 'border-[#C8FF3A] shadow-[0_0_18px_rgba(200,255,58,0.12)]'
                      : isPlayingThis
                      ? 'border-indigo-400'
                      : 'border-[#272A2F]'
                  }`}
                >
                  <div className="flex gap-3 min-w-0">
                    <div className="w-20 flex-shrink-0 flex flex-col gap-1">
                      <div className="w-full aspect-[9/16] rounded-lg bg-[#0E0F11] border border-[#272A2F] overflow-hidden relative group">
                        {thumbUrl ? (
                          <>
                            <img
                              src={thumbUrl}
                              alt={`Miniaturka ${item.champion_name}`}
                              onError={() => setBrokenThumbs(prev => ({ ...prev, [item.output_filename]: true }))}
                              onClick={() => {
                                if (item.thumbnail_path && window.electronApp?.openPath) {
                                  window.electronApp.openPath(item.thumbnail_path);
                                } else if (item.render_ok) {
                                  handlePreviewShort(item.output_filename);
                                }
                              }}
                              className="w-full h-full object-cover cursor-pointer group-hover:scale-105 transition-transform"
                            />
                            {item.thumbnail_path && (
                              <button
                                type="button"
                                onClick={() => window.electronApp?.showItemInFolder?.(item.thumbnail_path!)}
                                title="Pokaż miniaturkę w folderze"
                                className="absolute bottom-1 right-1 p-1 rounded bg-black/75 hover:bg-[#C8FF3A] text-white hover:text-black transition-colors"
                              >
                                <FolderOpen className="w-2.5 h-2.5" />
                              </button>
                            )}
                          </>
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center text-[#686E78] p-1 text-center">
                            <ImageIcon className="w-4 h-4 opacity-50 mb-0.5" />
                            <span className="text-[8px]">Brak</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="space-y-1.5 min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded font-black ${
                            isWinner
                              ? 'bg-[#C8FF3A] text-[#050505]'
                              : item.verdict === 'STRONG_ALT'
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                          }`}
                        >
                          {isWinner ? '⭐ REKOMENDACJA #1' : `#${item.overnight_rank} • ${item.verdict}`}
                        </span>
                        <div className="flex items-center gap-1.5">
                          {item.is_favorite && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-400/20 border border-amber-400/40 text-amber-300 font-bold flex items-center gap-0.5">
                              <Star className="w-2.5 h-2.5 fill-current" />Ulubiony
                            </span>
                          )}
                          <span className="text-[10px] font-bold uppercase text-indigo-300">
                            {item.champion_name} • {item.action_type}
                          </span>
                        </div>
                      </div>

                      <div className="text-xs font-bold text-[#FFFFFF] break-words">
                        {(item.title || item.output_filename).replace(/#\S+/g, '').replace(/\s{2,}/g, ' ').trim() || item.output_filename}
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 text-[9px] font-mono">
                        <span className="px-1.5 py-0.5 rounded bg-[#E62117]/15 border border-[#E62117]/30 text-[#FF8A80]">
                          YT: #shorts #leagueoflegends #lol
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-[#00F2FE]/10 border border-[#00F2FE]/30 text-[#00F2FE]">
                          TikTok: {(ttTopTags.length > 0 ? ttTopTags : ['outplayed', 'pcgaming', 'leagueoflegends', 'lolhighlights']).map((t) => `#${t}`).join(' ')} #{(item.champion_name || 'katarina').replace(/['\s]/g, '').toLowerCase()}
                        </span>
                      </div>
                      <div className="text-[10px] font-mono text-[#686E78] truncate" title={item.source_filename}>
                        {item.match_date ? `${item.match_date} • ` : ''}{item.match_kda ? `KDA ${item.match_kda} • ` : ''}{item.source_filename}
                      </div>

                      <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-mono">
                        <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#C8FF3A]">Final {item.final_score}</span>
                        <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">Hype {item.hype_score}</span>
                        <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">Watch {item.watchability_score ?? '?'}</span>
                        <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">QA {item.qa_score}</span>
                      </div>

                      <p className="text-[11px] text-[#A0A7B1] break-words [overflow-wrap:anywhere]">{item.synapsa_comment_pl}</p>
                    </div>
                  </div>

                  {item.render_ok && (
                    <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                      <button
                        onClick={() => handlePreviewShort(item.output_filename)}
                        className="px-3 py-1.5 rounded-lg bg-[#272A2F] hover:bg-[#32363D] text-xs font-semibold text-[#FFFFFF] flex items-center gap-1.5"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />Odtwórz
                      </button>
                      <button
                        onClick={() => navigate('/outputs', { state: { publishFilename: item.output_filename } })}
                        className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-black flex items-center justify-center gap-1.5 ${
                          isWinner
                            ? 'bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505]'
                            : 'bg-[#17191C] hover:bg-[#272A2F] text-[#C8FF3A] border border-[#C8FF3A]/40'
                        }`}
                      >
                        <Share2 className="w-3.5 h-3.5" />Wybierz i Opublikuj
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Grid: 3 Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Card 1: Backend Connection */}
        <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#A0A7B1]">Backend Status</span>
            <div className={`p-2 rounded-lg ${backendOk ? 'bg-[#2ECC71]/10 text-[#2ECC71]' : 'bg-[#FF5C5C]/10 text-[#FF5C5C]'}`}>
              <Server className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${backendOk ? 'bg-[#2ECC71] animate-pulse' : 'bg-[#FF5C5C]'}`} />
              <span className={`text-lg font-black ${backendOk ? 'text-[#55E88D]' : 'text-[#FF5C5C]'}`}>
                {backendOk ? 'ONLINE (Port 8765)' : 'OFFLINE'}
              </span>
            </div>
            <p className="text-xs text-[#A0A7B1] mt-1">
              {backendOk
                ? 'FastAPI serwer odpowiada prawidłowo'
                : 'Uruchom lol_agent/api/start_server.bat'}
            </p>
          </div>
        </div>

        {/* Card 2: Pipeline State */}
        <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#A0A7B1]">Pipeline Progress</span>
            <div className="p-2 rounded-lg bg-[#5CAEFF]/10 text-[#5CAEFF]">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline justify-between">
              <div className="flex items-center gap-2">
                <span className="text-2xl font-black text-[#FFFFFF]">
                  {pipelineState.progress}%
                </span>
                {pipelineState.queue_length != null && pipelineState.queue_length > 0 && (
                  <span className="text-[10px] font-bold text-[#5CAEFF] bg-[#5CAEFF]/15 px-2 py-0.5 rounded-md border border-[#5CAEFF]/30">
                    +{pipelineState.queue_length} w kolejce
                  </span>
                )}
              </div>
              <span className="text-xs text-[#C8FF3A] font-semibold truncate max-w-[150px]">
                {pipelineState.current_step || (pipelineState.status === 'idle' ? 'Oczekiwanie' : 'Gotowy')}
              </span>
            </div>
            {/* Progress bar */}
            <div className="w-full bg-[#272A2F] h-2 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-[#C8FF3A] h-full transition-all duration-500 rounded-full"
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

      {/* Job Queue Status Panel if queue has items */}
      {pipelineState.queue && pipelineState.queue.length > 0 && (
        <div className="p-4 fk-cut bg-[#0E0F11] border border-[#5CAEFF]/40 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#5CAEFF]" />
              <span className="text-xs font-bold uppercase tracking-wider text-[#FFFFFF]">
                Kolejka renderowania ({pipelineState.queue.length} {pipelineState.queue.length === 1 ? 'zadanie oczekujące' : 'zadań w kolejce'})
              </span>
            </div>
            <button
              onClick={() => navigate('/render')}
              className="text-[11px] font-bold text-[#5CAEFF] hover:text-[#5CAEFF] transition-colors cursor-pointer"
            >
              Otwórz monitor &rarr;
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
            {pipelineState.queue.map((job, idx) => (
              <div key={idx} className="p-3 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5 overflow-hidden">
                  <span className="w-5 h-5 rounded-full bg-[#272A2F] text-[10px] font-bold text-[#A0A7B1] flex items-center justify-center shrink-0">
                    {idx + 1}
                  </span>
                  <div className="truncate">
                    <div className="text-xs font-bold text-[#FFFFFF] truncate">
                      {job.champion_name || 'Brak postaci'} • <span className="text-[#C8FF3A] uppercase">{job.action_type || 'Klip'}</span>
                    </div>
                    <div className="text-[10px] text-[#686E78] font-mono truncate">
                      {job.output_filename || 'auto-output.mp4'}
                    </div>
                  </div>
                </div>
                <span className="text-[10px] font-bold text-[#A0A7B1] bg-[#272A2F] px-2 py-0.5 rounded shrink-0">
                  W kolejce
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error alert if any */}
      {pipelineState.error && (
        <div className="p-4 fk-cut-sm bg-[#FF5C5C]/10 border border-[#FF5C5C]/30 text-[#FF5C5C] text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 flex-shrink-0" />
            <span className="font-semibold">Ostatni błąd renderowania: {pipelineState.error}</span>
          </div>
        </div>
      )}

      {/* Live Logs Terminal Viewer */}
      <div className="flex-1 min-h-[280px] flex flex-col fk-cut bg-[#050505] border border-[#272A2F] overflow-hidden">
        {/* Terminal Header */}
        <div className="px-4 py-3 bg-[#0E0F11] border-b border-[#272A2F] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Terminal className="w-4 h-4 text-[#C8FF3A]" />
            <span className="text-xs font-bold uppercase tracking-wider text-[#FFFFFF]">Live Pipeline Logs</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#272A2F] text-[#A0A7B1] font-mono">
              polling 1.5s
            </span>
          </div>

          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-[#A0A7B1] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="rounded border-[#272A2F] bg-[#050505] text-[#C8FF3A] focus:ring-0"
              />
              <span>Auto-scroll</span>
            </label>
            <button
              onClick={() => navigate('/render')}
              className="text-xs text-[#C8FF3A] hover:text-[#C8FF3A] flex items-center gap-1 font-semibold"
            >
              <span>Pełny monitor</span>
              <ArrowUpRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Terminal Content */}
        <div
          ref={logsContainerRef}
          className="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-1 bg-[#050505] text-[#A0A7B1] leading-relaxed selection:bg-[#C8FF3A]/30"
          style={{ minHeight: '180px', maxHeight: '360px' }}
        >
          {pipelineState.logs && pipelineState.logs.length > 0 ? (
            pipelineState.logs.map((log, index) => {
              const isInfo = log.includes('[INFO]') || log.includes('✅');
              const isWarn = log.includes('[WARN]') || log.includes('⚠');
              const isError = log.includes('[ERROR]') || log.includes('❌') || log.includes('Traceback');
              const isStep = log.includes('[STEP') || log.includes('[1/7]') || log.includes('[2/7]') || log.includes('[7/7]');

              let colorClass = 'text-[#A0A7B1]';
              if (isError) colorClass = 'text-[#FF5C5C] font-semibold';
              else if (isWarn) colorClass = 'text-[#F0893A]';
              else if (isStep) colorClass = 'text-[#C8FF3A] font-bold';
              else if (isInfo) colorClass = 'text-[#55E88D]';

              return (
                <div key={index} className={`flex items-start gap-2 ${colorClass}`}>
                  <span className="text-[#686E78] select-none text-[10px] pt-0.5">{String(index + 1).padStart(2, '0')}</span>
                  <span className="break-all whitespace-pre-wrap">{log}</span>
                </div>
              );
            })
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-[#686E78] py-12">
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
          className="p-4 fk-cut-sm bg-[#0E0F11] hover:bg-[#17191C] border border-[#272A2F] hover:border-[#C8FF3A]/40 cursor-pointer transition-all flex items-center justify-between group"
        >
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-lg bg-[#C8FF3A]/10 text-[#C8FF3A] group-hover:scale-105 transition-transform">
              <Film className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-[#FFFFFF] group-hover:text-[#C8FF3A] transition-colors">
                Przeglądaj nowe klipy Outplayed
              </div>
              <div className="text-xs text-[#A0A7B1]">Auto-skan nagrań i ranking pre-analizy</div>
            </div>
          </div>
          <ArrowUpRight className="w-4 h-4 text-[#A0A7B1] group-hover:text-[#C8FF3A] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
        </div>

        <div
          onClick={() => navigate('/outputs')}
          className="p-4 fk-cut-sm bg-[#0E0F11] hover:bg-[#17191C] border border-[#272A2F] hover:border-[#2ECC71]/40 cursor-pointer transition-all flex items-center justify-between group"
        >
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-lg bg-[#2ECC71]/10 text-[#2ECC71] group-hover:scale-105 transition-transform">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-[#FFFFFF] group-hover:text-[#55E88D] transition-colors">
                Biblioteka wyrenderowanych Shortów
              </div>
              <div className="text-xs text-[#A0A7B1]">Podgląd wideo i 1-click publikacja na YouTube</div>
            </div>
          </div>
          <ArrowUpRight className="w-4 h-4 text-[#A0A7B1] group-hover:text-[#55E88D] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
        </div>
      </div>
    </div>
  );
}
