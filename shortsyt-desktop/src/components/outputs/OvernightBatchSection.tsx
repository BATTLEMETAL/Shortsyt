import React from 'react';
import {
  Moon, Trophy, Image as ImageIcon, Loader, RotateCcw, Upload, FolderOpen,
  Star, Play, Share2,
} from 'lucide-react';
import {
  OvernightBatchManifest, OvernightVariantSummary, ViralMontageStyle, VIRAL_STYLE_OPTIONS,
} from '../../lib/api';
import { ThumbLightboxData } from './socialCopyHelpers';

interface OvernightBatchSectionProps {
  latestBatch: OvernightBatchManifest;
  selectedVariantByCard: Record<string, string>;
  setSelectedVariantByCard: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  thumbBusyFor: string | null;
  restyleBusyFor: string | null;
  restyleError: string | null;
  onClearRestyleError: () => void;
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
  onPlay: (filename: string) => void;
  onOpenUpload: (filename: string) => void;
  onRestyle: (outputFilename: string, targetStyle: ViralMontageStyle, cardKey?: string) => void;
}

export default function OvernightBatchSection({
  latestBatch,
  selectedVariantByCard,
  setSelectedVariantByCard,
  thumbBusyFor,
  restyleBusyFor,
  restyleError,
  onClearRestyleError,
  resolveThumbForVideo,
  getThumbSrc,
  onOpenLightbox,
  onTriggerThumbUpload,
  onRegenerateThumb,
  onOpenFolder,
  onPlay,
  onOpenUpload,
  onRestyle,
}: OvernightBatchSectionProps) {
  if (!latestBatch.items || latestBatch.items.length === 0) return null;

  return (
    <div className="p-5 fk-cut bg-[#0E0F11] border border-[#C8FF3A]/40 space-y-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-black text-[#FFFFFF] flex items-center gap-2 flex-wrap">
            <Moon className="w-4 h-4 text-[#C8FF3A]" />
            Nocna Paczka Synapsy — Top {latestBatch.items.length} do Wyboru
            <span className="text-[9px] px-2 py-0.5 rounded bg-[#C8FF3A]/15 border border-[#C8FF3A]/35 text-[#C8FF3A] font-bold">ZERO AUTO-UPLOADU</span>
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

      {restyleError && (
        <div className="p-2.5 fk-cut-sm bg-red-500/15 border border-red-500/40 text-xs text-red-200 flex items-center justify-between gap-2">
          <span className="min-w-0 break-words">{restyleError}</span>
          <button type="button" onClick={onClearRestyleError} className="text-[11px] font-bold px-2 py-0.5 rounded bg-red-500/20 hover:bg-red-500/30">Zamknij</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {latestBatch.items.map((item) => {
          const isWinner = item.overnight_rank === 1 && item.verdict === 'PICK_WINNER';
          const rawAlts: OvernightVariantSummary[] = Array.isArray(item.alternate_renders) ? item.alternate_renders : [];
          const selectedAltFn = selectedVariantByCard[item.output_filename];
          const activeAlt: OvernightVariantSummary | undefined =
            rawAlts.find((a) => a.output_filename === selectedAltFn && a.render_ok !== false && a.file_exists !== false)
            ?? rawAlts.find((a) => a.output_filename === item.output_filename);

          const activeFilename = activeAlt?.output_filename || item.output_filename;
          const activeStyle = activeAlt?.montage_style || item.montage_style;
          const activeDuration = activeAlt?.duration_s ?? item.duration_s;
          const activeFinalScore = activeAlt?.final_score ?? item.final_score;
          const activeWatchScore = activeAlt?.watchability_score ?? item.watchability_score;
          const activeQaScore = activeAlt?.qa_score ?? item.qa_score;
          const activeDefects = activeAlt?.defects ?? item.defects;
          const activePubRec = activeAlt?.publish_recommended ?? item.publish_recommended;
          const activeBlockReasons = activeAlt?.publish_block_reasons ?? item.publish_block_reasons;
          const activeComment = activeAlt?.synapsa_comment_pl || item.synapsa_comment_pl;
          const activeTitle = activeAlt?.title || item.title || activeFilename;
          const activeFileExists = activeAlt?.file_exists !== undefined ? activeAlt.file_exists : item.file_exists;
          const activeThumb = resolveThumbForVideo(
            activeFilename,
            activeAlt?.thumbnail_path ?? item.thumbnail_path,
            activeAlt?.thumbnail_filename ?? item.thumbnail_filename
          );
          const isThumbBusy = thumbBusyFor === activeFilename;
          const readyStyleCount = VIRAL_STYLE_OPTIONS.filter((opt) => {
            const matchAlt = rawAlts.find((a) => a.montage_style === opt.id && a.render_ok !== false && a.file_exists !== false);
            return Boolean(matchAlt || (item.montage_style === opt.id && item.file_exists !== false));
          }).length;

          return (
            <div
              key={item.output_filename}
              className={`p-3.5 fk-cut-sm bg-[#050505] border flex flex-col justify-between gap-3 ${
                isWinner ? 'border-[#C8FF3A] shadow-[0_0_20px_rgba(200,255,58,0.12)]' : 'border-[#272A2F]'
              }`}
            >
              <div className="flex gap-3 min-w-0">
                {/* Lewa kolumna: Miniaturka 9:16 + akcje */}
                <div className="w-20 sm:w-24 flex-shrink-0 flex flex-col gap-1.5">
                  <div className="w-full aspect-[9/16] rounded-lg bg-[#0E0F11] border border-[#272A2F] overflow-hidden relative group">
                    {activeThumb ? (
                      <>
                        <img
                          src={getThumbSrc(activeThumb.filename)}
                          alt={`Miniaturka ${item.champion_name} ${item.action_type}`}
                          onClick={() => onOpenLightbox({
                            url: getThumbSrc(activeThumb.filename),
                            path: activeThumb.path,
                            filename: activeThumb.filename,
                            videoFilename: activeFilename,
                          })}
                          className="w-full h-full object-cover cursor-pointer group-hover:scale-105 transition-transform"
                        />
                        <button
                          type="button"
                          onClick={() => onOpenLightbox({
                            url: getThumbSrc(activeThumb.filename),
                            path: activeThumb.path,
                            filename: activeThumb.filename,
                            videoFilename: activeFilename,
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
                            onClick={() => onRegenerateThumb(activeFilename)}
                            className="px-1.5 py-1 rounded bg-[#17191C] hover:bg-[#C8FF3A] text-[#C8FF3A] hover:text-[#050505] border border-[#C8FF3A]/40 text-[9px] font-bold disabled:opacity-50"
                          >
                            {isThumbBusy ? '...' : 'Wygeneruj'}
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
                        onClick={() => onTriggerThumbUpload(activeFilename)}
                        title="Podmień własną miniaturkę"
                        className="p-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[9px] font-semibold text-[#FFFFFF] flex items-center justify-center disabled:opacity-50"
                      >
                        <Upload className="w-2.5 h-2.5 text-[#C8FF3A]" />
                      </button>
                      <button
                        type="button"
                        disabled={isThumbBusy}
                        onClick={() => onRegenerateThumb(activeFilename)}
                        title="Wygeneruj nową miniaturkę"
                        className="p-1 rounded bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-[9px] font-semibold text-[#FFFFFF] flex items-center justify-center disabled:opacity-50"
                      >
                        {isThumbBusy ? <Loader className="w-2.5 h-2.5 animate-spin text-[#C8FF3A]" /> : <RotateCcw className="w-2.5 h-2.5 text-[#C8FF3A]" />}
                      </button>
                      {activeThumb?.path ? (
                        <button
                          type="button"
                          onClick={() => onOpenFolder(activeThumb.path!)}
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
                        ? 'bg-[#C8FF3A] text-[#050505]'
                        : item.verdict === 'STRONG_ALT'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                        : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                    }`}>
                      {isWinner ? '⭐ REKOMENDACJA SYNAPSY #1' : `#${item.overnight_rank} • ${item.verdict}`}
                    </span>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {item.is_favorite && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-400/20 border border-amber-400/40 text-amber-300 font-bold flex items-center gap-0.5">
                          <Star className="w-2.5 h-2.5 fill-current" />Ulubiony
                        </span>
                      )}
                      {item.can_retry_publish ? (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-400/50 text-amber-300 font-bold">
                          ⚠️ Brak: {(item.missing_platforms || []).map((p) => p.toUpperCase()).join('+') || 'YT'}
                        </span>
                      ) : item.already_published && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2ECC71]/20 border border-[#2ECC71]/40 text-[#2ECC71] font-bold">
                          ✅ {(item.published_platforms || []).length > 0 ? item.published_platforms!.join('+').toUpperCase() : 'OPUBL./KOLEJKA'}
                        </span>
                      )}
                      {activePubRec === true ? (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2ECC71]/15 border border-[#2ECC71]/45 text-[#2ECC71] font-bold">
                          ✓ GOTOWE DO PUBLIKACJI
                        </span>
                      ) : activePubRec === false && (
                        <span
                          title={(activeBlockReasons || []).join(', ')}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-[#FE2C55]/20 border border-[#FE2C55]/50 text-[#FF7A96] font-bold"
                        >
                          🚫 ODRADZANE DO PUBLIKACJI
                        </span>
                      )}
                      {activeStyle && (() => {
                        const stOpt = VIRAL_STYLE_OPTIONS.find((o) => o.id === activeStyle);
                        return (
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${stOpt ? stOpt.badgeCls : 'bg-[#17191C] border-[#272A2F] text-[#A0A7B1]'}`}>
                            {stOpt ? stOpt.label : activeStyle}
                          </span>
                        );
                      })()}
                      {item.fallback_triggered && item.fallback_from_style && activeFilename === item.output_filename && (
                        <span
                          title={`Styl ${item.fallback_from_style} nie przeszedł bramki — automatycznie przełączono na ${item.montage_style}`}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-amber-400/15 border border-amber-400/40 text-amber-200 font-bold"
                        >
                          ↪ Fallback z {item.fallback_from_style}
                        </span>
                      )}
                      <span className="text-[10px] font-bold uppercase text-indigo-300">
                        {item.champion_name} • {item.action_type}{typeof activeDuration === 'number' && activeDuration > 0 ? ` • ${activeDuration.toFixed(1)}s` : ''}
                      </span>
                    </div>
                  </div>

                  <div className="text-xs font-bold text-[#FFFFFF] break-words">
                    {activeTitle.replace(/#\S+/g, '').replace(/\s{2,}/g, ' ').trim() || activeFilename}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 text-[9px] font-mono">
                    <span className="px-1.5 py-0.5 rounded bg-[#E62117]/15 border border-[#E62117]/30 text-[#FF8A80]">
                      YT: #shorts #leagueoflegends #lol
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-[#00F2FE]/10 border border-[#00F2FE]/30 text-[#00F2FE]">
                      TikTok: #outplayed #pcgaming #leagueoflegends #lolhighlights #{(item.champion_name || 'katarina').replace(/['\s]/g, '').toLowerCase()}
                    </span>
                  </div>
                  <div className="text-[10px] font-mono text-[#686E78] truncate" title={item.source_filename}>
                    {item.match_date ? `${item.match_date} • ` : ''}{item.match_kda ? `KDA ${item.match_kda} • ` : ''}{String(item.event_source || '').startsWith('outplayed_') ? 'Riot Outplayed • ' : ''}Źródło: {item.source_filename}
                  </div>

                  <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-mono">
                    <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#C8FF3A]">Final {activeFinalScore ?? '?'}</span>
                    <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">Hype {item.hype_score}</span>
                    <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">Watch {activeWatchScore ?? '?'}</span>
                    <span className="px-1.5 py-0.5 rounded bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1]">QA {activeQaScore ?? '?'}</span>
                  </div>

                  <p className="text-[11px] text-[#A0A7B1] break-words [overflow-wrap:anywhere]">{activeComment}</p>
                  {activeDefects && activeDefects.filter((d) => d !== 'ig_needs_transcode_on_upload').length > 0 && (
                    <div className="text-[10px] text-amber-300 break-words">
                      Wady: {activeDefects.filter((d) => d !== 'ig_needs_transcode_on_upload').join(', ')}
                    </div>
                  )}
                </div>
              </div>

              {item.render_ok && (
                <div className="space-y-2 pt-2 border-t border-white/5">
                  <div className="flex items-center gap-2">
                    {activeFileExists !== false && (
                      <button
                        onClick={() => onPlay(activeFilename)}
                        className="px-3 py-1.5 rounded-lg bg-[#272A2F] hover:bg-[#32363D] text-xs font-semibold text-[#FFFFFF] flex items-center gap-1.5"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />Odtwórz
                      </button>
                    )}
                    <button
                      disabled={Boolean(item.already_published && !item.can_retry_publish)}
                      onClick={() => onOpenUpload(activeFilename)}
                      className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-black flex items-center justify-center gap-1.5 disabled:opacity-55 disabled:cursor-not-allowed ${
                        item.can_retry_publish
                          ? 'bg-amber-400 hover:bg-amber-300 text-[#050505]'
                          : item.already_published
                          ? 'bg-[#17191C] text-[#2ECC71] border border-[#2ECC71]/40'
                          : isWinner
                          ? 'bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505]'
                          : 'bg-[#17191C] hover:bg-[#272A2F] text-[#C8FF3A] border border-[#C8FF3A]/40'
                      }`}
                    >
                      <Share2 className="w-3.5 h-3.5" />
                      {item.can_retry_publish
                        ? `Wrzuć ponownie (brak: ${(item.missing_platforms || []).map((p) => p.toUpperCase()).join('+') || 'YT'})`
                        : item.already_published
                        ? 'Już w kolejce / opublikowano'
                        : 'Wybierz i Opublikuj'}
                    </button>
                  </div>
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[9px] font-bold uppercase text-[#686E78] mr-1">
                      GOTOWE STYLE ({readyStyleCount}/3):
                    </span>
                    {VIRAL_STYLE_OPTIONS.map((opt) => {
                      const readyAlt = rawAlts.find((a) => a.montage_style === opt.id && a.render_ok !== false && a.file_exists !== false);
                      const readyFn = readyAlt?.output_filename || (item.montage_style === opt.id && item.file_exists !== false ? item.output_filename : undefined);
                      const isReady = Boolean(readyFn);
                      const isActiveStyle = activeStyle === opt.id;
                      const isBusyThis = restyleBusyFor === `${item.output_filename}:${opt.id}`;
                      const readyScore = readyAlt?.final_score ?? (item.montage_style === opt.id ? item.final_score : undefined);
                      const readyPub = readyAlt?.publish_recommended ?? (item.montage_style === opt.id ? item.publish_recommended : undefined);
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          disabled={Boolean(restyleBusyFor) || (isActiveStyle && isReady)}
                          onClick={() => {
                            if (isReady && readyFn) {
                              setSelectedVariantByCard((prev) => ({ ...prev, [item.output_filename]: readyFn }));
                            } else {
                              onRestyle(activeFilename, opt.id, item.output_filename);
                            }
                          }}
                          title={isReady
                            ? `Gotowy wariant ${opt.label} (Final=${readyScore ?? '?'}) — kliknij aby przełączyć od razu bez renderu`
                            : `Brak pliku na dysku — kliknij aby wyrenderować styl ${opt.label}`}
                          className={`px-2 py-1 rounded text-[10px] font-bold border transition-colors flex items-center gap-1 disabled:cursor-not-allowed ${
                            isActiveStyle
                              ? 'bg-[#C8FF3A]/20 border-[#C8FF3A] text-[#C8FF3A]'
                              : isReady
                              ? 'bg-[#111418] hover:bg-[#1B2026] border-emerald-500/35 text-emerald-200'
                              : 'bg-[#0E0F11] hover:bg-[#1C1F24] border-[#272A2F] text-[#8E95A0] disabled:opacity-45'
                          }`}
                        >
                          {isBusyThis ? (
                            <Loader className="w-2.5 h-2.5 animate-spin text-[#C8FF3A]" />
                          ) : isReady ? (
                            <span className={readyPub === true ? 'text-emerald-400' : 'text-amber-300'}>✓</span>
                          ) : (
                            <span className="text-[#686E78]">↻</span>
                          )}
                          <span>{opt.shortLabel}</span>
                          {typeof readyScore === 'number' && (
                            <span className="text-[9px] opacity-80 font-mono">• {Math.round(readyScore)}</span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
