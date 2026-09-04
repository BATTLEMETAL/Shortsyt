import React, { useState, useEffect } from 'react';
import { 
  Calendar as CalendarIcon, Clock, Sparkles, Trash2, Send, 
  CheckCircle, AlertCircle, RefreshCw, Film, Flame, ShieldAlert,
  ArrowRight, Plus, ExternalLink
} from 'lucide-react';
import { 
  apiGetCalendarSlots, apiReserveCalendarSlot, apiDeleteCalendarSlot, 
  apiPublishCalendarSlot, apiAutoFillCalendar, apiListClips, apiAnalyzeFrag,
  CalendarSlot, FragAnalysis, ClipItem
} from '../lib/api';

export function CalendarScheduler() {
  const [slots, setSlots] = useState<CalendarSlot[]>([]);
  const [days, setDays] = useState<number>(14);
  const [loading, setLoading] = useState<boolean>(true);
  const [autoFilling, setAutoFilling] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

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

  const loadSlots = async () => {
    try {
      setLoading(true);
      const res = await apiGetCalendarSlots(undefined, days);
      setSlots(res.slots || []);
    } catch (e: any) {
      setMessage({ type: 'error', text: `Błąd wczytywania kalendarza: ${e.message}` });
    } finally {
      setLoading(false);
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
    loadSlots();
    loadClips();
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

  // Group slots by Date
  const groupedSlots: { [date: string]: CalendarSlot[] } = {};
  slots.forEach(s => {
    if (!groupedSlots[s.date]) groupedSlots[s.date] = [];
    groupedSlots[s.date].push(s);
  });

  // Calculate KPIs
  const totalReserved = slots.filter(s => s.status === 'reserved').length;
  const totalReady = slots.filter(s => s.status === 'ready').length;
  const totalScheduled = slots.filter(s => s.status === 'scheduled').length;
  const totalFreePeak = slots.filter(s => s.status === 'free' && !s.is_past).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div>
          <div className="flex items-center gap-2">
            <CalendarIcon className="w-7 h-7 text-indigo-400" />
            <h1 className="text-2xl font-bold text-white tracking-tight">Kalendarz Publikacji i Rezerwacje Pipeline</h1>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Harmonogram publikacji YouTube Shorts w oparciu o okna najwyższego ruchu (08:30, 12:00, 18:30, 20:30 CET)
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
            onClick={loadSlots}
            disabled={loading}
            className="p-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition"
            title="Odśwież kalendarz"
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
          <span className="text-xs text-slate-500">Najbliższe okna szczytowe</span>
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
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Gotowe do wysyłki</span>
            <Film className="w-5 h-5 text-cyan-400" />
          </div>
          <p className="text-2xl font-bold text-cyan-300 mt-2">{totalReady}</p>
          <span className="text-xs text-slate-500">Wyrenderowane wideo</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Zaplanowane na YT</span>
            <CheckCircle className="w-5 h-5 text-emerald-400" />
          </div>
          <p className="text-2xl font-bold text-emerald-300 mt-2">{totalScheduled}</p>
          <span className="text-xs text-slate-500">W harmonogramie YouTube</span>
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="space-y-6">
        {Object.entries(groupedSlots).map(([dateStr, daySlots]) => {
          const isToday = new Date().toISOString().slice(0, 10) === dateStr;

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
                </div>
                <span className="text-xs text-slate-400">4 okna czasowe (Peak CET)</span>
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
                          ? 'bg-slate-800/80 border-slate-700 shadow-sm'
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
                          <div className="space-y-2 mt-3">
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

                            {slot.notes && (
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
                              className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded transition"
                              title="Zwolnij rezerwację"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
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
    </div>
  );
}
