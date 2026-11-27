import { LearningDirective } from '../../lib/api';

export interface VideoMetric {
  video_id: string;
  title: string;
  action_type: string;
  champion: string;
  views: number;
  likes: number;
  comments?: number;
  retention?: string;
  timestamp: string;
  published_at?: string;
  url: string;
}

export interface ChannelInfo {
  channel_title: string;
  subscriber_count: number;
  total_channel_views: number;
  total_video_count: number;
}

export type PlatformTab = 'youtube' | 'instagram' | 'facebook' | 'tiktok' | 'omni';

export type FormatBucketKey = 'solo_bolo' | 'outplay' | 'triple' | 'double' | 'quadra_penta' | 'other';

export interface YouTubeAnalyticsState {
  count: number;
  total_views: number;
  total_likes: number;
  total_comments?: number;
  avg_views: number;
  channel?: ChannelInfo;
  synced_at?: string;
  videos: VideoMetric[];
  top_videos?: VideoMetric[];
}

export interface FormatRow {
  type: string;
  count: number;
  avgViews: string;
  perfRatio: string;
  score: string;
  isPromoted: boolean;
}

export function classifyVideoFormat(v: VideoMetric): FormatBucketKey {
  const at = (v.action_type || '').toLowerCase().trim();
  const title = (v.title || '').toLowerCase();
  const src = at || title;

  if (at.includes('solo') || at.includes('1v1') || (!at && (title.includes('solo') || title.includes('1v1')))) {
    return 'solo_bolo';
  }
  if (at.includes('outplay') || at.includes('clutch') || (!at && (title.includes('outplay') || title.includes('clutch')))) {
    return 'outplay';
  }
  if (at.includes('penta') || at.includes('quadra') || (!at && (title.includes('penta') || title.includes('quadra')))) {
    return 'quadra_penta';
  }
  if (at.includes('triple') || (!at && title.includes('triple'))) {
    return 'triple';
  }
  if (at.includes('double') || (!at && title.includes('double'))) {
    return 'double';
  }
  if (src.includes('solo')) return 'solo_bolo';
  if (src.includes('outplay') || src.includes('clutch')) return 'outplay';
  if (src.includes('penta') || src.includes('quadra')) return 'quadra_penta';
  if (src.includes('triple')) return 'triple';
  if (src.includes('double')) return 'double';
  return 'other';
}

export function buildFormatRow(
  bucket: FormatBucketKey,
  label: string,
  learningKeys: string[],
  videos: VideoMetric[],
  periodAvgViews: number,
  topPeriodVideo: VideoMetric | undefined,
  topPeriodViews: number,
  learning: LearningDirective | null,
  demotedFormats: Set<string>
): FormatRow {
  const list = videos.filter((v) => classifyVideoFormat(v) === bucket);
  const count = list.length;
  const sumViews = list.reduce((acc, v) => acc + (v.views || 0), 0);
  const avgRaw = count > 0 ? sumViews / count : 0;
  const maxRaw = list.reduce((m, v) => Math.max(m, v.views || 0), 0);
  const ratio = count > 0 && periodAvgViews > 0 ? avgRaw / periodAvgViews : null;

  const statMatch = learningKeys
    .map((k) => learning?.action_stats?.[k])
    .find((s) => s !== undefined);
  const weightVal =
    learningKeys
      .map((k) => learning?.action_weights?.[k])
      .find((w): w is number => typeof w === 'number') ??
    statMatch?.weight ??
    1.0;

  const isDemoted = learningKeys.some((k) => demotedFormats.has(k));
  const hasTopHit =
    count > 0 &&
    Boolean(topPeriodVideo) &&
    list.some((v) => v.video_id === topPeriodVideo!.video_id) &&
    topPeriodViews >= 3000;

  let score = `WAGA ${weightVal.toFixed(2)}x`;
  let isPromoted = false;
  if (count === 0) {
    if (isDemoted) {
      score = `BRAK W OKRESIE • KARA -${learning?.evaluator_config?.demoted_penalty_points ?? 12}pkt`;
    } else if (statMatch?.count) {
      score = `BRAK W OKRESIE (hist. ${statMatch.count})`;
    } else {
      score = 'BRAK W OKRESIE';
    }
  } else if (hasTopHit) {
    score = `🔥 MAX ${maxRaw.toLocaleString()} • WAGA ${weightVal.toFixed(2)}x`;
    isPromoted = true;
  } else if (isDemoted) {
    score = `⚠️ NISKI CTR • WAGA ${weightVal.toFixed(2)}x`;
  } else if ((ratio !== null && ratio >= 1.15) || weightVal >= 1.15) {
    score = `👑 PRIORYTET • WAGA ${weightVal.toFixed(2)}x`;
    isPromoted = true;
  } else if ((ratio !== null && ratio >= 0.9) || weightVal >= 0.95) {
    score = `⚡ STABILNY • WAGA ${weightVal.toFixed(2)}x`;
  } else {
    score = `🎯 NISKI • WAGA ${weightVal.toFixed(2)}x`;
  }

  return {
    type: label,
    count,
    avgViews: count > 0 ? Math.round(avgRaw).toLocaleString() : '0',
    perfRatio: ratio !== null ? `${ratio.toFixed(2)}x` : '—',
    score,
    isPromoted,
  };
}

export function computeActionBreakdown(
  videos: VideoMetric[],
  avgViews: number,
  topVideos: VideoMetric[] | undefined,
  learning: LearningDirective | null
): { actionBreakdown: FormatRow[]; topPeriodVideo?: VideoMetric; topPeriodViews: number } {
  const sortedByViews = [...videos].sort((a, b) => (b.views || 0) - (a.views || 0));
  const topPeriodVideo = topVideos?.[0] || sortedByViews[0];
  const topPeriodViews = topPeriodVideo?.views || 0;
  const periodAvgViews =
    avgViews > 0
      ? avgViews
      : videos.length > 0
        ? videos.reduce((acc, v) => acc + (v.views || 0), 0) / videos.length
        : 0;

  const demotedFormats = new Set(learning?.evaluator_config?.demoted_formats || []);

  const rowArgs = [videos, periodAvgViews, topPeriodVideo, topPeriodViews, learning, demotedFormats] as const;
  const baseBreakdown = [
    buildFormatRow('solo_bolo', '👑 Solo Bolo / 1v1', ['solo_bolo'], ...rowArgs),
    buildFormatRow('outplay', '🔥 Outplay / Clutch (1v2 / 1v3 / Dive)', ['outplay', 'clutch'], ...rowArgs),
    buildFormatRow('triple', '⚔️ Triple Kill (Katarina Core)', ['triple'], ...rowArgs),
    buildFormatRow('double', '🎯 Double Kill (Fast Skirmish)', ['double'], ...rowArgs),
    buildFormatRow('quadra_penta', '💀 Quadra / Pentakill', ['quadrakill', 'pentakill'], ...rowArgs),
  ];
  const otherRow = buildFormatRow('other', '⚡ Inne / Starsze Multikill', ['multikill'], ...rowArgs);
  const actionBreakdown = otherRow.count > 0 ? [...baseBreakdown, otherRow] : baseBreakdown;

  return { actionBreakdown, topPeriodVideo, topPeriodViews };
}

export function exportAnalyticsCSV(
  activePlatform: PlatformTab,
  ytData: YouTubeAnalyticsState,
  igData: any,
  fbData: any,
  omniData: any
): void {
  let headers = '';
  let rows = '';

  if (activePlatform === 'youtube') {
    if (!ytData.videos || ytData.videos.length === 0) return;
    headers = 'Platforma,VideoID,Tytul,Akcja,Wyswietlenia,Polubienia,Komentarze,Data,URL\n';
    rows = ytData.videos
      .map(
        (v) =>
          `"YouTube","${v.video_id}","${(v.title || '').replace(/"/g, '""')}","${v.action_type || ''}",${v.views || 0},${v.likes || 0},${v.comments || 0},"${v.timestamp || v.published_at || ''}","${v.url || ''}"`
      )
      .join('\n');
  } else if (activePlatform === 'instagram') {
    const reels = igData?.reels || [];
    if (reels.length === 0) return;
    headers = 'Platforma,ID,Tytul,Wyswietlenia,Zasieg,Polubienia,Komentarze,Zapisania,Udostepnienia,Data,URL\n';
    rows = reels
      .map(
        (r: any) =>
          `"Instagram","${r.id}","${(r.title || '').replace(/"/g, '""')}",${r.views || 0},${r.reach || 0},${r.likes || 0},${r.comments || 0},${r.saved || 0},${r.shares || 0},"${r.timestamp || ''}","${r.url || ''}"`
      )
      .join('\n');
  } else if (activePlatform === 'facebook') {
    const vids = fbData?.videos || [];
    if (vids.length === 0) return;
    headers = 'Platforma,ID,Tytul,Wyswietlenia,Reakcje,Komentarze,Data,URL\n';
    rows = vids
      .map(
        (v: any) =>
          `"Facebook","${v.id}","${(v.title || '').replace(/"/g, '""')}",${v.views || 0},${v.reactions || 0},${v.comments || 0},"${v.timestamp || ''}","${v.url || ''}"`
      )
      .join('\n');
  } else if (activePlatform === 'omni') {
    const topVids = omniData?.top_videos || [];
    if (topVids.length === 0) return;
    headers = 'Platforma,Tytul,Wyswietlenia,Polubienia/Reakcje,Komentarze,Data,URL\n';
    rows = topVids
      .map(
        (v: any) =>
          `"${v.platform}","${(v.title || '').replace(/"/g, '""')}",${v.views || 0},${v.likes || 0},${v.comments || 0},"${v.timestamp || ''}","${v.url || ''}"`
      )
      .join('\n');
  }

  if (!rows) return;
  const blob = new Blob([headers + rows], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `dwannellenga_${activePlatform}_analytics_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
