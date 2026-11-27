import React from 'react';
import { Video, Check, Copy } from 'lucide-react';
import { TikTokCreatorInfo, OutputMetadata } from '../../lib/api';

const PRIVACY_LABELS: Record<string, string> = {
  PUBLIC_TO_EVERYONE: 'Public to everyone',
  MUTUAL_FOLLOW_FRIENDS: 'Friends',
  FOLLOWER_OF_CREATOR: 'Followers',
  SELF_ONLY: 'Only you',
};

interface TikTokPublishPanelProps {
  ttCreatorInfo: TikTokCreatorInfo | null;
  ttCreatorLoading: boolean;
  uploadVideoDurationSec: number | null;
  ttPostMode: 'direct' | 'inbox';
  setTtPostMode: (mode: 'direct' | 'inbox') => void;
  ttLearningInfo: { analyzed_videos: number; recommended_hashtags: string[] } | null;
  uploadModalMeta: OutputMetadata | null;
  tiktokCopyText: string;
  setTiktokCopyText: (v: string) => void;
  tiktokCopied: boolean;
  onCopyTiktokText: () => void;
  ttPrivacy: string;
  setTtPrivacy: (v: string) => void;
  ttAllowComment: boolean;
  setTtAllowComment: (v: boolean) => void;
  ttAllowDuet: boolean;
  setTtAllowDuet: (v: boolean) => void;
  ttAllowStitch: boolean;
  setTtAllowStitch: (v: boolean) => void;
  ttDisclose: boolean;
  setTtDisclose: (v: boolean) => void;
  ttYourBrand: boolean;
  setTtYourBrand: (v: boolean) => void;
  ttBrandedContent: boolean;
  setTtBrandedContent: (v: boolean) => void;
}

export default function TikTokPublishPanel({
  ttCreatorInfo,
  ttCreatorLoading,
  uploadVideoDurationSec,
  ttPostMode,
  setTtPostMode,
  ttLearningInfo,
  uploadModalMeta,
  tiktokCopyText,
  setTiktokCopyText,
  tiktokCopied,
  onCopyTiktokText,
  ttPrivacy,
  setTtPrivacy,
  ttAllowComment,
  setTtAllowComment,
  ttAllowDuet,
  setTtAllowDuet,
  ttAllowStitch,
  setTtAllowStitch,
  ttDisclose,
  setTtDisclose,
  ttYourBrand,
  setTtYourBrand,
  ttBrandedContent,
  setTtBrandedContent,
}: TikTokPublishPanelProps) {
  const allowedPrivacies = (
    ttCreatorInfo?.ok &&
    Array.isArray(ttCreatorInfo.privacy_level_options) &&
    ttCreatorInfo.privacy_level_options.length > 0
  )
    ? ttCreatorInfo.privacy_level_options
    : ['PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'SELF_ONLY'];

  const maxTtSec = ttCreatorInfo?.ok ? ttCreatorInfo.max_video_post_duration_sec : undefined;
  const ttDurationExceeded = Boolean(maxTtSec && uploadVideoDurationSec && uploadVideoDurationSec > maxTtSec);
  const commentLocked = Boolean(ttCreatorInfo?.comment_disabled);
  const duetLocked = Boolean(ttCreatorInfo?.duet_disabled);
  const stitchLocked = Boolean(ttCreatorInfo?.stitch_disabled);

  return (
    <div className="space-y-2.5 bg-[#00F2FE]/5 border border-[#00F2FE]/30 rounded-lg p-3">
      <div className="flex items-center justify-between gap-2">
        <label className="text-[11px] font-bold text-[#00F2FE] flex items-center gap-1.5">
          <Video className="w-3.5 h-3.5" /> TikTok Content Posting API
        </label>
        <button
          type="button"
          onClick={onCopyTiktokText}
          className="px-2 py-0.5 rounded bg-[#00F2FE]/15 hover:bg-[#00F2FE]/25 text-[#00F2FE] border border-[#00F2FE]/40 text-[10px] font-bold flex items-center gap-1 transition-all"
        >
          {tiktokCopied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {tiktokCopied ? 'Skopiowano!' : 'Kopiuj opis + tagi TikTok'}
        </button>
      </div>

      {/* Live Creator Info from /v2/post/publish/creator_info/query/ */}
      <div className="px-2.5 py-2 rounded bg-[#050505] border border-[#272A2F] flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {ttCreatorInfo?.ok && ttCreatorInfo.creator_avatar_url ? (
            <img src={ttCreatorInfo.creator_avatar_url} alt="Creator avatar" className="w-7 h-7 rounded-full object-cover border border-[#00F2FE]/40 shrink-0" />
          ) : (
            <div className="w-7 h-7 rounded-full bg-[#FE2C55]/25 text-white flex items-center justify-center text-[10px] font-black shrink-0">DW</div>
          )}
          <div className="min-w-0">
            <div className="text-[11px] font-bold text-[#FFFFFF] truncate">
              {ttCreatorInfo?.ok && ttCreatorInfo.creator_nickname ? ttCreatorInfo.creator_nickname : 'Dwannellenga'}{' '}
              <span className="text-[#00F2FE] font-mono text-[10px]">
                @{ttCreatorInfo?.ok && ttCreatorInfo.creator_username ? ttCreatorInfo.creator_username : 'dwannellenga'}
              </span>
            </div>
            <div className="text-[10px] text-[#A0A7B1]">
              {ttCreatorLoading
                ? 'Querying creator_info...'
                : ttCreatorInfo?.ok
                ? `creator_info verified • Max video duration: ${ttCreatorInfo.max_video_post_duration_sec}s`
                : 'TikTok Creator Info ready (sandbox/token check)'}
            </div>
          </div>
        </div>
      </div>

      {ttDurationExceeded && (
        <div className="px-2.5 py-1.5 rounded bg-[#FF5C5C]/15 border border-[#FF5C5C]/40 text-[10px] text-[#FF5C5C] font-semibold">
          Video duration ({uploadVideoDurationSec?.toFixed(1)}s) exceeds creator max limit ({maxTtSec}s).
        </div>
      )}

      {/* Publish Method Toggle: video.publish vs video.upload */}
      <div className="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          onClick={() => setTtPostMode('direct')}
          className={`px-2 py-1.5 rounded border text-[10px] font-bold transition-all ${
            ttPostMode === 'direct'
              ? 'bg-[#00F2FE]/20 border-[#00F2FE] text-[#FFFFFF]'
              : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:text-[#FFFFFF]'
          }`}
        >
          Direct Post (video.publish)
        </button>
        <button
          type="button"
          onClick={() => setTtPostMode('inbox')}
          className={`px-2 py-1.5 rounded border text-[10px] font-bold transition-all ${
            ttPostMode === 'inbox'
              ? 'bg-[#C8FF3A]/20 border-[#C8FF3A] text-[#FFFFFF]'
              : 'bg-[#050505] border-[#272A2F] text-[#A0A7B1] hover:text-[#FFFFFF]'
          }`}
        >
          Upload as Draft / Inbox (video.upload)
        </button>
      </div>

      <div className="px-2.5 py-1.5 rounded bg-[#050505] border border-[#00F2FE]/25 text-[10px] text-[#A0A7B1]">
        <span className="text-[#00F2FE] font-bold">
          {ttLearningInfo && ttLearningInfo.analyzed_videos > 0
            ? `Synapsa TikTok AI (${ttLearningInfo.analyzed_videos} filmów @dwannellenga)`
            : 'Synapsa TikTok AI (@dwannellenga)'}
        </span>
        {' • '}Top tagi TikTok:{' '}
        <span className="text-[#C8FF3A] font-mono">
          {(() => {
            const base = (ttLearningInfo?.recommended_hashtags && ttLearningInfo.recommended_hashtags.length > 0)
              ? ttLearningInfo.recommended_hashtags.slice(0, 4)
              : ['outplayed', 'pcgaming', 'leagueoflegends', 'lolhighlights'];
            const champTag = (uploadModalMeta?.champion_name || 'katarina').replace(/['\s]/g, '').toLowerCase();
            const combined = Array.from(new Set([...base, champTag]));
            return combined.map((t) => `#${t}`).join(' ');
          })()}
        </span>
      </div>
      <textarea
        value={tiktokCopyText}
        onChange={(e) => setTiktokCopyText(e.target.value)}
        rows={2}
        className="w-full bg-[#050505] border border-[#272A2F] rounded px-2.5 py-1.5 text-[11px] text-[#FFFFFF] focus:border-[#00F2FE] outline-none resize-none font-mono"
      />

      {ttPostMode === 'inbox' ? (
        <div className="p-2.5 rounded bg-[#050505] border border-[#C8FF3A]/30 text-[10px] text-[#A0A7B1] space-y-1">
          <div className="font-bold text-[#C8FF3A]">Draft Upload Mode (scope: video.upload)</div>
          <div>
            Uploads video to your TikTok Inbox/Drafts via <span className="font-mono text-[#FFFFFF]">/v2/post/publish/inbox/video/init/</span> so you can finalize audio, privacy, and effects in the TikTok app.
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
            <div>
              <label className="text-[10px] font-semibold text-[#A0A7B1] block mb-1">Who can view this video</label>
              <select
                value={ttPrivacy}
                onChange={(e) => setTtPrivacy(e.target.value)}
                className={`w-full bg-[#050505] border rounded px-2 py-1 text-[11px] text-[#FFFFFF] focus:border-[#00F2FE] outline-none ${ttPrivacy ? 'border-[#272A2F]' : 'border-[#FE2C55]'}`}
              >
                <option value="">-- Select privacy level --</option>
                {allowedPrivacies.map((opt) => (
                  <option
                    key={opt}
                    value={opt}
                    disabled={Boolean(opt === 'SELF_ONLY' && ttDisclose && ttBrandedContent)}
                  >
                    {PRIVACY_LABELS[opt] || opt}
                    {opt === 'SELF_ONLY' && ttDisclose && ttBrandedContent ? ' (unavailable for Branded content)' : ''}
                  </option>
                ))}
              </select>
              {ttDisclose && ttBrandedContent && ttPrivacy === 'SELF_ONLY' && (
                <div className="text-[10px] text-[#FF5C5C] mt-1">
                  Branded content visibility cannot be private (Only you).
                </div>
              )}
            </div>
            <div>
              <label className="text-[10px] font-semibold text-[#A0A7B1] block mb-1">Allow users to</label>
              <div className="flex items-center gap-2.5 pt-1 text-[11px] text-[#FFFFFF]">
                <label className={`flex items-center gap-1 ${commentLocked ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}>
                  <input
                    type="checkbox"
                    disabled={commentLocked}
                    checked={!commentLocked && ttAllowComment}
                    onChange={(e) => setTtAllowComment(e.target.checked)}
                    className="accent-[#00F2FE]"
                  /> Comment
                </label>
                <label className={`flex items-center gap-1 ${duetLocked ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}>
                  <input
                    type="checkbox"
                    disabled={duetLocked}
                    checked={!duetLocked && ttAllowDuet}
                    onChange={(e) => setTtAllowDuet(e.target.checked)}
                    className="accent-[#00F2FE]"
                  /> Duet
                </label>
                <label className={`flex items-center gap-1 ${stitchLocked ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}>
                  <input
                    type="checkbox"
                    disabled={stitchLocked}
                    checked={!stitchLocked && ttAllowStitch}
                    onChange={(e) => setTtAllowStitch(e.target.checked)}
                    className="accent-[#00F2FE]"
                  /> Stitch
                </label>
              </div>
            </div>
          </div>
          <div className="pt-1 border-t border-white/10 space-y-1.5">
            <label className="flex items-center justify-between text-[11px] font-semibold text-[#FFFFFF] cursor-pointer">
              <span>Disclose video content</span>
              <input
                type="checkbox"
                checked={ttDisclose}
                onChange={(e) => {
                  const checked = e.target.checked;
                  setTtDisclose(checked);
                  if (!checked) {
                    setTtYourBrand(false);
                    setTtBrandedContent(false);
                  }
                }}
                className="accent-[#00F2FE]"
              />
            </label>
            {ttDisclose && (
              <div className="space-y-1">
                <div className="flex items-center gap-4 text-[10px] text-[#A0A7B1]">
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input type="checkbox" checked={ttYourBrand} onChange={(e) => setTtYourBrand(e.target.checked)} className="accent-[#00F2FE]" /> Your brand
                  </label>
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input type="checkbox" checked={ttBrandedContent} onChange={(e) => setTtBrandedContent(e.target.checked)} className="accent-[#00F2FE]" /> Branded content
                  </label>
                </div>
                {ttBrandedContent ? (
                  <div className="text-[10px] text-[#C8FF3A] font-semibold">
                    Your video will be labeled as &apos;Paid partnership&apos;
                  </div>
                ) : ttYourBrand ? (
                  <div className="text-[10px] text-[#C8FF3A] font-semibold">
                    Your video will be labeled as &apos;Promotional content&apos;
                  </div>
                ) : (
                  <div className="text-[10px] text-[#FF5C5C] font-semibold">
                    You need to indicate if your content promotes yourself, a third party, or both.
                  </div>
                )}
              </div>
            )}
            <p className="text-[10px] text-[#A0A7B1] leading-snug">
              By posting, you agree to TikTok&apos;s{' '}
              {ttDisclose && ttBrandedContent ? (
                <>
                  <a
                    href="https://www.tiktok.com/legal/page/global/bc-policy/en"
                    target="_blank"
                    rel="noreferrer"
                    className="text-[#00F2FE] underline"
                  >
                    Branded Content Policy
                  </a>
                  {' and '}
                </>
              ) : null}
              <a
                href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en"
                target="_blank"
                rel="noreferrer"
                className="text-[#00F2FE] underline"
              >
                Music Usage Confirmation
              </a>
              . After publishing, it may take a few minutes for your video to process and appear on your profile.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
