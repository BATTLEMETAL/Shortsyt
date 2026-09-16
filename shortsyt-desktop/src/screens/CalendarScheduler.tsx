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
  CalendarSlot, FragAnalysis, ClipItem, LearningDirective, VideoRetentionData
} from '../lib/api';

export function CalendarScheduler() {
  const [slots, setSlots] = useState<CalendarSlot[]>([]);
  const [days, setDays] = useState<number>(14);
  const [loading, setLoading] = useState<boolean>(true);
  const [autoFilling, setAutoFilling] = useState<boolean>(false);
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
      // silent
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
      const res = await apiGetCalendarSlots(undefined, days, forceRefresh);
      setSlots(res.slots || []);
    } catch (e: any) {
      if (!silent) setMessage({ type: 'error', text: `Błąd wczytywania kalendarza: ${e.message}` });
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const loadClips = async () => {
    try {
      const clips = await apiListClips();
      setAvailableClips(clips || []);
    } catch (e) {
      // ignore
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
      // fallback
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
        title: slotTitle || `League of Legends ${finalFrag.toUpperCase()} #Shorts`,
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
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div>
          <div className="flex items-center gap-2">
            <CalendarIcon className="w-7 h-7 text-indigo-400" />
            <h1 className="text-2xl font-bold text-white tracking-tight">Kalendarz Publikacji i Analityka Skuteczności</h1>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Harmonogram 2 filmów dziennie (08:30 i 18:30 CET) • Zero kanibalizacji zasięgów • Wskaźnik skuteczności Shortsów
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleAutoFill}
            disabled={autoFilling}
            className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-black font-semibold rounded-lg shadow-md transition disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            {autoFilling ? 'Rezerwowanie...' : '⚡ Auto-Rezerwacja AI'}
          </button>

          <div className="flex items-center bg-slate-800 rounded-lg p-1 border border-slate-700">
            {[7, 14, 30].map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                  days === d ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                {d} dni
              </button>
            ))}
          </div>

          <button
            onClick={() => loadSlots(false, true)}
            disabled={loading}
            className="p-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition"
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
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Wolne Sloty Peak</span>
            <Flame className="w-5 h-5 text-amber-400" />
          </div>
          <p className="text-2xl font-bold text-white mt-2">{totalFreePeak}</p>
          <span className="text-xs text-slate-500">Okna 08:30 & 18:30 CET</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Zarezerwowane</span>
            <Clock className="w-5 h-5 text-indigo-400" />
          </div>
          <p className="text-2xl font-bold text-indigo-300 mt-2">{totalReserved}</p>
          <span className="text-xs text-slate-500">W kolejce do renderu</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Zaplanowane na YT</span>
            <CheckCircle className="w-5 h-5 text-emerald-400" />
          </div>
          <p className="text-2xl font-bold text-emerald-300 mt-2">{totalScheduled}</p>
          <span className="text-xs text-slate-500">Oczekują na publikację</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Opublikowane YT</span>
            <Film className="w-5 h-5 text-purple-400" />
          </div>
          <p className="text-2xl font-bold text-purple-300 mt-2">{totalPublished}</p>
          <span className="text-xs text-slate-500">Śr. {avgViews.toLocaleString()} wyśw./film</span>
        </div>
      </div>

      {/* AI Autonomous Learning Status Banner */}
      {learning && (
        <div className="bg-gradient-to-r from-purple-950/40 via-slate-900 to-indigo-950/40 border border-purple-500/30 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2.5 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-400 shrink-0">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white">Autonomiczna Pętla Samouczenia AI (Dwannellenga)</h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  AKTYWNA
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-1">
                Faworyzowany format: <strong className="text-amber-400">{learning.top_action_type?.toUpperCase()}</strong> ({learning.action_stats?.[learning.top_action_type]?.performance_ratio || 1.0}x średniej) • Pacing: <span className="font-mono text-indigo-300 font-bold">{learning.recommended_pacing}</span> {learning.duration_analysis?.viral_avg_duration_s ? `(Viral śr. ${learning.duration_analysis.viral_avg_duration_s}s)` : ''} • Tytuły: <span className="text-emerald-300 font-semibold">{learning.top_title_structure || 'RAMPAGE'}</span>
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
                    <span className="text-[11px] text-slate-400 ml-1">Wygrywające CTR:</span>
                    {learning.winning_keywords.slice(0, 4).map(kw => (
                      <span key={kw} className="px-1.5 py-0.5 bg-purple-500/20 text-purple-200 border border-purple-500/40 rounded text-[10px] font-semibold">
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
            className="flex items-center gap-2 py-2 px-3.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-semibold transition disabled:opacity-50 shrink-0 shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${learningLoading ? 'animate-spin' : ''}`} />
            {learningLoading ? 'Kalibracja...' : 'Rekalibruj AI'}
          </button>
        </div>
      )}

      {/* Filters & Sorting Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-slate-900 border border-slate-800 rounded-xl p-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-slate-400 flex items-center gap-1 mr-1">
            <Filter className="w-3.5 h-3.5 text-indigo-400" />
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
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-800/80 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700/60'
              }`}
            >
              <span>{f.label}</span>
              <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                statusFilter === f.id ? 'bg-indigo-800 text-indigo-200' : 'bg-slate-700 text-slate-300'
              }`}>
                {f.count}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <span className="text-xs font-semibold text-slate-400">Sortuj:</span>
          <button
            onClick={() => setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc')}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg border border-slate-700 text-xs font-medium transition shadow-sm"
            title="Zmień kolejność chronologiczną"
          >
            <ArrowDownUp className="w-3.5 h-3.5 text-amber-400" />
            <span>{sortOrder === 'desc' ? 'Od najnowszych 🔽' : 'Od najstarszych 🔼'}</span>
          </button>
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="space-y-6">
        {sortedDates.length === 0 ? (
          <div className="text-center py-12 bg-slate-900/40 border border-slate-800 rounded-xl">
            <p className="text-slate-400 text-sm">Brak slotów spełniających wybrane kryteria filtrów.</p>
          </div>
        ) : (
          sortedDates.map(dateStr => {
            const daySlots = [...groupedSlots[dateStr]].sort((s1, s2) => {
              return sortOrder === 'desc' ? s2.time.localeCompare(s1.time) : s1.time.localeCompare(s2.time);
            });
            const isToday = new Date().toISOString().slice(0, 10) === dateStr;
            const isPastDate = dateStr < new Date().toISOString().slice(0, 10);

          return (
            <div key={dateStr} className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center gap-3">
                  <h3 className="text-base font-bold text-white">{dateStr}</h3>
                  {isToday && (
                    <span className="px-2 py-0.5 bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs font-medium rounded-full">
                      Dzisiaj 🌟
                    </span>
                  )}
                  {isPastDate && (
                    <span className="px-2 py-0.5 bg-slate-800 text-slate-400 border border-slate-700 text-xs font-medium rounded-full">
                      Historia publikacji
                    </span>
                  )}
                </div>
                <span className="text-xs text-slate-400">
                  {isPastDate ? `${daySlots.length} film(ów)` : '2 okna publikacji (08:30 & 18:30 CET)'}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {daySlots.map(slot => {
                  const isBusy = slot.status !== 'free' && slot.status !== 'past';

                  let statusBadge = (
                    <span className="px-2 py-0.5 text-xs font-medium rounded bg-slate-800 text-slate-400 border border-slate-700">
                      Wolny slot
                    </span>
                  );
                  if (slot.status === 'reserved') {
                    statusBadge = (
                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1">
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
                      <span className="px-2 py-0.5 text-xs font-semibold rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" /> Opublikowany
                      </span>
                    );
                  } else if (slot.status === 'past') {
                    statusBadge = (
                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-slate-800/40 text-slate-600 border border-slate-800">
                        Minął
                      </span>
                    );
                  }

                  let fragBadge = null;
                  if (slot.frag_type) {
                    const f = slot.frag_type.toLowerCase();
                    if (f.includes('penta')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-amber-500/30 text-amber-300 border border-amber-500/40">👑 PENTAKILL</span>;
                    } else if (f.includes('clutch') || f.includes('1%')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-red-500/30 text-red-300 border border-red-500/40">🩸 1% HP CLUTCH</span>;
                    } else if (f.includes('quadra')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-orange-500/30 text-orange-300 border border-orange-500/40">⚡ QUADRA KILL</span>;
                    } else if (f.includes('triple')) {
                      fragBadge = <span className="px-2 py-0.5 text-xs font-black rounded bg-purple-500/30 text-purple-300 border border-purple-500/40">⚔️ TRIPLE KILL</span>;
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
                      className={`relative flex flex-col justify-between p-4 rounded-xl border transition ${
                        isBusy
                          ? slot.status === 'published'
                            ? 'bg-slate-900/90 border-purple-500/25 shadow-sm'
                            : 'bg-slate-800/80 border-slate-700 shadow-sm'
                          : slot.is_past
                            ? 'bg-slate-900/30 border-slate-800/40 opacity-60'
                            : 'bg-slate-900/90 border-dashed border-slate-700/80 hover:border-indigo-500/60 hover:bg-slate-850'
                      }`}
                    >
                      {/* Slot Header */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-1.5 font-bold text-white text-sm">
                            <Clock className="w-3.5 h-3.5 text-amber-400" />
                            {slot.time} CET
                          </div>
                          {statusBadge}
                        </div>

                        {/* Content Preview */}
                        {isBusy ? (
                          <div className="space-y-2.5 mt-3">
                            {/* Miniaturka wideo (jeśli dostępna) */}
                            {slot.thumbnail_url && (
                              <div className="relative w-full h-24 rounded-lg overflow-hidden border border-slate-700/60 bg-black">
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
                                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
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
                              <div className="flex items-center justify-between text-[11px] text-slate-300 bg-slate-950/60 px-2.5 py-1 rounded border border-slate-800">
                                <span className="font-semibold text-white">👁️ {slot.views.toLocaleString()} wyśw.</span>
                                <span>👍 {slot.likes || 0}</span>
                                <span>💬 {slot.comments || 0}</span>
                              </div>
                            )}

                            <div className="flex items-center gap-2">
                              {fragBadge}
                              {slot.champion && (
                                <span className="text-xs font-semibold text-slate-300">
                                  {slot.champion}
                                </span>
                              )}
                            </div>

                            <p className="text-xs text-slate-300 line-clamp-2 font-medium">
                              {slot.title || 'Brak tytułu'}
                            </p>

                            {slot.notes && !slot.performance_tier && (
                              <p className="text-[11px] text-slate-400 italic">
                                {slot.notes}
                              </p>
                            )}

                            {slot.yt_url && (
                              <a 
                                href={slot.yt_url} 
                                target="_blank" 
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 mt-1"
                              >
                                <ExternalLink className="w-3 h-3" /> Zobacz na YouTube
                              </a>
                            )}
                          </div>
                        ) : (
                          <div className="my-4 text-center">
                            <span className="text-xs text-slate-500">
                              {slot.is_past ? 'Slot archiwalny' : 'Wolny slot publikacji'}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between gap-2">
                        {!slot.is_past && !isBusy && (
                          <button
                            onClick={() => handleOpenReserveModal(slot)}
                            className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 bg-indigo-600/20 hover:bg-indigo-600 text-indigo-300 hover:text-white border border-indigo-500/30 rounded-lg text-xs font-medium transition"
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
                                  className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 bg-indigo-600/30 hover:bg-indigo-600 text-indigo-200 hover:text-white border border-indigo-500/40 rounded-lg text-xs font-semibold transition"
                                  title="Analiza retencji klatka-po-klatce i Swiped Away z YouTube Analytics API"
                                >
                                  <BarChart3 className="w-3.5 h-3.5" /> Retencja
                                </button>
                                {slot.yt_url && (
                                  <a 
                                    href={slot.yt_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="p-1.5 bg-purple-600/20 hover:bg-purple-600 text-purple-300 hover:text-white border border-purple-500/30 rounded-lg transition"
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
                                  className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded transition ml-auto"
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
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <h3 className="text-lg font-bold text-white">Rezerwacja Slotu Publikacji</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  {selectedSlot.datetime_local} (YouTube Peak Slot ⚡)
                </p>
              </div>
              <button
                onClick={() => setSelectedSlot(null)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="space-y-4">
              {/* Select Input Clip */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Wybierz klip z dysku / bazy nagrań:
                </label>
                <select
                  value={selectedClipPath}
                  onChange={(e) => handleClipSelect(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-lg p-2.5 text-sm focus:outline-none focus:border-indigo-500"
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
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Bohater (Champion):
                </label>
                <input
                  type="text"
                  value={champion}
                  onChange={(e) => setChampion(e.target.value)}
                  placeholder="np. Katarina, Yone, Zed, Yasuo"
                  className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-lg p-2.5 text-sm focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Frag Detection Mode Selector */}
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
                <label className="block text-xs font-bold text-white uppercase tracking-wider">
                  Klasyfikacja i Styl Fraga:
                </label>
                
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setFragMode('auto')}
                    className={`py-2 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 border ${
                      fragMode === 'auto'
                        ? 'bg-indigo-600 border-indigo-500 text-white'
                        : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                    }`}
                  >
                    <Sparkles className="w-3.5 h-3.5" /> Automatyczna Detekcja AI/CV
                  </button>

                  <button
                    type="button"
                    onClick={() => setFragMode('manual')}
                    className={`py-2 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 border ${
                      fragMode === 'manual'
                        ? 'bg-indigo-600 border-indigo-500 text-white'
                        : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                    }`}
                  >
                    Ręczny Wybór Fraga
                  </button>
                </div>

                {/* Auto Detection Result */}
                {fragMode === 'auto' && (
                  <div className="mt-3 p-3 bg-slate-900 rounded-lg border border-slate-700 space-y-2">
                    {analyzingFrag ? (
                      <div className="flex items-center gap-2 text-xs text-indigo-400">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        Analiza OCR, sekwencji killów i poziomu paska HP...
                      </div>
                    ) : analyzedFrag ? (
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-slate-400">Wykryty typ akcji:</span>
                          <span 
                            className="px-2 py-0.5 text-xs font-black rounded"
                            style={{ backgroundColor: `${analyzedFrag.suggested_badge_color}30`, color: analyzedFrag.suggested_badge_color, border: `1px solid ${analyzedFrag.suggested_badge_color}50` }}
                          >
                            {analyzedFrag.badge_label}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-400">Min. zdrowie gracza (HP):</span>
                          <span className={analyzedFrag.is_clutch_1hp ? 'text-rose-400 font-bold' : 'text-emerald-400'}>
                            {analyzedFrag.min_hp_percentage}% {analyzedFrag.is_clutch_1hp && '(⚠️ CLUTCH DETECTED)'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-400">Pewność klasyfikacji:</span>
                          <span className="text-slate-200 font-medium">
                            {Math.round(analyzedFrag.confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 italic">
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
                            ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                            : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
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
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Tytuł publikacji na YouTube:
                </label>
                <input
                  type="text"
                  value={slotTitle}
                  onChange={(e) => setSlotTitle(e.target.value)}
                  placeholder="np. Insane 1% HP Katarina Clutch Survival #Shorts #LeagueOfLegends"
                  className="w-full bg-slate-800 border border-slate-700 text-slate-200 rounded-lg p-2.5 text-sm focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setSelectedSlot(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-lg transition"
              >
                Anuluj
              </button>
              <button
                type="button"
                onClick={handleSaveReservation}
                disabled={actionLoading === 'saving'}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-bold rounded-lg shadow-lg transition disabled:opacity-50"
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
          <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl p-6 space-y-5 my-8">
            {/* Header */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
                  <BarChart3 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span>YouTube Analytics: Retencja & Odpływ Widzów</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">
                      100 Punktów Pomiaru
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">
                    {retentionSlot.title || 'Wideo YouTube Shorts'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => { setRetentionSlot(null); setRetentionData(null); }}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            {retentionLoading ? (
              <div className="py-12 flex flex-col items-center justify-center gap-3 text-slate-400">
                <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
                <span className="text-sm font-medium">Odpytywanie YouTube Analytics API (elapsedVideoTimeRatio)...</span>
              </div>
            ) : retentionData && !retentionData.has_curve ? (
              <div className="p-6 bg-slate-800/50 border border-slate-700/60 rounded-xl text-center space-y-2">
                <AlertCircle className="w-8 h-8 text-amber-400 mx-auto" />
                <h4 className="text-sm font-bold text-slate-200">Brak pełnej krzywej retencji w YouTube Analytics</h4>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  {retentionData.message || 'YouTube udostępnia 100 punktów retencji dla filmów z minimum ~1,000 wyświetleń. Ten film ma obecnie: ' + (retentionSlot.views?.toLocaleString() || 0) + ' wyświetleń.'}
                </p>
              </div>
            ) : retentionData && retentionData.has_curve ? (
              <div className="space-y-4">
                {/* 4 KPI Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className={`p-3 rounded-xl border ${
                    (retentionData.swiped_away_pct || 0) <= 20
                      ? 'bg-emerald-950/30 border-emerald-800/50 text-emerald-300'
                      : (retentionData.swiped_away_pct || 0) <= 30
                      ? 'bg-amber-950/30 border-amber-800/50 text-amber-300'
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

                  <div className="p-3 rounded-xl border bg-slate-800/60 border-slate-700 text-slate-200">
                    <span className="text-[10px] uppercase font-bold tracking-wider block text-slate-400">Hook Retention</span>
                    <span className="text-xl font-black mt-1 block text-indigo-300">
                      {retentionData.hook_retention_pct}%
                    </span>
                    <span className="text-[10px] text-slate-400 mt-0.5 block">
                      Widzowie po 3s
                    </span>
                  </div>

                  <div className="p-3 rounded-xl border bg-slate-800/60 border-slate-700 text-slate-200">
                    <span className="text-[10px] uppercase font-bold tracking-wider block text-slate-400">Średnia (AVD)</span>
                    <span className="text-xl font-black mt-1 block text-purple-300">
                      {retentionData.avg_view_pct}%
                    </span>
                    <span className="text-[10px] text-slate-400 mt-0.5 block">
                      {retentionData.avg_view_duration_s}s / {retentionData.duration_s || 13}s
                    </span>
                  </div>

                  <div className="p-3 rounded-xl border bg-slate-800/60 border-slate-700 text-slate-200">
                    <span className="text-[10px] uppercase font-bold tracking-wider block text-slate-400">Ukończenie</span>
                    <span className="text-xl font-black mt-1 block text-cyan-300">
                      {retentionData.completion_rate_pct}%
                    </span>
                    <span className="text-[10px] text-slate-400 mt-0.5 block">
                      Dotrwało do końca
                    </span>
                  </div>
                </div>

                {/* AI Diagnosis */}
                {retentionData.diagnosis && (
                  <div className="p-3.5 rounded-xl bg-purple-950/30 border border-purple-500/30 flex items-start gap-2.5">
                    <Sparkles className="w-4 h-4 text-purple-400 flex-shrink-0 mt-0.5" />
                    <div className="text-xs text-purple-200">
                      <strong className="text-white block font-semibold mb-0.5">Diagnoza Samouczenia AI:</strong>
                      {retentionData.diagnosis}
                    </div>
                  </div>
                )}

                {/* 10-Point Retention Curve Visualizer */}
                {retentionData.sampled_curve && retentionData.sampled_curve.length > 0 && (
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-300">Krzywa Utrzymania Uwagi (10 punktów kontrolnych):</span>
                      <span className="text-slate-500 text-[11px]">YouTube elapsedVideoTimeRatio</span>
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
                                isHigh ? 'bg-indigo-500' : isLow ? 'bg-rose-500/70' : 'bg-slate-600'
                              }`}
                              style={{ height: `${hPct}%` }}
                            />
                            <span className="text-[9px] text-slate-500 mt-1 font-mono">{pt.time_s}s</span>
                            {/* Hover Tooltip */}
                            <div className="absolute bottom-full mb-1 hidden group-hover:flex flex-col items-center z-10 bg-black/90 border border-slate-700 px-1.5 py-0.5 rounded text-[10px] text-white whitespace-nowrap shadow-lg">
                              <span>{pt.retention_pct}%</span>
                              <span className="text-[8px] text-slate-400">{pt.percentile}% filmu ({pt.time_s}s)</span>
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
                    <span className="text-xs font-semibold text-slate-300 block">
                      Krytyczne punkty opuszczenia filmu (Drop-offs):
                    </span>
                    <div className="space-y-1.5 max-h-36 overflow-y-auto">
                      {retentionData.top_drop_offs.map((drop, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between text-xs p-2 rounded-lg bg-slate-800/60 border border-slate-700/80"
                        >
                          <div className="flex items-center gap-2">
                            <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono text-[10px] font-bold">
                              {drop.time_s}s ({drop.elapsed_pct}%)
                            </span>
                            <span className="text-slate-300 line-clamp-1">{drop.reason}</span>
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
            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              {retentionSlot.yt_url ? (
                <a
                  href={retentionSlot.yt_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Otwórz Shorta na YouTube
                </a>
              ) : <div />}
              <button
                type="button"
                onClick={() => { setRetentionSlot(null); setRetentionData(null); }}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition"
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
