import React, { useEffect, useState, useRef } from "react";
import {
  apiListOutputs, OutputItem, apiGetOutputUrl, apiListThumbnails,
  ThumbnailItem, apiGetNextPeakSlot, PeakSlotInfo,
  apiGetOutputMetadata, apiSaveOutputMetadata, OutputMetadata, apiStartPipeline,
  apiRecordCorrection, apiPublishMulti, apiGetLatestOvernight, OvernightBatchManifest,
  apiGetBackendBaseUrl, apiUploadOutputThumbnail, apiRegenerateOutputThumbnail,
  apiPreviewSocialCopy, parseError
} from "../lib/api";
import {
  Video, RefreshCw, Upload, Play, Film, FolderOpen, Image as ImageIcon,
  Copy, Check, X, Loader, Clock, Zap, Edit3, Save, RotateCcw, AlertTriangle,
  Info, Sliders, CheckCircle2, Youtube, Instagram, Share2, Moon, Trophy, Star
} from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";

const CHAMPIONS = ["Katarina","Ahri","Zed","Yasuo","Jinx","Thresh","Lee Sin","Vayne","Samira","Akali","Yone","Riven","Kassadin","Evelynn","Master Yi","Darius"];
const ACTION_TYPES = [
  {id:"pentakill",label:"PENTAKILL 🔥"},
  {id:"quadrakill",label:"QUADRAKILL ⚡"},
  {id:"triple",label:"TRIPLE KILL 🎯"},
  {id:"double",label:"DOUBLE KILL ⚔️"},
  {id:"solo_bolo",label:"SOLO BOLO 👑"},
  {id:"outplay",label:"OUTPLAY 🧠"},
  {id:"clutch",label:"CLUTCH 1% HP 💀"},
];

// Which fields require re-render when changed
const RENDER_FIELDS: (keyof OutputMetadata)[] = ["champion_name","action_type","hook_text","clip_start","clip_end","peak_moment","use_speed_ramp","use_zoom_punch","use_smart_camera"];

export default function Outputs() {
  const navigate = useNavigate();
  const location = useLocation();
  const handledNavKeyRef = useRef<string | null>(null);
  const [outputs, setOutputs] = useState<OutputItem[]>([]);
  const [thumbnails, setThumbnails] = useState<ThumbnailItem[]>([]);
  const [latestBatch, setLatestBatch] = useState<OvernightBatchManifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedVideoUrl, setSelectedVideoUrl] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [backendUrl, setBackendUrl] = useState<string>("http://localhost:8765");
  const [thumbVersion, setThumbVersion] = useState<number>(() => Date.now());
  const [thumbBusyFor, setThumbBusyFor] = useState<string | null>(null);
  const [thumbError, setThumbError] = useState<string | null>(null);
  const [thumbLightbox, setThumbLightbox] = useState<{ url: string; path?: string | null; filename: string; videoFilename: string } | null>(null);
  const thumbFileInputRef = useRef<HTMLInputElement | null>(null);
  const thumbUploadTargetRef = useRef<string | null>(null);

  // Upload modal
  const [uploadModal, setUploadModal] = useState<{ filename: string } | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDesc, setUploadDesc] = useState("Watch till the end 🔥\n\n🔔 Subscribe for daily LoL clips!\n👍 Leave a like if you enjoyed!\n\n#Shorts #LeagueOfLegends #LoL #Gaming");
  const [uploadMode, setUploadMode] = useState<"peak"|"now"|"private">("peak");
  const [peakSlot, setPeakSlot] = useState<PeakSlotInfo | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ok:boolean;url?:string;error?:string;scheduledFor?:string}|null>(null);
  const [selYt, setSelYt] = useState(true);
  const [selTt, setSelTt] = useState(true);
  const [selIg, setSelIg] = useState(true);
  const [selFb, setSelFb] = useState(true);
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
      const [baseUrl, outData, thumbData, slotData, nightData] = await Promise.all([
        apiGetBackendBaseUrl().catch(() => "http://localhost:8765"),
        apiListOutputs(),
        apiListThumbnails(),
        apiGetNextPeakSlot().catch(() => null),
        apiGetLatestOvernight().catch(() => null),
      ]);
      setBackendUrl((baseUrl || "http://localhost:8765").replace(/\/$/, ""));
      setOutputs(outData); setThumbnails(thumbData);
      if (slotData) setPeakSlot(slotData);
      setLatestBatch(nightData?.batch || null);
      setThumbVersion(Date.now());
    } catch { } finally { setLoading(false); }
  };
  useEffect(() => { fetchOutputs(); }, []);

  useEffect(() => {
    const st = (location.state || {}) as { publishFilename?: string; playFilename?: string };
    const targetPub = st.publishFilename;
    const targetPlay = st.playFilename;
    if (!targetPub && !targetPlay) return;
    const navKey = `${location.key}:${targetPub || ''}:${targetPlay || ''}`;
    if (handledNavKeyRef.current === navKey) return;
    handledNavKeyRef.current = navKey;
    if (targetPlay) handlePlay(targetPlay);
    if (targetPub) openUploadModal(targetPub);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.key, location.pathname, location.state]);

  const handlePlay = async (filename: string) => {
    try {
      const url = await apiGetOutputUrl(filename);
      setSelectedVideoUrl(url);
    } catch { }
  };

  const basenameOf = (p?: string | null): string | null => {
    if (!p) return null;
    const parts = p.split(/[\\/]/).filter(Boolean);
    return parts.length > 0 ? parts[parts.length - 1] : null;
  };

  const findMatchingThumb = (videoFilename: string) => {
    const base = videoFilename.replace(/\.mp4$/i, "").toLowerCase();
    return thumbnails.find(t => t.filename.toLowerCase().includes(base) || t.associated_video.toLowerCase() === videoFilename.toLowerCase());
  };

  const resolveThumbForVideo = (
    videoFilename: string,
    itemThumbPath?: string | null,
    itemThumbFilename?: string | null,
  ): { filename: string; path: string | null } | null => {
    const match = findMatchingThumb(videoFilename);
    const nightItem = latestBatch?.items?.find(it => it.output_filename === videoFilename);
    const filename =
      itemThumbFilename ||
      basenameOf(itemThumbPath) ||
      nightItem?.thumbnail_filename ||
      basenameOf(nightItem?.thumbnail_path) ||
      match?.filename ||
      null;
    const path = itemThumbPath || nightItem?.thumbnail_path || match?.path || null;
    if (!filename) return null;
    return { filename, path };
  };

  const getThumbSrc = (thumbFilename: string) =>
    `${backendUrl}/thumbnails/${encodeURIComponent(thumbFilename)}?v=${thumbVersion}`;

  const handleTriggerThumbUpload = (videoFilename: string) => {
    setThumbError(null);
    thumbUploadTargetRef.current = videoFilename;
    if (thumbFileInputRef.current) {
      thumbFileInputRef.current.value = "";
      thumbFileInputRef.current.click();
    }
  };

  const handleThumbFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const targetVideo = thumbUploadTargetRef.current;
    e.target.value = "";
    if (!file || !targetVideo) return;
    setThumbBusyFor(targetVideo);
    setThumbError(null);
    try {
      const res = await apiUploadOutputThumbnail(targetVideo, file);
      const nextV = Date.now();
      setThumbVersion(nextV);
      if (thumbLightbox && thumbLightbox.videoFilename === targetVideo) {
        setThumbLightbox({
          url: `${backendUrl}/thumbnails/${encodeURIComponent(res.thumbnail_filename)}?v=${nextV}`,
          path: res.thumbnail_path,
          filename: res.thumbnail_filename,
          videoFilename: targetVideo,
        });
      }
      await fetchOutputs();
    } catch (err) {
      setThumbError(`Nie udało się podmienić miniaturki: ${parseError(err)}`);
    } finally {
      setThumbBusyFor(null);
      thumbUploadTargetRef.current = null;
    }
  };

  const handleRegenerateThumb = async (videoFilename: string) => {
    setThumbBusyFor(videoFilename);
    setThumbError(null);
    try {
      const res = await apiRegenerateOutputThumbnail(videoFilename);
      const nextV = Date.now();
      setThumbVersion(nextV);
      if (thumbLightbox && thumbLightbox.videoFilename === videoFilename) {
        setThumbLightbox({
          url: `${backendUrl}/thumbnails/${encodeURIComponent(res.thumbnail_filename)}?v=${nextV}`,
          path: res.thumbnail_path,
          filename: res.thumbnail_filename,
          videoFilename,
        });
      }
      await fetchOutputs();
    } catch (err) {
      setThumbError(`Nie udało się wygenerować miniaturki: ${parseError(err)}`);
    } finally {
      setThumbBusyFor(null);
    }
  };

  const handleOpenFolder = (p: string) => window.electronApp?.showItemInFolder?.(p);
  const handleOpenImage = (p: string) => window.electronApp?.openPath?.(p);
  const handleCopyPath = (p: string) => { navigator.clipboard.writeText(p); setCopiedPath(p); setTimeout(()=>setCopiedPath(null),2000); };

  const [uploadOriginalTitle, setUploadOriginalTitle] = useState("");
  const [uploadModalMeta, setUploadModalMeta] = useState<OutputMetadata | null>(null);
  const [tiktokCopyText, setTiktokCopyText] = useState("");
  const [tiktokCopied, setTiktokCopied] = useState(false);

  const buildLocalTiktokCopy = (rawTitle: string, champion?: string, actionType?: string) => {
    const clean = (rawTitle || "").replace(/#\S+/g, "").replace(/\s{2,}/g, " ").trim();
    const champTag = (champion || "katarina").replace(/['\s]/g, "").toLowerCase();
    const actMap: Record<string, string> = {
      pentakill: "pentakill",
      quadrakill: "quadrakill",
      triple: "triplekill",
      double: "doublekill",
      solo_bolo: "1v1",
      clutch: "lolclutch",
      steal: "dragonsteal",
    };
    const actTag = actMap[(actionType || "outplay").toLowerCase()] || "outplay";
    return `${clean}\n#leagueoflegends #${champTag} #${champTag}mains #${actTag} #fyp`;
  };

  const openUploadModal = async (filename: string) => {
    setUploadResult(null);
    setMultiResults(null);
    setThumbError(null);
    setTiktokCopied(false);
    setUploadModal({ filename });
    try {
      const meta = await apiGetOutputMetadata(filename);
      setUploadModalMeta(meta);
      const initialTitle = meta.title || "Sick Play! #Shorts #LoL";
      setUploadTitle(initialTitle);
      setUploadOriginalTitle(initialTitle);
      setUploadDesc(meta.description || "");
      setTiktokCopyText(buildLocalTiktokCopy(initialTitle, meta.champion_name, meta.action_type));
      apiPreviewSocialCopy({
        title: initialTitle,
        champion_name: meta.champion_name || "Katarina",
        action_type: meta.action_type || "outplay",
      }).then((prev) => {
        if (prev?.tiktok_copy_text) setTiktokCopyText(prev.tiktok_copy_text);
      }).catch(() => {});
    } catch {
      setUploadModalMeta(null);
      const fallbackTitle = "Sick Play! #Shorts #LoL";
      setUploadTitle(fallbackTitle);
      setUploadOriginalTitle(fallbackTitle);
      setUploadDesc("");
      setTiktokCopyText(buildLocalTiktokCopy(fallbackTitle, "Katarina", "outplay"));
    }
  };

  const handleCopyTiktokText = () => {
    if (!tiktokCopyText.trim()) return;
    navigator.clipboard.writeText(tiktokCopyText);
    setTiktokCopied(true);
    setTimeout(() => setTiktokCopied(false), 2000);
  };

  const handleUpload = async () => {
    if (!uploadModal) return;
    const platforms: string[] = [];
    if (selYt) platforms.push("youtube");
    if (selTt) platforms.push("tiktok");
    if (selIg) platforms.push("instagram");
    if (selFb) platforms.push("facebook");

    if (platforms.length === 0) {
      setUploadResult({ ok: false, error: "Wybierz przynajmniej jedną platformę do publikacji!" });
      return;
    }

    setUploading(true); setUploadResult(null); setMultiResults(null);
    try {
      let privacy = "public", publishAt: string|undefined, scheduledLabel: string|undefined;
      if (uploadMode==="peak" && peakSlot) { privacy="private"; publishAt=peakSlot.publish_at; scheduledLabel=peakSlot.label; }
      else if (uploadMode==="private") { privacy="private"; }
      const resolvedThumb = resolveThumbForVideo(uploadModal.filename);
      if (uploadTitle !== uploadOriginalTitle && uploadOriginalTitle) {
        apiRecordCorrection("title", uploadOriginalTitle, uploadTitle, "ui_upload_modal");
      }

      const res = await apiPublishMulti(uploadModal.filename, {
        title: uploadTitle,
        description: uploadDesc,
        tags: uploadModalMeta?.tags && uploadModalMeta.tags.length > 0 ? uploadModalMeta.tags : undefined,
        hashtags: uploadModalMeta?.hashtags && uploadModalMeta.hashtags.length > 0 ? uploadModalMeta.hashtags : undefined,
        platforms,
        privacy_yt: privacy,
        privacy_tiktok: "PUBLIC_TO_EVERYONE",
        share_to_ig_feed: true,
        thumbnail_path: resolvedThumb?.path || undefined,
        publish_at: publishAt,
        pinned_comment: uploadModalMeta?.pinned_comment,
        champion_name: uploadModalMeta?.champion_name,
        action_type: uploadModalMeta?.action_type,
        rank: uploadModalMeta?.rank,
        tiktok_caption: selTt ? tiktokCopyText : undefined,
      });

      const results = res.results || {};
      setMultiResults(results);

      const anySuccess = Object.values(results).some((r: any) => r && r.success);
      if (anySuccess) {
        setUploadResult({
          ok: true,
          url: results.youtube?.url || results.instagram?.url || results.facebook?.url || (results.tiktok?.publish_id ? `TikTok Publish ID: ${results.tiktok.publish_id}` : undefined),
          scheduledFor: scheduledLabel
        });
      } else {
        const firstErr = Object.values(results).map((r: any) => r?.error).filter(Boolean)[0] || "Błąd publikacji";
        setUploadResult({ ok: false, error: String(firstErr) });
      }
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
      // Rejestruj korekty tytułu i opisu w pętli uczenia (fire-and-forget)
      if (editOriginal?.title !== editMeta.title) {
        apiRecordCorrection("title", editOriginal?.title ?? "", editMeta.title, "ui_edit_panel");
      }
      if (editOriginal?.description !== editMeta.description) {
        apiRecordCorrection("description", editOriginal?.description ?? "", editMeta.description, "ui_edit_panel");
      }
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
      className={`flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg transition-colors ${editSection===id ? "bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/40" : "text-[#A0A7B1] hover:text-[#FFFFFF]"}`}>
      {icon}{label}
    </button>
  );

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#050505] p-6 lg:p-8 space-y-6 text-[#FFFFFF]">
      <input
        ref={thumbFileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleThumbFileSelected}
        className="hidden"
      />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#272A2F]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#FFFFFF] flex items-center gap-2.5">
            <Video className="w-6 h-6 text-[#C8FF3A]" />Biblioteka Gotowych Shortów
          </h1>
          <p className="text-xs text-[#A0A7B1] mt-1">Wyrenderowane wideo 9:16 — edytuj statystyki, modyfikuj parametry lub wgraj na YouTube</p>
        </div>
        <button onClick={fetchOutputs} disabled={loading}
          className="flex items-center gap-1.5 px-3.5 py-2 fk-cut-sm bg-[#0E0F11] hover:bg-[#17191C] border border-[#272A2F] text-xs font-semibold text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${loading?"animate-spin text-[#C8FF3A]":""}`} />Odśwież listę
        </button>
      </div>

      {thumbError && (
        <div className="p-3 fk-cut-sm bg-red-500/10 border border-red-500/40 text-xs text-red-300 flex items-center justify-between gap-2">
          <span className="break-words">{thumbError}</span>
          <button onClick={() => setThumbError(null)} className="text-red-200 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* THUMBNAIL LIGHTBOX */}
      {thumbLightbox && (
        <div className="fixed inset-0 bg-black/85 z-[60] flex items-center justify-center p-4" onClick={() => setThumbLightbox(null)}>
          <div className="bg-[#0E0F11] border border-[#C8FF3A]/50 fk-cut p-5 w-full max-w-md space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-bold text-[#C8FF3A] truncate flex items-center gap-1.5">
                <ImageIcon className="w-4 h-4 flex-shrink-0" />Podgląd Miniaturki (9:16)
              </span>
              <button onClick={() => setThumbLightbox(null)} className="text-[#A0A7B1] hover:text-white"><X className="w-4 h-4" /></button>
            </div>
            <div className="text-[10px] font-mono text-[#A0A7B1] truncate">{thumbLightbox.filename}</div>
            <div className="flex justify-center bg-[#050505] rounded-lg border border-[#272A2F] p-2">
              <img src={thumbLightbox.url} alt="Podgląd miniaturki 9:16" className="max-h-[60vh] aspect-[9/16] object-cover rounded" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                disabled={thumbBusyFor === thumbLightbox.videoFilename}
                onClick={() => handleTriggerThumbUpload(thumbLightbox.videoFilename)}
                className="py-2 px-3 fk-cut-sm bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                <Upload className="w-3.5 h-3.5 text-[#C8FF3A]" />Zmień plik
              </button>
              <button
                type="button"
                disabled={thumbBusyFor === thumbLightbox.videoFilename}
                onClick={() => handleRegenerateThumb(thumbLightbox.videoFilename)}
                className="py-2 px-3 fk-cut-sm bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                {thumbBusyFor === thumbLightbox.videoFilename ? <Loader className="w-3.5 h-3.5 animate-spin text-[#C8FF3A]" /> : <RotateCcw className="w-3.5 h-3.5 text-[#C8FF3A]" />}
                Wygeneruj nową
              </button>
            </div>
            {thumbLightbox.path && (
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => handleOpenImage(thumbLightbox.path!)}
                  className="flex-1 py-1.5 px-2.5 rounded-lg bg-[#272A2F] hover:bg-[#32363D] text-[11px] font-semibold text-white flex items-center justify-center gap-1.5"
                >
                  <ImageIcon className="w-3.5 h-3.5" />Otwórz w systemie
                </button>
                <button
                  type="button"
                  onClick={() => handleOpenFolder(thumbLightbox.path!)}
                  className="flex-1 py-1.5 px-2.5 rounded-lg bg-[#272A2F] hover:bg-[#32363D] text-[11px] font-semibold text-white flex items-center justify-center gap-1.5"
                >
                  <FolderOpen className="w-3.5 h-3.5" />Pokaż w folderze
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* UPLOAD MODAL */}
      {uploadModal && (() => {
        const modalThumb = resolveThumbForVideo(uploadModal.filename);
        const modalThumbBusy = thumbBusyFor === uploadModal.filename;
        return (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-[#0E0F11] border border-[#C8FF3A]/40 fk-cut p-6 w-full max-w-lg max-h-[92vh] overflow-y-auto space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-[#FFFFFF] flex items-center gap-2"><Share2 className="w-4 h-4 text-[#C8FF3A]"/>Publikacja Multi-Platform</h2>
              <button onClick={() => setUploadModal(null)} className="text-[#A0A7B1] hover:text-[#FFFFFF]"><X className="w-4 h-4"/></button>
            </div>
            <div className="text-xs text-[#A0A7B1] bg-[#050505] rounded-lg px-3 py-2 font-mono truncate">{uploadModal.filename}</div>

            {/* Miniaturka 9:16 podpięta do publikacji */}
            <div className="p-3 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center gap-3">
              <div className="w-16 aspect-[9/16] rounded-md bg-[#0E0F11] border border-[#272A2F] overflow-hidden flex-shrink-0 relative group">
                {modalThumb ? (
                  <img
                    src={getThumbSrc(modalThumb.filename)}
                    alt="Miniaturka 9:16"
                    onClick={() => setThumbLightbox({
                      url: getThumbSrc(modalThumb.filename),
                      path: modalThumb.path,
                      filename: modalThumb.filename,
                      videoFilename: uploadModal.filename,
                    })}
                    className="w-full h-full object-cover cursor-pointer group-hover:scale-105 transition-transform"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-[#686E78] p-1 text-center">
                    <ImageIcon className="w-4 h-4 opacity-60" />
                    <span className="text-[8px] mt-0.5">Brak</span>
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0 space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-[#C8FF3A] flex items-center gap-1.5">
                    <ImageIcon className="w-3.5 h-3.5" />Miniaturka (9:16)
                  </span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${modalThumb ? "bg-[#2ECC71]/15 text-[#55E88D]" : "bg-amber-500/15 text-amber-300"}`}>
                    {modalThumb ? "Gotowa do uploadu" : "Brak miniaturki"}
                  </span>
                </div>
                <div className="text-[10px] font-mono text-[#A0A7B1] truncate" title={modalThumb?.path || modalThumb?.filename || ""}>
                  {modalThumb ? modalThumb.filename : "Kliknij „Wygeneruj nową” albo „Zmień plik” (JPG/PNG/WebP)."}
                </div>
                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  <button
                    type="button"
                    disabled={modalThumbBusy}
                    onClick={() => handleTriggerThumbUpload(uploadModal.filename)}
                    className="px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[10px] font-bold text-white flex items-center gap-1 disabled:opacity-50"
                  >
                    <Upload className="w-3 h-3 text-[#C8FF3A]" />Zmień plik
                  </button>
                  <button
                    type="button"
                    disabled={modalThumbBusy}
                    onClick={() => handleRegenerateThumb(uploadModal.filename)}
                    className="px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[10px] font-bold text-white flex items-center gap-1 disabled:opacity-50"
                  >
                    {modalThumbBusy ? <Loader className="w-3 h-3 animate-spin text-[#C8FF3A]" /> : <RotateCcw className="w-3 h-3 text-[#C8FF3A]" />}
                    Wygeneruj nową
                  </button>
                  {modalThumb?.path && (
                    <>
                      <button
                        type="button"
                        onClick={() => handleOpenFolder(modalThumb.path!)}
                        title="Pokaż w folderze"
                        className="px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[10px] font-semibold text-[#A0A7B1] hover:text-white flex items-center gap-1"
                      >
                        <FolderOpen className="w-3 h-3" />Folder
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCopyPath(modalThumb.path!)}
                        title="Kopiuj ścieżkę"
                        className="px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[10px] font-semibold text-[#C8FF3A] flex items-center gap-1"
                      >
                        {copiedPath === modalThumb.path ? <Check className="w-3 h-3 text-[#2ECC71]" /> : <Copy className="w-3 h-3" />}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Wybór platformy (5 Przycisków + Checkboxy) */}
            <div className="space-y-2 pt-0.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-[#A0A7B1] flex items-center gap-1.5">
                  <Share2 className="w-3.5 h-3.5 text-[#C8FF3A]" /> Gdzie wrzucać (Wybór / Presety):
                </label>
                <span className="text-[10px] text-[#C8FF3A] font-mono font-bold">
                  Wybrano ({[selYt, selTt, selIg, selFb].filter(Boolean).length}/4): {[selYt && 'YT', selTt && 'TikTok', selIg && 'IG', selFb && 'FB'].filter(Boolean).join(' + ') || 'Brak'}
                </span>
              </div>

              {/* 5 Dedykowanych Przycisków Wyboru Celu */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5">
                <button
                  type="button"
                  onClick={() => handleSelectPlatformPreset('yt')}
                  className={`p-2 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-0.5 cursor-pointer select-none ${
                    selYt && !selTt && !selIg && !selFb
                      ? 'bg-[#FF0000]/25 border-[#FF0000] text-white scale-[1.02]'
                      : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#FF0000]/60 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-1 text-xs font-bold">
                    <Youtube className="w-3.5 h-3.5 text-[#FF0000]" />
                    <span>1. YouTube</span>
                  </div>
                  <span className="text-[9px] text-[#A0A7B1]">Tylko YT</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSelectPlatformPreset('tt')}
                  className={`p-2 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-0.5 cursor-pointer select-none ${
                    !selYt && selTt && !selIg && !selFb
                      ? 'bg-[#00F2FE]/25 border-[#00F2FE] text-white scale-[1.02]'
                      : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#00F2FE]/60 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-1 text-xs font-bold">
                    <Video className="w-3.5 h-3.5 text-[#00F2FE]" />
                    <span>2. TikTok</span>
                  </div>
                  <span className="text-[9px] text-[#A0A7B1]">Tylko TikTok</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSelectPlatformPreset('ig')}
                  className={`p-2 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-0.5 cursor-pointer select-none ${
                    !selYt && !selTt && selIg && !selFb
                      ? 'bg-[#E1306C]/25 border-[#E1306C] text-white scale-[1.02]'
                      : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#E1306C]/60 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-1 text-xs font-bold">
                    <Instagram className="w-3.5 h-3.5 text-[#E1306C]" />
                    <span>3. Instagram</span>
                  </div>
                  <span className="text-[9px] text-[#A0A7B1]">Tylko Reels</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSelectPlatformPreset('fb')}
                  className={`p-2 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-0.5 cursor-pointer select-none ${
                    !selYt && !selTt && !selIg && selFb
                      ? 'bg-[#1877F2]/25 border-[#1877F2] text-white scale-[1.02]'
                      : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#1877F2]/60 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-1 text-xs font-bold">
                    <Share2 className="w-3.5 h-3.5 text-[#1877F2]" />
                    <span>4. Facebook</span>
                  </div>
                  <span className="text-[9px] text-[#A0A7B1]">Tylko Fanpage</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSelectPlatformPreset('all')}
                  className={`col-span-2 sm:col-span-1 p-2 fk-cut-sm border-2 text-center transition-all flex flex-col items-center justify-center gap-0.5 cursor-pointer select-none ${
                    selYt && selTt && selIg && selFb
                      ? 'bg-[#C8FF3A]/20 border-[#C8FF3A] text-[#FFFFFF] scale-[1.02]'
                      : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#C8FF3A]/60 hover:text-[#FFFFFF]'
                  }`}
                >
                  <div className="flex items-center gap-1 text-xs font-black text-[#C8FF3A]">
                    <Zap className="w-3.5 h-3.5" />
                    <span>5. WSZYSTKO</span>
                  </div>
                  <span className="text-[9px] text-[#C8FF3A] font-semibold">Wszystkie 4</span>
                </button>
              </div>

              {/* Checkboxy do precyzyjnego miksowania */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${selYt ? "bg-[#FF0000]/15 border-[#FF0000]/60 text-white" : "bg-[#050505] border-[#272A2F] text-[#A0A7B1]"}`}>
                  <input type="checkbox" checked={selYt} onChange={e=>setSelYt(e.target.checked)} className="accent-[#FF0000]" />
                  <span className="text-xs font-bold flex items-center gap-1"><Youtube className="w-3.5 h-3.5 text-[#FF0000]" /> YouTube</span>
                </label>
                <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${selTt ? "bg-[#00F2FE]/15 border-[#00F2FE]/60 text-white" : "bg-[#050505] border-[#272A2F] text-[#A0A7B1]"}`}>
                  <input type="checkbox" checked={selTt} onChange={e=>setSelTt(e.target.checked)} className="accent-[#00F2FE]" />
                  <span className="text-xs font-bold flex items-center gap-1"><Video className="w-3.5 h-3.5 text-[#00F2FE]" /> TikTok</span>
                </label>
                <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${selIg ? "bg-[#E1306C]/15 border-[#E1306C]/60 text-white" : "bg-[#050505] border-[#272A2F] text-[#A0A7B1]"}`}>
                  <input type="checkbox" checked={selIg} onChange={e=>setSelIg(e.target.checked)} className="accent-[#E1306C]" />
                  <span className="text-xs font-bold flex items-center gap-1"><Instagram className="w-3.5 h-3.5 text-[#E1306C]" /> Instagram</span>
                </label>
                <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${selFb ? "bg-[#1877F2]/15 border-[#1877F2]/60 text-white" : "bg-[#050505] border-[#272A2F] text-[#A0A7B1]"}`}>
                  <input type="checkbox" checked={selFb} onChange={e=>setSelFb(e.target.checked)} className="accent-[#1877F2]" />
                  <span className="text-xs font-bold flex items-center gap-1"><Share2 className="w-3.5 h-3.5 text-[#1877F2]" /> Facebook</span>
                </label>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-[#C8FF3A]">Tytuł (YouTube Shorts)</label>
              <input
                value={uploadTitle}
                onChange={e => {
                  const val = e.target.value;
                  setUploadTitle(val);
                  setTiktokCopyText(buildLocalTiktokCopy(val, uploadModalMeta?.champion_name, uploadModalMeta?.action_type));
                }}
                className="w-full bg-[#050505] border border-[#272A2F] rounded-lg px-3 py-2 text-sm text-[#FFFFFF] focus:border-[#C8FF3A] outline-none"
                placeholder="Tytuł wideo..."
              />
            </div>
            {selTt && (
              <div className="space-y-1 bg-[#00F2FE]/5 border border-[#00F2FE]/30 rounded-lg p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <label className="text-[11px] font-bold text-[#00F2FE] flex items-center gap-1.5">
                    <Video className="w-3.5 h-3.5" /> Opis + Tagi TikTok (bez #shorts, okładka 9:16 t=0.0s)
                  </label>
                  <button
                    type="button"
                    onClick={handleCopyTiktokText}
                    className="px-2 py-0.5 rounded bg-[#00F2FE]/15 hover:bg-[#00F2FE]/25 text-[#00F2FE] border border-[#00F2FE]/40 text-[10px] font-bold flex items-center gap-1 transition-all"
                  >
                    {tiktokCopied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    {tiktokCopied ? "Skopiowano!" : "Kopiuj opis + tagi TikTok"}
                  </button>
                </div>
                <textarea
                  value={tiktokCopyText}
                  onChange={e => setTiktokCopyText(e.target.value)}
                  rows={2}
                  className="w-full bg-[#050505] border border-[#272A2F] rounded px-2.5 py-1.5 text-[11px] text-[#FFFFFF] focus:border-[#00F2FE] outline-none resize-none font-mono"
                />
              </div>
            )}
            <div className="space-y-1">
              <label className="text-xs font-semibold text-[#C8FF3A]">Opis / Hashtagi</label>
              <textarea value={uploadDesc} onChange={e=>setUploadDesc(e.target.value)} rows={3} className="w-full bg-[#050505] border border-[#272A2F] rounded-lg px-3 py-2 text-xs text-[#FFFFFF] focus:border-[#C8FF3A] outline-none resize-none"/>
            </div>
            <div className="space-y-2 pt-1">
              <label className="text-xs font-semibold text-[#A0A7B1] flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-[#C8FF3A]"/>Tryb Publikacji (YouTube):</label>
              <div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={()=>setUploadMode("peak")} className={`p-2 fk-cut-sm border text-left transition-all ${uploadMode==="peak"?"bg-[#C8FF3A]/15 border-[#C8FF3A] text-[#FFFFFF]":"bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#C8FF3A]/40"}`}>
                  <div className="flex items-center justify-between"><span className="text-xs font-bold text-[#C8FF3A] flex items-center gap-1"><Zap className="w-3 h-3"/>AI Peak Slot</span><span className="text-[9px] bg-[#2ECC71]/20 text-[#2ECC71] px-1 rounded font-bold">TOP</span></div>
                  <div className="text-[11px] font-semibold text-[#FFFFFF] mt-0.5 truncate">{peakSlot?.label||"Dziś o 21:30 CET"}</div>
                </button>
                <button type="button" onClick={()=>setUploadMode("now")} className={`p-2 fk-cut-sm border text-left transition-all ${uploadMode==="now"?"bg-[#2ECC71]/15 border-[#2ECC71] text-[#FFFFFF]":"bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#2ECC71]/40"}`}>
                  <div className="text-xs font-bold text-[#2ECC71]">Opublikuj Teraz</div>
                  <div className="text-[11px] font-semibold text-[#FFFFFF] mt-0.5">Publiczny od razu</div>
                </button>
              </div>
            </div>

            {uploadResult && (() => {
              const multiEntries = multiResults
                ? (['youtube', 'tiktok', 'instagram', 'facebook'] as const)
                    .map((k) => multiResults[k])
                    .filter(Boolean)
                : [];
              const okCount = multiEntries.filter((v) => v?.success).length;
              const failCount = multiEntries.filter((v) => v && !v.success).length;
              const isPartialSuccess = Boolean(uploadResult.ok && failCount > 0);
              const boxCls = !uploadResult.ok
                ? "bg-red-500/10 text-red-400 border border-red-500/30"
                : isPartialSuccess
                ? "bg-[#FFB347]/15 text-[#FFD89B] border border-[#FFB347]/50"
                : "bg-[#2ECC71]/10 text-[#2ECC71] border border-[#2ECC71]/30";

              return (
              <div className={`rounded-lg px-3 py-2.5 text-xs font-semibold space-y-1.5 overflow-hidden ${boxCls}`}>
                {uploadResult.ok ? (
                  <div className="min-w-0">
                    {isPartialSuccess ? (
                      <div className="font-bold text-[#FFB347] mb-1">⚠️ Opublikowano częściowo ({okCount}/{multiEntries.length}) — sprawdź błędy!</div>
                    ) : (
                      <div className="font-bold text-[#55E88D] mb-1">🎉 Wyniki publikacji:</div>
                    )}
                    {multiResults && (
                      <div className="space-y-1 text-[11px] font-mono min-w-0">
                        {multiResults.youtube && (
                          <div className={`break-words [overflow-wrap:anywhere] ${multiResults.youtube.success ? "text-[#55E88D]" : "text-[#FF5C5C]"}`}>
                            • YouTube: {multiResults.youtube.success ? `✅ Wgrano (${multiResults.youtube.url})` : `❌ ${multiResults.youtube.error}`}
                          </div>
                        )}
                        {multiResults.tiktok && (
                          <div className={`break-words [overflow-wrap:anywhere] ${multiResults.tiktok.success ? "text-[#55E88D]" : "text-[#FFB347]"}`}>
                            • TikTok: {multiResults.tiktok.success ? `✅ Opublikowano (${multiResults.tiktok.publish_id || "OK"})` : `⚠️ ${multiResults.tiktok.error}`}
                          </div>
                        )}
                        {multiResults.instagram && (
                          <div className={`break-words [overflow-wrap:anywhere] ${multiResults.instagram.success ? "text-[#55E88D]" : "text-[#FF5C5C]"}`}>
                            • Instagram: {multiResults.instagram.success ? `✅ Reel opublikowany (${multiResults.instagram.url || "OK"})` : `❌ ${multiResults.instagram.error}`}
                          </div>
                        )}
                        {multiResults.facebook && (
                          <div className={`break-words [overflow-wrap:anywhere] ${multiResults.facebook.success ? "text-[#55E88D]" : "text-[#FF5C5C]"}`}>
                            • Facebook: {multiResults.facebook.success ? `✅ Fanpage opublikowano (${multiResults.facebook.url || multiResults.facebook.video_id || "OK"})` : `❌ ${multiResults.facebook.error}`}
                          </div>
                        )}
                      </div>
                    )}
                    {uploadResult.scheduledFor && <div className="text-[11px] text-[#C8FF3A] mt-1 font-sans">⏰ Zaplanowano na: {uploadResult.scheduledFor}</div>}
                  </div>
                ) : (
                  <span className="break-words [overflow-wrap:anywhere] block">❌ Błąd: {uploadResult.error}</span>
                )}
              </div>
              );
            })()}

            <div className="flex gap-3 pt-1">
              <button onClick={()=>setUploadModal(null)} className="flex-1 py-2 fk-cut-sm border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF] font-semibold">Anuluj</button>
              <button onClick={handleUpload} disabled={uploading||!uploadTitle.trim()||(!selYt&&!selTt&&!selIg&&!selFb)} className="flex-1 py-2.5 fk-cut-sm bg-[#C8FF3A] hover:bg-[#C8FF3A] disabled:opacity-50 text-[#050505] text-xs font-bold flex items-center justify-center gap-1.5 transition-all">
                {uploading?<Loader className="w-3.5 h-3.5 animate-spin"/>:<Share2 className="w-3.5 h-3.5"/>}
                {uploading
                  ? "Publikuję..."
                  : selYt && selTt && selIg && selFb
                  ? "🚀 Opublikuj na WSZYSTKO (4 platformy)"
                  : !selYt && !selTt && !selIg && !selFb
                  ? "⚠️ Zaznacz platformę"
                  : selYt && !selTt && !selIg && !selFb
                  ? "🚀 Opublikuj na YouTube Shorts"
                  : !selYt && selTt && !selIg && !selFb
                  ? "🚀 Opublikuj na TikTok"
                  : !selYt && !selTt && selIg && !selFb
                  ? "🚀 Opublikuj na Instagram Reels"
                  : !selYt && !selTt && !selIg && selFb
                  ? "🚀 Opublikuj na Facebook Page"
                  : `🚀 Opublikuj (${[selYt&&'YT', selTt&&'TT', selIg&&'IG', selFb&&'FB'].filter(Boolean).join(' + ')})`}
              </button>
            </div>
          </div>
        </div>
        );
      })()}

      {/* EDIT MODAL */}
      {editModal && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
          <div className="bg-[#0E0F11] border border-[#C8FF3A]/40 fk-cut p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto space-y-5 text-[#FFFFFF]">
            <div className="flex items-start justify-between pb-3 border-b border-[#272A2F]">
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-[#C8FF3A] flex items-center gap-1.5">
                  <Edit3 className="w-4 h-4"/>Edytor Shorta
                </div>
                <div className="text-sm font-bold text-[#FFFFFF] mt-1 truncate max-w-md">{editModal}</div>
              </div>
              <button onClick={()=>setEditModal(null)} className="p-1.5 rounded-lg bg-[#272A2F] hover:bg-[#272A2F] text-[#A0A7B1] hover:text-white transition-colors"><X className="w-4 h-4"/></button>
            </div>

            {/* Re-render warning banner */}
            {hasRenderChanges() && (
              <div className="p-3 fk-cut-sm bg-[#C8FF3A]/10 border border-[#C8FF3A]/30 text-[#C8FF3A] text-xs flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5"/>
                <div><b>Zmieniono parametry renderowania</b> — aby zapisać te zmiany, aplikacja wyrenderuje klip ponownie. Kliknij <b>"Zapisz i Re-Renderuj"</b>.</div>
              </div>
            )}

            {editError && <div className="p-3 fk-cut-sm bg-red-500/10 border border-red-500/30 text-red-400 text-xs">{editError}</div>}

            {/* Section tabs */}
            <div className="flex items-center gap-1 p-1 bg-[#050505] fk-cut-sm border border-[#272A2F]">
              {sectionTab("meta", "Metadane YouTube", <Upload className="w-3 h-3"/>)}
              {sectionTab("stats", "Statystyki AI", <Info className="w-3 h-3"/>)}
              {sectionTab("render", "Parametry Renderu", <Sliders className="w-3 h-3"/>)}
            </div>

            {editLoading ? (
              <div className="py-12 flex flex-col items-center justify-center text-[#A0A7B1]">
                <RefreshCw className="w-6 h-6 animate-spin text-[#C8FF3A] mb-2"/><span className="text-xs">Ładowanie metadanych...</span>
              </div>
            ) : editMeta && (
              <>
                {/* SECTION: META */}
                {editSection === "meta" && (
                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-[#C8FF3A]">Tytuł YouTube Shorts</label>
                      <input value={editMeta.title} onChange={e=>setEditMeta(m=>m?{...m,title:e.target.value}:m)}
                        className="w-full bg-[#050505] border border-[#272A2F] focus:border-[#C8FF3A] fk-cut-sm px-3 py-2.5 text-sm text-[#FFFFFF] outline-none"
                        placeholder="Tytuł Shorta..."/>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-[#C8FF3A]">Opis</label>
                      <textarea value={editMeta.description} onChange={e=>setEditMeta(m=>m?{...m,description:e.target.value}:m)}
                        rows={5} className="w-full bg-[#050505] border border-[#272A2F] focus:border-[#C8FF3A] fk-cut-sm px-3 py-2 text-xs text-[#FFFFFF] outline-none resize-none"/>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-[#C8FF3A]">Hashtagi (oddzielone przecinkami)</label>
                      <input value={(editMeta.tags||[]).join(", ")} onChange={e=>setEditMeta(m=>m?{...m,tags:e.target.value.split(",").map(t=>t.trim()).filter(Boolean)}:m)}
                        className="w-full bg-[#050505] border border-[#272A2F] focus:border-[#C8FF3A] fk-cut-sm px-3 py-2 text-xs text-[#FFFFFF] outline-none"
                        placeholder="league of legends, shorts, lol, outplay..."/>
                    </div>
                    <p className="text-[11px] text-[#686E78]">ℹ️ Zmiany metadanych nie wymagają ponownego renderowania — zostaną natychmiast zapisane i użyte przy uploadzie na YouTube.</p>
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
                        <div key={label} className="p-3 fk-cut-sm bg-[#050505] border border-[#272A2F]">
                          <div className="text-[10px] text-[#A0A7B1] uppercase tracking-wider mb-1">{label}</div>
                          <div className="text-sm font-bold text-[#C8FF3A]">{val}</div>
                        </div>
                      ))}
                    </div>
                    <div className="p-3 fk-cut-sm bg-[#050505] border border-[#272A2F]">
                      <div className="text-[10px] text-[#A0A7B1] uppercase tracking-wider mb-1">Źródłowy Plik</div>
                      <div className="text-xs font-mono text-[#FFFFFF] break-all">{editMeta.source_path || "—"}</div>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-[#A0A7B1]">
                      <span className="flex items-center gap-1">{editMeta.use_smart_camera?<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400"/>:<X className="w-3.5 h-3.5 text-red-400"/>}Smart Camera</span>
                      <span className="flex items-center gap-1">{editMeta.use_speed_ramp?<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400"/>:<X className="w-3.5 h-3.5 text-red-400"/>}Speed Ramp</span>
                      <span className="flex items-center gap-1">{editMeta.use_zoom_punch?<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400"/>:<X className="w-3.5 h-3.5 text-red-400"/>}Zoom Punch</span>
                    </div>
                  </div>
                )}

                {/* SECTION: RENDER PARAMS */}
                {editSection === "render" && (
                  <div className="space-y-4">
                    <div className="p-3 fk-cut-sm bg-[#C8FF3A]/10 border border-[#C8FF3A]/30 text-[#C8FF3A] text-xs flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5"/>
                      Zmiana poniższych parametrów WYMAGA ponownego wyrenderowania klipu (przycisk "Zapisz i Re-Renderuj").
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Bohater:</label>
                        <select value={editMeta.champion_name} onChange={e=>setEditMeta(m=>m?{...m,champion_name:e.target.value}:m)}
                          className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]">
                          {CHAMPIONS.map(c=><option key={c} value={c}>{c}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Typ Akcji:</label>
                        <select value={editMeta.action_type} onChange={e=>setEditMeta(m=>m?{...m,action_type:e.target.value}:m)}
                          className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#C8FF3A] focus:outline-none focus:border-[#C8FF3A]">
                          {ACTION_TYPES.map(a=><option key={a.id} value={a.id}>{a.label}</option>)}
                        </select>
                      </div>
                      <div className="md:col-span-2">
                        <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Hook Text (napis na początku):</label>
                        <input value={editMeta.hook_text} onChange={e=>setEditMeta(m=>m?{...m,hook_text:e.target.value}:m)}
                          className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]"/>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      {[{l:"Start (s)",k:"clip_start"},{l:"Koniec (s)",k:"clip_end"},{l:"Peak (s)",k:"peak_moment"}].map(({l,k})=>(
                        <div key={k}>
                          <label className="text-[11px] font-bold text-[#A0A7B1] block mb-1">{l}</label>
                          <div className="flex gap-1 mb-1">{[-1,1].map(d=><button key={d} type="button" onClick={()=>setEditMeta(m=>m?{...m,[k]:Math.max(0,+((m[k as keyof OutputMetadata] as number)+d).toFixed(1))}:m)} className="px-1.5 py-0.5 bg-[#0E0F11] hover:bg-[#272A2F] text-[#A0A7B1] rounded border border-[#272A2F] text-[10px]">{d>0?"+1s":"-1s"}</button>)}</div>
                          <input type="number" step="0.5" value={editMeta[k as keyof OutputMetadata] as number}
                            onChange={e=>setEditMeta(m=>m?{...m,[k]:parseFloat(e.target.value)||0}:m)}
                            className="w-full px-3 py-1.5 rounded-lg bg-[#0E0F11] border border-[#272A2F] text-xs font-mono text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]"/>
                        </div>
                      ))}
                    </div>
                    <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-2.5">
                      <div className="text-xs font-bold text-[#A0A7B1] uppercase tracking-wider mb-2">Moduły Efektów:</div>
                      {[{l:"Smart Camera (Śledzenie HP)",k:"use_smart_camera"},{l:"Slow-Mo Ramp 0.45x + Minterpolate",k:"use_speed_ramp"},{l:"Zoom-Punch 1.20x + Bass Boost",k:"use_zoom_punch"}].map(({l,k})=>(
                        <label key={k} className="flex items-center justify-between cursor-pointer text-xs font-semibold">
                          <span className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-[#C8FF3A]"/>{l}</span>
                          <input type="checkbox" checked={editMeta[k as keyof OutputMetadata] as boolean}
                            onChange={e=>setEditMeta(m=>m?{...m,[k]:e.target.checked}:m)}
                            className="rounded border-[#272A2F] bg-[#0E0F11] text-[#C8FF3A]"/>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex items-center justify-between gap-3 pt-3 border-t border-[#272A2F]">
                  <button type="button" onClick={()=>setEditModal(null)} className="px-4 py-2 fk-cut-sm bg-[#272A2F] hover:bg-[#272A2F] text-xs font-bold text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors">Anuluj</button>
                  <div className="flex items-center gap-2">
                    {editSaved && <span className="text-xs text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5"/>Zapisano!</span>}
                    {hasRenderChanges() ? (
                      <button type="button" disabled={editRerendering} onClick={handleRerender}
                        className="px-5 py-2.5 fk-cut-sm fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] text-xs font-black transition-colors flex items-center gap-2 disabled:opacity-50">
                        {editRerendering?<Loader className="w-3.5 h-3.5 animate-spin"/>:<RotateCcw className="w-3.5 h-3.5"/>}
                        {editRerendering?"Re-renderuję...":"Zapisz i Re-Renderuj"}
                      </button>
                    ) : (
                      <button type="button" disabled={editSaving} onClick={handleSaveMeta}
                        className="px-5 py-2.5 fk-cut-sm bg-[#C8FF3A] hover:bg-[#C8FF3A] text-[#050505] text-xs font-black transition-colors flex items-center gap-2 disabled:opacity-50">
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
        <div className="p-5 fk-cut bg-[#0E0F11] border border-[#C8FF3A]/40 flex flex-col items-center">
          <div className="w-full flex justify-between items-center mb-4">
            <span className="text-xs font-extrabold tracking-wide uppercase text-[#FFFFFF] flex items-center gap-2">
              <span className="fk-slash h-3.5 w-1.5" />
              Odtwarzacz Short (9:16)
            </span>
            <button onClick={()=>setSelectedVideoUrl(null)} className="fk-btn-ghost text-xs font-bold text-[#A0A7B1] hover:text-[#FFFFFF] px-3 py-1 bg-[#272A2F]">Zamknij</button>
          </div>
          <div className="fk-crn my-2">
            <video src={selectedVideoUrl} controls autoPlay className="h-[460px] fk-cut-sm border border-[#272A2F] bg-black block"/>
          </div>
        </div>
      )}

      {/* NOCNA PACZKA SYNAPSY */}
      {latestBatch && latestBatch.items && latestBatch.items.length > 0 && (
        <div className="p-5 fk-cut bg-[#0E0F11] border border-indigo-400/40 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-sm font-black text-[#FFFFFF] flex items-center gap-2 flex-wrap">
                <Moon className="w-4 h-4 text-indigo-300" />
                Nocna Paczka Synapsy — Top {latestBatch.items.length} do Wyboru
                <span className="text-[9px] px-2 py-0.5 rounded bg-indigo-500/20 border border-indigo-400/35 text-indigo-200 font-bold">ZERO AUTO-UPLOADU</span>
              </div>
              <div className="text-[11px] text-[#A0A7B1] mt-1">
                Przeskanowano {latestBatch.scan_stats?.scanned_unpublished ?? 0} nieopublikowanych • Mocne: {latestBatch.scan_stats?.qualified_count ?? 0} • Odrzucono przeciętnych: {latestBatch.scan_stats?.rejected_count ?? 0} • Pominięto opubl.: {latestBatch.scan_stats?.skipped_published ?? 0}
              </div>
            </div>
            <div className="text-[10px] font-mono text-[#686E78] flex-shrink-0">Batch: {latestBatch.batch_id}</div>
          </div>

          {latestBatch.summary_pl && (
            <div className="p-3 fk-cut-sm bg-[#C8FF3A]/10 border border-[#C8FF3A]/40 text-xs text-[#FFFFFF] flex items-start gap-2.5">
              <Trophy className="w-4 h-4 text-[#C8FF3A] flex-shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1 break-words">{latestBatch.summary_pl}</div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {latestBatch.items.map(item => {
              const isWinner = item.overnight_rank === 1 && item.verdict === "PICK_WINNER";
              const nightThumb = resolveThumbForVideo(item.output_filename, item.thumbnail_path, item.thumbnail_filename);
              const isThumbBusy = thumbBusyFor === item.output_filename;
              return (
                <div key={item.output_filename}
                  className={`p-3.5 fk-cut-sm bg-[#050505] border flex flex-col justify-between gap-3 ${
                    isWinner ? "border-[#C8FF3A] shadow-[0_0_20px_rgba(200,255,58,0.12)]" : "border-[#272A2F]"
                  }`}>
                  <div className="flex gap-3 min-w-0">
                    {/* Lewa kolumna: Miniaturka 9:16 + akcje */}
                    <div className="w-20 sm:w-24 flex-shrink-0 flex flex-col gap-1.5">
                      <div className="w-full aspect-[9/16] rounded-lg bg-[#0E0F11] border border-[#272A2F] overflow-hidden relative group">
                        {nightThumb ? (
                          <>
                            <img
                              src={getThumbSrc(nightThumb.filename)}
                              alt={`Miniaturka ${item.champion_name} ${item.action_type}`}
                              onClick={() => setThumbLightbox({
                                url: getThumbSrc(nightThumb.filename),
                                path: nightThumb.path,
                                filename: nightThumb.filename,
                                videoFilename: item.output_filename,
                              })}
                              className="w-full h-full object-cover cursor-pointer group-hover:scale-105 transition-transform"
                            />
                            <button
                              type="button"
                              onClick={() => setThumbLightbox({
                                url: getThumbSrc(nightThumb.filename),
                                path: nightThumb.path,
                                filename: nightThumb.filename,
                                videoFilename: item.output_filename,
                              })}
                              title="Powiększ miniaturkę"
                              className="absolute bottom-1 right-1 p-1 rounded bg-black/75 hover:bg-[#C8FF3A] text-white hover:text-black transition-colors"
                            >
                              <ImageIcon className="w-3 h-3" />
                            </button>
                          </>
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center text-[#686E78] p-1.5 text-center gap-1.5">
                            <ImageIcon className="w-4 h-4 opacity-50" />
                            <span className="text-[9px] leading-tight">Brak miniaturki</span>
                            {item.render_ok && (
                              <button
                                type="button"
                                disabled={isThumbBusy}
                                onClick={() => handleRegenerateThumb(item.output_filename)}
                                className="px-1.5 py-1 rounded bg-[#17191C] hover:bg-[#C8FF3A] text-[#C8FF3A] hover:text-[#050505] border border-[#C8FF3A]/40 text-[9px] font-bold disabled:opacity-50"
                              >
                                {isThumbBusy ? "..." : "Wygeneruj"}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                      {item.render_ok && (
                        <div className="grid grid-cols-3 gap-1">
                          <button
                            type="button"
                            disabled={isThumbBusy}
                            onClick={() => handleTriggerThumbUpload(item.output_filename)}
                            title="Podmień własną miniaturkę"
                            className="p-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[9px] font-semibold text-[#FFFFFF] flex items-center justify-center disabled:opacity-50"
                          >
                            <Upload className="w-2.5 h-2.5 text-[#C8FF3A]" />
                          </button>
                          <button
                            type="button"
                            disabled={isThumbBusy}
                            onClick={() => handleRegenerateThumb(item.output_filename)}
                            title="Wygeneruj nową miniaturkę"
                            className="p-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[9px] font-semibold text-[#FFFFFF] flex items-center justify-center disabled:opacity-50"
                          >
                            {isThumbBusy ? <Loader className="w-2.5 h-2.5 animate-spin text-[#C8FF3A]" /> : <RotateCcw className="w-2.5 h-2.5 text-[#C8FF3A]" />}
                          </button>
                          {nightThumb?.path ? (
                            <button
                              type="button"
                              onClick={() => handleOpenFolder(nightThumb.path!)}
                              title="Pokaż miniaturkę w folderze"
                              className="p-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[#A0A7B1] hover:text-white flex items-center justify-center"
                            >
                              <FolderOpen className="w-2.5 h-2.5" />
                            </button>
                          ) : (
                            <span />
                          )}
                        </div>
                      )}
                    </div>

                    {/* Prawa kolumna: Dane i ocena Synapsy */}
                    <div className="space-y-2 min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-black ${
                          isWinner
                            ? "bg-[#C8FF3A] text-[#050505]"
                            : item.verdict === "STRONG_ALT"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        }`}>
                          {isWinner ? "⭐ REKOMENDACJA SYNAPSY #1" : `#${item.overnight_rank} • ${item.verdict}`}
                        </span>
                        <div className="flex items-center gap-1.5 flex-wrap">
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

                      <div className="text-xs font-bold text-[#FFFFFF] break-words">{item.title || item.output_filename}</div>
                      <div className="text-[10px] font-mono text-[#686E78] truncate" title={item.source_filename}>
                        {item.match_date ? `${item.match_date} • ` : ""}{item.match_kda ? `KDA ${item.match_kda} • ` : ""}{String(item.event_source || "").startsWith("outplayed_") ? "Riot Outplayed • " : ""}Źródło: {item.source_filename}
                      </div>

                      <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-mono">
                        <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#C8FF3A]">Final {item.final_score}</span>
                        <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">Hype {item.hype_score}</span>
                        <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">Watch {item.watchability_score ?? "?"}</span>
                        <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">QA {item.qa_score}</span>
                      </div>

                      <p className="text-[11px] text-[#A0A7B1] break-words [overflow-wrap:anywhere]">{item.synapsa_comment_pl}</p>
                      {item.defects && item.defects.filter(d => d !== "ig_needs_transcode_on_upload").length > 0 && (
                        <div className="text-[10px] text-amber-300 break-words">
                          Wady: {item.defects.filter(d => d !== "ig_needs_transcode_on_upload").join(", ")}
                        </div>
                      )}
                    </div>
                  </div>

                  {item.render_ok && (
                    <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                      <button onClick={() => handlePlay(item.output_filename)}
                        className="px-3 py-1.5 rounded-lg bg-[#272A2F] hover:bg-[#32363D] text-xs font-semibold text-[#FFFFFF] flex items-center gap-1.5">
                        <Play className="w-3.5 h-3.5 fill-current" />Odtwórz
                      </button>
                      <button onClick={() => openUploadModal(item.output_filename)}
                        className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-black flex items-center justify-center gap-1.5 ${
                          isWinner ? "bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505]" : "bg-[#17191C] hover:bg-[#272A2F] text-[#C8FF3A] border border-[#C8FF3A]/40"
                        }`}>
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

      {/* LIST */}
      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center text-[#A0A7B1] py-16">
          <RefreshCw className="w-8 h-8 animate-spin text-[#C8FF3A] mb-2"/><p className="text-xs">Ładowanie biblioteki...</p>
        </div>
      ) : outputs.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {outputs.map(out => {
            const thumb = findMatchingThumb(out.filename);
            const isOutThumbBusy = thumbBusyFor === out.filename;
            return (
              <div key={out.filename} className="p-4 fk-cut-sm bg-[#0E0F11] border border-[#272A2F] hover:border-[#C8FF3A]/40 transition-all flex flex-col justify-between space-y-4">
                <div className="flex gap-3">
                  <div className="w-20 h-32 rounded-lg bg-[#050505] border border-[#272A2F] overflow-hidden flex-shrink-0 relative group">
                    {thumb ? (
                      <>
                        <img
                          src={getThumbSrc(thumb.filename)}
                          alt="Miniaturka"
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform cursor-pointer"
                          onClick={() => setThumbLightbox({
                            url: getThumbSrc(thumb.filename),
                            path: thumb.path,
                            filename: thumb.filename,
                            videoFilename: out.filename,
                          })}
                        />
                        <button
                          type="button"
                          onClick={() => setThumbLightbox({
                            url: getThumbSrc(thumb.filename),
                            path: thumb.path,
                            filename: thumb.filename,
                            videoFilename: out.filename,
                          })}
                          className="absolute bottom-1 right-1 p-1 rounded bg-black/70 hover:bg-[#C8FF3A] text-white hover:text-black transition-colors"
                        >
                          <ImageIcon className="w-3 h-3"/>
                        </button>
                      </>
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center text-[#686E78] p-1 text-center gap-1">
                        <ImageIcon className="w-4 h-4 opacity-50"/>
                        <span className="text-[9px]">Brak miniaturki</span>
                        <button
                          type="button"
                          disabled={isOutThumbBusy}
                          onClick={() => handleRegenerateThumb(out.filename)}
                          className="px-1.5 py-0.5 rounded bg-[#17191C] hover:bg-[#C8FF3A] text-[#C8FF3A] hover:text-black text-[9px] font-bold border border-[#C8FF3A]/35 disabled:opacity-50"
                        >
                          {isOutThumbBusy ? "..." : "Generuj"}
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-bold text-[#FFFFFF] truncate" title={out.filename}>
                        <Film className="w-3.5 h-3.5 text-[#2ECC71] flex-shrink-0"/><span className="truncate">{out.filename}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-[11px] text-[#A0A7B1]">
                        <span>{out.size_mb} MB</span><span>•</span><span>{new Date(out.modified*1000).toLocaleDateString("pl-PL")}</span>
                      </div>
                    </div>
                    <div className="flex items-center flex-wrap gap-1.5 pt-2">
                      <button
                        type="button"
                        disabled={isOutThumbBusy}
                        onClick={() => handleTriggerThumbUpload(out.filename)}
                        className="flex items-center gap-1 px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] text-[10px] text-white font-semibold transition-colors disabled:opacity-50"
                      >
                        <Upload className="w-3 h-3 text-[#C8FF3A]" />Zmień
                      </button>
                      <button
                        type="button"
                        disabled={isOutThumbBusy}
                        onClick={() => handleRegenerateThumb(out.filename)}
                        className="flex items-center gap-1 px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] text-[10px] text-white font-semibold transition-colors disabled:opacity-50"
                      >
                        {isOutThumbBusy ? <Loader className="w-3 h-3 animate-spin text-[#C8FF3A]" /> : <RotateCcw className="w-3 h-3 text-[#C8FF3A]" />}Nowa
                      </button>
                      {thumb && (
                        <>
                          <button onClick={()=>handleCopyPath(thumb.path)} className="flex items-center gap-1 px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] text-[10px] text-[#C8FF3A] font-semibold transition-colors">
                            {copiedPath===thumb.path?<Check className="w-3 h-3 text-[#2ECC71]"/>:<Copy className="w-3 h-3"/>}{copiedPath===thumb.path?"Skopiowano!":"Ścieżka"}
                          </button>
                          <button onClick={()=>handleOpenFolder(thumb.path)} title="Pokaż w folderze" className="p-1 rounded bg-[#17191C] hover:bg-[#272A2F] text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors"><FolderOpen className="w-3.5 h-3.5"/></button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="pt-3 border-t border-white/5 flex items-center justify-between gap-2">
                  <button onClick={()=>handlePlay(out.filename)} className="text-xs bg-[#272A2F] hover:bg-[#272A2F] text-[#FFFFFF] font-semibold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5">
                    <Play className="w-3.5 h-3.5 fill-current"/>Podgląd
                  </button>
                  <div className="flex items-center gap-2">
                    <button onClick={()=>openEditModal(out.filename)} className="text-xs bg-[#272A2F] hover:bg-[#272A2F] text-[#C8FF3A] hover:text-[#FFFFFF] font-bold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 border border-[#C8FF3A]/30">
                      <Edit3 className="w-3.5 h-3.5"/>Edytuj
                    </button>
                    <button onClick={()=>openUploadModal(out.filename)} className="text-xs bg-[#C8FF3A] hover:bg-[#C8FF3A] text-[#050505] font-bold px-3.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5">
                      <Share2 className="w-3.5 h-3.5"/>Publikuj
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-[#686E78] py-16">
          <Video className="w-10 h-10 mb-2 opacity-40"/><p className="text-sm font-semibold">Brak wyrenderowanych filmów</p>
          <p className="text-xs mt-1 opacity-70">Uruchom pipeline renderowania przez Studio Klipów.</p>
        </div>
      )}
    </div>
  );
}
