import React, { useEffect, useState, useRef } from 'react';
import {
  apiListOutputs, OutputItem, apiGetOutputUrl, apiListThumbnails,
  ThumbnailItem, apiGetNextPeakSlot, PeakSlotInfo, apiGetLatestOvernight,
  OvernightBatchManifest, apiRestyleOvernightShort, ViralMontageStyle,
  apiGetBackendBaseUrl, apiUploadOutputThumbnail, apiRegenerateOutputThumbnail,
  apiGetSocialAnalytics, parseError,
} from '../lib/api';
import {
  Video, RefreshCw, Upload, Play, Film, FolderOpen, Image as ImageIcon,
  Copy, Check, X, Loader, RotateCcw, AlertTriangle, Edit3, Share2,
} from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ThumbLightboxData, basenameOf } from '../components/outputs/socialCopyHelpers';
import ThumbnailLightbox from '../components/outputs/ThumbnailLightbox';
import EditMetadataModal from '../components/outputs/EditMetadataModal';
import OvernightBatchSection from '../components/outputs/OvernightBatchSection';
import PublishMultiModal from '../components/outputs/PublishMultiModal';

export default function Outputs() {
  const navigate = useNavigate();
  const location = useLocation();
  const handledNavKeyRef = useRef<string | null>(null);
  const [outputs, setOutputs] = useState<OutputItem[]>([]);
  const [thumbnails, setThumbnails] = useState<ThumbnailItem[]>([]);
  const [latestBatch, setLatestBatch] = useState<OvernightBatchManifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedVideoUrl, setSelectedVideoUrl] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [backendUrl, setBackendUrl] = useState<string>('http://127.0.0.1:8765');
  const [thumbVersion, setThumbVersion] = useState<number>(() => Date.now());
  const [thumbBusyFor, setThumbBusyFor] = useState<string | null>(null);
  const [thumbError, setThumbError] = useState<string | null>(null);
  const [restyleBusyFor, setRestyleBusyFor] = useState<string | null>(null);
  const [restyleError, setRestyleError] = useState<string | null>(null);
  const [selectedVariantByCard, setSelectedVariantByCard] = useState<Record<string, string>>({});
  const [thumbLightbox, setThumbLightbox] = useState<ThumbLightboxData | null>(null);
  const thumbFileInputRef = useRef<HTMLInputElement | null>(null);
  const thumbUploadTargetRef = useRef<string | null>(null);

  const [uploadFilename, setUploadFilename] = useState<string | null>(null);
  const [editModal, setEditModal] = useState<string | null>(null);
  const [peakSlot, setPeakSlot] = useState<PeakSlotInfo | null>(null);
  const [ttLearningInfo, setTtLearningInfo] = useState<{ analyzed_videos: number; recommended_hashtags: string[] } | null>(null);

  const fetchOutputs = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [baseUrl, outData, thumbData, slotData, nightData] = await Promise.all([
        apiGetBackendBaseUrl().catch((err) => { console.warn('[Outputs] apiGetBackendBaseUrl fallback:', err); return 'http://127.0.0.1:8765'; }),
        apiListOutputs(),
        apiListThumbnails(),
        apiGetNextPeakSlot().catch((err) => { console.warn('[Outputs] apiGetNextPeakSlot error:', err); return null; }),
        apiGetLatestOvernight().catch((err) => { console.warn('[Outputs] apiGetLatestOvernight error:', err); return null; }),
      ]);
      setBackendUrl((baseUrl || 'http://127.0.0.1:8765').replace(/\/$/, ''));
      setOutputs(outData);
      setThumbnails(thumbData);
      if (slotData) setPeakSlot(slotData);
      setLatestBatch(nightData?.batch || null);
      setThumbVersion(Date.now());
    } catch (err: any) {
      console.warn('[Outputs] fetchOutputs error:', err);
      setLoadError(parseError(err) || 'Nie udało się pobrać listy wyrenderowanych filmów.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchOutputs(); }, []);

  useEffect(() => {
    let active = true;
    apiGetSocialAnalytics('tiktok', false)
      .then((res) => {
        const learning = res?.tiktok_learning;
        if (active && learning) {
          setTtLearningInfo({
            analyzed_videos: Number(learning.analyzed_videos || 0),
            recommended_hashtags: Array.isArray(learning.recommended_hashtags)
              ? learning.recommended_hashtags.map((t: any) => String(t).replace(/^#/, '').toLowerCase()).filter(Boolean)
              : [],
          });
        }
      })
      .catch((err) => console.warn('[Outputs] tiktok learning fetch error:', err));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const st = (location.state || {}) as { publishFilename?: string; playFilename?: string };
    const targetPub = st.publishFilename;
    const targetPlay = st.playFilename;
    if (!targetPub && !targetPlay) return;
    const navKey = `${location.key}:${targetPub || ''}:${targetPlay || ''}`;
    if (handledNavKeyRef.current === navKey) return;
    handledNavKeyRef.current = navKey;
    if (targetPlay) handlePlay(targetPlay);
    if (targetPub) setUploadFilename(targetPub);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.key, location.pathname, location.state]);

  const handlePlay = async (filename: string) => {
    try {
      const url = await apiGetOutputUrl(filename);
      setSelectedVideoUrl(url);
      setTimeout(() => {
        document.querySelector('video')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 120);
    } catch (err) {
      console.warn('[Outputs] handlePlay error:', err);
    }
  };

  const findMatchingThumb = (videoFilename: string) => {
    const base = videoFilename.replace(/\.mp4$/i, '').toLowerCase();
    return thumbnails.find((t) => t.filename.toLowerCase().includes(base) || t.associated_video.toLowerCase() === videoFilename.toLowerCase());
  };

  const resolveThumbForVideo = (
    videoFilename: string,
    itemThumbPath?: string | null,
    itemThumbFilename?: string | null,
  ): { filename: string; path: string | null } | null => {
    const match = findMatchingThumb(videoFilename);
    const nightItem = latestBatch?.items?.find((it) => it.output_filename === videoFilename);
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
      thumbFileInputRef.current.value = '';
      thumbFileInputRef.current.click();
    }
  };

  const handleThumbFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const targetVideo = thumbUploadTargetRef.current;
    e.target.value = '';
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
  const handleCopyPath = (p: string) => {
    navigator.clipboard.writeText(p);
    setCopiedPath(p);
    setTimeout(() => setCopiedPath(null), 2000);
  };

  const handleRestyleOvernight = async (outputFilename: string, targetStyle: ViralMontageStyle, cardKey?: string) => {
    const busyKey = cardKey || outputFilename;
    setRestyleBusyFor(`${busyKey}:${targetStyle}`);
    setRestyleError(null);
    try {
      const res = await apiRestyleOvernightShort({
        output_filename: outputFilename,
        target_style: targetStyle,
      });
      await fetchOutputs();
      if (cardKey) {
        setSelectedVariantByCard((prev) => {
          const next = { ...prev };
          delete next[cardKey];
          return next;
        });
      }
      if (res?.item?.output_filename && res.item.render_ok) {
        handlePlay(res.item.output_filename);
      }
    } catch (err) {
      setRestyleError(`Nie udało się przerenderować (${targetStyle}): ${parseError(err)}`);
    } finally {
      setRestyleBusyFor(null);
    }
  };

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
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#C8FF3A]' : ''}`} />Odśwież listę
        </button>
      </div>

      {loadError && (
        <div className="p-3 fk-cut-sm bg-red-500/10 border border-red-500/40 text-xs text-red-300 flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 min-w-0 break-words">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 text-red-400" />
            <span>{loadError}</span>
          </span>
          <button type="button" onClick={fetchOutputs} className="px-2.5 py-1 rounded bg-red-500/20 hover:bg-red-500/30 text-red-100 font-bold text-[11px] flex-shrink-0">
            Ponów
          </button>
        </div>
      )}

      {thumbError && (
        <div className="p-3 fk-cut-sm bg-red-500/10 border border-red-500/40 text-xs text-red-300 flex items-center justify-between gap-2">
          <span className="break-words">{thumbError}</span>
          <button onClick={() => setThumbError(null)} className="text-red-200 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
      )}

      <ThumbnailLightbox
        thumbLightbox={thumbLightbox}
        thumbBusyFor={thumbBusyFor}
        onClose={() => setThumbLightbox(null)}
        onTriggerUpload={handleTriggerThumbUpload}
        onRegenerate={handleRegenerateThumb}
        onOpenImage={handleOpenImage}
        onOpenFolder={handleOpenFolder}
      />

      <PublishMultiModal
        filename={uploadFilename}
        outputs={outputs}
        latestBatch={latestBatch}
        peakSlot={peakSlot}
        onPeakSlotUpdate={setPeakSlot}
        ttLearningInfo={ttLearningInfo}
        thumbBusyFor={thumbBusyFor}
        copiedPath={copiedPath}
        resolveThumbForVideo={resolveThumbForVideo}
        getThumbSrc={getThumbSrc}
        onOpenLightbox={setThumbLightbox}
        onTriggerThumbUpload={handleTriggerThumbUpload}
        onRegenerateThumb={handleRegenerateThumb}
        onOpenFolder={handleOpenFolder}
        onCopyPath={handleCopyPath}
        onClearThumbError={() => setThumbError(null)}
        onRefreshOutputs={fetchOutputs}
        onClose={() => setUploadFilename(null)}
      />

      <EditMetadataModal
        filename={editModal}
        onClose={() => setEditModal(null)}
        onRerenderStarted={() => { setEditModal(null); navigate('/render'); }}
      />

      {selectedVideoUrl && (
        <div className="p-5 fk-cut bg-[#0E0F11] border border-[#C8FF3A]/40 flex flex-col items-center">
          <div className="w-full flex justify-between items-center mb-4">
            <span className="text-xs font-extrabold tracking-wide uppercase text-[#FFFFFF] flex items-center gap-2">
              <span className="fk-slash h-3.5 w-1.5" />
              Odtwarzacz Short (9:16)
            </span>
            <button onClick={() => setSelectedVideoUrl(null)} className="fk-btn-ghost text-xs font-bold text-[#A0A7B1] hover:text-[#FFFFFF] px-3 py-1 bg-[#272A2F]">Zamknij</button>
          </div>
          <div className="fk-crn my-2">
            <video src={selectedVideoUrl} controls autoPlay className="h-[460px] fk-cut-sm border border-[#272A2F] bg-black block" />
          </div>
        </div>
      )}

      {latestBatch && latestBatch.items && latestBatch.items.length > 0 && (
        <OvernightBatchSection
          latestBatch={latestBatch}
          selectedVariantByCard={selectedVariantByCard}
          setSelectedVariantByCard={setSelectedVariantByCard}
          thumbBusyFor={thumbBusyFor}
          restyleBusyFor={restyleBusyFor}
          restyleError={restyleError}
          onClearRestyleError={() => setRestyleError(null)}
          resolveThumbForVideo={resolveThumbForVideo}
          getThumbSrc={getThumbSrc}
          onOpenLightbox={setThumbLightbox}
          onTriggerThumbUpload={handleTriggerThumbUpload}
          onRegenerateThumb={handleRegenerateThumb}
          onOpenFolder={handleOpenFolder}
          onPlay={handlePlay}
          onOpenUpload={setUploadFilename}
          onRestyle={handleRestyleOvernight}
        />
      )}

      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center text-[#A0A7B1] py-16">
          <RefreshCw className="w-8 h-8 animate-spin text-[#C8FF3A] mb-2" /><p className="text-xs">Ładowanie biblioteki...</p>
        </div>
      ) : outputs.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {outputs.map((out) => {
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
                          <ImageIcon className="w-3 h-3" />
                        </button>
                      </>
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center text-[#686E78] p-1 text-center gap-1">
                        <ImageIcon className="w-4 h-4 opacity-50" />
                        <span className="text-[9px]">Brak miniaturki</span>
                        <button
                          type="button"
                          disabled={isOutThumbBusy}
                          onClick={() => handleRegenerateThumb(out.filename)}
                          className="px-1.5 py-0.5 rounded bg-[#17191C] hover:bg-[#C8FF3A] text-[#C8FF3A] hover:text-black text-[9px] font-bold border border-[#C8FF3A]/35 disabled:opacity-50"
                        >
                          {isOutThumbBusy ? '...' : 'Generuj'}
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-bold text-[#FFFFFF] truncate" title={out.filename}>
                        <Film className="w-3.5 h-3.5 text-[#2ECC71] flex-shrink-0" /><span className="truncate">{out.filename}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-[11px] text-[#A0A7B1] flex-wrap">
                        <span>{out.size_mb} MB</span><span>•</span><span>{new Date(out.modified * 1000).toLocaleDateString('pl-PL')}</span>
                        {out.can_retry_publish ? (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-400/50 text-amber-300 font-bold">
                            ⚠️ Brak: {(out.missing_platforms || []).map((p) => p.toUpperCase()).join('+') || 'YT'}
                          </span>
                        ) : out.already_published && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2ECC71]/20 border border-[#2ECC71]/40 text-[#2ECC71] font-bold">
                            ✅ {(out.published_platforms || []).length > 0 ? out.published_platforms!.join('+').toUpperCase() : 'OPUBL./KOLEJKA'}
                          </span>
                        )}
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
                          <button onClick={() => handleCopyPath(thumb.path)} className="flex items-center gap-1 px-2 py-1 rounded bg-[#17191C] hover:bg-[#272A2F] text-[10px] text-[#C8FF3A] font-semibold transition-colors">
                            {copiedPath === thumb.path ? <Check className="w-3 h-3 text-[#2ECC71]" /> : <Copy className="w-3 h-3" />}{copiedPath === thumb.path ? 'Skopiowano!' : 'Ścieżka'}
                          </button>
                          <button onClick={() => handleOpenFolder(thumb.path)} title="Pokaż w folderze" className="p-1 rounded bg-[#17191C] hover:bg-[#272A2F] text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors"><FolderOpen className="w-3.5 h-3.5" /></button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="pt-3 border-t border-white/5 flex items-center justify-between gap-2">
                  <button onClick={() => handlePlay(out.filename)} className="text-xs bg-[#272A2F] hover:bg-[#272A2F] text-[#FFFFFF] font-semibold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5">
                    <Play className="w-3.5 h-3.5 fill-current" />Podgląd
                  </button>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setEditModal(out.filename)} className="text-xs bg-[#272A2F] hover:bg-[#272A2F] text-[#C8FF3A] hover:text-[#FFFFFF] font-bold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 border border-[#C8FF3A]/30">
                      <Edit3 className="w-3.5 h-3.5" />Edytuj
                    </button>
                    <button
                      disabled={Boolean(out.already_published && !out.can_retry_publish)}
                      onClick={() => setUploadFilename(out.filename)}
                      className={`text-xs font-bold px-3.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-55 disabled:cursor-not-allowed ${
                        out.can_retry_publish
                          ? 'bg-amber-400 hover:bg-amber-300 text-[#050505]'
                          : out.already_published
                          ? 'bg-[#17191C] text-[#2ECC71] border border-[#2ECC71]/40'
                          : 'bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505]'
                      }`}
                    >
                      <Share2 className="w-3.5 h-3.5" />
                      {out.can_retry_publish
                        ? `Wrzuć ponownie (${(out.missing_platforms || []).map((p) => p.toUpperCase()).join('+') || 'YT'})`
                        : out.already_published
                        ? 'W kolejce / opubl.'
                        : 'Publikuj'}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-[#686E78] py-16">
          <Video className="w-10 h-10 mb-2 opacity-40" /><p className="text-sm font-semibold">Brak wyrenderowanych filmów</p>
          <p className="text-xs mt-1 opacity-70">Uruchom pipeline renderowania przez Studio Klipów.</p>
        </div>
      )}
    </div>
  );
}
