import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  apiListClips, apiStartPipeline, apiAutoDetectClip, ClipItem, AutoDetectResult,
  apiStartOvernight, apiGetOvernightStatus, apiStopOvernight, OvernightStatusResponse,
  apiGetOvernightCatalog, OvernightCatalogResponse
} from "../lib/api";
import {
  Film, UploadCloud, Play, Search, Sliders, Zap, CheckCircle2,
  AlertCircle, FileVideo, X, RefreshCw, FolderOpen, Wand2, Clock, Settings2,
  ChevronDown, ChevronUp, ArrowRight, Loader2, Moon, Sparkles, Square, Star
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

const GAME_OPTIONS = [
  { id: "lol", label: "League of Legends", icon: "⚔️" },
  { id: "valorant", label: "Valorant", icon: "🎯" },
  { id: "cs2", label: "CS2", icon: "💥" },
  { id: "fortnite", label: "Fortnite", icon: "🏗️" },
  { id: "generic", label: "Inna Gra", icon: "🎮" },
  { id: "product_ad", label: "Reklama / Ad", icon: "📦" },
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
  const [gameType, setGameType] = useState<string>("lol");


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

  // Tryb Nocny (Auto Top 5)
  const mountedRef = useRef<boolean>(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);
  const [overnightTopN, setOvernightTopN] = useState<number>(5);
  const [overnightSkipPub, setOvernightSkipPub] = useState<boolean>(true);
  const [overnightTierFilter, setOvernightTierFilter] = useState<'auto' | 'all' | 'any_kill' | 'double_plus' | 'triple_plus' | 'quadra_plus'>('auto');
  const [overnightOnlyChannelChamp, setOvernightOnlyChannelChamp] = useState<boolean>(true);
  const [catalog, setCatalog] = useState<OvernightCatalogResponse | null>(null);
  const [overnightStatus, setOvernightStatus] = useState<OvernightStatusResponse | null>(null);
  const [overnightErr, setOvernightErr] = useState<string | null>(null);
  const [startingOvernight, setStartingOvernight] = useState<boolean>(false);

  const fetchOvernightStatus = async () => {
    try {
      const st = await apiGetOvernightStatus();
      if (mountedRef.current) setOvernightStatus(st);
    } catch { }
  };

  const fetchCatalog = async (fp?: string) => {
    try {
      const cat = await apiGetOvernightCatalog({
        folder: (fp ?? selectedFolder) || undefined,
        champion_name: overnightOnlyChannelChamp ? (champion || "Katarina") : undefined,
        skip_published: overnightSkipPub,
      });
      if (mountedRef.current) setCatalog(cat);
    } catch { }
  };

  useEffect(() => { fetchOvernightStatus(); }, []);

  useEffect(() => {
    fetchCatalog();
  }, [champion, overnightSkipPub, overnightOnlyChannelChamp, selectedFolder]);

  useEffect(() => {
    const active = overnightStatus?.status && ["scanning", "rendering", "evaluating"].includes(overnightStatus.status);
    if (!active) return;
    const timer = setInterval(fetchOvernightStatus, 3000);
    return () => clearInterval(timer);
  }, [overnightStatus?.status]);

  const handleStartOvernight = async () => {
    if (startingOvernight) return;
    setOvernightErr(null);
    setStartingOvernight(true);
    try {
      await apiStartOvernight({
        folder: selectedFolder || undefined,
        top_n: overnightTopN,
        skip_published: overnightSkipPub,
        champion_name: champion || "Katarina",
        rank: "Master",
        use_local_ai: true,
        tier_filter: overnightTierFilter,
        only_channel_champion: overnightOnlyChannelChamp,
      });
      await fetchOvernightStatus();
    } catch (err: any) {
      if (mountedRef.current) {
        setOvernightErr(err.response?.data?.detail || err.message || "Nie udało się uruchomić trybu nocnego");
      }
    } finally {
      if (mountedRef.current) setStartingOvernight(false);
    }
  };

  const handleStopOvernight = async () => {
    try {
      await apiStopOvernight();
      await fetchOvernightStatus();
    } catch { }
  };

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
    } catch (e: any) {
      console.warn("[AutoDetect] Error during auto-detect:", e);
    }
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
        hook_text: detected?.hook_text ?? "INSANE OUTPLAY!",
        output_filename: outFile,
        use_speed_ramp: true,
        use_zoom_punch: true,
        use_smart_camera: true,
        combat_segments: (detected?.action_type === "solo_bolo") ? null : (detected?.combat_segments ?? null),
        game_type: gameType,
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
    if (v === 'solo_bolo') {
      setCombatSegments(null);
    }
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
        combat_segments: actionType === 'solo_bolo' ? null : combatSegments,
        game_type: gameType,
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
    `flex items-center gap-1 px-2.5 py-1 rounded-lg border transition-all ${active ? (pulse ? "bg-blue-500/15 border-blue-500/40 text-blue-400 animate-pulse" : "bg-[#C8FF3A]/15 border-[#C8FF3A]/40 text-[#C8FF3A]") : "bg-[#0E0F11] border-[#272A2F] text-[#686E78]"}`;

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#050505] p-6 lg:p-8 space-y-6 text-[#FFFFFF]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#272A2F]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#FFFFFF] flex items-center gap-2.5">
            <Film className="w-6 h-6 text-[#C8FF3A]" />Studio Klipow
          </h1>
          <p className="text-xs text-[#A0A7B1] mt-1">Wrzuc klip — AI robi reszte automatycznie. Opcje reczne dostepne ponizej.</p>
        </div>
        <button onClick={() => fetchClips()} disabled={loading}
          className="flex items-center gap-1.5 px-3.5 py-2 fk-cut-sm bg-[#0E0F11] hover:bg-[#17191C] border border-[#272A2F] text-xs font-semibold text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-[#C8FF3A]" : ""}`} />Odswiez
        </button>
      </div>

      {/* STREFA 1: AUTO-PIPELINE */}
      <div className="p-5 fk-cut fk-cut bg-[#0E0F11] border-2 border-[#C8FF3A]/50 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#C8FF3A]/15 border border-[#C8FF3A]/40 flex items-center justify-center">
              <Zap className="w-4 h-4 text-[#C8FF3A]" />
            </div>
            <div>
              <div className="text-sm font-black text-[#FFFFFF] flex items-center gap-2">
                TRYB AUTOMATYCZNY
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#2ECC71]/15 text-[#2ECC71] border border-[#2ECC71]/30 font-bold">ZALECANY</span>
              </div>
              <div className="text-[11px] text-[#A0A7B1]">Wrzuc klip → AI analizuje → Short gotowy automatycznie</div>
            </div>
          </div>
          {autoStage !== "idle" && (
            <button onClick={resetAuto} className="p-1.5 rounded-lg bg-[#272A2F] hover:bg-[#272A2F] text-[#A0A7B1] hover:text-white transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 text-[11px] font-semibold flex-wrap">
          <div className={autoStepCls(autoStage !== "idle", false)}><UploadCloud className="w-3.5 h-3.5" />Wrzuc klip</div>
          <ArrowRight className="w-3 h-3 text-[#686E78] flex-shrink-0" />
          <div className={autoStepCls(["detecting","launching","done"].includes(autoStage), autoStage==="detecting")}><Wand2 className="w-3.5 h-3.5" />AI analizuje</div>
          <ArrowRight className="w-3 h-3 text-[#686E78] flex-shrink-0" />
          <div className={autoStepCls(["launching","done"].includes(autoStage), autoStage==="launching")}><Zap className="w-3.5 h-3.5" />Short gotowy!</div>
        </div>

        {autoStage === "idle" && (
          <div onDragOver={e => e.preventDefault()} onDrop={handleFileDrop}
            onClick={() => fileInputRef.current?.click()}
            className="p-8 fk-cut-sm border-2 border-dashed border-[#C8FF3A]/40 hover:border-[#C8FF3A] bg-[#050505]/60 hover:bg-[#0E0F11]/60 transition-all cursor-pointer flex flex-col items-center justify-center text-center group">
            <input ref={fileInputRef} type="file" accept="video/mp4,video/mkv,video/avi,video/quicktime"
              onChange={e => {
                const f = e.target.files?.[0]; if (!f) return;
                const fp = (f as any).path || f.name;
                setAutoClip({ filename: f.name, path: fp, size_mb: Math.round(f.size/1048576), modified: Date.now()/1000 });
                setAutoStage("selected"); setAutoResult(null); setAutoError(null);
              }} className="hidden" />
            <div className="w-14 h-14 fk-cut bg-[#C8FF3A]/10 border border-[#C8FF3A]/30 flex items-center justify-center text-[#C8FF3A] group-hover:scale-110 transition-transform mb-3">
              <UploadCloud className="w-7 h-7" />
            </div>
            <div className="text-base font-bold text-[#FFFFFF] group-hover:text-[#C8FF3A] transition-colors">Przeciagnij klip tutaj lub kliknij</div>
            <div className="text-xs text-[#A0A7B1] mt-1">MP4 / MKV / AVI — AI automatycznie wykryje frag i uruchomi render</div>
          </div>
        )}

        {autoClip && autoStage !== "idle" && (
          <div className="p-3.5 fk-cut-sm bg-[#050505] border border-[#C8FF3A]/30 space-y-2">
            <div className="flex items-center gap-2">
              <FileVideo className="w-4 h-4 text-[#C8FF3A] flex-shrink-0" />
              <span className="text-xs font-bold text-[#FFFFFF] truncate flex-1">{autoClip.filename}</span>
              <span className="text-[10px] text-[#A0A7B1]">{autoClip.size_mb} MB</span>
            </div>
            {autoResult && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#C8FF3A]/15 border border-[#C8FF3A]/40 text-[#C8FF3A] font-bold">
                  {autoResult.action_type?.toUpperCase() || "OUTPLAY"} wykryty
                </span>
                <span className="text-[10px] text-[#A0A7B1]">
                  {autoResult.clip_start?.toFixed(1)}s – {autoResult.clip_end?.toFixed(1)}s
                </span>
                {autoResult.confidence && <span className="text-[10px] text-emerald-400">{autoResult.confidence}</span>}
              </div>
            )}
            {(autoStage === "detecting" || autoStage === "launching") && (
              <div className="text-[11px] text-[#A0A7B1] flex items-center gap-1.5">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[#C8FF3A]" />{stageMsg[autoStage]}
              </div>
            )}
            {autoStage === "done" && <div className="text-[11px] text-emerald-400 flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5" />{stageMsg["done"]}</div>}
            {autoStage === "error" && autoError && <div className="text-xs text-red-400 flex items-center gap-1.5"><AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />{autoError}</div>}
          </div>
        )}

        {(autoStage === "selected" || autoStage === "error") && autoClip && (
          <button onClick={() => handleAutoLaunch(autoClip)}
            className="w-full py-3.5 fk-cut-sm fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] font-black text-sm flex items-center justify-center gap-2.5 transition-all">
            <Zap className="w-5 h-5" />Uruchom AUTO-Pipeline
          </button>
        )}
      </div>

      {/* STREFA 1B: TRYB NOCNY (AUTO TOP 5 SYNAPSY, ZERO UPLOADU) */}
      {(() => {
        const isOnRunning = Boolean(overnightStatus?.status && ["scanning", "rendering", "evaluating"].includes(overnightStatus.status));
        const isOnDone = overnightStatus?.status === "done";
        return (
          <div className="p-5 fk-cut bg-[#0E0F11] border border-indigo-400/35 space-y-3.5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-indigo-500/15 border border-indigo-400/40 flex items-center justify-center flex-shrink-0">
                  <Moon className="w-4 h-4 text-indigo-300" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-black text-[#FFFFFF] flex items-center gap-2 flex-wrap">
                    OPCJA NOCNA — SKAN CAŁEGO FOLDERU
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-200 border border-indigo-400/35 font-bold">ZERO AUTO-UPLOADU</span>
                  </div>
                  <div className="text-[11px] text-[#A0A7B1] break-words">
                    Skanuje <span className="text-[#FFFFFF] font-semibold">{selectedFolder || "Outplayed + Medal"}</span>, odrzuca przeciętne klipy, montuje Top {overnightTopN} i rano daje rekomendację #1 Synapsy.
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap flex-shrink-0">
                <select
                  value={overnightTierFilter}
                  disabled={isOnRunning}
                  onChange={e => setOvernightTierFilter(e.target.value as any)}
                  className="px-2.5 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] focus:outline-none focus:border-indigo-400">
                  <option value="auto">Auto (Multikille jeśli są)</option>
                  <option value="double_plus">Double Kill+</option>
                  <option value="triple_plus">Triple Kill+</option>
                  <option value="quadra_plus">Quadra Kill+</option>
                  <option value="any_kill">Wszystkie Kille (bez asyst)</option>
                  <option value="all">Wszystkie klipy</option>
                </select>
                <select
                  value={overnightTopN}
                  disabled={isOnRunning}
                  onChange={e => setOvernightTopN(Number(e.target.value))}
                  className="px-2.5 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] focus:outline-none focus:border-indigo-400">
                  <option value={3}>Top 3 shorty</option>
                  <option value={5}>Top 5 shortów</option>
                </select>
                <label className="flex items-center gap-1.5 text-[11px] text-[#A0A7B1] px-2 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] cursor-pointer select-none">
                  <input type="checkbox" checked={overnightOnlyChannelChamp} disabled={isOnRunning} onChange={e => setOvernightOnlyChannelChamp(e.target.checked)} className="accent-indigo-400" />
                  Tylko {champion || "Katarina"}
                </label>
                <label className="flex items-center gap-1.5 text-[11px] text-[#A0A7B1] px-2 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] cursor-pointer select-none">
                  <input type="checkbox" checked={overnightSkipPub} disabled={isOnRunning} onChange={e => setOvernightSkipPub(e.target.checked)} className="accent-indigo-400" />
                  Pomiń opublikowane
                </label>
                {!isOnRunning ? (
                  <button onClick={handleStartOvernight}
                    disabled={startingOvernight}
                    className="px-4 py-2 fk-cut-sm bg-indigo-500 hover:bg-indigo-400 disabled:opacity-50 text-white font-black text-xs flex items-center gap-1.5 transition-colors">
                    <Sparkles className="w-3.5 h-3.5" />{startingOvernight ? "Uruchamiam..." : `Zostaw na noc (Montuj ${overnightTopN})`}
                  </button>
                ) : (
                  <button onClick={handleStopOvernight}
                    className="px-4 py-2 fk-cut-sm bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 text-red-300 font-bold text-xs flex items-center gap-1.5 transition-colors">
                    <Square className="w-3.5 h-3.5" />Zatrzymaj
                  </button>
                )}
              </div>
            </div>

            {catalog && (
              <div className="p-2.5 rounded-lg bg-[#050505] border border-[#272A2F] flex items-center gap-2 flex-wrap text-[11px]">
                <span className="font-bold text-indigo-200 mr-1">Katalog Riot Outplayed ({catalog.matches_count} meczów, {catalog.total_clips} klipów):</span>
                {(catalog.tier_counts?.pentakill ?? 0) > 0 && (
                  <span className="px-2 py-0.5 rounded bg-red-500/20 border border-red-500/40 text-red-300 font-bold">PENTA: {catalog.tier_counts.pentakill}</span>
                )}
                <span className="px-2 py-0.5 rounded bg-purple-500/20 border border-purple-500/40 text-purple-200 font-bold">QUADRA: {catalog.tier_counts?.quadrakill ?? 0}</span>
                <span className="px-2 py-0.5 rounded bg-[#C8FF3A]/15 border border-[#C8FF3A]/40 text-[#C8FF3A] font-bold">TRIPLE: {catalog.tier_counts?.triple ?? 0}</span>
                <span className="px-2 py-0.5 rounded bg-sky-500/15 border border-sky-500/40 text-sky-300 font-bold">DOUBLE: {catalog.tier_counts?.double ?? 0}</span>
                <span className="px-2 py-0.5 rounded bg-[#17191C] border border-[#272A2F] text-[#A0A7B1]">1-KILL: {catalog.tier_counts?.single_kill ?? 0}</span>
                <span className="px-2 py-0.5 rounded bg-[#17191C] border border-[#272A2F] text-[#686E78]">ASYSTY: {catalog.tier_counts?.assist_only ?? 0}</span>
                {catalog.favorites_count > 0 && (
                  <span className="px-2 py-0.5 rounded bg-amber-400/20 border border-amber-400/40 text-amber-300 font-bold flex items-center gap-1">
                    <Star className="w-3 h-3 fill-current" />Ulubione: {catalog.favorites_count}
                  </span>
                )}
              </div>
            )}

            {overnightErr && (
              <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-300 break-words">{overnightErr}</div>
            )}

            {overnightStatus && overnightStatus.status !== "idle" && (
              <div className="p-3 rounded-lg bg-[#050505] border border-[#272A2F] space-y-2">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-bold text-indigo-200 flex items-center gap-1.5 min-w-0 truncate">
                    {isOnRunning && <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-300 flex-shrink-0" />}
                    <span className="truncate">{overnightStatus.phase}</span>
                  </span>
                  <span className="font-mono text-[#C8FF3A] font-bold flex-shrink-0">{overnightStatus.progress}%</span>
                </div>
                <div className="w-full h-1.5 bg-[#17191C] rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-400 transition-all duration-300" style={{ width: `${Math.min(100, Math.max(2, overnightStatus.progress || 0))}%` }} />
                </div>
                <div className="flex items-center gap-3 text-[11px] text-[#A0A7B1] flex-wrap">
                  <span>Skan: {overnightStatus.scanned_clips}/{overnightStatus.total_clips}</span>
                  <span>Pominięto opubl.: {overnightStatus.skipped_published}</span>
                  <span className="text-emerald-400">Mocne: {overnightStatus.qualified_count}</span>
                  <span className="text-amber-300">Odrzucone przeciętne: {overnightStatus.rejected_count}</span>
                  <span className="text-[#C8FF3A]">Zmontowano: {overnightStatus.rendered_count}/{overnightStatus.selected_count || overnightTopN}</span>
                </div>
                {overnightStatus.error && (
                  <div className="text-xs text-red-400 break-words">{overnightStatus.error}</div>
                )}
                {isOnDone && (
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-1 border-t border-white/10">
                    <div className="text-xs text-emerald-300 break-words flex-1 min-w-0">{overnightStatus.summary_pl}</div>
                    <button onClick={() => navigate("/outputs")}
                      className="px-3.5 py-1.5 rounded-lg bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] font-black text-xs flex items-center gap-1.5 flex-shrink-0">
                      Otwórz Top {overnightStatus.rendered_count || overnightTopN} i rekomendację Synapsy <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })()}

      {/* STREFA 2: LISTA KLIPOW */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2.5 flex-wrap">
            <div className="text-xs font-bold uppercase tracking-wider text-[#A0A7B1] flex items-center gap-2">
              <Film className="w-4 h-4 text-[#C8FF3A]" />Nagrania z Outplayed ({filteredClips.length})
            </div>
            <button onClick={handlePickFolder} className="flex items-center gap-1 px-2 py-1 rounded-lg bg-[#0E0F11] hover:bg-[#272A2F] border border-[#272A2F] text-[10px] text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors">
              <FolderOpen className="w-3 h-3 text-[#C8FF3A]" />{selectedFolder ? "Zmien folder" : "Wybierz folder"}
            </button>
            {selectedFolder && <button onClick={() => { setSelectedFolder(""); fetchClips(""); }} className="text-[10px] text-[#A0A7B1] hover:text-[#FFFFFF] underline">Domyslny</button>}
          </div>
          <div className="relative w-56">
            <Search className="w-3.5 h-3.5 text-[#A0A7B1] absolute left-3 top-1/2 -translate-y-1/2" />
            <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Filtruj..."
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]" />
          </div>
        </div>
        {loading ? (
          <div className="py-10 flex flex-col items-center justify-center text-[#A0A7B1]">
            <RefreshCw className="w-6 h-6 animate-spin text-[#C8FF3A] mb-2" /><span className="text-xs">Skanowanie nagran...</span>
          </div>
        ) : filteredClips.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {filteredClips.map(clip => (
              <div key={clip.filename} className="p-3.5 fk-cut-sm bg-[#0E0F11] border border-[#272A2F] hover:border-[#C8FF3A]/30 transition-all flex flex-col justify-between gap-3 group">
                <div className="flex items-start gap-2.5">
                  <div className="p-2 rounded-lg bg-[#17191C] text-[#C8FF3A] border border-[#272A2F] flex-shrink-0"><FileVideo className="w-4 h-4" /></div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-bold text-[#FFFFFF] truncate group-hover:text-[#C8FF3A] transition-colors" title={clip.filename}>{clip.filename}</div>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      {clip.event_tier && (
                        <span className={`text-[9px] px-1.5 py-0.5 rounded font-black uppercase ${
                          clip.event_tier === "pentakill" || clip.event_tier === "quadrakill"
                            ? "bg-purple-500/25 text-purple-200 border border-purple-500/45"
                            : clip.event_tier === "triple"
                            ? "bg-[#C8FF3A]/20 text-[#C8FF3A] border border-[#C8FF3A]/45"
                            : clip.event_tier === "double"
                            ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                            : clip.event_tier === "assist_only"
                            ? "bg-[#17191C] text-[#686E78] border border-[#272A2F]"
                            : "bg-[#17191C] text-[#A0A7B1] border border-[#272A2F]"
                        }`}>{clip.event_tier}</span>
                      )}
                      {clip.champion && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-indigo-500/15 border border-indigo-400/30 text-indigo-200 font-bold">{clip.champion}</span>
                      )}
                      {clip.is_favorite && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-400/20 border border-amber-400/40 text-amber-300 font-bold flex items-center gap-0.5">
                          <Star className="w-2.5 h-2.5 fill-current" />Ulubiony
                        </span>
                      )}
                      {clip.already_published && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-bold">Opublikowano</span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      <span className="text-[10px] text-[#A0A7B1]">{clip.size_mb} MB</span>
                      <span className="text-[10px] text-[#686E78]">•</span>
                      <span className="text-[10px] text-[#A0A7B1]">{clip.match_date || new Date(clip.modified * 1000).toLocaleDateString("pl-PL")}</span>
                      {clip.match_kda && (
                        <>
                          <span className="text-[10px] text-[#686E78]">•</span>
                          <span className="text-[10px] font-mono text-[#686E78]">KDA {clip.match_kda}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                  <button onClick={() => handleAutoLaunch(clip)}
                    className="flex-1 text-xs bg-[#C8FF3A] hover:bg-[#C8FF3A] text-[#050505] font-black px-3 py-1.5 rounded-lg transition-colors flex items-center justify-center gap-1.5">
                    <Zap className="w-3.5 h-3.5" />Auto-Pipeline
                  </button>
                  <button onClick={() => openManualModal(clip)}
                    className="px-2.5 py-1.5 text-[10px] text-[#A0A7B1] hover:text-[#FFFFFF] font-semibold rounded-lg bg-[#272A2F] hover:bg-[#272A2F] transition-colors flex items-center gap-1">
                    <Settings2 className="w-3 h-3" />Recznie
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-10 text-center text-[#686E78] text-xs">Brak plikow. Wgraj klip przez strefe Auto lub wybierz folder.</div>
        )}
      </div>

      {/* STREFA 3: ZAAWANSOWANE */}
      <div className="fk-cut bg-[#0E0F11] border border-[#272A2F] overflow-hidden">
        <button onClick={() => setAdvancedOpen(p => !p)}
          className="w-full px-5 py-3.5 flex items-center justify-between text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
            <Settings2 className="w-3.5 h-3.5 text-[#C8FF3A]" />Konfiguracja Zaawansowana — Pelna Kontrola
          </div>
          {advancedOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {advancedOpen && (
          <div className="px-5 pb-5 space-y-3 border-t border-[#272A2F] pt-4">
            <p className="text-[11px] text-[#686E78]">Przeciagnij plik lub kliknij aby rcznie skonfigurowac timing, champion i efekty przed renderem.</p>
            <div onDragOver={e => e.preventDefault()} onDrop={e => {
                e.preventDefault(); const f = e.dataTransfer.files?.[0];
                if (f) openManualModal({ filename: f.name, path: (f as any).path || f.name, size_mb: Math.round(f.size/1048576), modified: Date.now()/1000 });
              }}
              onClick={() => {
                const inp = document.createElement("input"); inp.type = "file"; inp.accept = "video/*";
                inp.onchange = (e: any) => { const f = e.target.files?.[0]; if (f) openManualModal({ filename: f.name, path: (f as any).path || f.name, size_mb: Math.round(f.size/1048576), modified: Date.now()/1000 }); };
                inp.click();
              }}
              className="p-6 fk-cut-sm border-2 border-dashed border-[#272A2F] hover:border-[#C8FF3A]/40 bg-[#050505]/40 cursor-pointer flex items-center justify-center gap-3 text-xs text-[#686E78] hover:text-[#A0A7B1] transition-all">
              <Sliders className="w-4 h-4" />Przeciagnij klip lub kliknij — otworzy konfigurator z pelna kontrola ciecia i efektow
            </div>
          </div>
        )}
      </div>

      {/* MODAL RECZNY */}
      {selectedClip && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#0E0F11] border border-[#C8FF3A]/40 fk-cut w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 space-y-5 text-[#FFFFFF]">
            <div className="flex items-start justify-between pb-3 border-b border-[#272A2F]">
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-[#C8FF3A] flex items-center gap-1.5">
                  <Settings2 className="w-4 h-4" />Konfiguracja Reczna — Pelna Kontrola
                </div>
                <div className="text-sm font-bold text-[#FFFFFF] mt-1 truncate max-w-md">{selectedClip.filename}</div>
              </div>
              <button onClick={() => setSelectedClip(null)} className="p-1.5 rounded-lg bg-[#272A2F] hover:bg-[#272A2F] text-[#A0A7B1] hover:text-white transition-colors"><X className="w-4 h-4" /></button>
            </div>
            {submitError && <div className="p-3 fk-cut-sm bg-[#FF5C5C]/15 border border-[#FF5C5C]/30 text-[#FF5C5C] text-xs flex items-center gap-2"><AlertCircle className="w-4 h-4 flex-shrink-0" />{submitError}</div>}
            <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="text-xs font-bold text-[#A0A7B1] uppercase tracking-wider flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-[#C8FF3A]" />Czas Klipu:</div>
                <div className="flex items-center bg-[#0E0F11] p-1 fk-cut-sm border border-[#272A2F]">
                  <button type="button" onClick={() => setTimingMode("auto")} className={`flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-bold transition-colors ${timingMode==="auto"?"bg-[#C8FF3A] text-[#050505]":"text-[#A0A7B1] hover:text-[#FFFFFF]"}`}><Wand2 className="w-3 h-3"/>AI Auto-Trim</button>
                  <button type="button" onClick={() => setTimingMode("manual")} className={`flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-bold transition-colors ${timingMode==="manual"?"bg-[#272A2F] text-[#FFFFFF] border border-[#C8FF3A]/40":"text-[#A0A7B1] hover:text-[#FFFFFF]"}`}><Settings2 className="w-3 h-3"/>Reczny</button>
                </div>
              </div>
              {timingMode==="auto" && (
                <div className="p-3 rounded-lg bg-[#0E0F11] border border-[#C8FF3A]/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div>
                    <span className="text-[11px] font-bold text-[#2ECC71] flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5"/>{isAutoDetecting?"Analizowanie...":autoDetectResult?.confidence||"AI optymalne okno"}</span>
                    <div className="text-[11px] text-[#A0A7B1] mt-0.5">Start: <b className="font-mono text-[#FFFFFF]">{clipStart}s</b> Koniec: <b className="font-mono text-[#FFFFFF]">{clipEnd}s</b> Peak: <b className="font-mono text-[#C8FF3A]">{peakMoment}s</b></div>
                    {combatSegments && combatSegments.length > 1 && (
                      <div className="mt-1.5 flex items-center gap-1.5 px-2 py-1 rounded-md bg-blue-500/10 border border-blue-500/30">
                        <span className="text-[10px] font-bold text-blue-400">JUMP-CUT AKTYWNY</span>
                        <span className="text-[10px] text-[#A0A7B1]">— {combatSegments.length} segmenty walki | wycięto martwy bieg</span>
                      </div>
                    )}
                  </div>
                  <button type="button" onClick={() => runAutoDetect(selectedClip.path||selectedClip.filename)} disabled={isAutoDetecting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#272A2F] hover:bg-[#272A2F] text-xs font-bold text-[#C8FF3A] transition-colors shrink-0">
                    <RefreshCw className={`w-3 h-3 ${isAutoDetecting?"animate-spin":""}`}/>{isAutoDetecting?"Skanuje...":"Przelicz AI"}
                  </button>
                </div>
              )}
              <div className="grid grid-cols-3 gap-3 pt-1">
                {[{l:"Start (s)",v:clipStart,s:setClipStart},{l:"Koniec (s)",v:clipEnd,s:setClipEnd},{l:"Peak (s)",v:peakMoment,s:setPeakMoment}].map(({l,v,s})=>(
                  <div key={l}>
                    <label className="text-[11px] font-bold text-[#A0A7B1] block mb-1">{l}</label>
                    <div className="flex gap-1 mb-1">{[-1,1].map(d=><button key={d} type="button" onClick={()=>s((x:number)=>Math.max(0,+(x+d).toFixed(1)))} className="px-1.5 py-0.5 bg-[#0E0F11] hover:bg-[#272A2F] text-[#A0A7B1] rounded border border-[#272A2F] text-[10px]">{d>0?"+1s":"-1s"}</button>)}</div>
                    <input type="number" step="0.5" value={v} onChange={e=>s(parseFloat(e.target.value)||0)} className="w-full px-3 py-1.5 rounded-lg bg-[#0E0F11] border border-[#272A2F] text-xs font-mono text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]"/>
                  </div>
                ))}
              </div>
            </div>

            {/* Wybor Gry / Profilu */}
            <div className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-2">

              <label className="text-xs font-bold text-[#A0A7B1] uppercase tracking-wider block">Gra / Profil Treści:</label>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                {GAME_OPTIONS.map(g => (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => setGameType(g.id)}
                    className={`py-2 px-2 rounded-lg border text-center transition-all text-xs font-bold flex flex-col items-center gap-1 ${
                      gameType === g.id
                        ? "bg-[#C8FF3A]/20 border-[#C8FF3A] text-[#FFFFFF]"
                        : "bg-[#0E0F11] border-[#272A2F] text-[#A0A7B1] hover:border-[#C8FF3A]/40 hover:text-white"
                    }`}
                  >
                    <span className="text-base">{g.icon}</span>
                    <span className="text-[10px] truncate w-full">{g.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

              <div>
                <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Bohater:</label>
                <select value={champion} onChange={e=>setChampion(e.target.value)} className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]">
                  {CHAMPIONS.map(c=><option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Typ Akcji:</label>
                <select value={actionType} onChange={e=>handleActionChange(e.target.value)} className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#C8FF3A] focus:outline-none focus:border-[#C8FF3A]">
                  {ACTION_TYPES.map(a=><option key={a.id} value={a.id}>{a.label}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Hook Text:</label>
                <input type="text" value={hookText} onChange={e=>setHookText(e.target.value)} className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]"/>
              </div>
            </div>
            <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-2.5">
              <div className="text-xs font-bold text-[#A0A7B1] uppercase tracking-wider mb-2">Moduly Produkcyjne:</div>
              {[{l:"Smart Camera v11",v:useSmartCamera,s:setUseSmartCamera},{l:"Slow-Mo Ramp 0.45x + Minterpolate",v:useSpeedRamp,s:setUseSpeedRamp},{l:"Zoom-Punch 1.20x + bas",v:useZoomPunch,s:setUseZoomPunch}].map(({l,v,s})=>(
                <label key={l} className="flex items-center justify-between cursor-pointer text-xs font-semibold">
                  <span className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-[#C8FF3A]"/>{l}</span>
                  <input type="checkbox" checked={v} onChange={e=>s(e.target.checked)} className="rounded border-[#272A2F] bg-[#0E0F11] text-[#C8FF3A]"/>
                </label>
              ))}
            </div>
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#272A2F]">
              <button type="button" onClick={()=>setSelectedClip(null)} className="px-4 py-2 fk-cut-sm bg-[#272A2F] hover:bg-[#272A2F] text-xs font-bold text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors">Anuluj</button>
              <button type="button" disabled={isSubmitting || isAutoDetecting} onClick={handleLaunchRender}
                className="px-5 py-2.5 fk-cut-sm bg-[#C8FF3A] hover:bg-[#C8FF3A] text-[#050505] text-xs font-black transition-colors flex items-center gap-2 disabled:opacity-50">
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