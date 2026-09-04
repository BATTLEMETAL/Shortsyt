import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { apiListClips, apiStartPipeline, apiAutoDetectClip, ClipItem, AutoDetectResult } from "../lib/api";
import {
  Film, UploadCloud, Play, Search, Sliders, Zap, CheckCircle2,
  AlertCircle, FileVideo, X, RefreshCw, FolderOpen, Wand2, Clock, Settings2,
  ChevronDown, ChevronUp, ArrowRight, Loader2,
} from "lucide-react";

const CHAMPIONS = [
  "Katarina","Ahri","Zed","Yasuo","Jinx","Thresh","Lee Sin","Vayne",
  "Samira","Akali","Yone","Riven","Kassadin","Evelynn","Master Yi","Darius"
];
const ACTION_TYPES = [
  { id: "pentakill", label: "PENTAKILL 🔥", hook: "PENTAKILL! 💥" },
  { id: "quadrakill", label: "QUADRAKILL ⚡", hook: "QUADRA KILL! ⚡" },
  { id: "triple", label: "TRIPLE KILL 🎯", hook: "TRIPLE KILL! 🎯" },
  { id: "double", label: "DOUBLE KILL ⚔️", hook: "DOUBLE KILL! ⚔️" },
  { id: "solo_bolo", label: "SOLO BOLO 👑", hook: "SOLO BOLO! 👑" },
  { id: "outplay", label: "OUTPLAY / 1v3 🧠", hook: "NOBODY EXPECTED THIS 🎯" },
  { id: "clutch", label: "CLUTCH 1% HP 💀", hook: "1% HP CLUTCH 💀" },
];
type AutoStage = "idle" | "selected" | "detecting" | "launching" | "done" | "error";

export default function ClipBrowser() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedFolder, setSelectedFolder] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Auto
  const [autoClip, setAutoClip] = useState<ClipItem | null>(null);
  const [autoStage, setAutoStage] = useState<AutoStage>("idle");
  const [autoResult, setAutoResult] = useState<AutoDetectResult | null>(null);
  const [autoError, setAutoError] = useState<string | null>(null);

  // Manual
  const [selectedClip, setSelectedClip] = useState<ClipItem | null>(null);
  const [timingMode, setTimingMode] = useState<"auto" | "manual">("auto");
  const [isAutoDetecting, setIsAutoDetecting] = useState(false);
  const [autoDetectResult, setAutoDetectResult] = useState<AutoDetectResult | null>(null);
  const [champion, setChampion] = useState("Katarina");
  const [actionType, setActionType] = useState("pentakill");
  const [hookText, setHookText] = useState("PENTAKILL! 💥");
  const [clipStart, setClipStart] = useState(0);
  const [clipEnd, setClipEnd] = useState(12);
  const [peakMoment, setPeakMoment] = useState(8);
  const [useSmartCamera, setUseSmartCamera] = useState(true);
  const [useSpeedRamp, setUseSpeedRamp] = useState(true);
  const [useZoomPunch, setUseZoomPunch] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [combatSegments, setCombatSegments] = useState<Array<[number, number]> | null>(null);

  const fetchClips = async (fp?: string) => {
    setLoading(true);
    try { const d = await apiListClips((fp ?? selectedFolder) || undefined); setClips(d); }
    catch { } finally { setLoading(false); }
  };
  useEffect(() => { fetchClips(); }, []);

  const handlePickFolder = async () => {
    if (window.electronApp?.selectDirectory) {
      const f = await window.electronApp.selectDirectory().catch(() => null);
      if (f) { setSelectedFolder(f); fetchClips(f); }
    } else {
      const f = prompt("Sciezka do folderu:", selectedFolder);
      if (f !== null) { setSelectedFolder(f.trim()); fetchClips(f.trim()); }
    }
  };

  // AUTO PIPELINE
  const handleAutoLaunch = async (clip: ClipItem) => {
    setAutoClip(clip); setAutoStage("detecting"); setAutoError(null); setAutoResult(null);
    let detected: AutoDetectResult | null = null;
    try {
      detected = await apiAutoDetectClip({ source_path: clip.path || clip.filename });
      setAutoResult(detected);
    } catch { }
    setAutoStage("launching");
    const outFile = `short_${Date.now()}_auto.mp4`;
    try {
      await apiStartPipeline({
        source_path: clip.path || clip.filename,
        clip_start: detected?.clip_start ?? 0,
        clip_end: detected?.clip_end ?? 12,
        action_type: detected?.action_type ?? "outplay",
        champion_name: champion || "Katarina",
        rank: "Master",
        peak_moment: detected?.peak_moment ?? 8,
        hook_text: detected?.hook_text ?? "INSANE OUTPLAY! 🔥",
        output_filename: outFile,
        use_speed_ramp: true,
        use_zoom_punch: true,
        use_smart_camera: true,
        combat_segments: detected?.combat_segments ?? null,
      });
      setAutoStage("done");
      setTimeout(() => navigate("/render"), 800);
    } catch (err: any) {
      setAutoError(err.response?.data?.detail || err.message || "Blad pipeline");
      setAutoStage("error");
    }
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0]; if (!file) return;
    const fp = (file as any).path || file.name;
    setAutoClip({ filename: file.name, path: fp, size_mb: Math.round(file.size / 1048576), modified: Date.now() / 1000 });
    setAutoStage("selected"); setAutoResult(null); setAutoError(null);
  };

  const resetAuto = () => { setAutoClip(null); setAutoStage("idle"); setAutoResult(null); setAutoError(null); };

  const runAutoDetect = async (path: string) => {
    setIsAutoDetecting(true);
    setCombatSegments(null);
    try {
      // NOTE: Do NOT pass action_type to auto-detect — let OCR/CV determine it honestly
      const res = await apiAutoDetectClip({ source_path: path, champion_name: champion });
      setAutoDetectResult(res);
      setClipStart(res.clip_start);
      setClipEnd(res.clip_end);
      setPeakMoment(res.peak_moment);
      if (res.action_type) setActionType(res.action_type);
      if (res.hook_text) setHookText(res.hook_text);
      if (res.combat_segments && res.has_jump_cut) {
        setCombatSegments(res.combat_segments);
      }
    } catch { } finally { setIsAutoDetecting(false); }
  };

  const openManualModal = (clip: ClipItem) => {
    setSelectedClip(clip); setTimingMode("auto"); setAutoDetectResult(null); setCombatSegments(null);
    runAutoDetect(clip.path || clip.filename);
  };

  const handleActionChange = (v: string) => {
    setActionType(v);
    const m = ACTION_TYPES.find(a => a.id === v);
    if (m) setHookText(m.hook);
  };

  const handleLaunchRender = async () => {
    if (!selectedClip) return;
    setIsSubmitting(true); setSubmitError(null);
    const outFile = `short_${Date.now()}_${champion.toLowerCase()}.mp4`;
    try {
      await apiStartPipeline({
        source_path: selectedClip.path, clip_start: Number(clipStart), clip_end: Number(clipEnd),
        action_type: actionType, champion_name: champion, rank: "Master",
        peak_moment: Number(peakMoment), hook_text: hookText, output_filename: outFile,
        use_speed_ramp: useSpeedRamp, use_zoom_punch: useZoomPunch, use_smart_camera: useSmartCamera,
        combat_segments: combatSegments,
      });
      navigate("/render");
    } catch (err: any) {
      setSubmitError(err.response?.data?.detail || err.message || "Blad renderu");
      setIsSubmitting(false);
    }
  };

  const filteredClips = clips.filter(c => c.filename.toLowerCase().includes(search.toLowerCase()));
  const stageMsg: Record<AutoStage, string> = {
    idle: "", selected: "Gotowy do uruchomienia",
    detecting: "AI analizuje wideo (CV + OCR)...",
    launching: "Uruchamianie pipeline...",
    done: "Pipeline uruchomiony! Przekierowuje...",
    error: "Blad"
  };

  const autoStepCls = (active: boolean, pulse: boolean) =>
    `flex items-center gap-1 px-2.5 py-1 rounded-lg border transition-all ${active ? (pulse ? "bg-blue-500/15 border-blue-500/40 text-blue-400 animate-pulse" : "bg-[#C89B3C]/15 border-[#C89B3C]/40 text-[#C89B3C]") : "bg-[#121624] border-[#1E2438] text-[#50546A]"}`;

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2438]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
            <Film className="w-6 h-6 text-[#C89B3C]" />Studio Klipow
          </h1>
          <p className="text-xs text-[#8B8FA8] mt-1">Wrzuc klip — AI robi reszte automatycznie. Opcje reczne dostepne ponizej.</p>
        </div>
        <button onClick={() => fetchClips()} disabled={loading}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#121624] hover:bg-[#1A1E30] border border-[#1E2438] text-xs font-semibold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-[#C89B3C]" : ""}`} />Odswiez
        </button>
      </div>

      {/* STREFA 1: AUTO-PIPELINE */}
      <div className="p-5 rounded-2xl bg-gradient-to-br from-[#0E1524] to-[#121624] border-2 border-[#C89B3C]/50 shadow-lg shadow-[#C89B3C]/5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#C89B3C]/15 border border-[#C89B3C]/40 flex items-center justify-center">
              <Zap className="w-4 h-4 text-[#C89B3C]" />
            </div>
            <div>
              <div className="text-sm font-black text-[#E4D6B5] flex items-center gap-2">
                TRYB AUTOMATYCZNY
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#2ECC71]/15 text-[#2ECC71] border border-[#2ECC71]/30 font-bold">ZALECANY</span>
              </div>
              <div className="text-[11px] text-[#8B8FA8]">Wrzuc klip → AI analizuje → Short gotowy automatycznie</div>
            </div>
          </div>
          {autoStage !== "idle" && (
            <button onClick={resetAuto} className="p-1.5 rounded-lg bg-[#1E2438] hover:bg-[#2D3550] text-[#8B8FA8] hover:text-white transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 text-[11px] font-semibold flex-wrap">
          <div className={autoStepCls(autoStage !== "idle", false)}><UploadCloud className="w-3.5 h-3.5" />Wrzuc klip</div>
          <ArrowRight className="w-3 h-3 text-[#50546A] flex-shrink-0" />
          <div className={autoStepCls(["detecting","launching","done"].includes(autoStage), autoStage==="detecting")}><Wand2 className="w-3.5 h-3.5" />AI analizuje</div>
          <ArrowRight className="w-3 h-3 text-[#50546A] flex-shrink-0" />
          <div className={autoStepCls(["launching","done"].includes(autoStage), autoStage==="launching")}><Zap className="w-3.5 h-3.5" />Short gotowy!</div>
        </div>

        {autoStage === "idle" && (
          <div onDragOver={e => e.preventDefault()} onDrop={handleFileDrop}
            onClick={() => fileInputRef.current?.click()}
            className="p-8 rounded-xl border-2 border-dashed border-[#C89B3C]/40 hover:border-[#C89B3C] bg-[#0A0E1A]/60 hover:bg-[#121624]/60 transition-all cursor-pointer flex flex-col items-center justify-center text-center group">
            <input ref={fileInputRef} type="file" accept="video/mp4,video/mkv,video/avi,video/quicktime"
              onChange={e => {
                const f = e.target.files?.[0]; if (!f) return;
                const fp = (f as any).path || f.name;
                setAutoClip({ filename: f.name, path: fp, size_mb: Math.round(f.size/1048576), modified: Date.now()/1000 });
                setAutoStage("selected"); setAutoResult(null); setAutoError(null);
              }} className="hidden" />
            <div className="w-14 h-14 rounded-2xl bg-[#C89B3C]/10 border border-[#C89B3C]/30 flex items-center justify-center text-[#C89B3C] group-hover:scale-110 transition-transform mb-3">
              <UploadCloud className="w-7 h-7" />
            </div>
            <div className="text-base font-bold text-[#E4D6B5] group-hover:text-[#C89B3C] transition-colors">Przeciagnij klip tutaj lub kliknij</div>
            <div className="text-xs text-[#8B8FA8] mt-1">MP4 / MKV / AVI — AI automatycznie wykryje frag i uruchomi render</div>
          </div>
        )}

        {autoClip && autoStage !== "idle" && (
          <div className="p-3.5 rounded-xl bg-[#0A0E1A] border border-[#C89B3C]/30 space-y-2">
            <div className="flex items-center gap-2">
              <FileVideo className="w-4 h-4 text-[#C89B3C] flex-shrink-0" />
              <span className="text-xs font-bold text-[#E4D6B5] truncate flex-1">{autoClip.filename}</span>
              <span className="text-[10px] text-[#8B8FA8]">{autoClip.size_mb} MB</span>
            </div>
            {autoResult && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#C89B3C]/15 border border-[#C89B3C]/40 text-[#C89B3C] font-bold">
                  {autoResult.action_type?.toUpperCase() || "OUTPLAY"} wykryty
                </span>
                <span className="text-[10px] text-[#8B8FA8]">
                  {autoResult.clip_start?.toFixed(1)}s – {autoResult.clip_end?.toFixed(1)}s
                </span>
                {autoResult.confidence && <span className="text-[10px] text-emerald-400">{autoResult.confidence}</span>}
              </div>
            )}
            {(autoStage === "detecting" || autoStage === "launching") && (
              <div className="text-[11px] text-[#8B8FA8] flex items-center gap-1.5">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[#C89B3C]" />{stageMsg[autoStage]}
              </div>
            )}
            {autoStage === "done" && <div className="text-[11px] text-emerald-400 flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5" />{stageMsg["done"]}</div>}
            {autoStage === "error" && autoError && <div className="text-xs text-red-400 flex items-center gap-1.5"><AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />{autoError}</div>}
          </div>
        )}

        {(autoStage === "selected" || autoStage === "error") && autoClip && (
          <button onClick={() => handleAutoLaunch(autoClip)}
            className="w-full py-3.5 rounded-xl bg-gradient-to-r from-[#C89B3C] to-[#E5C269] hover:from-[#B58B32] hover:to-[#D4B25B] text-[#0A0E1A] font-black text-sm flex items-center justify-center gap-2.5 shadow-xl shadow-[#C89B3C]/20 transition-all">
            <Zap className="w-5 h-5" />Uruchom AUTO-Pipeline
          </button>
        )}
      </div>

      {/* STREFA 2: LISTA KLIPOW */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2.5 flex-wrap">
            <div className="text-xs font-bold uppercase tracking-wider text-[#8B8FA8] flex items-center gap-2">
              <Film className="w-4 h-4 text-[#C89B3C]" />Nagrania z Outplayed ({filteredClips.length})
            </div>
            <button onClick={handlePickFolder} className="flex items-center gap-1 px-2 py-1 rounded-lg bg-[#121624] hover:bg-[#1E2438] border border-[#1E2438] text-[10px] text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors">
              <FolderOpen className="w-3 h-3 text-[#C89B3C]" />{selectedFolder ? "Zmien folder" : "Wybierz folder"}
            </button>
            {selectedFolder && <button onClick={() => { setSelectedFolder(""); fetchClips(""); }} className="text-[10px] text-[#8B8FA8] hover:text-[#E4D6B5] underline">Domyslny</button>}
          </div>
          <div className="relative w-56">
            <Search className="w-3.5 h-3.5 text-[#8B8FA8] absolute left-3 top-1/2 -translate-y-1/2" />
            <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Filtruj..."
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-[#121624] border border-[#1E2438] text-xs text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]" />
          </div>
        </div>
        {loading ? (
          <div className="py-10 flex flex-col items-center justify-center text-[#8B8FA8]">
            <RefreshCw className="w-6 h-6 animate-spin text-[#C89B3C] mb-2" /><span className="text-xs">Skanowanie nagran...</span>
          </div>
        ) : filteredClips.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {filteredClips.map(clip => (
              <div key={clip.filename} className="p-3.5 rounded-xl bg-[#121624] border border-[#1E2438] hover:border-[#C89B3C]/30 transition-all flex flex-col justify-between gap-3 group">
                <div className="flex items-start gap-2.5">
                  <div className="p-2 rounded-lg bg-[#1A1E30] text-[#C89B3C] border border-[#1E2438] flex-shrink-0"><FileVideo className="w-4 h-4" /></div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-bold text-[#E4D6B5] truncate group-hover:text-[#C89B3C] transition-colors" title={clip.filename}>{clip.filename}</div>
                    <div className="flex items-center gap-1.5 mt-1">
                      <span className="text-[10px] text-[#8B8FA8]">{clip.size_mb} MB</span>
                      <span className="text-[10px] text-[#50546A]">•</span>
                      <span className="text-[10px] text-[#8B8FA8]">{new Date(clip.modified * 1000).toLocaleDateString("pl-PL")}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                  <button onClick={() => handleAutoLaunch(clip)}
                    className="flex-1 text-xs bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] font-black px-3 py-1.5 rounded-lg transition-colors flex items-center justify-center gap-1.5 shadow-sm">
                    <Zap className="w-3.5 h-3.5" />Auto-Pipeline
                  </button>
                  <button onClick={() => openManualModal(clip)}
                    className="px-2.5 py-1.5 text-[10px] text-[#8B8FA8] hover:text-[#E4D6B5] font-semibold rounded-lg bg-[#1E2438] hover:bg-[#2A2D40] transition-colors flex items-center gap-1">
                    <Settings2 className="w-3 h-3" />Recznie
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-10 text-center text-[#50546A] text-xs">Brak plikow. Wgraj klip przez strefe Auto lub wybierz folder.</div>
        )}
      </div>

      {/* STREFA 3: ZAAWANSOWANE */}
      <div className="rounded-2xl bg-[#0E1220] border border-[#1E2438] overflow-hidden">
        <button onClick={() => setAdvancedOpen(p => !p)}
          className="w-full px-5 py-3.5 flex items-center justify-between text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
            <Settings2 className="w-3.5 h-3.5 text-[#C89B3C]" />Konfiguracja Zaawansowana — Pelna Kontrola
          </div>
          {advancedOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {advancedOpen && (
          <div className="px-5 pb-5 space-y-3 border-t border-[#1E2438] pt-4">
            <p className="text-[11px] text-[#50546A]">Przeciagnij plik lub kliknij aby rcznie skonfigurowac timing, champion i efekty przed renderem.</p>
            <div onDragOver={e => e.preventDefault()} onDrop={e => {
                e.preventDefault(); const f = e.dataTransfer.files?.[0];
                if (f) openManualModal({ filename: f.name, path: (f as any).path || f.name, size_mb: Math.round(f.size/1048576), modified: Date.now()/1000 });
              }}
              onClick={() => {
                const inp = document.createElement("input"); inp.type = "file"; inp.accept = "video/*";
                inp.onchange = (e: any) => { const f = e.target.files?.[0]; if (f) openManualModal({ filename: f.name, path: (f as any).path || f.name, size_mb: Math.round(f.size/1048576), modified: Date.now()/1000 }); };
                inp.click();
              }}
              className="p-6 rounded-xl border-2 border-dashed border-[#1E2438] hover:border-[#C89B3C]/40 bg-[#0A0E1A]/40 cursor-pointer flex items-center justify-center gap-3 text-xs text-[#50546A] hover:text-[#8B8FA8] transition-all">
              <Sliders className="w-4 h-4" />Przeciagnij klip lub kliknij — otworzy konfigurator z pelna kontrola ciecia i efektow
            </div>
          </div>
        )}
      </div>

      {/* MODAL RECZNY */}
      {selectedClip && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#121624] border border-[#C89B3C]/40 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 shadow-2xl space-y-5 text-[#E4D6B5]">
            <div className="flex items-start justify-between pb-3 border-b border-[#1E2438]">
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-[#C89B3C] flex items-center gap-1.5">
                  <Settings2 className="w-4 h-4" />Konfiguracja Reczna — Pelna Kontrola
                </div>
                <div className="text-sm font-bold text-[#E4D6B5] mt-1 truncate max-w-md">{selectedClip.filename}</div>
              </div>
              <button onClick={() => setSelectedClip(null)} className="p-1.5 rounded-lg bg-[#1E2438] hover:bg-[#2D3550] text-[#8B8FA8] hover:text-white transition-colors"><X className="w-4 h-4" /></button>
            </div>
            {submitError && <div className="p-3 rounded-xl bg-[#E84040]/15 border border-[#E84040]/30 text-[#FF6060] text-xs flex items-center gap-2"><AlertCircle className="w-4 h-4 flex-shrink-0" />{submitError}</div>}
            <div className="p-4 rounded-xl bg-[#0A0E1A] border border-[#1E2438] space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="text-xs font-bold text-[#8B8FA8] uppercase tracking-wider flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-[#C89B3C]" />Czas Klipu:</div>
                <div className="flex items-center bg-[#121624] p-1 rounded-xl border border-[#1E2438]">
                  <button type="button" onClick={() => setTimingMode("auto")} className={`flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-bold transition-colors ${timingMode==="auto"?"bg-[#C89B3C] text-[#0A0E1A]":"text-[#8B8FA8] hover:text-[#E4D6B5]"}`}><Wand2 className="w-3 h-3"/>AI Auto-Trim</button>
                  <button type="button" onClick={() => setTimingMode("manual")} className={`flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-bold transition-colors ${timingMode==="manual"?"bg-[#1E2438] text-[#E4D6B5] border border-[#C89B3C]/40":"text-[#8B8FA8] hover:text-[#E4D6B5]"}`}><Settings2 className="w-3 h-3"/>Reczny</button>
                </div>
              </div>
              {timingMode==="auto" && (
                <div className="p-3 rounded-lg bg-[#121624] border border-[#C89B3C]/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div>
                    <span className="text-[11px] font-bold text-[#2ECC71] flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5"/>{isAutoDetecting?"Analizowanie...":autoDetectResult?.confidence||"AI optymalne okno"}</span>
                    <div className="text-[11px] text-[#8B8FA8] mt-0.5">Start: <b className="font-mono text-[#E4D6B5]">{clipStart}s</b> Koniec: <b className="font-mono text-[#E4D6B5]">{clipEnd}s</b> Peak: <b className="font-mono text-[#C89B3C]">{peakMoment}s</b></div>
                    {combatSegments && combatSegments.length > 1 && (
                      <div className="mt-1.5 flex items-center gap-1.5 px-2 py-1 rounded-md bg-blue-500/10 border border-blue-500/30">
                        <span className="text-[10px] font-bold text-blue-400">JUMP-CUT AKTYWNY</span>
                        <span className="text-[10px] text-[#8B8FA8]">— {combatSegments.length} segmenty walki | wycięto martwy bieg</span>
                      </div>
                    )}
                  </div>
                  <button type="button" onClick={() => runAutoDetect(selectedClip.path||selectedClip.filename)} disabled={isAutoDetecting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1E2438] hover:bg-[#2A2D40] text-xs font-bold text-[#C89B3C] transition-colors shrink-0">
                    <RefreshCw className={`w-3 h-3 ${isAutoDetecting?"animate-spin":""}`}/>{isAutoDetecting?"Skanuje...":"Przelicz AI"}
                  </button>
                </div>
              )}
              <div className="grid grid-cols-3 gap-3 pt-1">
                {[{l:"Start (s)",v:clipStart,s:setClipStart},{l:"Koniec (s)",v:clipEnd,s:setClipEnd},{l:"Peak (s)",v:peakMoment,s:setPeakMoment}].map(({l,v,s})=>(
                  <div key={l}>
                    <label className="text-[11px] font-bold text-[#8B8FA8] block mb-1">{l}</label>
                    <div className="flex gap-1 mb-1">{[-1,1].map(d=><button key={d} type="button" onClick={()=>s((x:number)=>Math.max(0,+(x+d).toFixed(1)))} className="px-1.5 py-0.5 bg-[#121624] hover:bg-[#1E2438] text-[#8B8FA8] rounded border border-[#1E2438] text-[10px]">{d>0?"+1s":"-1s"}</button>)}</div>
                    <input type="number" step="0.5" value={v} onChange={e=>s(parseFloat(e.target.value)||0)} className="w-full px-3 py-1.5 rounded-lg bg-[#121624] border border-[#1E2438] text-xs font-mono text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"/>
                  </div>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">Bohater:</label>
                <select value={champion} onChange={e=>setChampion(e.target.value)} className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]">
                  {CHAMPIONS.map(c=><option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">Typ Akcji:</label>
                <select value={actionType} onChange={e=>handleActionChange(e.target.value)} className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#C89B3C] focus:outline-none focus:border-[#C89B3C]">
                  {ACTION_TYPES.map(a=><option key={a.id} value={a.id}>{a.label}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">Hook Text:</label>
                <input type="text" value={hookText} onChange={e=>setHookText(e.target.value)} className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"/>
              </div>
            </div>
            <div className="p-4 rounded-xl bg-[#0A0E1A] border border-[#1E2438] space-y-2.5">
              <div className="text-xs font-bold text-[#8B8FA8] uppercase tracking-wider mb-2">Moduly Produkcyjne:</div>
              {[{l:"Smart Camera v11",v:useSmartCamera,s:setUseSmartCamera},{l:"Slow-Mo Ramp 0.45x + Minterpolate",v:useSpeedRamp,s:setUseSpeedRamp},{l:"Zoom-Punch 1.20x + bas",v:useZoomPunch,s:setUseZoomPunch}].map(({l,v,s})=>(
                <label key={l} className="flex items-center justify-between cursor-pointer text-xs font-semibold">
                  <span className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-[#C89B3C]"/>{l}</span>
                  <input type="checkbox" checked={v} onChange={e=>s(e.target.checked)} className="rounded border-[#1E2438] bg-[#121624] text-[#C89B3C]"/>
                </label>
              ))}
            </div>
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#1E2438]">
              <button type="button" onClick={()=>setSelectedClip(null)} className="px-4 py-2 rounded-xl bg-[#1E2438] hover:bg-[#2D3550] text-xs font-bold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors">Anuluj</button>
              <button type="button" disabled={isSubmitting || isAutoDetecting} onClick={handleLaunchRender}
                className="px-5 py-2.5 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-black transition-colors flex items-center gap-2 shadow-lg shadow-[#C89B3C]/20 disabled:opacity-50">
                {isAutoDetecting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>AI dopasowuje okno...</span>
                  </>
                ) : isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Uruchamianie...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current"/>
                    <span>Renderuj Short (9:16)</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}