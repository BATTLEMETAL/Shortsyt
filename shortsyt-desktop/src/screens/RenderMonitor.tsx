import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  apiGetStatus, apiStopPipeline, PipelineStateResponse,
  apiGetOutputUrl, apiGetThumbnailUrl, apiDeleteOutput, apiUploadToYt,
  apiGetNextPeakSlot, PeakSlotInfo, apiPublishMulti
} from '../lib/api';
import StatusBadge, { PipelineStatusType } from '../components/StatusBadge';
import {
  Cpu, Square, Terminal, RefreshCw, Layers, CheckCircle2, Trash2,
  ArrowLeft, Upload, Play, Film, MessageSquare, Sparkles, FolderOpen, Video, ExternalLink,
  Clock, Calendar, Zap, ShieldCheck, Globe, Lock, AlertCircle,
  Youtube, Instagram, Share2
} from 'lucide-react';

export default function RenderMonitor() {
  const navigate = useNavigate();
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
  const [isStopping, setIsStopping] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);

  // Review & Metadata state
  const [title, setTitle] = useState<string>('');
  const [selectedVariant, setSelectedVariant] = useState<'A' | 'B'>('A');
  const [description, setDescription] = useState<string>('');
  const [pinnedComment, setPinnedComment] = useState<string>('');
  const [publishMode, setPublishMode] = useState<'now' | 'peak' | 'custom' | 'private'>('now');
  const [peakSlot, setPeakSlot] = useState<PeakSlotInfo | null>(null);
  const [customPublishTime, setCustomPublishTime] = useState<string>('');
  const [isPublishing, setIsPublishing] = useState<boolean>(false);
  const [publishResult, setPublishResult] = useState<{ ok: boolean; url?: string; error?: string; scheduledFor?: string; privacy?: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [selYt, setSelYt] = useState<boolean>(true);
  const [selTt, setSelTt] = useState<boolean>(true);
  const [selIg, setSelIg] = useState<boolean>(true);
  const [selFb, setSelFb] = useState<boolean>(true);
  const [multiResults, setMultiResults] = useState<Record<string, any> | null>(null);

  const handleSelectPlatformPreset = (preset: 'yt' | 'tt' | 'ig' | 'fb' | 'all') => {
    if (preset === 'yt') {
      setSelYt(true); setSelTt(false); setSelIg(false); setSelFb(false);
    } else if (preset === 'tt') {
      setSelYt(false); setSelTt(true); setSelIg(false); setSelFb(false);
    } else if (preset === 'ig') {
      setSelYt(false); setSelTt(false); setSelIg(true); setSelFb(false);
    } else if (preset === 'fb') {
      setSelYt(false); setSelTt(false); setSelIg(false); setSelFb(true);
    } else if (preset === 'all') {
      setSelYt(true); setSelTt(true); setSelIg(true); setSelFb(true);
    }
  };

  const logsContainerRef = useRef<HTMLDivElement>(null);
  const inFlightRef = useRef<boolean>(false);
  const isRunningRef = useRef<boolean>(false);

  const handleSelectVariant = (variant: 'A' | 'B') => {
    setSelectedVariant(variant);
    if (variant === 'A' && pipelineState.title) {
      setTitle(pipelineState.title);
    } else if (variant === 'B' && pipelineState.title_variant_b) {
      setTitle(pipelineState.title_variant_b);
    }
  };

  const fetchStatus = async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const st = await apiGetStatus();
      isRunningRef.current = st.status === 'running';
      setPipelineState(st);

      if (st.status === 'done' && st.output_path && !videoUrl) {
        const filename = st.output_path.split(/[\\/]/).pop() || st.output_path;
        const vUrl = await apiGetOutputUrl(filename);
        setVideoUrl(vUrl);

        const thumbFilename = filename.replace('.mp4', '_thumb.jpg');
        try {
          const tUrl = await apiGetThumbnailUrl(thumbFilename);
          setThumbUrl(tUrl);
        } catch (err) {
          console.warn('[RenderMonitor] Błąd pobierania URL miniaturki:', err);
        }

        if (st.title) setTitle(st.title);
        if (st.description) setDescription(st.description);
        if (st.pinned_comment) setPinnedComment(st.pinned_comment);
      }
    } catch (err) {
      isRunningRef.current = false;
      console.error(err);
    } finally {
      inFlightRef.current = false;
    }
  };

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const scheduleNext = () => {
      if (!active) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(tick, isRunningRef.current ? 1500 : 5000);
    };

    const tick = async () => {
      if (!active) return;
      if (!document.hidden) {
        await fetchStatus();
      }
      scheduleNext();
    };

    const onVisibilityChange = () => {
      if (!document.hidden && active) {
        if (timer) clearTimeout(timer);
        tick();
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    tick();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [videoUrl]);

  useEffect(() => {
    apiGetNextPeakSlot()
      .then((slot) => setPeakSlot(slot))
      .catch((e) => console.error('Błąd pobierania slotu peak:', e));
  }, []);

  useEffect(() => {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [pipelineState.logs]);

  const handleStop = async () => {
    setIsStopping(true);
    try {
      await apiStopPipeline();
      await fetchStatus();
    } finally {
      setIsStopping(false);
    }
  };

  const handlePublish = async () => {
    if (!pipelineState.output_path) return;
    setIsPublishing(true);
    setPublishResult(null);
    setMultiResults(null);

    const filename = pipelineState.output_path.split(/[\\/]/).pop() || pipelineState.output_path;
    try {
      let finalPrivacy = 'public';
      let finalPublishAt: string | undefined = undefined;
      let scheduledLabel: string | undefined = undefined;

      if (publishMode === 'peak' && peakSlot) {
        finalPrivacy = 'private'; // YouTube API requirement for scheduled
        finalPublishAt = peakSlot.publish_at;
        scheduledLabel = peakSlot.label;
      } else if (publishMode === 'custom' && customPublishTime) {
        finalPrivacy = 'private';
        finalPublishAt = new Date(customPublishTime).toISOString();
        scheduledLabel = customPublishTime;
      } else if (publishMode === 'private') {
        finalPrivacy = 'private';
      } else {
        finalPrivacy = 'public';
      }

      const platforms: string[] = [];
      if (selYt) platforms.push('youtube');
      if (selTt) platforms.push('tiktok');
      if (selIg) platforms.push('instagram');
      if (selFb) platforms.push('facebook');

      if (platforms.length === 0) {
        alert('Zaznacz co najmniej jedną platformę do publikacji!');
        setIsPublishing(false);
        return;
      }

      const res = await apiPublishMulti(filename, {
        title: title || `Katarina ${pipelineState.action_type || 'Outplay'} #shorts`,
        description: description || 'Watch till the end 🔥 #shorts #leagueoflegends',
        platforms,
        privacy_yt: finalPrivacy,
        privacy_tiktok: 'PUBLIC_TO_EVERYONE',
        share_to_ig_feed: true,
        thumbnail_path: pipelineState.thumbnail_path || undefined,
        publish_at: finalPublishAt,
        pinned_comment: pipelineState.pinned_comment || undefined,
        champion_name: pipelineState.champion_name || undefined,
        action_type: pipelineState.action_type || undefined,
        rank: pipelineState.rank || undefined,
      });

      const results = res.results || {};
      setMultiResults(results);

      const anySuccess = Object.values(results).some((r: any) => r?.success);
      const mainUrl = results.youtube?.url || results.instagram?.url || results.facebook?.url;

      setPublishResult({
        ok: anySuccess,
        url: mainUrl,
        scheduledFor: scheduledLabel,
        privacy: finalPrivacy,
        error: anySuccess ? undefined : 'Wszystkie wybrane platformy zgłosiły błąd publikacji'
      });
    } catch (err: any) {
      setPublishResult({
        ok: false,
        error: err.response?.data?.detail || err.message || 'Błąd uploadu multi-platform',
      });
    } finally {
      setIsPublishing(false);
    }
  };

  const handleRejectAndDelete = async () => {
    if (!pipelineState.output_path) return;
    if (!window.confirm('Czy na pewno chcesz odrzucić i usunąć ten wyrenderowany Short?')) return;

    setIsDeleting(true);
    const filename = pipelineState.output_path.split(/[\\/]/).pop() || pipelineState.output_path;
    try {
      await apiDeleteOutput(filename);
      alert('Short został odrzucony i usunięty z dysku.');
      navigate('/clips');
    } catch (err: any) {
      alert(`Błąd usuwania: ${err.message}`);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleBackToEditor = () => {
    navigate('/clips');
  };

  const filename = pipelineState.output_path ? (pipelineState.output_path.split(/[\\/]/).pop() || pipelineState.output_path) : '';

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#050505] p-6 lg:p-8 space-y-6 text-[#FFFFFF]">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#272A2F]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#FFFFFF] flex items-center gap-2.5">
            <Cpu className="w-6 h-6 text-[#C8FF3A]" />
            <span>Monitor Renderu & Weryfikacja</span>
            <StatusBadge status={pipelineState.status as PipelineStatusType} />
          </h1>
          <p className="text-xs text-[#A0A7B1] mt-1 font-medium">
            {pipelineState.status === 'done'
              ? 'Weryfikacja jakości wyrenderowanego wideo — podejmij decyzję o publikacji lub zmianie parametrów'
              : 'Śledzenie procesu renderowania FFmpeg i analizy OCR w czasie rzeczywistym'}
          </p>
        </div>

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
      </div>

      {/* Progress Bar (Visible while running/idle) */}
      {pipelineState.status !== 'done' && (
        <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#C8FF3A]" />
              <span className="text-xs font-bold uppercase tracking-wider text-[#A0A7B1]">
                Krok: {pipelineState.current_step || 'Brak aktywnego zadania'}
              </span>
            </div>
            <span className="text-xl font-black text-[#C8FF3A]">{pipelineState.progress}%</span>
          </div>

          <div className="w-full bg-[#050505] h-3 rounded-full overflow-hidden border border-[#272A2F]">
            <div
              className="bg-[#C8FF3A] h-full transition-all duration-500 rounded-full"
              style={{ width: `${Math.max(pipelineState.progress, 0)}%` }}
            />
          </div>
        </div>
      )}

      {/* Job Queue Status Panel */}
      {pipelineState.queue && pipelineState.queue.length > 0 && (
        <div className="p-5 fk-cut bg-[#0E0F11] border border-[#5CAEFF]/40 space-y-3.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 fk-cut-sm bg-[#5CAEFF]/10 text-[#5CAEFF]">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-black uppercase tracking-wider text-[#FFFFFF]">
                  Kolejka renderowania ({pipelineState.queue.length} {pipelineState.queue.length === 1 ? 'zadanie w kolejce' : 'zadań w kolejce'})
                </h3>
                <p className="text-[11px] text-[#A0A7B1]">Zadania będą przetwarzane automatycznie jedno po drugim (FIFO)</p>
              </div>
            </div>
            <span className="text-[10px] font-bold text-[#5CAEFF] bg-[#5CAEFF]/15 px-2.5 py-1 rounded-full border border-[#5CAEFF]/30 uppercase tracking-wider">
              Aktywny Worker
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
            {pipelineState.queue.map((job, idx) => (
              <div key={idx} className="p-3 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center justify-between gap-2.5">
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
                  Oczekuje
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════════════════════ */}
      {/* INTERACTIVE POST-RENDER REVIEW & APPROVAL SUITE (DONE STATE)                 */}
      {/* ════════════════════════════════════════════════════════════════════════════ */}
      {pipelineState.status === 'done' && pipelineState.output_path && (
        <div className="space-y-6">
          {/* Main Verification Grid: Video Player on Left, Metadata & Decision on Right */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left: 9:16 Vertical Video Player */}
            <div className="lg:col-span-5 flex flex-col items-center bg-[#0E0F11] p-5 fk-cut border border-[#C8FF3A]/30">
              <div className="w-full flex items-center justify-between pb-3 border-b border-[#272A2F] mb-4">
                <span className="text-xs font-bold uppercase tracking-wider text-[#C8FF3A] flex items-center gap-2">
                  <Play className="w-4 h-4 text-[#C8FF3A]" />
                  Podgląd 9:16 (Zmontowane wideo)
                </span>
                <span className="text-[11px] font-mono text-[#A0A7B1] truncate max-w-[160px]">{filename}</span>
              </div>

              {videoUrl ? (
                <div className="fk-crn my-2 max-w-[280px] sm:max-w-[320px] w-full">
                  <div className="relative fk-cut-sm overflow-hidden border border-[#272A2F] bg-black aspect-[9/16] w-full">
                    <video
                      src={videoUrl}
                      controls
                      autoPlay
                      loop
                      className="w-full h-full object-contain"
                    />
                  </div>
                </div>
              ) : (
                <div className="fk-crn my-2 max-w-[280px] w-full">
                  <div className="w-full aspect-[9/16] fk-cut-sm bg-[#050505] flex flex-col items-center justify-center text-[#A0A7B1] border border-[#272A2F]">
                    <RefreshCw className="w-6 h-6 animate-spin text-[#C8FF3A] mb-2" />
                    <span className="text-xs font-medium">Ładowanie odtwarzacza...</span>
                  </div>
                </div>
              )}

              {/* Thumbnail 9:16 Section */}
              <div className="w-full mt-5 pt-4 border-t border-[#272A2F] flex flex-col items-center space-y-3">
                <div className="w-full flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-[#A0A7B1] flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-[#C8FF3A]" />
                    <span>Miniaturka 9:16 (Hero-Frame)</span>
                  </span>
                  <span className="text-[10px] text-[#2ECC71] font-bold">Auto-Upload z filmem ✅</span>
                </div>

                {thumbUrl ? (
                  <div className="fk-crn my-2 max-w-[200px] w-full">
                    <div className="relative fk-cut-sm overflow-hidden border border-[#272A2F] bg-black aspect-[9/16] w-full group">
                      <img
                        src={thumbUrl}
                        alt="Miniaturka 9:16"
                        className="w-full h-full object-cover"
                      />
                    </div>
                  </div>
                ) : (
                  <div className="fk-crn my-2 max-w-[200px] w-full">
                    <div className="w-full aspect-[9/16] fk-cut-sm bg-[#050505] flex flex-col items-center justify-center text-[#A0A7B1] border border-[#272A2F] text-[11px] p-4 text-center">
                      <span>Miniaturka zostanie wgrana automatycznie na YouTube</span>
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 justify-center w-full">
                  <button
                    onClick={() => {
                      if (pipelineState.thumbnail_path && window.electronApp?.showItemInFolder) {
                        window.electronApp.showItemInFolder(pipelineState.thumbnail_path);
                      } else if (pipelineState.output_path && window.electronApp?.showItemInFolder) {
                        window.electronApp.showItemInFolder(pipelineState.output_path.replace('.mp4', '_thumb.jpg'));
                      }
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#272A2F] hover:bg-[#272A2F] text-xs font-bold text-[#FFFFFF] transition-colors"
                  >
                    <FolderOpen className="w-3.5 h-3.5 text-[#C8FF3A]" />
                    <span>Pokaż miniaturkę na dysku</span>
                  </button>

                  <button
                    onClick={() => {
                      const tPath = pipelineState.thumbnail_path || (pipelineState.output_path ? pipelineState.output_path.replace('.mp4', '_thumb.jpg') : '');
                      if (tPath) {
                        navigator.clipboard.writeText(tPath);
                        alert('Skopiowano ścieżkę miniaturki do schowka!');
                      }
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0E0F11] hover:bg-[#272A2F] border border-[#272A2F] text-xs font-semibold text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors"
                  >
                    <span>Kopiuj ścieżkę</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Right: Metadata Review & Decision Action Panel */}
            <div className="lg:col-span-7 space-y-4">
              {/* Decision Box Header */}
              <div className="p-5 fk-cut bg-[#0E0F11] border border-[#C8FF3A]/40 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 fk-cut-sm bg-[#2ECC71]/10 text-[#2ECC71]">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-black text-[#FFFFFF]">Montaż Zakończony — Weryfikacja Widza</h2>
                      <p className="text-xs text-[#A0A7B1]">Obejrzyj klip po lewej i zdecyduj co z nim zrobić</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-2.5 py-1 rounded-md bg-[#C8FF3A]/20 border border-[#C8FF3A]/40 text-[11px] font-bold text-[#C8FF3A] uppercase">
                      {pipelineState.action_type || 'OUTPLAY'}
                    </span>
                    {pipelineState.qa_status === 'PASS' && (
                      <span className="px-2.5 py-1 rounded-md bg-[#2ECC71]/20 border border-[#2ECC71]/40 text-[11px] font-bold text-[#55E88D]">
                        QA PASS ✅ {pipelineState.qa_score != null ? `(${pipelineState.qa_score}/100)` : ''}
                      </span>
                    )}
                    {pipelineState.qa_status === 'WARN' && (
                      <span className="px-2.5 py-1 rounded-md bg-yellow-500/20 border border-yellow-500/40 text-[11px] font-bold text-yellow-400">
                        QA WARN ⚠ {pipelineState.qa_score != null ? `(${pipelineState.qa_score}/100)` : ''}
                      </span>
                    )}
                    {pipelineState.qa_status === 'FAIL' && (
                      <span className="px-2.5 py-1 rounded-md bg-red-500/20 border border-red-500/40 text-[11px] font-bold text-red-400">
                        QA FAIL ❌ {pipelineState.qa_score != null ? `(${pipelineState.qa_score}/100)` : ''}
                      </span>
                    )}
                    {!pipelineState.qa_status && (
                      <span className="px-2.5 py-1 rounded-md bg-[#272A2F]/50 border border-[#272A2F] text-[11px] text-[#686E78]">
                        QA brak danych
                      </span>
                    )}
                    {pipelineState.combat_segments && pipelineState.combat_segments.length > 1 && (
                      <span className="px-2.5 py-1 rounded-md bg-blue-500/15 border border-blue-500/30 text-[11px] font-bold text-blue-400">
                        JUMP-CUT ✂ ({pipelineState.combat_segments.length} seg.)
                      </span>
                    )}
                  </div>
                </div>

                {/* QA Details */}
                {pipelineState.qa_details && pipelineState.qa_details.length > 0 && (
                  <div className="mt-2 p-2.5 rounded-lg bg-[#050505] border border-[#272A2F]">
                    <p className="text-[10px] font-bold text-[#A0A7B1] mb-1.5 uppercase tracking-wider">Raport QA</p>
                    <ul className="space-y-0.5">
                      {pipelineState.qa_details.map((d, i) => (
                        <li key={i} className="text-[10px] text-[#686E78] font-mono leading-relaxed">{d}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Metadata Fields */}
                <div className="space-y-3 pt-2">
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs font-bold text-[#C8FF3A] flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5" />
                        Tytuł YouTube Shorts
                      </label>
                      {pipelineState.title_variant_b && (
                        <div className="flex items-center gap-1 bg-[#050505] p-0.5 rounded-lg border border-[#272A2F]">
                          <button
                            type="button"
                            onClick={() => handleSelectVariant('A')}
                            className={`px-2.5 py-0.5 rounded text-[10px] font-bold transition-all cursor-pointer ${
                              selectedVariant === 'A'
                                ? 'bg-[#C8FF3A] text-[#050505]'
                                : 'text-[#A0A7B1] hover:text-[#FFFFFF]'
                            }`}
                          >
                            Wariant A (Standard)
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSelectVariant('B')}
                            className={`px-2.5 py-0.5 rounded text-[10px] font-bold transition-all flex items-center gap-1 cursor-pointer ${
                              selectedVariant === 'B'
                                ? 'bg-[#5CAEFF] text-white'
                                : 'text-[#A0A7B1] hover:text-[#FFFFFF]'
                            }`}
                          >
                            <span>Wariant B (CTR Hook)</span>
                            <span className="text-[9px]">🧪</span>
                          </button>
                        </div>
                      )}
                    </div>
                    <input
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Tytuł shortsa..."
                      className="w-full bg-[#050505] border border-[#272A2F] fk-cut-sm px-3.5 py-2 text-xs font-bold text-[#FFFFFF] focus:border-[#C8FF3A] outline-none"
                    />
                    {pipelineState.title_variant_b && (
                      <div className="mt-1 text-[10px] text-[#A0A7B1] flex items-center gap-1.5">
                        <span className="text-[#686E78]">
                          {selectedVariant === 'A' ? 'Alternatywny wariant B (CTR Hook):' : 'Bazowy wariant A (Standard):'}
                        </span>
                        <span className="font-mono text-[#FFFFFF]/80 truncate">
                          {selectedVariant === 'A' ? pipelineState.title_variant_b : (pipelineState.title || '')}
                        </span>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="text-xs font-bold text-[#C8FF3A] flex items-center gap-1.5 mb-1">
                      <Film className="w-3.5 h-3.5" />
                      Opis i Hashtagi
                    </label>
                    <textarea
                      rows={3}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="Opis wideo..."
                      className="w-full bg-[#050505] border border-[#272A2F] fk-cut-sm px-3.5 py-2 text-xs text-[#A0A7B1] focus:border-[#C8FF3A] outline-none font-mono"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold text-[#C8FF3A] flex items-center gap-1.5 mb-1">
                      <MessageSquare className="w-3.5 h-3.5" />
                      Przypięty Komentarz (Pinned Comment)
                    </label>
                    <input
                      type="text"
                      value={pinnedComment}
                      onChange={(e) => setPinnedComment(e.target.value)}
                      placeholder="Komentarz zachęcający do dyskusji..."
                      className="w-full bg-[#050505] border border-[#272A2F] fk-cut-sm px-3.5 py-2 text-xs text-[#FFFFFF] focus:border-[#C8FF3A] outline-none"
                    />
                  </div>

                  {/* Multi-Platform Publish Selector Grid */}
                  <div className="pt-2 border-t border-[#272A2F] space-y-2.5">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-[#FFFFFF] flex items-center gap-1.5">
                        <Share2 className="w-3.5 h-3.5 text-[#C8FF3A]" />
                        Gdzie wrzucać (Wybierz platformę lub Wszystko):
                      </label>
                      <span className="text-[10px] text-[#C8FF3A] font-mono font-bold">
                        Wybrano ({[selYt, selTt, selIg, selFb].filter(Boolean).length}/4): {[selYt && 'YT', selTt && 'TikTok', selIg && 'IG', selFb && 'FB'].filter(Boolean).join(' + ') || 'Brak'}
                      </span>
                    </div>

                    {/* 5 Dedykowanych Przycisków Wyboru Celu */}
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                      <button
                        type="button"
                        onClick={() => handleSelectPlatformPreset('yt')}
                        className={`p-2.5 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-1 cursor-pointer select-none ${
                          selYt && !selTt && !selIg && !selFb
                            ? 'bg-[#FF0000]/25 border-[#FF0000] text-white scale-[1.02]'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#FF0000]/60 hover:text-white'
                        }`}
                      >
                        <div className="flex items-center gap-1 text-xs font-bold">
                          <Youtube className="w-4 h-4 text-[#FF0000]" />
                          <span>1. YouTube</span>
                        </div>
                        <span className="text-[10px] text-[#A0A7B1]">Tylko YT Shorts</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleSelectPlatformPreset('tt')}
                        className={`p-2.5 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-1 cursor-pointer select-none ${
                          !selYt && selTt && !selIg && !selFb
                            ? 'bg-[#00F2FE]/25 border-[#00F2FE] text-white scale-[1.02]'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#00F2FE]/60 hover:text-white'
                        }`}
                      >
                        <div className="flex items-center gap-1 text-xs font-bold">
                          <Video className="w-4 h-4 text-[#00F2FE]" />
                          <span>2. TikTok</span>
                        </div>
                        <span className="text-[10px] text-[#A0A7B1]">Tylko TikTok</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleSelectPlatformPreset('ig')}
                        className={`p-2.5 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-1 cursor-pointer select-none ${
                          !selYt && !selTt && selIg && !selFb
                            ? 'bg-[#E1306C]/25 border-[#E1306C] text-white scale-[1.02]'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#E1306C]/60 hover:text-white'
                        }`}
                      >
                        <div className="flex items-center gap-1 text-xs font-bold">
                          <Instagram className="w-4 h-4 text-[#E1306C]" />
                          <span>3. Instagram</span>
                        </div>
                        <span className="text-[10px] text-[#A0A7B1]">Tylko Reels</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleSelectPlatformPreset('fb')}
                        className={`p-2.5 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-1 cursor-pointer select-none ${
                          !selYt && !selTt && !selIg && selFb
                            ? 'bg-[#1877F2]/25 border-[#1877F2] text-white scale-[1.02]'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#1877F2]/60 hover:text-white'
                        }`}
                      >
                        <div className="flex items-center gap-1 text-xs font-bold">
                          <Share2 className="w-4 h-4 text-[#1877F2]" />
                          <span>4. Facebook</span>
                        </div>
                        <span className="text-[10px] text-[#A0A7B1]">Tylko Fanpage</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleSelectPlatformPreset('all')}
                        className={`col-span-2 sm:col-span-1 p-2.5 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-1 cursor-pointer select-none ${
                          selYt && selTt && selIg && selFb
                            ? 'bg-[#C8FF3A]/20 border-[#C8FF3A] text-[#FFFFFF] scale-[1.02]'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#C8FF3A]/60 hover:text-[#FFFFFF]'
                        }`}
                      >
                        <div className="flex items-center gap-1 text-xs font-black text-[#C8FF3A]">
                          <Zap className="w-4 h-4" />
                          <span>5. WSZYSTKO</span>
                        </div>
                        <span className="text-[10px] text-[#C8FF3A] font-semibold">Wszystkie 4 na raz</span>
                      </button>
                    </div>

                    {/* Precyzyjne checkboxy do indywidualnego włączania / wyłączania */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                      <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${
                        selYt ? 'bg-[#FF0000]/15 border-[#FF0000] text-[#FFFFFF]' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] opacity-60'
                      }`}>
                        <input type="checkbox" checked={selYt} onChange={e => setSelYt(e.target.checked)} className="accent-[#FF0000]" />
                        <span className="text-xs font-bold flex items-center gap-1"><Youtube className="w-3.5 h-3.5 text-[#FF0000]" /> YouTube</span>
                      </label>
                      <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${
                        selTt ? 'bg-[#00F2FE]/15 border-[#00F2FE] text-[#FFFFFF]' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] opacity-60'
                      }`}>
                        <input type="checkbox" checked={selTt} onChange={e => setSelTt(e.target.checked)} className="accent-[#00F2FE]" />
                        <span className="text-xs font-bold flex items-center gap-1"><Video className="w-3.5 h-3.5 text-[#00F2FE]" /> TikTok</span>
                      </label>
                      <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${
                        selIg ? 'bg-[#E1306C]/15 border-[#E1306C] text-[#FFFFFF]' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] opacity-60'
                      }`}>
                        <input type="checkbox" checked={selIg} onChange={e => setSelIg(e.target.checked)} className="accent-[#E1306C]" />
                        <span className="text-xs font-bold flex items-center gap-1"><Instagram className="w-3.5 h-3.5 text-[#E1306C]" /> Reels</span>
                      </label>
                      <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${
                        selFb ? 'bg-[#1877F2]/15 border-[#1877F2] text-[#FFFFFF]' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] opacity-60'
                      }`}>
                        <input type="checkbox" checked={selFb} onChange={e => setSelFb(e.target.checked)} className="accent-[#1877F2]" />
                        <span className="text-xs font-bold flex items-center gap-1"><Share2 className="w-3.5 h-3.5 text-[#1877F2]" /> Facebook</span>
                      </label>
                    </div>
                  </div>

                  {/* Publication Timing & Scheduling Engine */}
                  <div className="pt-2 border-t border-[#272A2F] space-y-2.5">
                    <label className="text-xs font-bold text-[#C8FF3A] flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5" />
                      Harmonogram & Godziny Publikacji (Peak Hours Engine):
                    </label>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {/* Option 1: Publish Now (Default) */}
                      <button
                        type="button"
                        onClick={() => setPublishMode('now')}
                        className={`p-3.5 fk-cut-sm border-2 text-left flex flex-col justify-between transition-all cursor-pointer ${
                          publishMode === 'now'
                            ? 'bg-[#2ECC71]/20 border-[#2ECC71] text-[#FFFFFF] ring-2 ring-[#2ECC71]/30 scale-[1.01]'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#2ECC71]/50 opacity-75 hover:opacity-100'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className={`text-xs font-bold flex items-center gap-1.5 ${publishMode === 'now' ? 'text-[#2ECC71]' : 'text-[#A0A7B1]'}`}>
                            <Globe className="w-4 h-4" />
                            Opublikuj Teraz
                          </span>
                          {publishMode === 'now' ? (
                            <span className="text-[10px] bg-[#2ECC71] text-[#050505] px-2 py-0.5 rounded-full font-black flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" />
                              WYBRANO: PUBLICZNY
                            </span>
                          ) : (
                            <span className="text-[10px] bg-[#272A2F] text-[#A0A7B1] px-2 py-0.5 rounded font-bold">
                              PUBLICZNY
                            </span>
                          )}
                        </div>
                        <div className={`text-xs font-bold mt-1.5 ${publishMode === 'now' ? 'text-[#FFFFFF]' : 'text-[#A0A7B1]'}`}>
                          Natychmiast (Publiczny)
                        </div>
                        <div className={`text-[10px] mt-0.5 ${publishMode === 'now' ? 'text-[#A0E8B5]' : 'text-[#686E78]'}`}>
                          Film od razu widoczny dla wszystkich widzów na kanale!
                        </div>
                      </button>

                      {/* Option 2: AI Peak Hours */}
                      <button
                        type="button"
                        onClick={() => setPublishMode('peak')}
                        className={`p-3.5 fk-cut-sm border-2 text-left flex flex-col justify-between transition-all cursor-pointer ${
                          publishMode === 'peak'
                            ? 'bg-[#C8FF3A]/20 border-[#C8FF3A] text-[#FFFFFF] ring-2 ring-[#C8FF3A]/30 scale-[1.01]'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#C8FF3A]/50 opacity-75 hover:opacity-100'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className={`text-xs font-bold flex items-center gap-1.5 ${publishMode === 'peak' ? 'text-[#C8FF3A]' : 'text-[#A0A7B1]'}`}>
                            <Zap className="w-4 h-4" />
                            AI Peak Slot
                          </span>
                          {publishMode === 'peak' ? (
                            <span className="text-[10px] bg-[#C8FF3A] text-[#050505] px-2 py-0.5 rounded-full font-black flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" />
                              WYBRANO: ZAPLANUJ
                            </span>
                          ) : (
                            <span className="text-[10px] bg-[#272A2F] text-[#A0A7B1] px-2 py-0.5 rounded font-bold">
                              ZAPLANUJ
                            </span>
                          )}
                        </div>
                        <div className={`text-xs font-bold mt-1.5 ${publishMode === 'peak' ? 'text-[#FFFFFF]' : 'text-[#A0A7B1]'}`}>
                          {peakSlot?.label || 'Dziś o 21:30 CET'}
                        </div>
                        <div className={`text-[10px] mt-0.5 ${publishMode === 'peak' ? 'text-[#FFFFFF]/90' : 'text-[#686E78]'}`}>
                          Wgrywa jako prywatny i upublicznia w oknie ruchu
                        </div>
                      </button>

                      {/* Option 3: Private Upload */}
                      <button
                        type="button"
                        onClick={() => setPublishMode('private')}
                        className={`p-2.5 fk-cut-sm border text-left flex items-center justify-between transition-all cursor-pointer ${
                          publishMode === 'private'
                            ? 'bg-[#272A2F] border-2 border-[#A0A7B1] text-[#FFFFFF] ring-2 ring-[#A0A7B1]/30 font-bold'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#272A2F] opacity-75 hover:opacity-100'
                        }`}
                      >
                        <span className="text-xs flex items-center gap-1.5">
                          <Lock className="w-3.5 h-3.5" />
                          Wgraj jako Prywatny (Do wglądu)
                        </span>
                        {publishMode === 'private' && (
                          <span className="text-[9px] bg-[#A0A7B1] text-[#050505] px-1.5 py-0.5 rounded font-bold">WYBRANO</span>
                        )}
                      </button>

                      {/* Option 4: Custom Date/Time */}
                      <button
                        type="button"
                        onClick={() => setPublishMode('custom')}
                        className={`p-2.5 fk-cut-sm border text-left flex items-center justify-between transition-all cursor-pointer ${
                          publishMode === 'custom'
                            ? 'bg-[#272A2F] border-2 border-[#5CAEFF] text-[#FFFFFF] ring-2 ring-[#5CAEFF]/30 font-bold'
                            : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#272A2F] opacity-75 hover:opacity-100'
                        }`}
                      >
                        <span className="text-xs flex items-center gap-1.5">
                          <Calendar className="w-3.5 h-3.5" />
                          Własna data / godzina
                        </span>
                        {publishMode === 'custom' && (
                          <span className="text-[9px] bg-[#5CAEFF] text-white px-1.5 py-0.5 rounded font-bold">WYBRANO</span>
                        )}
                      </button>
                    </div>

                    {publishMode === 'custom' && (
                      <div className="pt-2">
                        <label className="text-[11px] font-bold text-[#A0A7B1] block mb-1">
                          Wybierz dokładną datę i godzinę publikacji:
                        </label>
                        <input
                          type="datetime-local"
                          value={customPublishTime}
                          onChange={(e) => setCustomPublishTime(e.target.value)}
                          className="bg-[#050505] border border-[#272A2F] fk-cut-sm px-3 py-2 text-xs font-mono text-[#FFFFFF] focus:border-[#C8FF3A] outline-none"
                        />
                      </div>
                    )}
                  </div>
                </div>

                {/* Publish Result Alert with explicit status report */}
                {publishResult && (() => {
                  const multiEntries = multiResults
                    ? (['youtube', 'tiktok', 'instagram', 'facebook'] as const)
                        .map((k) => multiResults[k])
                        .filter(Boolean)
                    : [];
                  const okCount = multiEntries.filter((v) => v?.success).length;
                  const failCount = multiEntries.filter((v) => v && !v.success).length;
                  const isPartialSuccess = Boolean(publishResult.ok && failCount > 0);
                  const alertStyle = !publishResult.ok
                    ? 'bg-[#FF5C5C]/15 border border-[#FF5C5C]/40 text-[#FF5C5C]'
                    : isPartialSuccess
                    ? 'bg-[#FFB347]/15 border-2 border-[#FFB347] text-[#FFFFFF]'
                    : publishResult.privacy === 'public'
                    ? 'bg-[#2ECC71]/15 border-2 border-[#2ECC71] text-[#FFFFFF]'
                    : 'bg-[#C8FF3A]/15 border-2 border-[#C8FF3A] text-[#FFFFFF]';

                  return (
                  <div className={`p-4 fk-cut-sm border text-xs font-semibold flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 overflow-hidden ${alertStyle}`}>
                    <div className="space-y-1 min-w-0 flex-1">
                      {publishResult.ok ? (
                        <>
                          {isPartialSuccess ? (
                            <div className="flex items-center gap-2 text-sm font-black text-[#FFB347]">
                              <AlertCircle className="w-5 h-5 text-[#FFB347] shrink-0" />
                              <span>⚠️ Opublikowano częściowo ({okCount}/{multiEntries.length}) — sprawdź błędy!</span>
                            </div>
                          ) : publishResult.privacy === 'public' ? (
                            <div className="flex items-center gap-2 text-sm font-black text-[#2ECC71]">
                              <CheckCircle2 className="w-5 h-5 text-[#2ECC71] shrink-0" />
                              <span>🎉 Opublikowano pomyślnie jako PUBLICZNY!</span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2 text-sm font-black text-[#C8FF3A]">
                              <Clock className="w-5 h-5 text-[#C8FF3A] shrink-0" />
                              <span>⏰ Short został wgrany i ZAPLANOWANY!</span>
                            </div>
                          )}

                          {isPartialSuccess ? (
                            <p className="text-[11px] text-[#FFD89B] font-medium">
                              Część platform zgłosiła błąd publikacji — szczegóły poniżej.
                            </p>
                          ) : publishResult.privacy === 'public' ? (
                            <p className="text-[11px] text-[#A0E8B5] font-medium">
                              ✅ Film opublikowany na wybranych platformach.
                            </p>
                          ) : (
                            <p className="text-[11px] text-[#FFFFFF] font-medium">
                              🔒 Film jest obecnie <b>prywatny</b>. Zostanie automatycznie upubliczniony: <b>{publishResult.scheduledFor || 'o zaplanowanej godzinie'}</b>.
                            </p>
                          )}

                          {multiResults && (
                            <div className="pt-2 mt-2 border-t border-[#272A2F] space-y-1 text-[11px] min-w-0">
                              {multiResults.youtube && (
                                <div className={`break-words [overflow-wrap:anywhere] ${multiResults.youtube.success ? "text-[#55E88D]" : "text-[#FF5C5C]"}`}>
                                  YouTube: {multiResults.youtube.success ? `✅ Opublikowano (${multiResults.youtube.url || "OK"})` : `❌ ${multiResults.youtube.error}`}
                                </div>
                              )}
                              {multiResults.tiktok && (
                                <div className={`break-words [overflow-wrap:anywhere] ${multiResults.tiktok.success ? "text-[#55E88D]" : "text-[#FFB347]"}`}>
                                  TikTok: {multiResults.tiktok.success ? `✅ Opublikowano (${multiResults.tiktok.publish_id || "OK"})` : `⚠️ ${multiResults.tiktok.error}`}
                                </div>
                              )}
                              {multiResults.instagram && (
                                <div className={`break-words [overflow-wrap:anywhere] ${multiResults.instagram.success ? "text-[#55E88D]" : "text-[#FF5C5C]"}`}>
                                  Instagram Reels: {multiResults.instagram.success ? `✅ Reel opublikowany (${multiResults.instagram.url || "OK"})` : `❌ ${multiResults.instagram.error}`}
                                </div>
                              )}
                              {multiResults.facebook && (
                                <div className={`break-words [overflow-wrap:anywhere] ${multiResults.facebook.success ? "text-[#55E88D]" : "text-[#FF5C5C]"}`}>
                                  Facebook Page: {multiResults.facebook.success ? `✅ Post opublikowany (${multiResults.facebook.url || "OK"})` : `❌ ${multiResults.facebook.error}`}
                                </div>
                              )}
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="flex items-center gap-2 text-red-400 font-bold break-words [overflow-wrap:anywhere]">
                          <AlertCircle className="w-4 h-4 shrink-0" />
                          <span>Błąd publikacji: {publishResult.error}</span>
                        </div>
                      )}
                    </div>
                    {publishResult.url && (
                      <a
                        href={publishResult.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-1.5 px-4 py-2 bg-[#2ECC71] text-[#050505] fk-cut-sm font-black hover:bg-[#55E88D] transition-all shrink-0 cursor-pointer text-xs"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span>Otwórz Short na YouTube</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                  );
                })()}

                {/* USER DECISION ACTION BUTTONS (The 3 Choices) */}
                <div className="pt-4 border-t border-[#272A2F] flex flex-col sm:flex-row items-center gap-3">
                  {/* Choice 1: Dynamic Accept & Publish Button */}
                  <button
                    onClick={handlePublish}
                    disabled={isPublishing}
                    className={`w-full sm:flex-1 py-3.5 px-5 fk-cut-sm font-black text-xs flex items-center justify-center gap-2 transition-all cursor-pointer ${
                      publishMode === 'now'
                        ? 'fk-btn bg-[#2ECC71] hover:bg-[#55E88D] text-[#050505] shadow-[#2ECC71]/20'
                        : publishMode === 'peak'
                        ? 'fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] shadow-[#C8FF3A]/20'
                        : publishMode === 'private'
                        ? 'bg-[#272A2F] hover:bg-[#272A2F] text-[#FFFFFF] border border-[#A0A7B1]/40'
                        : 'bg-[#5CAEFF] hover:bg-[#5CAEFF] text-white shadow-[#5CAEFF]/20'
                    }`}
                  >
                    {isPublishing ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Publikowanie na wybrane platformy...</span>
                      </>
                    ) : publishMode === 'now' ? (
                      <>
                        <Globe className="w-4 h-4" />
                        <span>
                          {selYt && selTt && selIg && selFb
                            ? '🚀 Opublikuj na WSZYSTKIE 4 platformy (YouTube + TikTok + IG + FB)'
                            : !selYt && !selTt && !selIg && !selFb
                            ? '⚠️ Zaznacz co najmniej jedną platformę'
                            : selYt && !selTt && !selIg && !selFb
                            ? '🚀 Opublikuj na YouTube Shorts'
                            : !selYt && selTt && !selIg && !selFb
                            ? '🚀 Opublikuj na TikTok'
                            : !selYt && !selTt && selIg && !selFb
                            ? '🚀 Opublikuj na Instagram Reels'
                            : !selYt && !selTt && !selIg && selFb
                            ? '🚀 Opublikuj na Facebook Page / Reels'
                            : `🚀 Opublikuj na: ${[selYt && 'YouTube', selTt && 'TikTok', selIg && 'Instagram', selFb && 'Facebook'].filter(Boolean).join(' + ')}`}
                        </span>
                      </>
                    ) : publishMode === 'peak' ? (
                      <>
                        <Zap className="w-4 h-4" />
                        <span>
                          ⏰ Zaplanuj na {peakSlot?.label || '21:30 CET'} ({[selYt && 'YT', selTt && 'TT', selIg && 'IG', selFb && 'FB'].filter(Boolean).join('+') || 'Wybierz'})
                        </span>
                      </>
                    ) : publishMode === 'private' ? (
                      <>
                        <Lock className="w-4 h-4" />
                        <span>
                          🔒 Wgraj jako PRYWATNY ({[selYt && 'YT', selTt && 'TT', selIg && 'IG', selFb && 'FB'].filter(Boolean).join('+') || 'Wybierz'})
                        </span>
                      </>
                    ) : (
                      <>
                        <Calendar className="w-4 h-4" />
                        <span>
                          🗓️ Zaplanuj na {customPublishTime || 'wybraną datę'} ({[selYt && 'YT', selTt && 'TT', selIg && 'IG', selFb && 'FB'].filter(Boolean).join('+') || 'Wybierz'})
                        </span>
                      </>
                    )}
                  </button>

                  {/* Choice 2: Return to Editor & Adjust */}
                  <button
                    onClick={handleBackToEditor}
                    className="w-full sm:w-auto py-3 px-4 fk-cut-sm bg-[#272A2F] hover:bg-[#272A2F] text-[#FFFFFF] font-bold text-xs flex items-center justify-center gap-2 transition-colors cursor-pointer"
                  >
                    <ArrowLeft className="w-4 h-4" />
                    <span>🔄 Wróć / Zmień parametry</span>
                  </button>

                  {/* Choice 3: Reject & Delete */}
                  <button
                    onClick={handleRejectAndDelete}
                    disabled={isDeleting}
                    className="w-full sm:w-auto py-3 px-4 fk-cut-sm bg-[#FF5C5C]/15 hover:bg-[#FF5C5C]/25 border border-[#FF5C5C]/40 text-[#FF5C5C] font-bold text-xs flex items-center justify-center gap-2 transition-colors cursor-pointer"
                  >
                    <Trash2 className="w-4 h-4" />
                    <span>{isDeleting ? 'Usuwanie...' : '🗑️ Odrzuć i Usuń'}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Full Live Logs Section */}
      <div className="flex-1 min-h-[260px] flex flex-col fk-cut bg-[#050505] border border-[#272A2F] overflow-hidden">
        <div className="px-4 py-3 bg-[#0E0F11] border-b border-[#272A2F] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#FFFFFF]">
            <Terminal className="w-4 h-4 text-[#C8FF3A]" />
            <span>Pełny strumień logów montażu</span>
          </div>
        </div>

        <div
          ref={logsContainerRef}
          className="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-1 bg-[#050505] text-[#A0A7B1]"
        >
          {pipelineState.logs && pipelineState.logs.length > 0 ? (
            pipelineState.logs.map((log, index) => (
              <div key={index} className="flex items-start gap-2">
                <span className="text-[#686E78] select-none text-[10px]">{String(index + 1).padStart(3, '0')}</span>
                <span className="break-all whitespace-pre-wrap">{log}</span>
              </div>
            ))
          ) : (
            <div className="h-full flex items-center justify-center text-[#686E78] py-16">
              Brak logów aktywnych.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

