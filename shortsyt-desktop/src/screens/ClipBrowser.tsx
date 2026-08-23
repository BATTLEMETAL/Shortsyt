import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiListClips, apiStartPipeline, ClipItem } from '../lib/api';
import {
  Film,
  UploadCloud,
  Play,
  Search,
  Sliders,
  Sparkles,
  Zap,
  CheckCircle2,
  AlertCircle,
  FileVideo,
  X,
  RefreshCw,
  FolderOpen,
} from 'lucide-react';

const CHAMPIONS = [
  'Katarina', 'Ahri', 'Zed', 'Yasuo', 'Jinx', 'Thresh', 'Lee Sin', 'Vayne',
  'Samira', 'Akali', 'Yone', 'Riven', 'Kassadin', 'Evelynn', 'Master Yi', 'Darius'
];

const ACTION_TYPES = [
  { id: 'pentakill', label: 'PENTAKILL 🔥', hook: 'PENTAKILL! 💥' },
  { id: 'quadrakill', label: 'QUADRAKILL ⚡', hook: 'QUADRA KILL! ⚡' },
  { id: 'triple', label: 'TRIPLE KILL 🎯', hook: 'TRIPLE KILL! 🎯' },
  { id: 'outplay', label: 'OUTPLAY / 1v3 🧠', hook: 'NOBODY EXPECTED THIS 🎯' },
  { id: 'clutch', label: 'CLUTCH 1% HP 💀', hook: '1% HP CLUTCH 💀' },
];

export default function ClipBrowser() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [clips, setClips] = useState<ClipItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [search, setSearch] = useState<string>('');

  // Selected clip for rendering configuration modal
  const [selectedClip, setSelectedClip] = useState<ClipItem | null>(null);
  const [customPath, setCustomPath] = useState<string>('');

  // Pipeline Render Config
  const [champion, setChampion] = useState<string>('Katarina');
  const [actionType, setActionType] = useState<string>('pentakill');
  const [hookText, setHookText] = useState<string>('PENTAKILL! 💥');
  const [clipStart, setClipStart] = useState<number>(0);
  const [clipEnd, setClipEnd] = useState<number>(25);
  const [peakMoment, setPeakMoment] = useState<number>(18);
  const [useSmartCamera, setUseSmartCamera] = useState<boolean>(true);
  const [useSpeedRamp, setUseSpeedRamp] = useState<boolean>(true);
  const [useZoomPunch, setUseZoomPunch] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const fetchClips = async () => {
    setLoading(true);
    try {
      const data = await apiListClips();
      setClips(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClips();
  }, []);

  const handleActionChange = (id: string) => {
    setActionType(id);
    const found = ACTION_TYPES.find((a) => a.id === id);
    if (found) setHookText(found.hook);
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      // File path in Electron
      const filePath = (file as any).path || file.name;
      setCustomPath(filePath);
      setSelectedClip({
        filename: file.name,
        path: filePath,
        size_mb: Math.round(file.size / (1024 * 1024)),
        modified: Date.now() / 1000,
      });
    }
  };

  const handleManualFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      const filePath = (file as any).path || file.name;
      setCustomPath(filePath);
      setSelectedClip({
        filename: file.name,
        path: filePath,
        size_mb: Math.round(file.size / (1024 * 1024)),
        modified: Date.now() / 1000,
      });
    }
  };

  const handleLaunchRender = async () => {
    if (!selectedClip && !customPath) return;
    setIsSubmitting(true);
    setSubmitError(null);

    const sourcePath = selectedClip ? selectedClip.path : customPath;
    const outputFilename = `short_${Date.now()}_${champion.toLowerCase()}.mp4`;

    try {
      await apiStartPipeline({
        source_path: sourcePath,
        clip_start: Number(clipStart),
        clip_end: Number(clipEnd),
        action_type: actionType,
        champion_name: champion,
        rank: 'Master',
        peak_moment: Number(peakMoment),
        hook_text: hookText,
        output_filename: outputFilename,
        use_speed_ramp: useSpeedRamp,
        use_zoom_punch: useZoomPunch,
        use_smart_camera: useSmartCamera,
      });

      // Redirect directly to live render monitor
      navigate('/render');
    } catch (err: any) {
      setSubmitError(err.response?.data?.detail || err.message || 'Nie udało się uruchomić renderu');
      setIsSubmitting(false);
    }
  };

  const filteredClips = clips.filter((c) =>
    c.filename.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2438]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
            <Film className="w-6 h-6 text-[#C89B3C]" />
            <span>Studio Klipów & Konfiguracja Montażu</span>
          </h1>
          <p className="text-xs text-[#8B8FA8] mt-1 font-medium">
            Ręczne wgrywanie plików MP4 lub wybór z automatycznego skanera nagrań Outplayed / Medal
          </p>
        </div>

        <button
          onClick={fetchClips}
          disabled={loading}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#121624] hover:bg-[#1A1E30] border border-[#1E2438] text-xs font-semibold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#C89B3C]' : ''}`} />
          <span>Odśwież skan</span>
        </button>
      </div>

      {/* Manual Drag & Drop Zone */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleFileDrop}
        onClick={() => fileInputRef.current?.click()}
        className="p-6 rounded-2xl border-2 border-dashed border-[#C89B3C]/40 hover:border-[#C89B3C] bg-[#121624]/60 hover:bg-[#1A1E30]/60 transition-all cursor-pointer flex flex-col items-center justify-center text-center group"
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="video/mp4,video/mkv,video/avi,video/quicktime"
          onChange={handleManualFileSelect}
          className="hidden"
        />
        <div className="w-12 h-12 rounded-xl bg-[#C89B3C]/10 border border-[#C89B3C]/30 flex items-center justify-center text-[#C89B3C] group-hover:scale-110 transition-transform mb-3">
          <UploadCloud className="w-6 h-6" />
        </div>
        <div className="text-sm font-bold text-[#E4D6B5] group-hover:text-[#C89B3C] transition-colors">
          Przeciągnij i upuść dowolny plik wideo z dysku (MP4 / MKV)
        </div>
        <div className="text-xs text-[#8B8FA8] mt-1">
          lub kliknij tutaj, aby wybrać plik ręcznie i natychmiast dostosować parametry cięcia
        </div>
      </div>

      {/* Search & Auto-scan clips */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-xs font-bold uppercase tracking-wider text-[#8B8FA8] flex items-center gap-2">
            <FolderOpen className="w-4 h-4 text-[#C89B3C]" />
            <span>Wykryte nagrania w folderze gry ({filteredClips.length})</span>
          </div>

          <div className="relative w-72">
            <Search className="w-3.5 h-3.5 text-[#8B8FA8] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filtruj po tytule/dacie..."
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-[#121624] border border-[#1E2438] text-xs text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"
            />
          </div>
        </div>

        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center text-[#8B8FA8]">
            <RefreshCw className="w-6 h-6 animate-spin text-[#C89B3C] mb-2" />
            <span className="text-xs">Skanowanie nagrań...</span>
          </div>
        ) : filteredClips.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredClips.map((clip) => (
              <div
                key={clip.filename}
                className="p-4 rounded-xl bg-[#121624] border border-[#1E2438] hover:border-[#C89B3C]/40 transition-all flex flex-col justify-between group"
              >
                <div className="flex items-start gap-3">
                  <div className="p-2.5 rounded-lg bg-[#1A1E30] text-[#C89B3C] border border-[#1E2438]">
                    <FileVideo className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-bold text-[#E4D6B5] truncate group-hover:text-[#C89B3C] transition-colors" title={clip.filename}>
                      {clip.filename}
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-[11px] text-[#8B8FA8]">
                      <span>{clip.size_mb} MB</span>
                      <span>•</span>
                      <span>{new Date(clip.modified * 1000).toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-[#1A1E30] text-[#8B8FA8] font-mono">
                    RAW CLUTCH
                  </span>
                  <button
                    onClick={() => setSelectedClip(clip)}
                    className="text-xs bg-[#C89B3C]/15 hover:bg-[#C89B3C] text-[#C89B3C] hover:text-[#0A0E1A] font-bold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1 shadow-sm"
                  >
                    <Sliders className="w-3 h-3" />
                    <span>Konfiguruj & Renderuj</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-10 text-center text-[#50546A] text-xs">
            Brak plików w domyślnym katalogu. Użyj powyższego pola dropzone do ręcznego wgrania klipu.
          </div>
        )}
      </div>

      {/* Render Configuration Drawer Modal */}
      {selectedClip && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#121624] border border-[#C89B3C]/40 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 shadow-2xl space-y-5 text-[#E4D6B5]">
            {/* Modal Header */}
            <div className="flex items-start justify-between pb-3 border-b border-[#1E2438]">
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-[#C89B3C] flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4" />
                  <span>Kreator Montażu Shorts (9:16)</span>
                </div>
                <div className="text-sm font-bold text-[#E4D6B5] mt-1 truncate max-w-md">
                  {selectedClip.filename}
                </div>
              </div>
              <button
                onClick={() => setSelectedClip(null)}
                className="p-1.5 rounded-lg bg-[#1E2438] hover:bg-[#2D3550] text-[#8B8FA8] hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {submitError && (
              <div className="p-3 rounded-xl bg-[#E84040]/15 border border-[#E84040]/30 text-[#FF6060] text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{submitError}</span>
              </div>
            )}

            {/* Form Fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Champion Whitelist */}
              <div>
                <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">
                  Bohater (Champion):
                </label>
                <select
                  value={champion}
                  onChange={(e) => setChampion(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"
                >
                  {CHAMPIONS.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              {/* Action Type */}
              <div>
                <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">
                  Typ Akcji:
                </label>
                <select
                  value={actionType}
                  onChange={(e) => handleActionChange(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#C89B3C] focus:outline-none focus:border-[#C89B3C]"
                >
                  {ACTION_TYPES.map((a) => (
                    <option key={a.id} value={a.id}>{a.label}</option>
                  ))}
                </select>
              </div>

              {/* Hook Text Overlay */}
              <div className="md:col-span-2">
                <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">
                  Napis na starcie (Hook Overlay pierwsze 2s):
                </label>
                <input
                  type="text"
                  value={hookText}
                  onChange={(e) => setHookText(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"
                />
              </div>

              {/* Timing settings */}
              <div>
                <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">
                  Start cięcia (sekundy):
                </label>
                <input
                  type="number"
                  step="0.5"
                  value={clipStart}
                  onChange={(e) => setClipStart(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-mono text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"
                />
              </div>

              <div>
                <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">
                  Koniec cięcia (sekundy):
                </label>
                <input
                  type="number"
                  step="0.5"
                  value={clipEnd}
                  onChange={(e) => setClipEnd(parseFloat(e.target.value) || 20)}
                  className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-mono text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"
                />
              </div>
            </div>

            {/* Effect Toggles */}
            <div className="p-4 rounded-xl bg-[#0A0E1A] border border-[#1E2438] space-y-2.5">
              <div className="text-xs font-bold text-[#8B8FA8] uppercase tracking-wider mb-2">
                Moduły Produkcyjne v25:
              </div>

              <label className="flex items-center justify-between cursor-pointer text-xs font-semibold">
                <span className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-[#C89B3C]" />
                  <span>Smart Camera v11 (Dynamiczne śledzenie HP barów gracza)</span>
                </span>
                <input
                  type="checkbox"
                  checked={useSmartCamera}
                  onChange={(e) => setUseSmartCamera(e.target.checked)}
                  className="rounded border-[#1E2438] bg-[#121624] text-[#C89B3C]"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer text-xs font-semibold">
                <span className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-[#2ECC71]" />
                  <span>Slow-Mo Ramp 0.45x + Minterpolate Blend na decydujący cios</span>
                </span>
                <input
                  type="checkbox"
                  checked={useSpeedRamp}
                  onChange={(e) => setUseSpeedRamp(e.target.checked)}
                  className="rounded border-[#1E2438] bg-[#121624] text-[#C89B3C]"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer text-xs font-semibold">
                <span className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-[#2A7FD4]" />
                  <span>Zoom-Punch 1.20x i podbicie basu na kill moment</span>
                </span>
                <input
                  type="checkbox"
                  checked={useZoomPunch}
                  onChange={(e) => setUseZoomPunch(e.target.checked)}
                  className="rounded border-[#1E2438] bg-[#121624] text-[#C89B3C]"
                />
              </label>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#1E2438]">
              <button
                type="button"
                onClick={() => setSelectedClip(null)}
                className="px-4 py-2 rounded-xl bg-[#1E2438] hover:bg-[#2D3550] text-xs font-bold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors"
              >
                Anuluj
              </button>

              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleLaunchRender}
                className="px-5 py-2.5 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-black transition-colors flex items-center gap-2 shadow-lg shadow-[#C89B3C]/20"
              >
                <Play className="w-4 h-4 fill-current" />
                <span>{isSubmitting ? 'Uruchamianie pipeline...' : 'Renderuj Short (9:16)'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
