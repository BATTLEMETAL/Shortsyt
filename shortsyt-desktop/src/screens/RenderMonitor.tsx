import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  apiGetStatus, apiStopPipeline, PipelineStateResponse,
  apiGetOutputUrl, apiGetThumbnailUrl, apiDeleteOutput, apiUploadToYt,
  apiGetNextPeakSlot, PeakSlotInfo
} from '../lib/api';
import StatusBadge, { PipelineStatusType } from '../components/StatusBadge';
import {
  Cpu, Square, Terminal, RefreshCw, Layers, CheckCircle2, Trash2,
  ArrowLeft, Upload, Play, Film, MessageSquare, Sparkles, FolderOpen, Video, ExternalLink,
  Clock, Calendar, Zap, ShieldCheck
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
  const [description, setDescription] = useState<string>('');
  const [pinnedComment, setPinnedComment] = useState<string>('');
  const [publishMode, setPublishMode] = useState<'peak' | 'now' | 'custom' | 'private'>('peak');
  const [peakSlot, setPeakSlot] = useState<PeakSlotInfo | null>(null);
  const [customPublishTime, setCustomPublishTime] = useState<string>('');
  const [isPublishing, setIsPublishing] = useState<boolean>(false);
  const [publishResult, setPublishResult] = useState<{ ok: boolean; url?: string; error?: string; scheduledFor?: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  const logsContainerRef = useRef<HTMLDivElement>(null);

  const fetchStatus = async () => {
    try {
      const st = await apiGetStatus();
      setPipelineState(st);

      if (st.status === 'done' && st.output_path && !videoUrl) {
        const filename = st.output_path.split('\\').pop() || st.output_path;
        const vUrl = await apiGetOutputUrl(filename);
        setVideoUrl(vUrl);

        const thumbFilename = filename.replace('.mp4', '_thumb.jpg');
        try {
          const tUrl = await apiGetThumbnailUrl(thumbFilename);
          setThumbUrl(tUrl);
        } catch {
          // thumb URL fallback
        }

        if (st.title) setTitle(st.title);
        if (st.description) setDescription(st.description);
        if (st.pinned_comment) setPinnedComment(st.pinned_comment);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1500);
    return () => clearInterval(interval);
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

    const filename = pipelineState.output_path.split('\\').pop() || pipelineState.output_path;
    try {
      const tags = ['league of legends', 'katarina', 'lol', 'shorts', 'gaming', 'montage'];
      
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

      const res = await apiUploadToYt(
        filename,
        title || `Katarina ${pipelineState.action_type || 'Outplay'} #Shorts`,
        description || 'Watch till the end 🔥 #Shorts #LeagueOfLegends',
        tags,
        finalPrivacy,
        pinnedComment || undefined,
        pipelineState.thumbnail_path || undefined,
        finalPublishAt
      );

      setPublishResult({
        ok: true,
        url: res.url || `https://youtube.com/shorts/${res.video_id}`,
        scheduledFor: scheduledLabel,
      });
    } catch (err: any) {
      setPublishResult({
        ok: false,
        error: err.response?.data?.detail || err.message || 'Błąd uploadu na YouTube',
      });
    } finally {
      setIsPublishing(false);
    }
  };

  const handleRejectAndDelete = async () => {
    if (!pipelineState.output_path) return;
    if (!window.confirm('Czy na pewno chcesz odrzucić i usunąć ten wyrenderowany Short?')) return;

    setIsDeleting(true);
    const filename = pipelineState.output_path.split('\\').pop() || pipelineState.output_path;
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

  const filename = pipelineState.output_path ? (pipelineState.output_path.split('\\').pop() || pipelineState.output_path) : '';

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2438]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
            <Cpu className="w-6 h-6 text-[#C89B3C]" />
            <span>Monitor Renderu & Weryfikacja</span>
            <StatusBadge status={pipelineState.status as PipelineStatusType} />
          </h1>
          <p className="text-xs text-[#8B8FA8] mt-1 font-medium">
            {pipelineState.status === 'done'
              ? 'Weryfikacja jakości wyrenderowanego wideo — podejmij decyzję o publikacji lub zmianie parametrów'
              : 'Śledzenie procesu renderowania FFmpeg i analizy OCR w czasie rzeczywistym'}
          </p>
        </div>

        {pipelineState.status === 'running' && (
          <button
            onClick={handleStop}
            disabled={isStopping}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#E84040]/20 hover:bg-[#E84040]/30 border border-[#E84040]/40 text-xs font-bold text-[#FF6060] transition-colors"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            <span>{isStopping ? 'Zatrzymywanie...' : 'Stop Pipeline'}</span>
          </button>
        )}
      </div>

      {/* Progress Bar (Visible while running/idle) */}
      {pipelineState.status !== 'done' && (
        <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#C89B3C]" />
              <span className="text-xs font-bold uppercase tracking-wider text-[#8B8FA8]">
                Krok: {pipelineState.current_step || 'Brak aktywnego zadania'}
              </span>
            </div>
            <span className="text-xl font-black text-[#C89B3C]">{pipelineState.progress}%</span>
          </div>

          <div className="w-full bg-[#0A0E1A] h-3 rounded-full overflow-hidden border border-[#1E2438]">
            <div
              className="bg-gradient-to-r from-[#2A7FD4] via-[#C89B3C] to-[#2ECC71] h-full transition-all duration-500 rounded-full"
              style={{ width: `${Math.max(pipelineState.progress, 0)}%` }}
            />
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
            <div className="lg:col-span-5 flex flex-col items-center bg-[#121624] p-5 rounded-2xl border border-[#C89B3C]/30 shadow-2xl">
              <div className="w-full flex items-center justify-between pb-3 border-b border-[#1E2438] mb-4">
                <span className="text-xs font-bold uppercase tracking-wider text-[#C89B3C] flex items-center gap-2">
                  <Play className="w-4 h-4 text-[#C89B3C]" />
                  Podgląd 9:16 (Zmontowane wideo)
                </span>
                <span className="text-[11px] font-mono text-[#8B8FA8] truncate max-w-[160px]">{filename}</span>
              </div>

              {videoUrl ? (
                <div className="relative rounded-xl overflow-hidden border border-[#1E2438] bg-black shadow-inner max-w-[280px] sm:max-w-[320px] aspect-[9/16] w-full">
                  <video
                    src={videoUrl}
                    controls
                    autoPlay
                    loop
                    className="w-full h-full object-contain"
                  />
                </div>
              ) : (
                <div className="w-full max-w-[280px] aspect-[9/16] rounded-xl bg-[#0A0E1A] flex flex-col items-center justify-center text-[#8B8FA8] border border-[#1E2438]">
                  <RefreshCw className="w-6 h-6 animate-spin text-[#C89B3C] mb-2" />
                  <span className="text-xs font-medium">Ładowanie odtwarzacza...</span>
                </div>
              )}

              {/* Thumbnail 9:16 Section */}
              <div className="w-full mt-5 pt-4 border-t border-[#1E2438] flex flex-col items-center space-y-3">
                <div className="w-full flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-[#8B8FA8] flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-[#C89B3C]" />
                    <span>Miniaturka 9:16 (Hero-Frame)</span>
                  </span>
                  <span className="text-[10px] text-[#2ECC71] font-bold">Auto-Upload z filmem ✅</span>
                </div>

                {thumbUrl ? (
                  <div className="relative rounded-xl overflow-hidden border border-[#1E2438] bg-black max-w-[200px] aspect-[9/16] w-full shadow-lg group">
                    <img
                      src={thumbUrl}
                      alt="Miniaturka 9:16"
                      className="w-full h-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="w-full max-w-[200px] aspect-[9/16] rounded-xl bg-[#0A0E1A] flex flex-col items-center justify-center text-[#8B8FA8] border border-[#1E2438] text-[11px] p-4 text-center">
                    <span>Miniaturka zostanie wgrana automatycznie na YouTube</span>
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
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1E2438] hover:bg-[#2A2D40] text-xs font-bold text-[#E4D6B5] transition-colors"
                  >
                    <FolderOpen className="w-3.5 h-3.5 text-[#C89B3C]" />
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
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#121624] hover:bg-[#1E2438] border border-[#1E2438] text-xs font-semibold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors"
                  >
                    <span>Kopiuj ścieżkę</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Right: Metadata Review & Decision Action Panel */}
            <div className="lg:col-span-7 space-y-4">
              {/* Decision Box Header */}
              <div className="p-5 rounded-2xl bg-[#121624] border border-[#C89B3C]/40 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-xl bg-[#2ECC71]/10 text-[#2ECC71]">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-black text-[#E4D6B5]">Montaż Zakończony — Weryfikacja Widza</h2>
                      <p className="text-xs text-[#8B8FA8]">Obejrzyj klip po lewej i zdecyduj co z nim zrobić</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-2.5 py-1 rounded-md bg-[#C89B3C]/20 border border-[#C89B3C]/40 text-[11px] font-bold text-[#C89B3C] uppercase">
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
                      <span className="px-2.5 py-1 rounded-md bg-[#1E2438]/50 border border-[#1E2438] text-[11px] text-[#50546A]">
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
                  <div className="mt-2 p-2.5 rounded-lg bg-[#0A0E1A] border border-[#1E2438]">
                    <p className="text-[10px] font-bold text-[#8B8FA8] mb-1.5 uppercase tracking-wider">Raport QA</p>
                    <ul className="space-y-0.5">
                      {pipelineState.qa_details.map((d, i) => (
                        <li key={i} className="text-[10px] text-[#50546A] font-mono leading-relaxed">{d}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Metadata Fields */}
                <div className="space-y-3 pt-2">
                  <div>
                    <label className="text-xs font-bold text-[#C89B3C] flex items-center gap-1.5 mb-1">
                      <Sparkles className="w-3.5 h-3.5" />
                      Tytuł YouTube Shorts
                    </label>
                    <input
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Tytuł shortsa..."
                      className="w-full bg-[#0A0E1A] border border-[#1E2438] rounded-xl px-3.5 py-2 text-xs font-bold text-[#E4D6B5] focus:border-[#C89B3C] outline-none"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold text-[#C89B3C] flex items-center gap-1.5 mb-1">
                      <Film className="w-3.5 h-3.5" />
                      Opis i Hashtagi
                    </label>
                    <textarea
                      rows={3}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="Opis wideo..."
                      className="w-full bg-[#0A0E1A] border border-[#1E2438] rounded-xl px-3.5 py-2 text-xs text-[#8B8FA8] focus:border-[#C89B3C] outline-none font-mono"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold text-[#C89B3C] flex items-center gap-1.5 mb-1">
                      <MessageSquare className="w-3.5 h-3.5" />
                      Przypięty Komentarz (Pinned Comment)
                    </label>
                    <input
                      type="text"
                      value={pinnedComment}
                      onChange={(e) => setPinnedComment(e.target.value)}
                      placeholder="Komentarz zachęcający do dyskusji..."
                      className="w-full bg-[#0A0E1A] border border-[#1E2438] rounded-xl px-3.5 py-2 text-xs text-[#E4D6B5] focus:border-[#C89B3C] outline-none"
                    />
                  </div>

                  {/* Publication Timing & Scheduling Engine */}
                  <div className="pt-2 border-t border-[#1E2438] space-y-2.5">
                    <label className="text-xs font-bold text-[#C89B3C] flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5" />
                      Harmonogram & Godziny Publikacji (Peak Hours Engine):
                    </label>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {/* Option 1: AI Peak Hours */}
                      <button
                        type="button"
                        onClick={() => setPublishMode('peak')}
                        className={`p-3 rounded-xl border text-left flex flex-col justify-between transition-all ${
                          publishMode === 'peak'
                            ? 'bg-[#C89B3C]/15 border-[#C89B3C] text-[#E4D6B5] shadow-md shadow-[#C89B3C]/10'
                            : 'bg-[#0A0E1A] border-[#1E2438] text-[#8B8FA8] hover:border-[#C89B3C]/40'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold flex items-center gap-1 text-[#C89B3C]">
                            <Zap className="w-3.5 h-3.5" />
                            AI Peak Slot (Zalecane)
                          </span>
                          <span className="text-[10px] bg-[#2ECC71]/20 text-[#2ECC71] px-1.5 py-0.5 rounded font-bold">
                            TOP TRAFFIC
                          </span>
                        </div>
                        <div className="text-xs font-semibold text-[#E4D6B5] mt-1.5">
                          {peakSlot?.label || 'Dziś o 18:30 CET'}
                        </div>
                        <div className="text-[10px] text-[#8B8FA8] mt-0.5">
                          Automatyczna publikacja w oknie największego ruchu
                        </div>
                      </button>

                      {/* Option 2: Publish Now */}
                      <button
                        type="button"
                        onClick={() => setPublishMode('now')}
                        className={`p-3 rounded-xl border text-left flex flex-col justify-between transition-all ${
                          publishMode === 'now'
                            ? 'bg-[#2ECC71]/15 border-[#2ECC71] text-[#E4D6B5] shadow-md'
                            : 'bg-[#0A0E1A] border-[#1E2438] text-[#8B8FA8] hover:border-[#2ECC71]/40'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold flex items-center gap-1 text-[#2ECC71]">
                            <Upload className="w-3.5 h-3.5" />
                            Opublikuj Teraz
                          </span>
                          <span className="text-[10px] bg-[#2ECC71]/20 text-[#2ECC71] px-1.5 py-0.5 rounded font-bold">
                            PUBLICZNY
                          </span>
                        </div>
                        <div className="text-xs font-semibold text-[#E4D6B5] mt-1.5">
                          Natychmiast (Publiczny)
                        </div>
                        <div className="text-[10px] text-[#8B8FA8] mt-0.5">
                          Film od razu widoczny dla wszystkich widzów
                        </div>
                      </button>

                      {/* Option 3: Private Upload */}
                      <button
                        type="button"
                        onClick={() => setPublishMode('private')}
                        className={`p-2.5 rounded-xl border text-left flex items-center justify-between transition-all ${
                          publishMode === 'private'
                            ? 'bg-[#1E2438] border-[#C89B3C]/50 text-[#E4D6B5]'
                            : 'bg-[#0A0E1A] border-[#1E2438] text-[#8B8FA8] hover:border-[#1E2438]'
                        }`}
                      >
                        <span className="text-xs font-semibold">🔒 Wgraj jako Prywatny (Do wglądu)</span>
                      </button>

                      {/* Option 4: Custom Date/Time */}
                      <button
                        type="button"
                        onClick={() => setPublishMode('custom')}
                        className={`p-2.5 rounded-xl border text-left flex items-center justify-between transition-all ${
                          publishMode === 'custom'
                            ? 'bg-[#1E2438] border-[#C89B3C] text-[#E4D6B5]'
                            : 'bg-[#0A0E1A] border-[#1E2438] text-[#8B8FA8] hover:border-[#1E2438]'
                        }`}
                      >
                        <span className="text-xs font-semibold">🗓️ Własna data / godzina</span>
                      </button>
                    </div>

                    {publishMode === 'custom' && (
                      <div className="pt-2">
                        <label className="text-[11px] font-bold text-[#8B8FA8] block mb-1">
                          Wybierz dokładną datę i godzinę publikacji:
                        </label>
                        <input
                          type="datetime-local"
                          value={customPublishTime}
                          onChange={(e) => setCustomPublishTime(e.target.value)}
                          className="bg-[#0A0E1A] border border-[#1E2438] rounded-xl px-3 py-2 text-xs font-mono text-[#E4D6B5] focus:border-[#C89B3C] outline-none"
                        />
                      </div>
                    )}
                  </div>
                </div>

                {/* Publish Result Alert */}
                {publishResult && (
                  <div className={`p-4 rounded-xl border text-xs font-semibold flex items-center justify-between gap-3 ${publishResult.ok ? 'bg-[#2ECC71]/10 border-[#2ECC71]/40 text-[#55E88D]' : 'bg-[#E84040]/10 border-[#E84040]/40 text-[#FF6060]'}`}>
                    <div>
                      <div>{publishResult.ok ? '🎉 Pomyślnie wgrano na kanał YouTube!' : `Błąd publikacji: ${publishResult.error}`}</div>
                      {publishResult.scheduledFor && (
                        <div className="text-[11px] text-[#C89B3C] font-normal mt-0.5">
                          ⏰ Zaplanowano na: <b>{publishResult.scheduledFor}</b>
                        </div>
                      )}
                    </div>
                    {publishResult.url && (
                      <a
                        href={publishResult.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-1 px-3 py-1 bg-[#2ECC71] text-[#0A0E1A] rounded-lg font-bold hover:bg-[#55E88D] transition-colors shrink-0"
                      >
                        <span>Otwórz Short</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                )}

                {/* USER DECISION ACTION BUTTONS (The 3 Choices) */}
                <div className="pt-4 border-t border-[#1E2438] flex flex-col sm:flex-row items-center gap-3">
                  {/* Choice 1: Accept & Publish */}
                  <button
                    onClick={handlePublish}
                    disabled={isPublishing}
                    className="w-full sm:flex-1 py-3 px-4 rounded-xl bg-gradient-to-r from-[#C89B3C] to-[#E5C269] hover:from-[#E5C269] hover:to-[#F3D78A] text-[#0A0E1A] font-black text-xs flex items-center justify-center gap-2 shadow-lg hover:shadow-[#C89B3C]/20 transition-all cursor-pointer"
                  >
                    <Upload className="w-4 h-4" />
                    <span>{isPublishing ? 'Publikowanie na YouTube...' : '🚀 Zatwierdź i Publikuj na YouTube'}</span>
                  </button>

                  {/* Choice 2: Return to Editor & Adjust */}
                  <button
                    onClick={handleBackToEditor}
                    className="w-full sm:w-auto py-3 px-4 rounded-xl bg-[#1E2438] hover:bg-[#2A2D40] text-[#E4D6B5] font-bold text-xs flex items-center justify-center gap-2 transition-colors cursor-pointer"
                  >
                    <ArrowLeft className="w-4 h-4" />
                    <span>🔄 Wróć / Zmień parametry</span>
                  </button>

                  {/* Choice 3: Reject & Delete */}
                  <button
                    onClick={handleRejectAndDelete}
                    disabled={isDeleting}
                    className="w-full sm:w-auto py-3 px-4 rounded-xl bg-[#E84040]/15 hover:bg-[#E84040]/25 border border-[#E84040]/40 text-[#FF6060] font-bold text-xs flex items-center justify-center gap-2 transition-colors cursor-pointer"
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
      <div className="flex-1 min-h-[260px] flex flex-col rounded-2xl bg-[#070A12] border border-[#1E2438] overflow-hidden shadow-2xl">
        <div className="px-4 py-3 bg-[#121624] border-b border-[#1E2438] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#E4D6B5]">
            <Terminal className="w-4 h-4 text-[#C89B3C]" />
            <span>Pełny strumień logów montażu</span>
          </div>
        </div>

        <div
          ref={logsContainerRef}
          className="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-1 bg-[#070A12] text-[#8B8FA8]"
        >
          {pipelineState.logs && pipelineState.logs.length > 0 ? (
            pipelineState.logs.map((log, index) => (
              <div key={index} className="flex items-start gap-2">
                <span className="text-[#50546A] select-none text-[10px]">{String(index + 1).padStart(3, '0')}</span>
                <span className="break-all whitespace-pre-wrap">{log}</span>
              </div>
            ))
          ) : (
            <div className="h-full flex items-center justify-center text-[#50546A] py-16">
              Brak logów aktywnych.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

