import React, { useEffect, useState } from 'react';
import {
  Share2, X, Play, Image as ImageIcon, Upload, Loader, RotateCcw, FolderOpen,
  Check, Copy, Youtube, Video, Instagram, Zap, Clock,
} from 'lucide-react';
import {
  OutputItem, OvernightBatchManifest, PeakSlotInfo, OutputMetadata, TikTokCreatorInfo,
  apiGetNextPeakSlot, apiGetTikTokCreatorInfo, apiGetOutputUrl, apiGetOutputMetadata,
  apiPreviewSocialCopy, apiRecordCorrection, apiPublishMulti,
} from '../../lib/api';
import {
  ThumbLightboxData, buildLocalTiktokCopy, buildLocalIgCopy, buildLocalFbCopy,
} from './socialCopyHelpers';
import TikTokPublishPanel from './TikTokPublishPanel';

interface PublishMultiModalProps {
  filename: string | null;
  outputs: OutputItem[];
  latestBatch: OvernightBatchManifest | null;
  peakSlot: PeakSlotInfo | null;
  onPeakSlotUpdate: (slot: PeakSlotInfo) => void;
  ttLearningInfo: { analyzed_videos: number; recommended_hashtags: string[] } | null;
  thumbBusyFor: string | null;
  copiedPath: string | null;
  resolveThumbForVideo: (
    videoFilename: string,
    itemThumbPath?: string | null,
    itemThumbFilename?: string | null,
  ) => { filename: string; path: string | null } | null;
  getThumbSrc: (thumbFilename: string) => string;
  onOpenLightbox: (data: ThumbLightboxData) => void;
  onTriggerThumbUpload: (videoFilename: string) => void;
  onRegenerateThumb: (videoFilename: string) => void;
  onOpenFolder: (path: string) => void;
  onCopyPath: (path: string) => void;
  onClearThumbError: () => void;
  onRefreshOutputs: () => Promise<void>;
  onClose: () => void;
}

export default function PublishMultiModal({
  filename,
  outputs,
  latestBatch,
  peakSlot,
  onPeakSlotUpdate,
  ttLearningInfo,
  thumbBusyFor,
  copiedPath,
  resolveThumbForVideo,
  getThumbSrc,
  onOpenLightbox,
  onTriggerThumbUpload,
  onRegenerateThumb,
  onOpenFolder,
  onCopyPath,
  onClearThumbError,
  onRefreshOutputs,
  onClose,
}: PublishMultiModalProps) {
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadOriginalTitle, setUploadOriginalTitle] = useState('');
  const [uploadDesc, setUploadDesc] = useState(
    'Watch till the end 🔥\n\n🔔 Subscribe for daily LoL clips!\n👍 Leave a like if you enjoyed!\n\n#Shorts #LeagueOfLegends #LoL #Gaming'
  );
  const [uploadMode, setUploadMode] = useState<'peak' | 'now' | 'private'>('peak');
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ ok: boolean; url?: string; error?: string; scheduledFor?: string } | null>(null);
  const [selYt, setSelYt] = useState(true);
  const [selTt, setSelTt] = useState(true);
  const [selIg, setSelIg] = useState(true);
  const [selFb, setSelFb] = useState(true);
  const [ttPrivacy, setTtPrivacy] = useState<string>('PUBLIC_TO_EVERYONE');
  const [ttAllowComment, setTtAllowComment] = useState(true);
  const [ttAllowDuet, setTtAllowDuet] = useState(true);
  const [ttAllowStitch, setTtAllowStitch] = useState(true);
  const [ttDisclose, setTtDisclose] = useState(false);
  const [ttYourBrand, setTtYourBrand] = useState(false);
  const [ttBrandedContent, setTtBrandedContent] = useState(false);
  const [ttCreatorInfo, setTtCreatorInfo] = useState<TikTokCreatorInfo | null>(null);
  const [ttCreatorLoading, setTtCreatorLoading] = useState(false);
  const [ttPostMode, setTtPostMode] = useState<'direct' | 'inbox'>('direct');
  const [uploadPreviewUrl, setUploadPreviewUrl] = useState<string | null>(null);
  const [uploadVideoDurationSec, setUploadVideoDurationSec] = useState<number | null>(null);
  const [multiResults, setMultiResults] = useState<Record<string, any> | null>(null);
  const [partialPublishInfo, setPartialPublishInfo] = useState<{ done: string[]; missing: string[]; failed: Record<string, string> } | null>(null);
  const [forcePublishOverride, setForcePublishOverride] = useState(false);
  const [uploadModalMeta, setUploadModalMeta] = useState<OutputMetadata | null>(null);
  const [tiktokCopyText, setTiktokCopyText] = useState('');
  const [igCopyText, setIgCopyText] = useState('');
  const [fbCopyText, setFbCopyText] = useState('');
  const [tiktokCopied, setTiktokCopied] = useState(false);

  useEffect(() => {
    if (!filename) return;
    let active = true;

    setUploadResult(null);
    setMultiResults(null);
    onClearThumbError();
    setTiktokCopied(false);
    setForcePublishOverride(false);

    const outMatch = outputs.find((o) => o.filename === filename);
    const nightMatch = latestBatch?.items?.find(
      (it) => it.output_filename === filename || it.alternate_renders?.some((a) => a.output_filename === filename)
    );
    const donePlats = Array.from(
      new Set(
        [
          ...(outMatch?.published_platforms || []),
          ...(nightMatch?.published_platforms || []),
        ].map((p) => String(p).toLowerCase())
      )
    ).filter(Boolean);
    const failedMap: Record<string, string> = {
      ...(outMatch?.failed_platforms || {}),
      ...(nightMatch?.failed_platforms || {}),
    };
    const allPlats = ['youtube', 'tiktok', 'instagram', 'facebook'] as const;
    const missingPlats = allPlats.filter((p) => !donePlats.includes(p));
    if (donePlats.length > 0 && missingPlats.length > 0) {
      setSelYt(missingPlats.includes('youtube'));
      setSelTt(missingPlats.includes('tiktok'));
      setSelIg(missingPlats.includes('instagram'));
      setSelFb(missingPlats.includes('facebook'));
      setPartialPublishInfo({ done: donePlats, missing: [...missingPlats], failed: failedMap });
    } else {
      setSelYt(true);
      setSelTt(true);
      setSelIg(true);
      setSelFb(true);
      setPartialPublishInfo(null);
    }

    setTtPrivacy('PUBLIC_TO_EVERYONE');
    setTtAllowComment(true);
    setTtAllowDuet(true);
    setTtAllowStitch(true);
    setTtDisclose(false);
    setTtYourBrand(false);
    setTtBrandedContent(false);
    setTtPostMode('direct');
    setTtCreatorInfo(null);
    setTtCreatorLoading(true);
    setUploadPreviewUrl(null);
    setUploadVideoDurationSec(null);

    apiGetNextPeakSlot()
      .then((s) => { if (active && s) onPeakSlotUpdate(s); })
      .catch((err) => console.warn('[PublishMultiModal] apiGetNextPeakSlot error:', err));

    apiGetTikTokCreatorInfo()
      .then((info) => {
        if (!active) return;
        setTtCreatorInfo(info);
        if (info?.ok) {
          if (
            Array.isArray(info.privacy_level_options) &&
            info.privacy_level_options.length > 0 &&
            !info.privacy_level_options.includes('PUBLIC_TO_EVERYONE')
          ) {
            setTtPrivacy(info.privacy_level_options[0]);
          }
          if (info.comment_disabled) setTtAllowComment(false);
          if (info.duet_disabled) setTtAllowDuet(false);
          if (info.stitch_disabled) setTtAllowStitch(false);
        }
      })
      .catch((err) => {
        console.warn('[PublishMultiModal] apiGetTikTokCreatorInfo error:', err);
        if (active) setTtCreatorInfo(null);
      })
      .finally(() => { if (active) setTtCreatorLoading(false); });

    apiGetOutputUrl(filename)
      .then((u) => { if (active) setUploadPreviewUrl(u); })
      .catch((err) => console.warn('[PublishMultiModal] apiGetOutputUrl error:', err));

    apiGetOutputMetadata(filename)
      .then((meta) => {
        if (!active) return;
        setUploadModalMeta(meta);
        if (meta.duration && Number(meta.duration) > 0) {
          setUploadVideoDurationSec(Number(meta.duration));
        }
        const initialTitle = meta.title || 'Sick Play! #Shorts #LoL';
        setUploadTitle(initialTitle);
        setUploadOriginalTitle(initialTitle);
        setUploadDesc(meta.description || '');
        setTiktokCopyText(buildLocalTiktokCopy(initialTitle, meta.champion_name, meta.action_type));
        setIgCopyText(buildLocalIgCopy(initialTitle, meta.champion_name));
        setFbCopyText(buildLocalFbCopy(initialTitle, meta.champion_name));
        apiPreviewSocialCopy({
          title: initialTitle,
          champion_name: meta.champion_name || 'Katarina',
          action_type: meta.action_type || 'outplay',
        }).then((prev) => {
          if (!active) return;
          if (prev?.tiktok_copy_text) setTiktokCopyText(prev.tiktok_copy_text);
          if (prev?.copies?.instagram?.caption) setIgCopyText(prev.copies.instagram.caption);
          if (prev?.copies?.facebook?.caption) setFbCopyText(prev.copies.facebook.caption);
        }).catch((err) => console.warn('[PublishMultiModal] apiPreviewSocialCopy error:', err));
      })
      .catch((err) => {
        console.warn('[PublishMultiModal] apiGetOutputMetadata fallback:', err);
        if (!active) return;
        setUploadModalMeta(null);
        const fallbackTitle = 'Sick Play! #Shorts #LoL';
        setUploadTitle(fallbackTitle);
        setUploadOriginalTitle(fallbackTitle);
        setUploadDesc('');
        setTiktokCopyText(buildLocalTiktokCopy(fallbackTitle, 'Katarina', 'outplay'));
        setIgCopyText(buildLocalIgCopy(fallbackTitle, 'Katarina'));
        setFbCopyText(buildLocalFbCopy(fallbackTitle, 'Katarina'));
      });

    return () => { active = false; };
  }, [filename]);

  if (!filename) return null;

  const handleSelectPlatformPreset = (preset: 'yt' | 'tt' | 'ig' | 'fb' | 'all') => {
    setSelYt(preset === 'yt' || preset === 'all');
    setSelTt(preset === 'tt' || preset === 'all');
    setSelIg(preset === 'ig' || preset === 'all');
    setSelFb(preset === 'fb' || preset === 'all');
  };

  const handleCopyTiktokText = () => {
    if (!tiktokCopyText.trim()) return;
    navigator.clipboard.writeText(tiktokCopyText);
    setTiktokCopied(true);
    setTimeout(() => setTiktokCopied(false), 2000);
  };

  const modalThumb = resolveThumbForVideo(filename);
  const modalThumbBusy = thumbBusyFor === filename;
  const gateMatchCard = latestBatch?.items?.find(
    (it) => it.output_filename === filename || it.alternate_renders?.some((a) => a.output_filename === filename)
  );
  const gateMatchAlt = gateMatchCard?.alternate_renders?.find((a) => a.output_filename === filename);
  const gatePubRec =
    gateMatchAlt?.publish_recommended ??
    (gateMatchCard?.output_filename === filename ? gateMatchCard?.publish_recommended : undefined) ??
    (uploadModalMeta as any)?.publish_recommended;
  const gateBlockReasons: string[] =
    gateMatchAlt?.publish_block_reasons ??
    (gateMatchCard?.output_filename === filename ? gateMatchCard?.publish_block_reasons : undefined) ??
    (uploadModalMeta as any)?.publish_block_reasons ??
    [];
  const isBlockedByGate = gatePubRec === false;

  const handleUpload = async () => {
    const platforms: string[] = [];
    if (selYt) platforms.push('youtube');
    if (selTt) platforms.push('tiktok');
    if (selIg) platforms.push('instagram');
    if (selFb) platforms.push('facebook');

    if (platforms.length === 0) {
      setUploadResult({ ok: false, error: 'Wybierz przynajmniej jedną platformę do publikacji!' });
      return;
    }
    const maxTtSec = ttCreatorInfo?.ok ? ttCreatorInfo.max_video_post_duration_sec : undefined;
    if (selTt && maxTtSec && uploadVideoDurationSec && uploadVideoDurationSec > maxTtSec) {
      setUploadResult({ ok: false, error: `Video duration (${Math.round(uploadVideoDurationSec)}s) exceeds creator max (${maxTtSec}s).` });
      return;
    }
    if (selTt && ttPostMode === 'direct') {
      if (!ttPrivacy) {
        setUploadResult({ ok: false, error: 'Wybierz poziom prywatności TikTok (Who can view this video).' });
        return;
      }
      if (ttDisclose && !ttYourBrand && !ttBrandedContent) {
        setUploadResult({ ok: false, error: 'Przy zaznaczonym Disclose video content wybierz Your brand i/lub Branded content.' });
        return;
      }
      if (ttDisclose && ttBrandedContent && ttPrivacy === 'SELF_ONLY') {
        setUploadResult({ ok: false, error: 'Branded content nie może mieć widoczności Only you (SELF_ONLY).' });
        return;
      }
    }

    setUploading(true);
    setUploadResult(null);
    setMultiResults(null);
    try {
      let privacy = 'public';
      let publishAt: string | undefined;
      let scheduledLabel: string | undefined;
      if (uploadMode === 'peak' && peakSlot) {
        privacy = 'private';
        publishAt = peakSlot.publish_at;
        scheduledLabel = peakSlot.label;
      } else if (uploadMode === 'private') {
        privacy = 'private';
      }
      if (uploadTitle !== uploadOriginalTitle && uploadOriginalTitle) {
        apiRecordCorrection('title', uploadOriginalTitle, uploadTitle, 'ui_upload_modal');
      }

      const effectiveTitle =
        uploadTitle.trim() ||
        (selTt ? tiktokCopyText.trim().split('\n')[0] : '') ||
        (selIg ? igCopyText.trim().split('\n')[0] : '') ||
        (selFb ? fbCopyText.trim().split('\n')[0] : '') ||
        'LoL Highlight';

      const effectiveAllowComment = Boolean(ttAllowComment && !ttCreatorInfo?.comment_disabled);
      const effectiveAllowDuet = Boolean(ttAllowDuet && !ttCreatorInfo?.duet_disabled);
      const effectiveAllowStitch = Boolean(ttAllowStitch && !ttCreatorInfo?.stitch_disabled);

      const res = await apiPublishMulti(filename, {
        title: effectiveTitle,
        description: uploadDesc,
        tags: uploadModalMeta?.tags && uploadModalMeta.tags.length > 0 ? uploadModalMeta.tags : undefined,
        hashtags: uploadModalMeta?.hashtags && uploadModalMeta.hashtags.length > 0 ? uploadModalMeta.hashtags : undefined,
        platforms,
        privacy_yt: privacy,
        privacy_tiktok: selTt && ttPostMode === 'direct' ? ttPrivacy : undefined,
        share_to_ig_feed: true,
        thumbnail_path: modalThumb?.path || undefined,
        publish_at: publishAt,
        pinned_comment: uploadModalMeta?.pinned_comment,
        champion_name: uploadModalMeta?.champion_name,
        action_type: uploadModalMeta?.action_type,
        rank: uploadModalMeta?.rank,
        tiktok_caption: selTt ? tiktokCopyText : undefined,
        instagram_caption: selIg ? igCopyText : undefined,
        facebook_caption: selFb ? fbCopyText : undefined,
        tiktok_allow_comment: effectiveAllowComment,
        tiktok_allow_duet: effectiveAllowDuet,
        tiktok_allow_stitch: effectiveAllowStitch,
        tiktok_disclose_content: ttPostMode === 'direct' ? ttDisclose : false,
        tiktok_brand_organic: ttPostMode === 'direct' && ttDisclose && ttYourBrand,
        tiktok_branded_content: ttPostMode === 'direct' && ttDisclose && ttBrandedContent,
        tiktok_post_mode: ttPostMode,
        force_publish: forcePublishOverride,
      });

      const results = res.results || {};
      setMultiResults(results);

      const anySuccess = Object.values(results).some((r: any) => r && r.success);
      if (anySuccess) {
        setUploadResult({
          ok: true,
          url: results.youtube?.url || results.instagram?.url || results.facebook?.url || (results.tiktok?.publish_id ? `TikTok Publish ID: ${results.tiktok.publish_id}` : undefined),
          scheduledFor: scheduledLabel,
        });
        apiGetNextPeakSlot()
          .then((s) => { if (s) onPeakSlotUpdate(s); })
          .catch((err) => console.warn('[PublishMultiModal] refresh peak slot error:', err));
        onRefreshOutputs().catch((err) => console.warn('[PublishMultiModal] fetchOutputs refresh error:', err));
      } else {
        const firstErr = Object.values(results).map((r: any) => r?.error).filter(Boolean)[0] || 'Błąd publikacji';
        setUploadResult({ ok: false, error: String(firstErr) });
      }
    } catch (e: any) {
      setUploadResult({ ok: false, error: String(e) });
    } finally {
      setUploading(false);
    }
  };

  const anyPlatformSelected = selYt || selTt || selIg || selFb;
  const hasContentForSelected = Boolean(
    (selYt && uploadTitle.trim()) ||
    (!selYt && (
      (selTt && (tiktokCopyText.trim() || uploadTitle.trim())) ||
      (selIg && (igCopyText.trim() || uploadTitle.trim())) ||
      (selFb && (fbCopyText.trim() || uploadTitle.trim()))
    ))
  );
  const maxTtSec = ttCreatorInfo?.ok ? ttCreatorInfo.max_video_post_duration_sec : undefined;
  const ttDurationExceeded = Boolean(selTt && maxTtSec && uploadVideoDurationSec && uploadVideoDurationSec > maxTtSec);
  const ttPrivacyMissing = Boolean(selTt && ttPostMode === 'direct' && !ttPrivacy);
  const ttDiscloseMissingType = Boolean(selTt && ttPostMode === 'direct' && ttDisclose && !ttYourBrand && !ttBrandedContent);
  const ttBrandedSelfConflict = Boolean(selTt && ttPostMode === 'direct' && ttDisclose && ttBrandedContent && ttPrivacy === 'SELF_ONLY');
  const blockedByQualityGate = isBlockedByGate && !forcePublishOverride;
  const publishDisabled =
    uploading || !anyPlatformSelected || !hasContentForSelected ||
    ttDurationExceeded || ttPrivacyMissing || ttDiscloseMissingType ||
    ttBrandedSelfConflict || blockedByQualityGate;

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-[#0E0F11] border border-[#C8FF3A]/40 fk-cut p-6 w-full max-w-lg max-h-[92vh] overflow-y-auto space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-[#FFFFFF] flex items-center gap-2"><Share2 className="w-4 h-4 text-[#C8FF3A]" />Publikacja Multi-Platform</h2>
          <button onClick={onClose} className="text-[#A0A7B1] hover:text-[#FFFFFF]"><X className="w-4 h-4" /></button>
        </div>
        <div className="text-xs text-[#A0A7B1] bg-[#050505] rounded-lg px-3 py-2 font-mono truncate">{filename}</div>

        {isBlockedByGate && (
          <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/50 text-[11px] text-red-200 space-y-2">
            <div className="font-bold text-red-300">
              ⛔ Klip odradzany przez bramkę jakości (`publish_recommended=False`)
            </div>
            {gateBlockReasons.length > 0 && (
              <div className="text-[10px] font-mono text-red-200/90 break-words">
                Powody: {gateBlockReasons.join(', ')}
              </div>
            )}
            <label className="flex items-center gap-2 cursor-pointer select-none pt-0.5 text-[11px] text-white font-semibold">
              <input
                type="checkbox"
                checked={forcePublishOverride}
                onChange={(e) => setForcePublishOverride(e.target.checked)}
                className="accent-red-500"
              />
              <span>Rozumiem ryzyko — wymuś publikację mimo odrzucenia bramki (force_publish)</span>
            </label>
          </div>
        )}

        {partialPublishInfo && (
          <div className="p-2.5 rounded-lg bg-amber-500/15 border border-amber-400/50 text-[11px] text-amber-200 space-y-0.5">
            <div className="font-bold">
              ⚠️ Częściowo opublikowano ({partialPublishInfo.done.map((p) => p.toUpperCase()).join('+')}) — domyślnie zaznaczono tylko brakujące ({partialPublishInfo.missing.map((p) => p.toUpperCase()).join('+')}).
            </div>
            {Object.keys(partialPublishInfo.failed).length > 0 && (
              <div className="text-[10px] text-amber-300/90 font-mono truncate" title={JSON.stringify(partialPublishInfo.failed)}>
                Ostatni błąd: {Object.entries(partialPublishInfo.failed).map(([k, v]) => `${k.toUpperCase()}: ${v}`).join(' | ')}
              </div>
            )}
          </div>
        )}

        {uploadPreviewUrl && (
          <div className="bg-[#050505] border border-[#272A2F] rounded-lg p-2 space-y-1">
            <div className="flex items-center justify-between text-[10px] text-[#A0A7B1]">
              <span className="font-bold text-[#C8FF3A] flex items-center gap-1"><Play className="w-3 h-3" />Video Preview</span>
              {uploadVideoDurationSec ? (
                <span className="font-mono">{uploadVideoDurationSec.toFixed(1)}s</span>
              ) : null}
            </div>
            <video
              src={uploadPreviewUrl}
              controls
              preload="metadata"
              onLoadedMetadata={(e) => {
                const dur = e.currentTarget.duration;
                if (Number.isFinite(dur) && dur > 0) setUploadVideoDurationSec(dur);
              }}
              className="w-full max-h-52 rounded bg-black object-contain"
            />
          </div>
        )}

        {/* Miniaturka 9:16 podpięta do publikacji */}
        <div className="p-3 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center gap-3">
          <div className="w-16 aspect-[9/16] rounded-md bg-[#0E0F11] border border-[#272A2F] overflow-hidden flex-shrink-0 relative group">
            {modalThumb ? (
              <img
                src={getThumbSrc(modalThumb.filename)}
                alt="Miniaturka 9:16"
                onClick={() => onOpenLightbox({
                  url: getThumbSrc(modalThumb.filename),
                  path: modalThumb.path,
                  filename: modalThumb.filename,
                  videoFilename: filename,
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
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${modalThumb ? 'bg-[#2ECC71]/15 text-[#55E88D]' : 'bg-amber-500/15 text-amber-300'}`}>
                {modalThumb ? 'Gotowa do uploadu' : 'Brak miniaturki'}
              </span>
            </div>
            <div className="text-[10px] font-mono text-[#A0A7B1] truncate" title={modalThumb?.path || modalThumb?.filename || ''}>
              {modalThumb ? modalThumb.filename : 'Kliknij „Wygeneruj nową” albo „Zmień plik” (JPG/PNG/WebP).'}
            </div>
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              <button
                type="button"
                disabled={modalThumbBusy}
                onClick={() => onTriggerThumbUpload(filename)}
                className="px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[10px] font-bold text-white flex items-center gap-1 disabled:opacity-50"
              >
                <Upload className="w-3 h-3 text-[#C8FF3A]" />Zmień plik
              </button>
              <button
                type="button"
                disabled={modalThumbBusy}
                onClick={() => onRegenerateThumb(filename)}
                className="px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[10px] font-bold text-white flex items-center gap-1 disabled:opacity-50"
              >
                {modalThumbBusy ? <Loader className="w-3 h-3 animate-spin text-[#C8FF3A]" /> : <RotateCcw className="w-3 h-3 text-[#C8FF3A]" />}
                Wygeneruj nową
              </button>
              {modalThumb?.path && (
                <>
                  <button
                    type="button"
                    onClick={() => onOpenFolder(modalThumb.path!)}
                    title="Pokaż w folderze"
                    className="px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[10px] font-semibold text-[#A0A7B1] hover:text-white flex items-center gap-1"
                  >
                    <FolderOpen className="w-3 h-3" />Folder
                  </button>
                  <button
                    type="button"
                    onClick={() => onCopyPath(modalThumb.path!)}
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

        {/* Wybór platformy */}
        <div className="space-y-2 pt-0.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-[#A0A7B1] flex items-center gap-1.5">
              <Share2 className="w-3.5 h-3.5 text-[#C8FF3A]" /> Gdzie wrzucać (Wybór / Presety):
            </label>
            <span className="text-[10px] text-[#C8FF3A] font-mono font-bold">
              Wybrano ({[selYt, selTt, selIg, selFb].filter(Boolean).length}/4): {[selYt && 'YT', selTt && 'TikTok', selIg && 'IG', selFb && 'FB'].filter(Boolean).join(' + ') || 'Brak'}
            </span>
          </div>

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
              <div className="flex items-center gap-1 text-xs font-bold"><Youtube className="w-3.5 h-3.5 text-[#FF0000]" /><span>1. YouTube</span></div>
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
              <div className="flex items-center gap-1 text-xs font-bold"><Video className="w-3.5 h-3.5 text-[#00F2FE]" /><span>2. TikTok</span></div>
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
              <div className="flex items-center gap-1 text-xs font-bold"><Instagram className="w-3.5 h-3.5 text-[#E1306C]" /><span>3. Instagram</span></div>
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
              <div className="flex items-center gap-1 text-xs font-bold"><Share2 className="w-3.5 h-3.5 text-[#1877F2]" /><span>4. Facebook</span></div>
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
              <div className="flex items-center gap-1 text-xs font-black text-[#C8FF3A]"><Zap className="w-3.5 h-3.5" /><span>5. WSZYSTKO</span></div>
              <span className="text-[9px] text-[#C8FF3A] font-semibold">Wszystkie 4</span>
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
            <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${selYt ? 'bg-[#FF0000]/15 border-[#FF0000]/60 text-white' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1]'}`}>
              <input type="checkbox" checked={selYt} onChange={(e) => setSelYt(e.target.checked)} className="accent-[#FF0000]" />
              <span className="text-xs font-bold flex items-center gap-1"><Youtube className="w-3.5 h-3.5 text-[#FF0000]" /> YouTube</span>
            </label>
            <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${selTt ? 'bg-[#00F2FE]/15 border-[#00F2FE]/60 text-white' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1]'}`}>
              <input type="checkbox" checked={selTt} onChange={(e) => setSelTt(e.target.checked)} className="accent-[#00F2FE]" />
              <span className="text-xs font-bold flex items-center gap-1"><Video className="w-3.5 h-3.5 text-[#00F2FE]" /> TikTok</span>
            </label>
            <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${selIg ? 'bg-[#E1306C]/15 border-[#E1306C]/60 text-white' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1]'}`}>
              <input type="checkbox" checked={selIg} onChange={(e) => setSelIg(e.target.checked)} className="accent-[#E1306C]" />
              <span className="text-xs font-bold flex items-center gap-1"><Instagram className="w-3.5 h-3.5 text-[#E1306C]" /> Instagram</span>
            </label>
            <label className={`flex items-center gap-2 p-2 fk-cut-sm border cursor-pointer select-none transition-all ${selFb ? 'bg-[#1877F2]/15 border-[#1877F2]/60 text-white' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1]'}`}>
              <input type="checkbox" checked={selFb} onChange={(e) => setSelFb(e.target.checked)} className="accent-[#1877F2]" />
              <span className="text-xs font-bold flex items-center gap-1"><Share2 className="w-3.5 h-3.5 text-[#1877F2]" /> Facebook</span>
            </label>
          </div>
        </div>

        {selYt && (
          <div className="space-y-1">
            <label className="text-xs font-semibold text-[#C8FF3A]">Tytuł (YouTube Shorts)</label>
            <input
              value={uploadTitle}
              onChange={(e) => {
                const val = e.target.value;
                setUploadTitle(val);
                setTiktokCopyText(buildLocalTiktokCopy(val, uploadModalMeta?.champion_name, uploadModalMeta?.action_type));
              }}
              className="w-full bg-[#050505] border border-[#272A2F] rounded-lg px-3 py-2 text-sm text-[#FFFFFF] focus:border-[#C8FF3A] outline-none"
              placeholder="Tytuł wideo..."
            />
          </div>
        )}

        {selTt && (
          <TikTokPublishPanel
            ttCreatorInfo={ttCreatorInfo}
            ttCreatorLoading={ttCreatorLoading}
            uploadVideoDurationSec={uploadVideoDurationSec}
            ttPostMode={ttPostMode}
            setTtPostMode={setTtPostMode}
            ttLearningInfo={ttLearningInfo}
            uploadModalMeta={uploadModalMeta}
            tiktokCopyText={tiktokCopyText}
            setTiktokCopyText={setTiktokCopyText}
            tiktokCopied={tiktokCopied}
            onCopyTiktokText={handleCopyTiktokText}
            ttPrivacy={ttPrivacy}
            setTtPrivacy={setTtPrivacy}
            ttAllowComment={ttAllowComment}
            setTtAllowComment={setTtAllowComment}
            ttAllowDuet={ttAllowDuet}
            setTtAllowDuet={setTtAllowDuet}
            ttAllowStitch={ttAllowStitch}
            setTtAllowStitch={setTtAllowStitch}
            ttDisclose={ttDisclose}
            setTtDisclose={setTtDisclose}
            ttYourBrand={ttYourBrand}
            setTtYourBrand={setTtYourBrand}
            ttBrandedContent={ttBrandedContent}
            setTtBrandedContent={setTtBrandedContent}
          />
        )}

        {selIg && (
          <div className="space-y-1.5 bg-[#E1306C]/5 border border-[#E1306C]/30 rounded-lg p-3">
            <label className="text-[11px] font-bold text-[#E1306C] flex items-center gap-1.5">
              <Instagram className="w-3.5 h-3.5" /> Instagram Reels (@dwannellenga — osobny opis i tagi IG)
            </label>
            <textarea
              value={igCopyText}
              onChange={(e) => setIgCopyText(e.target.value)}
              rows={2}
              className="w-full bg-[#050505] border border-[#272A2F] rounded px-2.5 py-1.5 text-[11px] text-[#FFFFFF] focus:border-[#E1306C] outline-none resize-none font-mono"
            />
          </div>
        )}

        {selFb && (
          <div className="space-y-1.5 bg-[#1877F2]/5 border border-[#1877F2]/30 rounded-lg p-3">
            <label className="text-[11px] font-bold text-[#1877F2] flex items-center gap-1.5">
              <Share2 className="w-3.5 h-3.5" /> Facebook Fanpage (Dwannellenga — osobny post FB)
            </label>
            <textarea
              value={fbCopyText}
              onChange={(e) => setFbCopyText(e.target.value)}
              rows={2}
              className="w-full bg-[#050505] border border-[#272A2F] rounded px-2.5 py-1.5 text-[11px] text-[#FFFFFF] focus:border-[#1877F2] outline-none resize-none font-mono"
            />
          </div>
        )}

        {selYt && (
          <div className="space-y-1">
            <label className="text-xs font-semibold text-[#C8FF3A]">Opis / Hashtagi (YouTube)</label>
            <textarea value={uploadDesc} onChange={(e) => setUploadDesc(e.target.value)} rows={3} className="w-full bg-[#050505] border border-[#272A2F] rounded-lg px-3 py-2 text-xs text-[#FFFFFF] focus:border-[#C8FF3A] outline-none resize-none" />
          </div>
        )}

        <div className="space-y-2 pt-1">
          <label className="text-xs font-semibold text-[#A0A7B1] flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-[#C8FF3A]" />
            Tryb Publikacji ({[selYt && 'YouTube', selTt && 'TikTok', selIg && 'Instagram', selFb && 'Facebook'].filter(Boolean).join(' + ') || 'Brak'}):
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button type="button" onClick={() => setUploadMode('peak')} className={`p-2 fk-cut-sm border text-left transition-all ${uploadMode === 'peak' ? 'bg-[#C8FF3A]/15 border-[#C8FF3A] text-[#FFFFFF]' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#C8FF3A]/40'}`}>
              <div className="flex items-center justify-between"><span className="text-xs font-bold text-[#C8FF3A] flex items-center gap-1"><Zap className="w-3 h-3" />AI Peak Slot</span><span className="text-[9px] bg-[#2ECC71]/20 text-[#2ECC71] px-1 rounded font-bold">TOP</span></div>
              <div className="text-[11px] font-semibold text-[#FFFFFF] mt-0.5 truncate">{peakSlot?.label || 'Dziś o 21:30 CET'}</div>
            </button>
            <button type="button" onClick={() => setUploadMode('now')} className={`p-2 fk-cut-sm border text-left transition-all ${uploadMode === 'now' ? 'bg-[#2ECC71]/15 border-[#2ECC71] text-[#FFFFFF]' : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:border-[#2ECC71]/40'}`}>
              <div className="text-xs font-bold text-[#2ECC71]">Opublikuj Teraz</div>
              <div className="text-[11px] font-semibold text-[#FFFFFF] mt-0.5">Publiczny od razu</div>
            </button>
          </div>
        </div>

        {uploadResult && (() => {
          const multiEntries = multiResults
            ? (['youtube', 'tiktok', 'instagram', 'facebook'] as const).map((k) => multiResults[k]).filter(Boolean)
            : [];
          const okCount = multiEntries.filter((v) => v?.success).length;
          const failCount = multiEntries.filter((v) => v && !v.success).length;
          const isPartialSuccess = Boolean(uploadResult.ok && failCount > 0);
          const boxCls = !uploadResult.ok
            ? 'bg-red-500/10 text-red-400 border border-red-500/30'
            : isPartialSuccess
            ? 'bg-[#FFB347]/15 text-[#FFD89B] border border-[#FFB347]/50'
            : 'bg-[#2ECC71]/10 text-[#2ECC71] border border-[#2ECC71]/30';

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
                        <div className={`break-words [overflow-wrap:anywhere] ${multiResults.youtube.success ? 'text-[#55E88D]' : 'text-[#FF5C5C]'}`}>
                          • YouTube: {multiResults.youtube.success ? `✅ Wgrano (${multiResults.youtube.url})` : `❌ ${multiResults.youtube.error}`}
                        </div>
                      )}
                      {multiResults.tiktok && (
                        <div className={`break-words [overflow-wrap:anywhere] ${
                          !multiResults.tiktok.success
                            ? 'text-[#FFB347]'
                            : (multiResults.tiktok.queued || multiResults.tiktok.is_scheduled)
                            ? 'text-[#C8FF3A]'
                            : 'text-[#55E88D]'
                        }`}>
                          • TikTok: {multiResults.tiktok.success
                            ? ((multiResults.tiktok.queued || multiResults.tiktok.is_scheduled)
                              ? `🕒 Zakolejkowano (${multiResults.tiktok.publish_at || uploadResult.scheduledFor || 'kolejka 24/7'})`
                              : (multiResults.tiktok.inbox || multiResults.tiktok.post_mode === 'inbox')
                              ? `⚠️ Wysłano do INBOX/szkiców na telefonie (${multiResults.tiktok.publish_id || 'inbox'}) — wymaga ręcznej publikacji`
                              : `✅ Opublikowano (${multiResults.tiktok.publish_id || 'OK'})`)
                            : `⚠️ ${multiResults.tiktok.error}`}
                        </div>
                      )}
                      {multiResults.instagram && (
                        <div className={`break-words [overflow-wrap:anywhere] ${
                          !multiResults.instagram.success
                            ? 'text-[#FF5C5C]'
                            : (multiResults.instagram.queued || multiResults.instagram.is_scheduled)
                            ? 'text-[#C8FF3A]'
                            : 'text-[#55E88D]'
                        }`}>
                          • Instagram: {multiResults.instagram.success
                            ? ((multiResults.instagram.queued || multiResults.instagram.is_scheduled)
                              ? `🕒 Zakolejkowano (${multiResults.instagram.publish_at || uploadResult.scheduledFor || 'kolejka 24/7'})`
                              : `✅ Reel opublikowany (${multiResults.instagram.url || 'OK'})`)
                            : `❌ ${multiResults.instagram.error}`}
                        </div>
                      )}
                      {multiResults.facebook && (
                        <div className={`break-words [overflow-wrap:anywhere] ${
                          !multiResults.facebook.success
                            ? 'text-[#FF5C5C]'
                            : (multiResults.facebook.queued || multiResults.facebook.is_scheduled)
                            ? 'text-[#C8FF3A]'
                            : 'text-[#55E88D]'
                        }`}>
                          • Facebook: {multiResults.facebook.success
                            ? ((multiResults.facebook.queued || multiResults.facebook.is_scheduled)
                              ? `🕒 Zakolejkowano (${multiResults.facebook.publish_at || uploadResult.scheduledFor || 'kolejka 24/7'})`
                              : `✅ Fanpage opublikowano (${multiResults.facebook.url || multiResults.facebook.video_id || 'OK'})`)
                            : `❌ ${multiResults.facebook.error}`}
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
          <button onClick={onClose} className="flex-1 py-2 fk-cut-sm border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF] font-semibold">Anuluj</button>
          <button
            onClick={handleUpload}
            disabled={publishDisabled}
            className="flex-1 py-2.5 fk-cut-sm bg-[#C8FF3A] hover:bg-[#C8FF3A] disabled:opacity-50 text-[#050505] text-xs font-bold flex items-center justify-center gap-1.5 transition-all"
          >
            {uploading ? <Loader className="w-3.5 h-3.5 animate-spin" /> : <Share2 className="w-3.5 h-3.5" />}
            {uploading
              ? 'Publikuję...'
              : blockedByQualityGate
              ? '⛔ Zablokowane przez bramkę (zaznacz wymuszenie)'
              : !anyPlatformSelected
              ? '⚠️ Zaznacz platformę'
              : ttDurationExceeded
              ? 'Wideo przekracza limit TikTok'
              : ttPrivacyMissing
              ? 'Wybierz prywatność TikTok'
              : ttDiscloseMissingType
              ? 'Wybierz Your brand / Branded content'
              : ttBrandedSelfConflict
              ? 'Zmień prywatność z Only you'
              : selYt && selTt && selIg && selFb
              ? '🚀 Opublikuj na WSZYSTKO (4 platformy)'
              : selYt && !selTt && !selIg && !selFb
              ? '🚀 Opublikuj na YouTube Shorts'
              : !selYt && selTt && !selIg && !selFb
              ? '🚀 Opublikuj na TikTok'
              : !selYt && !selTt && selIg && !selFb
              ? '🚀 Opublikuj na Instagram Reels'
              : !selYt && !selTt && !selIg && selFb
              ? '🚀 Opublikuj na Facebook Page'
              : `🚀 Opublikuj (${[selYt && 'YT', selTt && 'TT', selIg && 'IG', selFb && 'FB'].filter(Boolean).join(' + ')})`}
          </button>
        </div>
      </div>
    </div>
  );
}
