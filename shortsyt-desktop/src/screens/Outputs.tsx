import React, { useEffect, useState } from "react";
import {
  apiListOutputs, OutputItem, apiGetOutputUrl, apiListThumbnails,
  ThumbnailItem, apiUploadToYt, apiGetNextPeakSlot, PeakSlotInfo,
  apiGetOutputMetadata, apiSaveOutputMetadata, OutputMetadata, apiStartPipeline
} from "../lib/api";
import {
  Video, RefreshCw, Upload, Play, Film, FolderOpen, Image as ImageIcon,
  Copy, Check, X, Loader, Clock, Zap, Edit3, Save, RotateCcw, AlertTriangle,
  Info, Sliders, CheckCircle2
} from "lucide-react";
import { useNavigate } from "react-router-dom";

const CHAMPIONS = ["Katarina","Ahri","Zed","Yasuo","Jinx","Thresh","Lee Sin","Vayne","Samira","Akali","Yone","Riven","Kassadin","Evelynn","Master Yi","Darius"];
const ACTION_TYPES = [
  {id:"pentakill",label:"PENTAKILL 🔥"},
  {id:"quadrakill",label:"QUADRAKILL ⚡"},
  {id:"triple",label:"TRIPLE KILL 🎯"},
  {id:"double",label:"DOUBLE KILL 🎯"},
  {id:"outplay",label:"OUTPLAY 🧠"},
  {id:"clutch",label:"CLUTCH 1% HP 💀"},
];

// Which fields require re-render when changed
const RENDER_FIELDS: (keyof OutputMetadata)[] = ["champion_name","action_type","hook_text","clip_start","clip_end","peak_moment","use_speed_ramp","use_zoom_punch","use_smart_camera"];

export default function Outputs() {
  const navigate = useNavigate();
  const [outputs, setOutputs] = useState<OutputItem[]>([]);
  const [thumbnails, setThumbnails] = useState<ThumbnailItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVideoUrl, setSelectedVideoUrl] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  // Upload modal
  const [uploadModal, setUploadModal] = useState<{ filename: string } | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDesc, setUploadDesc] = useState("Watch till the end 🔥\n\n🔔 Subscribe for daily LoL clips!\n👍 Leave a like if you enjoyed!\n\n#Shorts #LeagueOfLegends #LoL #Gaming");
  const [uploadMode, setUploadMode] = useState<"peak"|"now"|"private">("peak");
  const [peakSlot, setPeakSlot] = useState<PeakSlotInfo | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ok:boolean;url?:string;error?:string;scheduledFor?:string}|null>(null);

  // Edit modal
  const [editModal, setEditModal] = useState<string | null>(null); // filename
  const [editMeta, setEditMeta] = useState<OutputMetadata | null>(null);
  const [editOriginal, setEditOriginal] = useState<OutputMetadata | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editSaved, setEditSaved] = useState(false);
  const [editRerendering, setEditRerendering] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editSection, setEditSection] = useState<"meta"|"stats"|"render">("meta");

  const fetchOutputs = async () => {
    setLoading(true);
    try {
      const [outData, thumbData, slotData] = await Promise.all([
        apiListOutputs(),
        apiListThumbnails(),
        apiGetNextPeakSlot().catch(() => null),
      ]);
      setOutputs(outData); setThumbnails(thumbData);
      if (slotData) setPeakSlot(slotData);
    } catch { } finally { setLoading(false); }
  };
  useEffect(() => { fetchOutputs(); }, []);

  const handlePlay = async (filename: string) => {
    const url = await apiGetOutputUrl(filename);
    setSelectedVideoUrl(url);
  };

  const findMatchingThumb = (videoFilename: string) => {
    const base = videoFilename.replace(".mp4","").toLowerCase();
    return thumbnails.find(t => t.filename.toLowerCase().includes(base) || t.associated_video.toLowerCase() === videoFilename.toLowerCase());
  };

  const handleOpenFolder = (p: string) => window.electronApp?.showItemInFolder?.(p);
  const handleOpenImage = (p: string) => window.electronApp?.openPath?.(p);
  const handleCopyPath = (p: string) => { navigator.clipboard.writeText(p); setCopiedPath(p); setTimeout(()=>setCopiedPath(null),2000); };

  const openUploadModal = (filename: string) => {
    setUploadTitle("Sick Play! #Shorts #LoL");
    setUploadModal({ filename }); setUploadResult(null);
  };

  const handleUpload = async () => {
    if (!uploadModal) return;
    setUploading(true); setUploadResult(null);
    try {
      let privacy = "public", publishAt: string|undefined, scheduledLabel: string|undefined;
      if (uploadMode==="peak" && peakSlot) { privacy="private"; publishAt=peakSlot.publish_at; scheduledLabel=peakSlot.label; }
      else if (uploadMode==="private") { privacy="private"; }
      const matchThumb = findMatchingThumb(uploadModal.filename);
      const res = await apiUploadToYt(uploadModal.filename, uploadTitle, uploadDesc,
        ["league of legends","lol","shorts","gaming"], privacy,
        "What would you have done here? Rate 1-10! 🔥", matchThumb?.path, publishAt);
      setUploadResult({ ok: true, url: res.url || `https://youtube.com/shorts/${res.video_id}`, scheduledFor: scheduledLabel });
    } catch (e: any) { setUploadResult({ ok: false, error: String(e) }); }
    finally { setUploading(false); }
  };

  // ── EDIT PANEL ─────────────────────────────────────────────────────────────
  const openEditModal = async (filename: string) => {
    setEditModal(filename); setEditLoading(true); setEditError(null);
    setEditSaved(false); setEditSection("meta");
    try {
      const meta = await apiGetOutputMetadata(filename);
      setEditMeta(meta); setEditOriginal(JSON.parse(JSON.stringify(meta)));
    } catch (e: any) { setEditError(String(e)); }
    finally { setEditLoading(false); }
  };

  const hasRenderChanges = () => {
    if (!editMeta || !editOriginal) return false;
    return RENDER_FIELDS.some(k => JSON.stringify(editMeta[k]) !== JSON.stringify(editOriginal[k]));
  };

  const handleSaveMeta = async () => {
    if (!editModal || !editMeta) return;
    setEditSaving(true); setEditError(null);
    try {
      await apiSaveOutputMetadata(editModal, {
        title: editMeta.title,
        description: editMeta.description,
        tags: editMeta.tags,
      });
      setEditOriginal(prev => prev ? { ...prev, title: editMeta.title, description: editMeta.description, tags: editMeta.tags } : prev);
      setEditSaved(true); setTimeout(() => setEditSaved(false), 3000);
    } catch (e: any) { setEditError(String(e)); }
    finally { setEditSaving(false); }
  };

  const handleRerender = async () => {
    if (!editModal || !editMeta) return;
    setEditRerendering(true); setEditError(null);
    try {
      await apiSaveOutputMetadata(editModal, editMeta);
      const outFile = `short_${Date.now()}_rerender.mp4`;
      await apiStartPipeline({
        source_path: editMeta.source_path,
        clip_start: editMeta.clip_start, clip_end: editMeta.clip_end,
        action_type: editMeta.action_type, champion_name: editMeta.champion_name,
        rank: "Master", peak_moment: editMeta.peak_moment, hook_text: editMeta.hook_text,
        output_filename: outFile, use_speed_ramp: editMeta.use_speed_ramp,
        use_zoom_punch: editMeta.use_zoom_punch, use_smart_camera: editMeta.use_smart_camera,
      });
      setEditModal(null); navigate("/render");
    } catch (e: any) { setEditError(String(e)); }
    finally { setEditRerendering(false); }
  };

  const sectionTab = (id: "meta"|"stats"|"render", label: string, icon: React.ReactNode) => (
    <button onClick={() => setEditSection(id)}
      className={`flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg transition-colors ${editSection===id ? "bg-[#C89B3C]/15 text-[#C89B3C] border border-[#C89B3C]/40" : "text-[#8B8FA8] hover:text-[#E4D6B5]"}`}>
      {icon}{label}
    </button>
  );

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2438]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
            <Video className="w-6 h-6 text-[#C89B3C]" />Biblioteka Gotowych Shortów
          </h1>
          <p className="text-xs text-[#8B8FA8] mt-1">Wyrenderowane wideo 9:16 — edytuj statystyki, modyfikuj parametry lub wgraj na YouTube</p>
        </div>
        <button onClick={fetchOutputs} disabled={loading}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#121624] hover:bg-[#1A1E30] border border-[#1E2438] text-xs font-semibold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${loading?"animate-spin text-[#C89B3C]":""}`} />Odśwież listę
        </button>
      </div>

      {/* UPLOAD MODAL */}
      {uploadModal && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-[#121624] border border-[#C89B3C]/40 rounded-2xl p-6 w-full max-w-lg space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-[#E4D6B5] flex items-center gap-2"><Upload className="w-4 h-4 text-[#C89B3C]"/>Upload na YouTube</h2>
              <button onClick={() => setUploadModal(null)} className="text-[#8B8FA8] hover:text-[#E4D6B5]"><X className="w-4 h-4"/></button>
            </div>
            <div className="text-xs text-[#8B8FA8] bg-[#0A0E1A] rounded-lg px-3 py-2 font-mono truncate">{uploadModal.filename}</div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-[#C89B3C]">Tytuł</label>
              <input value={uploadTitle} onChange={e=>setUploadTitle(e.target.value)} className="w-full bg-[#0A0E1A] border border-[#1E2438] rounded-lg px-3 py-2 text-sm text-[#E4D6B5] focus:border-[#C89B3C] outline-none" placeholder="Tytuł YouTube..."/>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-[#C89B3C]">Opis</label>
              <textarea value={uploadDesc} onChange={e=>setUploadDesc(e.target.value)} rows={4} className="w-full bg-[#0A0E1A] border border-[#1E2438] rounded-lg px-3 py-2 text-xs text-[#E4D6B5] focus:border-[#C89B3C] outline-none resize-none"/>
            </div>
            <div className="space-y-2 pt-1">
              <label className="text-xs font-semibold text-[#8B8FA8] flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-[#C89B3C]"/>Tryb Publikacji:</label>
              <div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={()=>setUploadMode("peak")} className={`p-2.5 rounded-xl border text-left transition-all ${uploadMode==="peak"?"bg-[#C89B3C]/15 border-[#C89B3C] text-[#E4D6B5]":"bg-[#0A0E1A] border-[#1E2438] text-[#8B8FA8] hover:border-[#C89B3C]/40"}`}>
                  <div className="flex items-center justify-between"><span className="text-xs font-bold text-[#C89B3C] flex items-center gap-1"><Zap className="w-3 h-3"/>AI Peak Slot</span><span className="text-[9px] bg-[#2ECC71]/20 text-[#2ECC71] px-1 rounded font-bold">TOP</span></div>
                  <div className="text-[11px] font-semibold text-[#E4D6B5] mt-1 truncate">{peakSlot?.label||"Dziś o 18:30 CET"}</div>
                </button>
                <button type="button" onClick={()=>setUploadMode("now")} className={`p-2.5 rounded-xl border text-left transition-all ${uploadMode==="now"?"bg-[#2ECC71]/15 border-[#2ECC71] text-[#E4D6B5]":"bg-[#0A0E1A] border-[#1E2438] text-[#8B8FA8] hover:border-[#2ECC71]/40"}`}>
                  <div className="text-xs font-bold text-[#2ECC71]">Opublikuj Teraz</div>
                  <div className="text-[11px] font-semibold text-[#E4D6B5] mt-1">Publiczny od razu</div>
                </button>
              </div>
            </div>
            {uploadResult && (
              <div className={`rounded-lg px-3 py-2 text-xs font-semibold ${uploadResult.ok?"bg-[#2ECC71]/10 text-[#2ECC71] border border-[#2ECC71]/30":"bg-red-500/10 text-red-400 border border-red-500/30"}`}>
                {uploadResult.ok ? (<div><div>✅ Wgrano na YouTube! <a href={uploadResult.url} target="_blank" rel="noreferrer" className="underline">{uploadResult.url}</a></div>{uploadResult.scheduledFor&&<div className="text-[11px] text-[#C89B3C] mt-0.5">⏰ Zaplanowano na: {uploadResult.scheduledFor}</div>}</div>)
                  : <span>❌ Błąd: {uploadResult.error}</span>}
              </div>
            )}
            <div className="flex gap-3 pt-1">
              <button onClick={()=>setUploadModal(null)} className="flex-1 py-2 rounded-xl border border-[#1E2438] text-xs text-[#8B8FA8] hover:text-[#E4D6B5] font-semibold">Anuluj</button>
              <button onClick={handleUpload} disabled={uploading||!uploadTitle.trim()} className="flex-1 py-2 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] disabled:opacity-50 text-[#0A0E1A] text-xs font-bold flex items-center justify-center gap-1.5">
                {uploading?<Loader className="w-3.5 h-3.5 animate-spin"/>:<Upload className="w-3.5 h-3.5"/>}{uploading?"Wgrywam...":"Wgraj na YouTube"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {editModal && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
          <div className="bg-[#121624] border border-[#C89B3C]/40 rounded-2xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl space-y-5 text-[#E4D6B5]">
            <div className="flex items-start justify-between pb-3 border-b border-[#1E2438]">
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-[#C89B3C] flex items-center gap-1.5">
                  <Edit3 className="w-4 h-4"/>Edytor Shorta
                </div>
                <div className="text-sm font-bold text-[#E4D6B5] mt-1 truncate max-w-md">{editModal}</div>
              </div>
              <button onClick={()=>setEditModal(null)} className="p-1.5 rounded-lg bg-[#1E2438] hover:bg-[#2D3550] text-[#8B8FA8] hover:text-white transition-colors"><X className="w-4 h-4"/></button>
            </div>

            {/* Re-render warning banner */}
            {hasRenderChanges() && (
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5"/>
                <div><b>Zmieniono parametry renderowania</b> — aby zapisać te zmiany, aplikacja wyrenderuje klip ponownie. Kliknij <b>"Zapisz i Re-Renderuj"</b>.</div>
              </div>
            )}

            {editError && <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs">{editError}</div>}

            {/* Section tabs */}
            <div className="flex items-center gap-1 p-1 bg-[#0A0E1A] rounded-xl border border-[#1E2438]">
              {sectionTab("meta", "Metadane YouTube", <Upload className="w-3 h-3"/>)}
              {sectionTab("stats", "Statystyki AI", <Info className="w-3 h-3"/>)}
              {sectionTab("render", "Parametry Renderu", <Sliders className="w-3 h-3"/>)}
            </div>

            {editLoading ? (
              <div className="py-12 flex flex-col items-center justify-center text-[#8B8FA8]">
                <RefreshCw className="w-6 h-6 animate-spin text-[#C89B3C] mb-2"/><span className="text-xs">Ładowanie metadanych...</span>
              </div>
            ) : editMeta && (
              <>
                {/* SECTION: META */}
                {editSection === "meta" && (
                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-[#C89B3C]">Tytuł YouTube Shorts</label>
                      <input value={editMeta.title} onChange={e=>setEditMeta(m=>m?{...m,title:e.target.value}:m)}
                        className="w-full bg-[#0A0E1A] border border-[#1E2438] focus:border-[#C89B3C] rounded-xl px-3 py-2.5 text-sm text-[#E4D6B5] outline-none"
                        placeholder="Tytuł Shorta..."/>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-[#C89B3C]">Opis</label>
                      <textarea value={editMeta.description} onChange={e=>setEditMeta(m=>m?{...m,description:e.target.value}:m)}
                        rows={5} className="w-full bg-[#0A0E1A] border border-[#1E2438] focus:border-[#C89B3C] rounded-xl px-3 py-2 text-xs text-[#E4D6B5] outline-none resize-none"/>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-[#C89B3C]">Hashtagi (oddzielone przecinkami)</label>
                      <input value={(editMeta.tags||[]).join(", ")} onChange={e=>setEditMeta(m=>m?{...m,tags:e.target.value.split(",").map(t=>t.trim()).filter(Boolean)}:m)}
                        className="w-full bg-[#0A0E1A] border border-[#1E2438] focus:border-[#C89B3C] rounded-xl px-3 py-2 text-xs text-[#E4D6B5] outline-none"
                        placeholder="league of legends, shorts, lol, outplay..."/>
                    </div>
                    <p className="text-[11px] text-[#50546A]">ℹ️ Zmiany metadanych nie wymagają ponownego renderowania — zostaną natychmiast zapisane i użyte przy uploadzie na YouTube.</p>
                  </div>
                )}

                {/* SECTION: STATS */}
                {editSection === "stats" && (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { label: "Wykryty Typ Fraga", val: editMeta.action_type?.toUpperCase() || "—" },
                        { label: "Confidence AI", val: editMeta.frag_confidence ? `${Math.round(editMeta.frag_confidence * 100)}%` : "—" },
                        { label: "Start Klipu", val: editMeta.clip_start != null ? `${editMeta.clip_start}s` : "—" },
                        { label: "Koniec Klipu", val: editMeta.clip_end != null ? `${editMeta.clip_end}s` : "—" },
                        { label: "Długość", val: (editMeta.clip_end != null && editMeta.clip_start != null) ? `${(editMeta.clip_end - editMeta.clip_start).toFixed(1)}s` : "—" },
                        { label: "Peak Moment", val: editMeta.peak_moment != null ? `${editMeta.peak_moment}s` : "—" },
                        { label: "Bohater", val: editMeta.champion_name || "—" },
                        { label: "Wyrenderowano", val: editMeta.rendered_at ? new Date(editMeta.rendered_at).toLocaleString("pl-PL") : "—" },
                      ].map(({label, val}) => (
                        <div key={label} className="p-3 rounded-xl bg-[#0A0E1A] border border-[#1E2438]">
                          <div className="text-[10px] text-[#8B8FA8] uppercase tracking-wider mb-1">{label}</div>
                          <div className="text-sm font-bold text-[#C89B3C]">{val}</div>
                        </div>
                      ))}
                    </div>
                    <div className="p-3 rounded-xl bg-[#0A0E1A] border border-[#1E2438]">
                      <div className="text-[10px] text-[#8B8FA8] uppercase tracking-wider mb-1">Źródłowy Plik</div>
                      <div className="text-xs font-mono text-[#E4D6B5] break-all">{editMeta.source_path || "—"}</div>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-[#8B8FA8]">
                      <span className="flex items-center gap-1">{editMeta.use_smart_camera?<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400"/>:<X className="w-3.5 h-3.5 text-red-400"/>}Smart Camera</span>
                      <span className="flex items-center gap-1">{editMeta.use_speed_ramp?<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400"/>:<X className="w-3.5 h-3.5 text-red-400"/>}Speed Ramp</span>
                      <span className="flex items-center gap-1">{editMeta.use_zoom_punch?<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400"/>:<X className="w-3.5 h-3.5 text-red-400"/>}Zoom Punch</span>
                    </div>
                  </div>
                )}

                {/* SECTION: RENDER PARAMS */}
                {editSection === "render" && (
                  <div className="space-y-4">
                    <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5"/>
                      Zmiana poniższych parametrów WYMAGA ponownego wyrenderowania klipu (przycisk "Zapisz i Re-Renderuj").
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">Bohater:</label>
                        <select value={editMeta.champion_name} onChange={e=>setEditMeta(m=>m?{...m,champion_name:e.target.value}:m)}
                          className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]">
                          {CHAMPIONS.map(c=><option key={c} value={c}>{c}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">Typ Akcji:</label>
                        <select value={editMeta.action_type} onChange={e=>setEditMeta(m=>m?{...m,action_type:e.target.value}:m)}
                          className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#C89B3C] focus:outline-none focus:border-[#C89B3C]">
                          {ACTION_TYPES.map(a=><option key={a.id} value={a.id}>{a.label}</option>)}
                        </select>
                      </div>
                      <div className="md:col-span-2">
                        <label className="text-xs font-bold text-[#8B8FA8] block mb-1.5">Hook Text (napis na początku):</label>
                        <input value={editMeta.hook_text} onChange={e=>setEditMeta(m=>m?{...m,hook_text:e.target.value}:m)}
                          className="w-full px-3 py-2 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-bold text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"/>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      {[{l:"Start (s)",k:"clip_start"},{l:"Koniec (s)",k:"clip_end"},{l:"Peak (s)",k:"peak_moment"}].map(({l,k})=>(
                        <div key={k}>
                          <label className="text-[11px] font-bold text-[#8B8FA8] block mb-1">{l}</label>
                          <div className="flex gap-1 mb-1">{[-1,1].map(d=><button key={d} type="button" onClick={()=>setEditMeta(m=>m?{...m,[k]:Math.max(0,+((m[k as keyof OutputMetadata] as number)+d).toFixed(1))}:m)} className="px-1.5 py-0.5 bg-[#121624] hover:bg-[#1E2438] text-[#8B8FA8] rounded border border-[#1E2438] text-[10px]">{d>0?"+1s":"-1s"}</button>)}</div>
                          <input type="number" step="0.5" value={editMeta[k as keyof OutputMetadata] as number}
                            onChange={e=>setEditMeta(m=>m?{...m,[k]:parseFloat(e.target.value)||0}:m)}
                            className="w-full px-3 py-1.5 rounded-lg bg-[#121624] border border-[#1E2438] text-xs font-mono text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"/>
                        </div>
                      ))}
                    </div>
                    <div className="p-4 rounded-xl bg-[#0A0E1A] border border-[#1E2438] space-y-2.5">
                      <div className="text-xs font-bold text-[#8B8FA8] uppercase tracking-wider mb-2">Moduły Efektów:</div>
                      {[{l:"Smart Camera (Śledzenie HP)",k:"use_smart_camera"},{l:"Slow-Mo Ramp 0.45x + Minterpolate",k:"use_speed_ramp"},{l:"Zoom-Punch 1.20x + Bass Boost",k:"use_zoom_punch"}].map(({l,k})=>(
                        <label key={k} className="flex items-center justify-between cursor-pointer text-xs font-semibold">
                          <span className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-[#C89B3C]"/>{l}</span>
                          <input type="checkbox" checked={editMeta[k as keyof OutputMetadata] as boolean}
                            onChange={e=>setEditMeta(m=>m?{...m,[k]:e.target.checked}:m)}
                            className="rounded border-[#1E2438] bg-[#121624] text-[#C89B3C]"/>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex items-center justify-between gap-3 pt-3 border-t border-[#1E2438]">
                  <button type="button" onClick={()=>setEditModal(null)} className="px-4 py-2 rounded-xl bg-[#1E2438] hover:bg-[#2D3550] text-xs font-bold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors">Anuluj</button>
                  <div className="flex items-center gap-2">
                    {editSaved && <span className="text-xs text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5"/>Zapisano!</span>}
                    {hasRenderChanges() ? (
                      <button type="button" disabled={editRerendering} onClick={handleRerender}
                        className="px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black text-xs font-black transition-colors flex items-center gap-2 disabled:opacity-50 shadow-lg shadow-amber-500/20">
                        {editRerendering?<Loader className="w-3.5 h-3.5 animate-spin"/>:<RotateCcw className="w-3.5 h-3.5"/>}
                        {editRerendering?"Re-renderuję...":"Zapisz i Re-Renderuj"}
                      </button>
                    ) : (
                      <button type="button" disabled={editSaving} onClick={handleSaveMeta}
                        className="px-5 py-2.5 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-black transition-colors flex items-center gap-2 disabled:opacity-50 shadow-lg shadow-[#C89B3C]/20">
                        {editSaving?<Loader className="w-3.5 h-3.5 animate-spin"/>:<Save className="w-3.5 h-3.5"/>}
                        {editSaving?"Zapisuję...":"Zapisz Metadane"}
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* VIDEO PREVIEW */}
      {selectedVideoUrl && (
        <div className="p-4 rounded-2xl bg-[#121624] border border-[#C89B3C]/40 flex flex-col items-center">
          <div className="w-full flex justify-between items-center mb-3">
            <span className="text-xs font-bold text-[#E4D6B5]">Odtwarzacz Short (9:16)</span>
            <button onClick={()=>setSelectedVideoUrl(null)} className="text-xs text-[#8B8FA8] hover:text-[#E4D6B5] px-2 py-1 bg-[#1E2438] rounded-md">Zamknij</button>
          </div>
          <video src={selectedVideoUrl} controls autoPlay className="h-[480px] rounded-xl border border-[#1E2438] shadow-2xl bg-black"/>
        </div>
      )}

      {/* LIST */}
      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center text-[#8B8FA8] py-16">
          <RefreshCw className="w-8 h-8 animate-spin text-[#C89B3C] mb-2"/><p className="text-xs">Ładowanie biblioteki...</p>
        </div>
      ) : outputs.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {outputs.map(out => {
            const thumb = findMatchingThumb(out.filename);
            return (
              <div key={out.filename} className="p-4 rounded-xl bg-[#121624] border border-[#1E2438] hover:border-[#C89B3C]/40 transition-all flex flex-col justify-between space-y-4">
                <div className="flex gap-3">
                  <div className="w-20 h-32 rounded-lg bg-[#070A12] border border-[#1E2438] overflow-hidden flex-shrink-0 relative group">
                    {thumb ? (
                      <>
                        <img src={`http://localhost:8765/thumbnails/${encodeURIComponent(thumb.filename)}`} alt="Miniaturka" className="w-full h-full object-cover group-hover:scale-105 transition-transform cursor-pointer" onClick={()=>handleOpenImage(thumb.path)}/>
                        <button onClick={()=>handleOpenImage(thumb.path)} className="absolute bottom-1 right-1 p-1 rounded bg-black/70 hover:bg-[#C89B3C] text-white hover:text-black transition-colors"><ImageIcon className="w-3 h-3"/></button>
                      </>
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center text-[#50546A] p-1 text-center"><ImageIcon className="w-4 h-4 mb-1 opacity-50"/><span className="text-[9px]">Brak miniaturki</span></div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-bold text-[#E4D6B5] truncate" title={out.filename}>
                        <Film className="w-3.5 h-3.5 text-[#2ECC71] flex-shrink-0"/><span className="truncate">{out.filename}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-[11px] text-[#8B8FA8]">
                        <span>{out.size_mb} MB</span><span>•</span><span>{new Date(out.modified*1000).toLocaleDateString("pl-PL")}</span>
                      </div>
                    </div>
                    {thumb && (
                      <div className="flex items-center gap-1.5 pt-2">
                        <button onClick={()=>handleCopyPath(thumb.path)} className="flex items-center gap-1 px-2 py-1 rounded bg-[#1A1E30] hover:bg-[#252A40] text-[10px] text-[#C89B3C] font-semibold transition-colors">
                          {copiedPath===thumb.path?<Check className="w-3 h-3 text-[#2ECC71]"/>:<Copy className="w-3 h-3"/>}{copiedPath===thumb.path?"Skopiowano!":"Kopiuj ścieżkę"}
                        </button>
                        <button onClick={()=>handleOpenFolder(thumb.path)} className="p-1 rounded bg-[#1A1E30] hover:bg-[#252A40] text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors"><FolderOpen className="w-3.5 h-3.5"/></button>
                      </div>
                    )}
                  </div>
                </div>
                <div className="pt-3 border-t border-white/5 flex items-center justify-between gap-2">
                  <button onClick={()=>handlePlay(out.filename)} className="text-xs bg-[#1E2438] hover:bg-[#2A2D40] text-[#E4D6B5] font-semibold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5">
                    <Play className="w-3.5 h-3.5 fill-current"/>Podgląd
                  </button>
                  <div className="flex items-center gap-2">
                    <button onClick={()=>openEditModal(out.filename)} className="text-xs bg-[#1E2438] hover:bg-[#2A2D40] text-[#C89B3C] hover:text-[#E4D6B5] font-bold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 border border-[#C89B3C]/30">
                      <Edit3 className="w-3.5 h-3.5"/>Edytuj
                    </button>
                    <button onClick={()=>openUploadModal(out.filename)} className="text-xs bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] font-bold px-3.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 shadow-md shadow-[#C89B3C]/10">
                      <Upload className="w-3.5 h-3.5"/>YouTube
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-[#50546A] py-16">
          <Video className="w-10 h-10 mb-2 opacity-40"/><p className="text-sm font-semibold">Brak wyrenderowanych filmów</p>
          <p className="text-xs mt-1 opacity-70">Uruchom pipeline renderowania przez Studio Klipów.</p>
        </div>
      )}
    </div>
  );
}
