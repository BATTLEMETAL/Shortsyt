import React, { useState, useEffect } from 'react';
import { 
  Calendar as CalendarIcon, Clock, Sparkles, Trash2, Send, 
  CheckCircle, AlertCircle, RefreshCw, Film, Flame, ShieldAlert,
  ArrowRight, Plus, ExternalLink, BarChart3, Activity, X,
  Filter, ArrowDownUp
} from 'lucide-react';
import { 
  apiGetCalendarSlots, apiReserveCalendarSlot, apiDeleteCalendarSlot, 
  apiPublishCalendarSlot, apiAutoFillCalendar, apiListClips, apiAnalyzeFrag,
  apiGetLearningStatus, apiRecalibrateLearning, apiGetVideoRetention,
  apiGetSocialQueue, apiFlushSocialQueue,
  CalendarSlot, FragAnalysis, ClipItem, LearningDirective, VideoRetentionData, SocialQueueItem
} from '../lib/api';

export function CalendarScheduler() {
  const [slots, setSlots] = useState<CalendarSlot[]>([]);
  const [peakHoursCet, setPeakHoursCet] = useState<string[]>(['15:00', '21:30']);
  const [days, setDays] = useState<number>(14);
  const [loading, setLoading] = useState<boolean>(true);
  const [autoFilling, setAutoFilling] = useState<boolean>(false);
  const [flushingQueue, setFlushingQueue] = useState<boolean>(false);
  const [socialQueueItems, setSocialQueueItems] = useState<SocialQueueItem[]>([]);
  const [socialSummary, setSocialSummary] = useState<{ total: number; pending: number; published: number; failed: number }>({ total: 0, pending: 0, published: 0, failed: 0 });
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [learning, setLearning] = useState<LearningDirective | null>(null);
  const [learningLoading, setLearningLoading] = useState<boolean>(false);
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const [statusFilter, setStatusFilter] = useState<'all' | 'published' | 'scheduled' | 'free' | 'reserved'>('all');

  // Modal State
  const [selectedSlot, setSelectedSlot] = useState<CalendarSlot | null>(null);
  const [availableClips, setAvailableClips] = useState<ClipItem[]>([]);
  const [selectedClipPath, setSelectedClipPath] = useState<string>('');
  const [champion, setChampion] = useState<string>('Katarina');
  const [fragMode, setFragMode] = useState<'auto' | 'manual'>('auto');
  const [manualFrag, setManualFrag] = useState<string>('pentakill');
  const [analyzedFrag, setAnalyzedFrag] = useState<FragAnalysis | null>(null);
  const [analyzingFrag, setAnalyzingFrag] = useState<boolean>(false);
  const [slotTitle, setSlotTitle] = useState<string>('');

  // Retention Modal State (Step 4: YouTube Analytics API)
  const [retentionSlot, setRetentionSlot] = useState<CalendarSlot | null>(null);
  const [retentionData, setRetentionData] = useState<VideoRetentionData | null>(null);
  const [retentionLoading, setRetentionLoading] = useState<boolean>(false);

  const handleOpenRetentionModal = async (slot: CalendarSlot) => {
    if (!slot.yt_video_id) return;
    setRetentionSlot(slot);
    setRetentionLoading(true);
    setRetentionData(null);
    try {
      const res = await apiGetVideoRetention(slot.yt_video_id, slot.duration_s || 13.0);
      if (res && res.data) {
        setRetentionData(res.data);
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: `Błąd pobierania retencji YouTube Analytics: ${e.message}` });
    } finally {
      setRetentionLoading(false);
    }
  };

  const loadLearning = async () => {
    try {
      const res = await apiGetLearningStatus();
      if (res && res.directive) setLearning(res.directive);
    } catch (e) {
      console.warn('[Calendar] Błąd pobierania statusu uczenia:', e);
    }
  };

  const handleRecalibrateLearning = async () => {
    try {
      setLearningLoading(true);
      const res = await apiRecalibrateLearning();
      if (res && res.result && res.result.directive) {
        setLearning(res.result.directive);
        setMessage({ type: 'success', text: `🧠 Zaktualizowano samouczenie: format ${res.result.directive.top_action_type.toUpperCase()} zyskał priorytet!` });
      }
      await loadSlots(true, true);
    } catch (e: any) {
      setMessage({ type: 'error', text: `Błąd rekalibracji: ${e.message}` });
    } finally {
      setLearningLoading(false);
    }
  };

  const loadSlots = async (silent: boolean = false, forceRefresh: boolean = false) => {
    try {
      if (!silent) setLoading(true);
      const [res, qRes] = await Promise.all([
        apiGetCalendarSlots(undefined, days, forceRefresh),
        apiGetSocialQueue().catch(() => null),
      ]);
      setSlots(res.slots || []);
      if (Array.isArray(res.peak_hours_cet) && res.peak_hours_cet.length > 0) {
        setPeakHoursCet(res.peak_hours_cet);
      }
      if (qRes) {
        setSocialQueueItems(qRes.items || []);
        setSocialSummary(qRes.summary || { total: 0, pending: 0, published: 0, failed: 0 });
      } else if (res.social_queue_summary) {
        setSocialSummary(res.social_queue_summary);
      }
    } catch (e: any) {
      if (!silent) setMessage({ type: 'error', text: `Błąd wczytywania kalendarza: ${e.message}` });
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleFlushSocialQueue = async () => {
    try {
      setFlushingQueue(true);
      const res = await apiFlushSocialQueue();
      setMessage({
        type: 'success',
        text: `⏰ Kolejka Multi-Platform wykonana: ${res.flushed_posts} post(ów) TikTok/IG + ${res.flushed_comments} komentarz(y) YT.`,
      });
      await loadSlots(true, false);
    } catch (e: any) {
      setMessage({ type: 'error', text: `Błąd kolejki TikTok/IG: ${e.message}` });
    } finally {
      setFlushingQueue(false);
    }
  };

  const loadClips = async () => {
    try {
      const clips = await apiListClips();
      setAvailableClips(clips || []);
    } catch (e) {
      console.warn('[Calendar] Błąd pobierania listy klipów:', e);
    }
  };

  useEffect(() => {
    loadSlots(false);
    loadClips();
    loadLearning();
    const interval = setInterval(() => {
      loadSlots(true);
    }, 45000); // odświeżanie danych YouTube w tle co 45s (cichy tryb)
    return () => clearInterval(interval);
  }, [days]);

  const handleAutoFill = async () => {
    try {
      setAutoFilling(true);
      setMessage(null);
      const res = await apiAutoFillCalendar(4);
      setMessage({ type: 'success', text: `⚡ Przypisano automatycznie ${res.assigned_count} klipów do najbliższych wolnych slotów Peak!` });
      await loadSlots();
    } catch (e: any) {
      setMessage({ type: 'error', text: `Błąd auto-rezerwacji: ${e.message}` });
      await loadSlots();
    } finally {
      setAutoFilling(false);
    }
  };

  const handleOpenReserveModal = (slot: CalendarSlot) => {
    setSelectedSlot(slot);
    setSelectedClipPath(slot.source_clip || '');
    setChampion(slot.champion || 'Katarina');
    setSlotTitle(slot.title || '');
    setFragMode('auto');
    setManualFrag(slot.frag_type || 'pentakill');
    setAnalyzedFrag(null);
  };

  const handleClipSelect = async (path: string) => {
    setSelectedClipPath(path);
    if (!path) {
      setAnalyzedFrag(null);
      return;
    }

    try {
      setAnalyzingFrag(true);
      const analysis = await apiAnalyzeFrag(path);
      setAnalyzedFrag(analysis);
      if (fragMode === 'auto') {
        setSlotTitle(`${analysis.suggested_title_hook} #Shorts #LeagueOfLegends`);
      }
    } catch (e) {
      console.warn('[Calendar] Błąd analizy fraga klipu:', e);
    } finally {
      setAnalyzingFrag(false);
    }
  };

  const handleSaveReservation = async () => {
    if (!selectedSlot) return;
    try {
      setActionLoading('saving');
      const finalFrag = fragMode === 'auto' 
        ? (analyzedFrag?.detected_frag_type || 'outplay')
        : manualFrag;

      await apiReserveCalendarSlot({
        slot_id: selectedSlot.slot_id,
        title: slotTitle || `League of Legends ${finalFrag.toUpperCase()} #shorts`,
        champion: champion,
        frag_type: finalFrag,
        source_clip: selectedClipPath,
        notes: fragMode === 'auto' && analyzedFrag 
          ? `Auto AI: ${analyzedFrag.badge_label} (Pewność: ${Math.round(analyzedFrag.confidence * 100)}%)` 
          : 'Ręczna rezerwacja użytkownika',
      });

      setMessage({ type: 'success', text: `✅ Pomyślnie zarezerwowano slot: ${selectedSlot.datetime_local}` });
      setSelectedSlot(null);
      await loadSlots();
    } catch (e: any) {
      setMessage({ type: 'error', text: `Błąd rezerwacji: ${e.message}` });
    } finally {
      setActionLoading(null);
    }
  };

  const handleReleaseSlot = async (slotId: string) => {
    if (!confirm('Czy na pewno chcesz zwolnić tę rezerwację?')) return;
    try {
      setActionLoading(slotId);
      await apiDeleteCalendarSlot(slotId);
      setMessage({ type: 'success', text: 'Zwolniono slot w kalendarzu' });
      await loadSlots();
    } catch (e: any) {
      setMessage({ type: 'error', text: `Błąd zwalniania: ${e.message}` });
    } finally {
      setActionLoading(null);
    }
  };

  const handlePublishNow = async (slotId: string) => {
    try {
      setActionLoading(slotId);
      const res = await apiPublishCalendarSlot(slotId);
      setMessage({ type: 'success', text: `🚀 Wideo zostało zaplanowane na YouTube! ID: ${res.youtube?.video_id}` });
      await loadSlots();
    } catch (e: any) {
      setMessage({ type: 'error', text: `Błąd planowania na YT: ${e.message}` });
    } finally {
      setActionLoading(null);
    }
  };

  // Filter slots
  const filteredSlots = slots.filter(s => {
    if (statusFilter === 'all') return true;
    if (statusFilter === 'published') return s.status === 'published';
    if (statusFilter === 'scheduled') return s.status === 'scheduled';
    if (statusFilter === 'free') return s.status === 'free' && !s.is_past;
    if (statusFilter === 'reserved') return s.status === 'reserved';
    return true;
  });

  // Group slots by Date
  const groupedSlots: { [date: string]: CalendarSlot[] } = {};
  filteredSlots.forEach(s => {
    if (!groupedSlots[s.date]) groupedSlots[s.date] = [];
    groupedSlots[s.date].push(s);
  });

  const sortedDates = Object.keys(groupedSlots).sort((a, b) => {
    return sortOrder === 'desc' ? b.localeCompare(a) : a.localeCompare(b);
  });

  // Calculate KPIs
  const totalReserved = slots.filter(s => s.status === 'reserved').length;
  const totalScheduled = slots.filter(s => s.status === 'scheduled').length;
  const totalPublished = slots.filter(s => s.status === 'published').length;
  const totalFreePeak = slots.filter(s => s.status === 'free' && !s.is_past).length;

  const publishedWithViews = slots.filter(s => s.status === 'published' && s.views !== undefined);
  const totalViews = publishedWithViews.reduce((acc, s) => acc + (s.views || 0), 0);
  const avgViews = publishedWithViews.length > 0 ? Math.round(totalViews / publishedWithViews.length) : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-[#0E0F11] border border-[#272A2F] fk-cut-sm p-6">
        <div>
          <div className="flex items-center gap-2">
            <CalendarIcon className="w-7 h-7 text-[#C8FF3A]" />
            <h1 className="text-2xl font-bold text-white tracking-tight">Kalendarz Publikacji i Analityka Skuteczności</h1>
          </div>
          <p className="text-[#A0A7B1] text-sm mt-1">
            Harmonogram 2 filmów dziennie ({peakHoursCet.join(' i ')} CET) • Zero kanibalizacji zasięgów • Wskaźnik skuteczności Shortsów
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleAutoFill}
            disabled={autoFilling}
            className="flex items-center gap-2 px-4 py-2.5 fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] font-semibold rounded-lg transition disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            {autoFilling ? 'Rezerwowanie...' : '⚡ Auto-Rezerwacja AI'}
          </button>

          <div className="flex items-center bg-[#17191C] rounded-lg p-1 border border-[#272A2F]">
            {[7, 14, 30].map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                  days === d ? 'bg-[#C8FF3A] text-[#050505] font-extrabold' : 'text-[#A0A7B1] hover:text-white'
                }`}
              >
                {d} dni
              </button>
            ))}
          </div>

          <button
            onClick={() => loadSlots(false, true)}
            disabled={loading}
            className="p-2.5 bg-[#17191C] hover:bg-[#272A2F] text-[#FFFFFF] rounded-lg border border-[#272A2F] transition"
            title="Wymuś odświeżenie kalendarza z YouTube"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

        </div>
      </div>

      {/* Notifications */}
      {message && (
        <div className={`p-4 rounded-lg flex items-center gap-3 border ${
          message.type === 'success' 
            ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300' 
            : 'bg-rose-950/40 border-rose-800 text-rose-300'
        }`}>
          {message.type === 'success' ? <CheckCircle className="w-5 h-5 flex-shrink-0" /> : <AlertCircle className="w-5 h-5 flex-shrink-0" />}
          <span className="text-sm">{message.text}</span>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-[#0E0F11] border border-[#272A2F] fk-cut-sm p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#A0A7B1] uppercase tracking-wider">Wolne Sloty Peak</span>
            <Flame className="w-5 h-5 text-[#C8FF3A]" />
          </div>
          <p className="text-2xl font-bold text-white mt-2">{totalFreePeak}</p>
          <span className="text-xs text-[#686E78]">Okna {peakHoursCet.join(' & ')} CET</span>
        </div>

        <div className="bg-[#0E0F11] border border-[#272A2F] fk-cut-sm p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#A0A7B1] uppercase tracking-wider">Zarezerwowane</span>
            <Clock className="w-5 h-5 text-[#C8FF3A]" />
          </div>
          <p className="text-2xl font-bold text-[#C8FF3A] mt-2">{totalReserved}</p>
          <span className="text-xs text-[#686E78]">W kolejce do renderu</span>
        </div>

        <div className="bg-[#0E0F11] border border-[#272A2F] fk-cut-sm p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#A0A7B1] uppercase tracking-wider">Zaplanowane na YT</span>
            <CheckCircle className="w-5 h-5 text-emerald-400" />
          </div>
          <p className="text-2xl font-bold text-emerald-300 mt-2">{totalScheduled}</p>
          <span className="text-xs text-[#686E78]">Oczekują na publikację</span>
        </div>

        <div className="bg-[#0E0F11] border border-[#272A2F] fk-cut-sm p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#A0A7B1] uppercase tracking-wider">Opublikowane YT</span>
            <Film className="w-5 h-5 text-[#C8FF3A]" />
          </div>
          <p className="text-2xl font-bold text-[#C8FF3A] mt-2">{totalPublished}</p>
          <span className="text-xs text-[#686E78]">Śr. {avgViews.toLocaleString()} wyśw./film</span>
        </div>
      </div>

      {/* Kolejka TikTok / Instagram Status Bar */}
      {socialSummary.total > 0 && (
        <div className="bg-[#0E0F11] border border-[#00F2FE]/35 fk-cut-sm p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-[#00F2FE]">Kolejka Social 24/7 (TikTok / Instagram)</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/35">
                Oczekuje: {socialSummary.pending}
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                Wysłane: {socialSummary.published}
              </span>
              {socialSummary.failed > 0 && (
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  Błędy: {socialSummary.failed}
                </span>
              )}
            </div>
            {socialQueueItems.filter(i => i.status === 'pending').slice(0, 2).map(qi => (
              <p key={qi.id} className="text-[11px] text-[#A0A7B1] truncate max-w-2xl">
                • <strong className="uppercase text-white">{qi.platform}</strong> ({new Date(qi.publish_at).toLocaleString('pl-PL')}): {qi.caption}
              </p>
            ))}
          </div>
          <button
            type="button"
            onClick={handleFlushSocialQueue}
            disabled={flushingQueue}
            className="flex items-center gap-2 px-3.5 py-2 bg-[#00F2FE]/15 hover:bg-[#00F2FE]/25 text-[#00F2FE] border border-[#00F2FE]/40 rounded-lg text-xs font-bold transition disabled:opacity-50 shrink-0"
          >
            <Send className={`w-3.5 h-3.5 ${flushingQueue ? 'animate-pulse' : ''}`} />
            {flushingQueue ? 'Wysyłam kolejkę...' : 'Wyślij zaległe (TikTok/IG)'}
          </button>
        </div>
      )}

      {/* AI Autonomous Learning Status Banner */}
      {learning && (
        <div className="fk-cut bg-[#0E0F11] border border-[#C8FF3A]/40 fk-cut-sm p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2.5 rounded-lg bg-[#17191C] border border-[#C8FF3A]/35 text-[#C8FF3A] shrink-0">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white">Autonomiczna Pętla Samouczenia AI (Dwannellenga)</h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  AKTYWNA
                </span>
              </div>
              <p className="text-xs text-[#FFFFFF] mt-1">
                Faworyzowany format: <strong className="text-[#C8FF3A]">{learning.top_action_type?.toUpperCase()}</strong> ({learning.action_stats?.[learning.top_action_type]?.performance_ratio || 1.0}x średniej) • Pacing: <span className="font-mono text-[#C8FF3A] font-bold">{learning.recommended_pacing}</span> {learning.duration_analysis?.viral_avg_duration_s ? `(Viral śr. ${learning.duration_analysis.viral_avg_duration_s}s)` : ''} • Tytuły: <span className="text-emerald-300 font-semibold">{learning.top_title_structure || 'RAMPAGE'}</span>
              </p>
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                {learning.retention_analysis && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-[10px] font-bold">
                    <Activity className="w-3 h-3 text-cyan-400" />
                    Swiped Away: {learning.retention_analysis.channel_avg_swiped_away_pct}% • Hook: {learning.retention_analysis.channel_avg_hook_retention_pct}% • AVD: {learning.retention_analysis.channel_avg_view_pct}%
                  </span>
                )}
                {learning.winning_keywords && learning.winning_keywords.length > 0 && (
                  <>
                    <span className="text-[11px] text-[#A0A7B1] ml-1">Wygrywające CTR:</span>
                    {learning.winning_keywords.slice(0, 4).map(kw => (
                      <span key={kw} className="px-1.5 py-0.5 bg-[#272A2F] text-[#FFFFFF] border border-[#C8FF3A]/30 rounded text-[10px] font-semibold">
                        +{kw}
                      </span>
                    ))}
                  </>
                )}
                {learning.evaluator_config?.demoted_formats && learning.evaluator_config.demoted_formats.length > 0 && (
                  <span className="text-[10px] text-rose-300/80 ml-1 font-mono">
                    (Filtr: {learning.evaluator_config.demoted_formats.join(', ').toUpperCase()} -{learning.evaluator_config.demoted_penalty_points}pkt)
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={handleRecalibrateLearning}
            disabled={learningLoading}
            className="flex items-center gap-2 py-2 px-3.5 fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] rounded-lg text-xs font-semibold transition disabled:opacity-50 shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${learningLoading ? 'animate-spin' : ''}`} />
            {learningLoading ? 'Kalibracja...' : 'Rekalibruj AI'}
          </button>
        </div>
      )}

      {/* Filters & Sorting Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-[#0E0F11] border border-[#272A2F] fk-cut-sm p-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-[#A0A7B1] flex items-center gap-1 mr-1">
            <Filter className="w-3.5 h-3.5 text-[#C8FF3A]" />
            Filtruj:
          </span>
          {[
            { id: 'all', label: 'Wszystkie', count: slots.length },
            { id: 'published', label: 'Opublikowane', count: totalPublished },
            { id: 'scheduled', label: 'Zaplanowane', count: totalScheduled },
            { id: 'free', label: 'Wolne Peak', count: totalFreePeak },
            { id: 'reserved', label: 'Zarezerwowane', count: totalReserved },
          ].map(f => (
            <button
              key={f.id}
              onClick={() => setStatusFilter(f.id as any)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition flex items-center gap-1.5 ${
                statusFilter === f.id
                  ? 'bg-[#C8FF3A] text-[#050505] font-extrabold'
                  : 'bg-[#17191C] hover:bg-[#17191C] text-[#A0A7B1] hover:text-[#FFFFFF] border border-[#272A2F]'
              }`}
            >
              <span>{f.label}</span>
              <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                statusFilter === f.id ? 'bg-[#050505]/20 text-[#050505] font-extrabold' : 'bg-[#272A2F] text-[#FFFFFF]'
              }`}>
                {f.count}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <span className="text-xs font-semibold text-[#A0A7B1]">Sortuj:</span>
          <button
            onClick={() => setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc')}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#17191C] hover:bg-[#272A2F] text-[#FFFFFF] rounded-lg border border-[#272A2F] text-xs font-medium transition"
            title="Zmień kolejność chronologiczną"
          >
            <ArrowDownUp className="w-3.5 h-3.5 text-[#C8FF3A]" />
            <span>{sortOrder === 'desc' ? 'Od najnowszych 🔽' : 'Od najstarszych 🔼'}</span>
          </button>
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="space-y-6">
        {sortedDates.length === 0 ? (
          <div className="text-center py-12 bg-[#0E0F11]/40 border border-[#272A2F] fk-cut-sm">
            <p className="text-[#A0A7B1] text-sm">Brak slotów spełniających wybrane kryteria filtrów.</p>
          </div>
        ) : (
          sortedDates.map(dateStr => {
            const daySlots = [...groupedSlots[dateStr]].sort((s1, s2) => {
              return sortOrder === 'desc' ? s2.time.localeCompare(s1.time) : s1.time.localeCompare(s2.time);
            });
            const isToday = new Date().toISOString().slice(0, 10) === dateStr;
            const isPastDate = dateStr < new Date().toISOString().slice(0, 10);

          return (
            <div key={dateStr} className="bg-[#0E0F11]/60 border border-[#272A2F] fk-cut-sm p-5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-[#272A2F]">
                <div className="flex items-center gap-3">
                  <h3 className="text-base font-bold text-white">{dateStr}</h3>
                  {isToday && (
                    <span className="px-2 py-0.5 bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/35 text-xs font-medium rounded-full">
                      Dzisiaj 🌟
                    </span>
                  )}
                  {isPastDate && (
                    <span className="px-2 py-0.5 bg-[#17191C] text-[#A0A7B1] border border-[#272A2F] text-xs font-medium rounded-full">
                      Historia publikacji
                    </span>
                  )}
                </div>
                <span className="text-xs text-[#A0A7B1]">
                  {isPastDate ? `${daySlots.length} film(ów)` : `${peakHoursCet.length} okna publikacji (${peakHoursCet.join(' & ')} CET)`}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {daySlots.map(slot => {
                  const isBusy = slot.status !== 'free' && slot.status !== 'past';

                  let statusBadge = (
                    <span className="px-2 py-0.5 text-xs font-medium rounded bg-[#17191C] text-[#A0A7B1] border border-[#272A2F]">
                      Wolny slot
                    </span>
                  );
                  if (slot.status === 'reserved') {
                    statusBadge = (
                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/35 flex items-center gap-1">
                        <Clock className="w-3 h-3" /> Zarezerwowany
                      </span>
                    );
                  } else if (slot.status === 'ready') {
                    statusBadge = (
                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 flex items-center gap-1">
                        <Film className="w-3 h-3" /> Gotowy do YT
                      </span>
                    );
                  } else if (slot.status === 'scheduled') {
                    statusBadge = (
                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" /> Zaplanowany YT
                      </span>
                    );
                  } else if (slot.status === 'published') {
                    statusBadge = (
                      <span className="px-2 py-0.5 text-xs font-semibold rounded bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/35 flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" /> Opublikowany
                      </span>
                    );
                  } else if (slot.status === 'past') {
                    statusBadge = (
                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-[#17191C]/40 text-slate-600 border border-[#272A2F]">
                        Minął
                      </span>
                    );
                  }

                  let fragBadge = null;
                  if (slot.frag_type) {
                    const f = slot.frag_type.toLowerCase();
                    if (f.includes('penta')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-[#C8FF3A]/25 text-[#C8FF3A] border border-[#C8FF3A]/50">👑 PENTAKILL</span>;
                    } else if (f.includes('clutch') || f.includes('1%')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-red-500/30 text-red-300 border border-red-500/40">🩸 1% HP CLUTCH</span>;
                    } else if (f.includes('quadra')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-orange-500/30 text-orange-300 border border-orange-500/40">⚡ QUADRA KILL</span>;
                    } else if (f.includes('triple')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-[#C8FF3A]/20 text-[#C8FF3A] border border-[#C8FF3A]/45">⚔️ TRIPLE KILL</span>;
                    } else if (f.includes('double')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-cyan-500/30 text-cyan-300 border border-cyan-500/40">🎯 DOUBLE KILL</span>;
                    } else if (f.includes('solo') || f.includes('bolo') || f.includes('1v1')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-rose-500/30 text-rose-300 border border-rose-500/40">👑 SOLO BOLO</span>;
                    } else {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-semibold rounded bg-blue-500/30 text-blue-300 border border-blue-500/40">🔥 OUTPLAY</span>;
                    }
                  }

                  return (
                    <div 
                      key={slot.slot_id}
                      className={`relative flex flex-col justify-between p-4 fk-cut-sm border transition ${
                        isBusy
                          ? slot.status === 'published'
                            ? 'bg-[#0E0F11] border-[#272A2F]'
                            : 'bg-[#17191C] border-[#272A2F]'
                          : slot.is_past
                            ? 'bg-[#0E0F11]/30 border-[#272A2F]/40 opacity-60'
                            : 'bg-[#0E0F11] border-dashed border-[#272A2F] hover:border-[#C8FF3A]/60 hover:bg-[#17191C]'
                      }`}
                    >
                      {/* Slot Header */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-1.5 font-bold text-white text-sm">
                            <Clock className="w-3.5 h-3.5 text-[#C8FF3A]" />
                            {slot.time} CET
                          </div>
                          {statusBadge}
                        </div>

                        {/* Content Preview */}
                        {isBusy ? (
                          <div className="space-y-2.5 mt-3">
                            {/* Miniaturka wideo (jeśli dostępna) */}
                            {slot.thumbnail_url && (
                              <div className="relative w-full h-24 rounded-lg overflow-hidden border border-[#272A2F] bg-black">
                                <img src={slot.thumbnail_url} alt={slot.title} className="w-full h-full object-cover" />
                                {slot.views !== undefined && (
                                  <div className="absolute bottom-1 right-1 px-1.5 py-0.5 bg-black/85 text-[10px] font-bold text-white rounded backdrop-blur-sm flex items-center gap-1 border border-white/10">
                                    👁️ {slot.views.toLocaleString()}
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Wskaźnik Skuteczności AI (Performance Score) */}
                            {slot.performance_tier && (
                              <div className={`px-2.5 py-1 rounded-md text-xs font-bold flex items-center justify-between border ${
                                slot.performance_tier === 'viral_hit'
                                  ? 'bg-amber-500/20 text-[#C8FF3A] border-[#C8FF3A]/40'
                                  : slot.performance_tier === 'above_avg'
                                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                                  : slot.performance_tier === 'average'
                                  ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                                  : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                              }`}>
                                <span className="truncate mr-1 font-semibold">{slot.performance_label}</span>
                                <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-black/50 border border-white/10 shrink-0">
                                  {slot.performance_score}
                                </span>
                              </div>
                            )}

                            {/* Statystyki: wyświetlenia, polubienia, komentarze */}
                            {slot.views !== undefined && (
                              <div className="flex items-center justify-between text-[11px] text-[#FFFFFF] bg-slate-950/60 px-2.5 py-1 rounded border border-[#272A2F]">
                                <span className="font-semibold text-white">👁️ {slot.views.toLocaleString()} wyśw.</span>
                                <span>👍 {slot.likes || 0}</span>
                                <span>💬 {slot.comments || 0}</span>
                              </div>
                            )}

                            <div className="flex items-center gap-2">
                              {fragBadge}
                              {slot.champion && (
                                <span className="text-xs font-semibold text-[#FFFFFF]">
                                  {slot.champion}
                                </span>
                              )}
                            </div>

                            <p className="text-xs text-[#FFFFFF] line-clamp-2 font-medium">
                              {slot.title || 'Brak tytułu'}
                            </p>

                            {slot.notes && !slot.performance_tier && (
                              <p className="text-[11px] text-[#A0A7B1] italic">
                                {slot.notes}
                              </p>
                            )}

                            {slot.yt_url && (
                              <a 
                                href={slot.yt_url} 
                                target="_blank" 
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-xs text-[#C8FF3A] hover:text-[#AEE820] mt-1"
                              >
                                <ExternalLink className="w-3 h-3" /> Zobacz na YouTube
                              </a>
                            )}

                            {slot.social_queue && slot.social_queue.length > 0 && (
                              <div className="flex flex-wrap gap-1 pt-1">
                                {slot.social_queue.map((sq) => (
                                  <span
                                    key={sq.id}
                                    title={sq.caption || sq.error || ''}
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                                      sq.status === 'published'
                                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35'
                                        : sq.status === 'pending'
                                        ? 'bg-[#00F2FE]/15 text-[#00F2FE] border-[#00F2FE]/35'
                                        : 'bg-rose-500/15 text-rose-300 border-rose-500/35'
                                    }`}
                                  >
                                    {sq.platform.toUpperCase()}: {sq.status === 'published' ? '✓' : sq.status === 'pending' ? '⏰' : '⚠️'}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="my-4 text-center">
                            <span className="text-xs text-[#686E78]">
                              {slot.is_past ? 'Slot archiwalny' : 'Wolny slot publikacji'}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="mt-4 pt-3 border-t border-[#272A2F] flex items-center justify-between gap-2">
                        {!slot.is_past && !isBusy && (
                          <button
                            onClick={() => handleOpenReserveModal(slot)}
                            className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 fk-btn-ghost bg-[#17191C] hover:bg-[#C8FF3A] text-[#FFFFFF] hover:text-[#050505] border border-[#272A2F] hover:border-[#C8FF3A] rounded-lg text-xs font-medium transition"
                          >
                            <Plus className="w-3.5 h-3.5" /> Zarezerwuj Slot
                          </button>
                        )}

                        {isBusy && (
                          <div className="w-full flex items-center justify-between gap-2">
                            {slot.status === 'published' ? (
                              <div className="w-full flex items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => handleOpenRetentionModal(slot)}
                                  className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 fk-btn-ghost bg-[#17191C] hover:bg-[#C8FF3A] text-[#FFFFFF] hover:text-[#050505] border border-[#272A2F] hover:border-[#C8FF3A] rounded-lg text-xs font-semibold transition"
                                  title="Analiza retencji klatka-po-klatce i Swiped Away z YouTube Analytics API"
                                >
                                  <BarChart3 className="w-3.5 h-3.5" /> Retencja
                                </button>
                                {slot.yt_url && (
                                  <a 
                                    href={slot.yt_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="p-1.5 fk-btn-ghost bg-[#17191C] hover:bg-[#C8FF3A] text-[#FFFFFF] hover:text-[#050505] border border-[#272A2F] hover:border-[#C8FF3A] rounded-lg transition"
                                    title="Oglądaj na YouTube"
                                  >
                                    <ExternalLink className="w-3.5 h-3.5" />
                                  </a>
                                )}
                              </div>
                            ) : (
                              <>
                                {slot.status === 'ready' && (
                                  <button
                                    onClick={() => handlePublishNow(slot.slot_id)}
                                    disabled={actionLoading === slot.slot_id}
                                    className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-semibold transition"
                                  >
                                    <Send className="w-3 h-3" /> Planuj na YT
                                  </button>
                                )}

                                <button
                                  onClick={() => handleReleaseSlot(slot.slot_id)}
                                  disabled={actionLoading === slot.slot_id}
                                  className="p-1.5 text-[#A0A7B1] hover:text-rose-400 hover:bg-rose-500/10 rounded transition ml-auto"
                                  title="Zwolnij rezerwację"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        }))}
      </div>

      {/* Reservation Modal */}
      {selectedSlot && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#0E0F11] border border-[#272A2F] fk-cut max-w-xl w-full p-6 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-[#272A2F]">
              <div>
                <h3 className="text-lg font-bold text-white">Rezerwacja Slotu Publikacji</h3>
                <p className="text-xs text-[#A0A7B1] mt-0.5">
                  {selectedSlot.datetime_local} (YouTube Peak Slot ⚡)
                </p>
              </div>
              <button
                onClick={() => setSelectedSlot(null)}
                className="text-[#A0A7B1] hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="space-y-4">
              {/* Select Input Clip */}
              <div>
                <label className="block text-xs font-semibold text-[#FFFFFF] mb-1.5">
                  Wybierz klip z dysku / bazy nagrań:
                </label>
                <select
                  value={selectedClipPath}
                  onChange={(e) => handleClipSelect(e.target.value)}
                  className="w-full bg-[#17191C] border border-[#272A2F] text-[#FFFFFF] rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#C8FF3A]"
                >
                  <option value="">-- Wybierz klip lub wprowadź ręcznie --</option>
                  {availableClips.map((c, i) => (
                    <option key={i} value={c.path}>
                      {c.filename || c.path} ({c.size_mb ? `${c.size_mb} MB` : 'Wideo'})
                    </option>
                  ))}
                </select>
              </div>

              {/* Champion Input */}
              <div>
                <label className="block text-xs font-semibold text-[#FFFFFF] mb-1.5">
                  Bohater (Champion):
                </label>
                <input
                  type="text"
                  value={champion}
                  onChange={(e) => setChampion(e.target.value)}
                  placeholder="np. Katarina, Yone, Zed, Yasuo"
                  className="w-full bg-[#17191C] border border-[#272A2F] text-[#FFFFFF] rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#C8FF3A]"
                />
              </div>

              {/* Frag Detection Mode Selector */}
              <div className="bg-[#17191C]/80 border border-[#272A2F] fk-cut-sm p-4 space-y-3">
                <label className="block text-xs font-bold text-white uppercase tracking-wider">
                  Klasyfikacja i Styl Fraga:
                </label>
                
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setFragMode('auto')}
                    className={`py-2 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 border ${
                      fragMode === 'auto'
                        ? 'bg-[#C8FF3A] border-[#C8FF3A] text-[#050505] font-extrabold'
                        : 'bg-[#17191C] border-[#272A2F] text-[#A0A7B1] hover:text-white'
                    }`}
                  >
                    <Sparkles className="w-3.5 h-3.5" /> Automatyczna Detekcja AI/CV
                  </button>

                  <button
                    type="button"
                    onClick={() => setFragMode('manual')}
                    className={`py-2 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 border ${
                      fragMode === 'manual'
                        ? 'bg-[#C8FF3A] border-[#C8FF3A] text-[#050505] font-extrabold'
                        : 'bg-[#17191C] border-[#272A2F] text-[#A0A7B1] hover:text-white'
                    }`}
                  >
                    Ręczny Wybór Fraga
                  </button>
                </div>

                {/* Auto Detection Result */}
                {fragMode === 'auto' && (
                  <div className="mt-3 p-3 bg-[#0E0F11] rounded-lg border border-[#272A2F] space-y-2">
                    {analyzingFrag ? (
                      <div className="flex items-center gap-2 text-xs text-[#C8FF3A]">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        Analiza OCR, sekwencji killów i poziomu paska HP...
                      </div>
                    ) : analyzedFrag ? (
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-[#A0A7B1]">Wykryty typ akcji:</span>
                          <span 
                            className="px-2 py-0.5 text-xs font-black rounded"
                            style={{ backgroundColor: `${analyzedFrag.suggested_badge_color}30`, color: analyzedFrag.suggested_badge_color, border: `1px solid ${analyzedFrag.suggested_badge_color}50` }}
                          >
                            {analyzedFrag.badge_label}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-[#A0A7B1]">Min. zdrowie gracza (HP):</span>
                          <span className={analyzedFrag.is_clutch_1hp ? 'text-rose-400 font-bold' : 'text-emerald-400'}>
                            {analyzedFrag.min_hp_percentage}% {analyzedFrag.is_clutch_1hp && '(⚠️ CLUTCH DETECTED)'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-[#A0A7B1]">Pewność klasyfikacji:</span>
                          <span className="text-[#FFFFFF] font-medium">
                            {Math.round(analyzedFrag.confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-[#A0A7B1] italic">
                        Wybierz klip powyżej, aby automatycznie przeskanować typ eliminacji i poziom HP.
                      </p>
                    )}
                  </div>
                )}

                {/* Manual Frag Options */}
                {fragMode === 'manual' && (
                  <div className="grid grid-cols-3 gap-2 mt-2">
                    {[
                      { id: 'pentakill', label: '👑 Pentakill' },
                      { id: 'quadrakill', label: '⚡ Quadra' },
                      { id: 'triple', label: '⚔️ Triple' },
                      { id: 'double', label: '🎯 Double' },
                      { id: 'clutch', label: '🩸 1% HP Clutch' },
                      { id: 'outplay', label: '🔥 Outplay' },
                      { id: 'solo_bolo', label: '👑 Solo Bolo' },
                    ].map(f => (
                      <button
                        key={f.id}
                        type="button"
                        onClick={() => setManualFrag(f.id)}
                        className={`py-1.5 px-2 text-xs font-bold rounded border transition ${
                          manualFrag === f.id
                            ? 'bg-amber-500/20 text-[#C8FF3A] border-[#C8FF3A]/50'
                            : 'bg-[#17191C] text-[#A0A7B1] border-[#272A2F] hover:text-white'
                        }`}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Title Input */}
              <div>
                <label className="block text-xs font-semibold text-[#FFFFFF] mb-1.5">
                  Tytuł publikacji na YouTube:
                </label>
                <input
                  type="text"
                  value={slotTitle}
                  onChange={(e) => setSlotTitle(e.target.value)}
                  placeholder="np. Insane 1% HP Katarina Clutch Survival #Shorts #LeagueOfLegends"
                  className="w-full bg-[#17191C] border border-[#272A2F] text-[#FFFFFF] rounded-lg p-2.5 text-sm focus:outline-none focus:border-[#C8FF3A]"
                />
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#272A2F]">
              <button
                type="button"
                onClick={() => setSelectedSlot(null)}
                className="px-4 py-2 bg-[#17191C] hover:bg-[#272A2F] text-[#FFFFFF] text-sm font-medium rounded-lg transition"
              >
                Anuluj
              </button>
              <button
                type="button"
                onClick={handleSaveReservation}
                disabled={actionLoading === 'saving'}
                className="px-5 py-2 fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] text-sm font-bold rounded-lg transition disabled:opacity-50"
              >
                {actionLoading === 'saving' ? 'Zapisywanie...' : 'Zapisz i Zarezerwuj Slot'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 4: YouTube Analytics Frame-by-Frame Retention Modal */}
      {retentionSlot && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-[#0E0F11] border border-[#272A2F] fk-cut w-full max-w-2xl overflow-hidden p-6 space-y-5 my-8">
            {/* Header */}
            <div className="flex items-center justify-between pb-3 border-b border-[#272A2F]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-[#17191C] border border-[#272A2F] text-[#C8FF3A]">
                  <BarChart3 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span>YouTube Analytics: Retencja & Odpływ Widzów</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/35 font-semibold">
                      100 Punktów Pomiaru
                    </span>
                  </h3>
                  <p className="text-xs text-[#A0A7B1] mt-0.5 line-clamp-1">
                    {retentionSlot.title || 'Wideo YouTube Shorts'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => { setRetentionSlot(null); setRetentionData(null); }}
                className="text-[#A0A7B1] hover:text-white p-1 rounded-lg hover:bg-[#17191C] transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            {retentionLoading ? (
              <div className="py-12 flex flex-col items-center justify-center gap-3 text-[#A0A7B1]">
                <RefreshCw className="w-8 h-8 animate-spin text-[#C8FF3A]" />
                <span className="text-sm font-medium">Odpytywanie YouTube Analytics API (elapsedVideoTimeRatio)...</span>
              </div>
            ) : retentionData && !retentionData.has_curve ? (
              <div className="p-6 bg-[#17191C]/50 border border-[#272A2F] fk-cut-sm text-center space-y-2">
                <AlertCircle className="w-8 h-8 text-[#C8FF3A] mx-auto" />
                <h4 className="text-sm font-bold text-[#FFFFFF]">Brak pełnej krzywej retencji w YouTube Analytics</h4>
                <p className="text-xs text-[#A0A7B1] max-w-md mx-auto">
                  {retentionData.message || 'YouTube udostępnia 100 punktów retencji dla filmów z minimum ~1,000 wyświetleń. Ten film ma obecnie: ' + (retentionSlot.views?.toLocaleString() || 0) + ' wyświetleń.'}
                </p>
              </div>
            ) : retentionData && retentionData.has_curve ? (
              <div className="space-y-4">
                {/* 4 KPI Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className={`p-3 fk-cut-sm border ${
                    (retentionData.swiped_away_pct || 0) <= 20
                      ? 'bg-emerald-950/30 border-emerald-800/50 text-emerald-300'
                      : (retentionData.swiped_away_pct || 0) <= 30
                      ? 'bg-[#C8FF3A]/10 border-[#C8FF3A]/40 text-[#C8FF3A]'
                      : 'bg-rose-950/30 border-rose-800/50 text-rose-300'
                  }`}>
                    <span className="text-[10px] uppercase font-bold tracking-wider block opacity-80">Swiped Away</span>
                    <span className="text-xl font-black mt-1 block">
                      {retentionData.swiped_away_pct}%
                    </span>
                    <span className="text-[10px] opacity-75 mt-0.5 block">
                      {(retentionData.swiped_away_pct || 0) <= 20 ? '🔥 Perfekcyjny hook' : 'Odpływ w oknie 0-3s'}
                    </span>
                  </div>

                  <div className="p-3 fk-cut-sm border bg-[#17191C]/80 border-[#272A2F] text-[#FFFFFF]">
                    <span className="text-[10px] uppercase font-bold tracking-wider block text-[#A0A7B1]">Hook Retention</span>
                    <span className="text-xl font-black mt-1 block text-[#C8FF3A]">
                      {retentionData.hook_retention_pct}%
                    </span>
                    <span className="text-[10px] text-[#A0A7B1] mt-0.5 block">
                      Widzowie po 3s
                    </span>
                  </div>

                  <div className="p-3 fk-cut-sm border bg-[#17191C]/80 border-[#272A2F] text-[#FFFFFF]">
                    <span className="text-[10px] uppercase font-bold tracking-wider block text-[#A0A7B1]">Średnia (AVD)</span>
                    <span className="text-xl font-black mt-1 block text-[#C8FF3A]">
                      {retentionData.avg_view_pct}%
                    </span>
                    <span className="text-[10px] text-[#A0A7B1] mt-0.5 block">
                      {retentionData.avg_view_duration_s}s / {retentionData.duration_s || 13}s
                    </span>
                  </div>

                  <div className="p-3 fk-cut-sm border bg-[#17191C]/80 border-[#272A2F] text-[#FFFFFF]">
                    <span className="text-[10px] uppercase font-bold tracking-wider block text-[#A0A7B1]">Ukończenie</span>
                    <span className="text-xl font-black mt-1 block text-cyan-300">
                      {retentionData.completion_rate_pct}%
                    </span>
                    <span className="text-[10px] text-[#A0A7B1] mt-0.5 block">
                      Dotrwało do końca
                    </span>
                  </div>
                </div>

                {/* AI Diagnosis */}
                {retentionData.diagnosis && (
                  <div className="p-3.5 fk-cut-sm fk-cut-sm bg-[#17191C] border border-[#C8FF3A]/35 flex items-start gap-2.5">
                    <Sparkles className="w-4 h-4 text-[#C8FF3A] flex-shrink-0 mt-0.5" />
                    <div className="text-xs text-[#FFFFFF]">
                      <strong className="text-white block font-semibold mb-0.5">Diagnoza Samouczenia AI:</strong>
                      {retentionData.diagnosis}
                    </div>
                  </div>
                )}

                {/* 10-Point Retention Curve Visualizer */}
                {retentionData.sampled_curve && retentionData.sampled_curve.length > 0 && (
                  <div className="bg-slate-950/70 border border-[#272A2F] fk-cut-sm p-3.5 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-[#FFFFFF]">Krzywa Utrzymania Uwagi (10 punktów kontrolnych):</span>
                      <span className="text-[#686E78] text-[11px]">YouTube elapsedVideoTimeRatio</span>
                    </div>
                    <div className="flex items-end gap-1.5 h-20 pt-2 px-1">
                      {retentionData.sampled_curve.map((pt, idx) => {
                        const hPct = Math.min(100, Math.max(12, pt.retention_pct));
                        const isHigh = pt.retention_pct >= 90;
                        const isLow = pt.retention_pct < 60;
                        return (
                          <div key={idx} className="flex-1 flex flex-col items-center h-full justify-end group relative">
                            <div
                              className={`w-full rounded-t transition-all ${
                                isHigh ? 'bg-[#C8FF3A]' : isLow ? 'bg-rose-500/70' : 'bg-[#272A2F]'
                              }`}
                              style={{ height: `${hPct}%` }}
                            />
                            <span className="text-[9px] text-[#686E78] mt-1 font-mono">{pt.time_s}s</span>
                            {/* Hover Tooltip */}
                            <div className="absolute bottom-full mb-1 hidden group-hover:flex flex-col items-center z-10 bg-black/90 border border-[#272A2F] px-1.5 py-0.5 rounded text-[10px] text-white whitespace-nowrap">
                              <span>{pt.retention_pct}%</span>
                              <span className="text-[8px] text-[#A0A7B1]">{pt.percentile}% filmu ({pt.time_s}s)</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Top Critical Drop-off Points */}
                {retentionData.top_drop_offs && retentionData.top_drop_offs.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-[#FFFFFF] block">
                      Krytyczne punkty opuszczenia filmu (Drop-offs):
                    </span>
                    <div className="space-y-1.5 max-h-36 overflow-y-auto">
                      {retentionData.top_drop_offs.map((drop, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between text-xs p-2 rounded-lg bg-[#17191C]/80 border border-[#272A2F]"
                        >
                          <div className="flex items-center gap-2">
                            <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono text-[10px] font-bold">
                              {drop.time_s}s ({drop.elapsed_pct}%)
                            </span>
                            <span className="text-[#FFFFFF] line-clamp-1">{drop.reason}</span>
                          </div>
                          <span className="font-bold text-rose-400 shrink-0 text-[11px]">
                            -{drop.drop_pct}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}

            {/* Footer */}
            <div className="flex items-center justify-between pt-3 border-t border-[#272A2F]">
              {retentionSlot.yt_url ? (
                <a
                  href={retentionSlot.yt_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-[#C8FF3A] hover:text-[#AEE820]"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Otwórz Shorta na YouTube
                </a>
              ) : <div />}
              <button
                type="button"
                onClick={() => { setRetentionSlot(null); setRetentionData(null); }}
                className="px-4 py-2 bg-[#17191C] hover:bg-[#272A2F] text-[#FFFFFF] text-xs font-semibold rounded-lg transition"
              >
                Zamknij
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
