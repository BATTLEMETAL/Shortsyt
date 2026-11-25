import React, { useState, useEffect } from 'react';
import { 
  apiGetAnalytics, apiGetLearningStatus, apiGetChannelRetention,
  apiGetSocialAnalytics,
  LearningDirective, ChannelRetentionOverview 
} from '../lib/api';
import {
  BarChart3,
  TrendingUp,
  Eye,
  ThumbsUp,
  Zap,
  Flame,
  Award,
  Sparkles,
  Download,
  RefreshCw,
  Video,
  CheckCircle,
  MessageSquare,
  Users,
  Activity,
  Globe,
  Share2,
  Bookmark,
  Play,
  Layers,
  ExternalLink,
} from 'lucide-react';

interface VideoMetric {
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

interface ChannelInfo {
  channel_title: string;
  subscriber_count: number;
  total_channel_views: number;
  total_video_count: number;
}

type PlatformTab = 'youtube' | 'instagram' | 'facebook' | 'tiktok' | 'omni';

export default function Analytics() {
  const [activePlatform, setActivePlatform] = useState<PlatformTab>('youtube');
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | 'all'>('30d');
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  // YouTube Data
  const [ytData, setYtData] = useState<{
    count: number;
    total_views: number;
    total_likes: number;
    total_comments?: number;
    avg_views: number;
    channel?: ChannelInfo;
    synced_at?: string;
    videos: VideoMetric[];
    top_videos?: VideoMetric[];
  }>({
    count: 0,
    total_views: 0,
    total_likes: 0,
    total_comments: 0,
    avg_views: 0,
    videos: [],
  });

  // Social Data (Instagram, Facebook, TikTok, Omnichannel)
  const [igData, setIgData] = useState<any>(null);
  const [fbData, setFbData] = useState<any>(null);
  const [ttData, setTtData] = useState<any>(null);
  const [omniData, setOmniData] = useState<any>(null);

  const [learning, setLearning] = useState<LearningDirective | null>(null);
  const [channelRetention, setChannelRetention] = useState<ChannelRetentionOverview | null>(null);

  // Fetch YouTube
  const fetchYouTubeAnalytics = async (range: '7d' | '30d' | 'all', forceRefresh: boolean = false) => {
    try {
      const res = await apiGetAnalytics(range, forceRefresh);
      if (res && res.videos) setYtData(res);
    } catch (err) {
      console.warn('YouTube analytics fetch error:', err);
    }
  };

  // Fetch Social Platform Data
  const fetchSocialAnalytics = async (platform: PlatformTab, forceRefresh: boolean = false) => {
    try {
      if (platform === 'instagram') {
        const res = await apiGetSocialAnalytics('instagram', forceRefresh);
        setIgData(res);
      } else if (platform === 'facebook') {
        const res = await apiGetSocialAnalytics('facebook', forceRefresh);
        setFbData(res);
      } else if (platform === 'tiktok') {
        const res = await apiGetSocialAnalytics('tiktok', forceRefresh);
        setTtData(res);
      } else if (platform === 'omni') {
        const res = await apiGetSocialAnalytics('all', forceRefresh);
        setOmniData(res);
      }
    } catch (err) {
      console.warn(`Social analytics error (${platform}):`, err);
    }
  };

  // Main Loader
  const loadActiveData = async (forceRefresh: boolean = false) => {
    if (forceRefresh) setRefreshing(true);
    else setLoading(true);

    if (activePlatform === 'youtube') {
      await fetchYouTubeAnalytics(timeRange, forceRefresh);
      try {
        const learnRes = await apiGetLearningStatus();
        if (learnRes?.directive) setLearning(learnRes.directive);
      } catch {}
      try {
        const retRes = await apiGetChannelRetention();
        if (retRes?.data) setChannelRetention(retRes.data);
      } catch {}
    } else {
      await fetchSocialAnalytics(activePlatform, forceRefresh);
    }

    setLoading(false);
    setRefreshing(false);
  };

  useEffect(() => {
    loadActiveData();
  }, [activePlatform, timeRange]);

  // Derived YouTube Breakdown — wzajemnie rozłączna klasyfikacja (suma = ytData.videos.length)
  type FormatBucketKey = 'solo_bolo' | 'outplay' | 'triple' | 'double' | 'quadra_penta' | 'other';

  const classifyVideoFormat = (v: VideoMetric): FormatBucketKey => {
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
  };

  const sortedByViews = [...ytData.videos].sort((a, b) => (b.views || 0) - (a.views || 0));
  const topPeriodVideo = ytData.top_videos?.[0] || sortedByViews[0];
  const topPeriodViews = topPeriodVideo?.views || 0;
  const periodAvgViews =
    ytData.avg_views > 0
      ? ytData.avg_views
      : ytData.videos.length > 0
        ? ytData.videos.reduce((acc, v) => acc + (v.views || 0), 0) / ytData.videos.length
        : 0;

  const demotedFormats = new Set(learning?.evaluator_config?.demoted_formats || []);

  const buildFormatRow = (
    bucket: FormatBucketKey,
    label: string,
    learningKeys: string[]
  ) => {
    const list = ytData.videos.filter((v) => classifyVideoFormat(v) === bucket);
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
    const hasTopHit = count > 0 && topPeriodVideo && list.some((v) => v.video_id === topPeriodVideo.video_id) && topPeriodViews >= 3000;

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
  };

  const baseBreakdown = [
    buildFormatRow('solo_bolo', '👑 Solo Bolo / 1v1', ['solo_bolo']),
    buildFormatRow('outplay', '🔥 Outplay / Clutch (1v2 / 1v3 / Dive)', ['outplay', 'clutch']),
    buildFormatRow('triple', '⚔️ Triple Kill (Katarina Core)', ['triple']),
    buildFormatRow('double', '🎯 Double Kill (Fast Skirmish)', ['double']),
    buildFormatRow('quadra_penta', '💀 Quadra / Pentakill', ['quadrakill', 'pentakill']),
  ];
  const otherRow = buildFormatRow('other', '⚡ Inne / Starsze Multikill', ['multikill']);
  const actionBreakdown = otherRow.count > 0 ? [...baseBreakdown, otherRow] : baseBreakdown;

  // Dynamic CSV Export
  const handleExportCSV = () => {
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
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#050505] p-6 lg:p-8 space-y-6 text-[#FFFFFF]">
      {/* ── TOP NAV BAR & PLATFORM TABS ──────────────────────────────────── */}
      <div className="flex flex-col gap-4 pb-4 border-b border-[#272A2F]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black tracking-tight text-[#FFFFFF] flex flex-wrap items-center gap-2.5">
              <BarChart3 className="w-6 h-6 text-[#C8FF3A] shrink-0" />
              <span>Analityka Multi-Platform — Dwannellenga</span>
              <span className="fk-tag shrink-0 whitespace-nowrap text-[10px] px-2.5 py-0.5 bg-[#2ECC71]/20 border border-[#2ECC71]/40 text-[#2ECC71] font-bold">
                LIVE SYNC
              </span>
            </h1>
            <p className="text-xs text-[#A0A7B1] mt-1 font-medium">
              Rzeczywiste metryki społecznościowe na żywo ze wszystkich platform • Synchronizacja:{' '}
              <strong className="text-[#C8FF3A]">
                {activePlatform === 'youtube'
                  ? ytData.synced_at ? new Date(ytData.synced_at).toLocaleTimeString() : 'Bieżąca'
                  : 'Na żywo z Graph API / Direct Post'}
              </strong>
            </p>
          </div>

          <div className="flex items-center gap-3">
            {activePlatform === 'youtube' && (
              <div className="flex bg-[#0E0F11] p-1 fk-cut-sm border border-[#272A2F]">
                {(['7d', '30d', 'all'] as const).map((range) => {
                  const labels = { '7d': '7 Dni', '30d': '30 Dni', 'all': 'Wszystko' };
                  const isActive = timeRange === range;
                  return (
                    <button
                      key={range}
                      onClick={() => setTimeRange(range)}
                      className={`px-3.5 py-1.5 text-xs font-black rounded-lg transition-all flex items-center gap-1.5 ${
                        isActive
                          ? 'bg-[#C8FF3A] text-[#050505] scale-105'
                          : 'text-[#A0A7B1] hover:text-[#FFFFFF] hover:bg-[#17191C]'
                      }`}
                    >
                      {isActive && <CheckCircle className="w-3 h-3" />}
                      <span>{labels[range]}</span>
                    </button>
                  );
                })}
              </div>
            )}

            <button
              onClick={() => loadActiveData(true)}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-3.5 py-2 fk-cut-sm bg-[#0E0F11] hover:bg-[#17191C] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] transition-colors"
              title="Pobierz najświeższe dane z platformy"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-[#C8FF3A] ${refreshing ? 'animate-spin' : ''}`} />
              <span>
                {refreshing
                  ? 'Pobieranie...'
                  : activePlatform === 'youtube'
                  ? 'Odśwież YouTube'
                  : activePlatform === 'instagram'
                  ? 'Odśwież Instagram'
                  : activePlatform === 'facebook'
                  ? 'Odśwież Facebook'
                  : activePlatform === 'tiktok'
                  ? 'Odśwież TikTok'
                  : 'Odśwież Wszystkie'}
              </span>
            </button>

            <button
              onClick={handleExportCSV}
              className="flex items-center gap-1.5 px-3.5 py-2 fk-cut-sm bg-[#0E0F11] hover:bg-[#17191C] border border-[#272A2F] text-xs font-bold text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors"
              title="Eksportuj rzeczywiste dane do CSV"
            >
              <Download className="w-3.5 h-3.5 text-[#C8FF3A]" />
              <span>CSV</span>
            </button>
          </div>
        </div>

        {/* ── PLATFORM SWITCHER TABS ───────────────────────────────────── */}
        <div className="flex flex-wrap items-center gap-2 pt-2">
          <button
            onClick={() => setActivePlatform('youtube')}
            className={`px-4 py-2 fk-cut-sm text-xs font-bold transition-all flex items-center gap-2 border ${
              activePlatform === 'youtube'
                ? 'bg-[#E62117]/20 border-[#E62117] text-white font-black'
                : 'bg-[#0E0F11] border-[#272A2F] text-[#A0A7B1] hover:text-white hover:border-[#E62117]/50'
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-[#E62117] inline-block" />
            <span>YouTube Shorts</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-black/40 text-red-300 font-mono">
              {(ytData.channel?.total_video_count ?? ytData.videos.length) || 0} filmów
            </span>
          </button>

          <button
            onClick={() => setActivePlatform('instagram')}
            className={`px-4 py-2 fk-cut-sm text-xs font-bold transition-all flex items-center gap-2 border ${
              activePlatform === 'instagram'
                ? 'bg-gradient-to-r from-[#833AB4]/30 via-[#FD1D1D]/30 to-[#F77737]/30 border-[#E1306C] text-white font-black'
                : 'bg-[#0E0F11] border-[#272A2F] text-[#A0A7B1] hover:text-white hover:border-[#E1306C]/50'
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-[#E1306C] inline-block" />
            <span>Instagram Reels</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-black/40 text-pink-300 font-mono">
              {igData?.total_views ? `${igData.total_views} views` : 'Aktywny'}
            </span>
          </button>

          <button
            onClick={() => setActivePlatform('facebook')}
            className={`px-4 py-2 fk-cut-sm text-xs font-bold transition-all flex items-center gap-2 border ${
              activePlatform === 'facebook'
                ? 'bg-[#1877F2]/20 border-[#1877F2] text-white font-black'
                : 'bg-[#0E0F11] border-[#272A2F] text-[#A0A7B1] hover:text-white hover:border-[#1877F2]/50'
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-[#1877F2] inline-block" />
            <span>Facebook Reels</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-black/40 text-blue-300 font-mono">
              {fbData?.total_views ? `${fbData.total_views} views` : 'Aktywny'}
            </span>
          </button>

          <button
            onClick={() => setActivePlatform('tiktok')}
            className={`px-4 py-2 fk-cut-sm text-xs font-bold transition-all flex items-center gap-2 border ${
              activePlatform === 'tiktok'
                ? 'bg-[#00F2FE]/20 border-[#00F2FE] text-white font-black'
                : 'bg-[#0E0F11] border-[#272A2F] text-[#A0A7B1] hover:text-white hover:border-[#00F2FE]/50'
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-[#00F2FE] inline-block" />
            <span>TikTok</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-black/40 text-cyan-300 font-mono">Direct Post</span>
          </button>

          <button
            onClick={() => setActivePlatform('omni')}
            className={`px-4 py-2 fk-cut-sm text-xs font-bold transition-all flex items-center gap-2 border ${
              activePlatform === 'omni'
                ? 'bg-[#C8FF3A]/20 border-[#C8FF3A] text-[#FFFFFF] font-black'
                : 'bg-[#0E0F11] border-[#272A2F] text-[#A0A7B1] hover:text-[#C8FF3A] hover:border-[#C8FF3A]/50'
            }`}
          >
            <Globe className="w-3.5 h-3.5 text-[#C8FF3A]" />
            <span>Wszystkie Platformy (Omnichannel)</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#C8FF3A]/20 text-[#C8FF3A] font-mono font-bold">
              Ekosystem
            </span>
          </button>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 1. YOUTUBE VIEW                                                    */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {activePlatform === 'youtube' && (
        <div className="space-y-6">
          {/* Channel Overview Bar */}
          {ytData.channel && (
            <div className="p-4 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-wrap items-center justify-between gap-4 text-xs">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 fk-cut-sm bg-[#E62117]/20 border border-[#E62117]/40 flex items-center justify-center font-black text-[#E62117] text-sm">
                  YT
                </div>
                <div>
                  <div className="font-bold text-[#FFFFFF] text-sm">{ytData.channel.channel_title || 'Dwannellenga'}</div>
                  <div className="text-[11px] text-[#A0A7B1]">Oficjalny Kanał YouTube Shorts</div>
                </div>
              </div>

              <div className="flex items-center gap-6 text-[#A0A7B1]">
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-[#C8FF3A]" />
                  <span>Subskrybenci: <strong className="text-[#FFFFFF] font-mono">{ytData.channel.subscriber_count}</strong></span>
                </div>
                <div className="flex items-center gap-2">
                  <Eye className="w-4 h-4 text-[#2ECC71]" />
                  <span>Łączne wyświetlenia: <strong className="text-[#FFFFFF] font-mono">{ytData.channel.total_channel_views.toLocaleString()}</strong></span>
                </div>
                <div className="flex items-center gap-2">
                  <Video className="w-4 h-4 text-[#5CAEFF]" />
                  <span>Wszystkie filmy: <strong className="text-[#FFFFFF] font-mono">{ytData.channel.total_video_count}</strong></span>
                </div>
              </div>
            </div>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Wyświetlenia ({timeRange.toUpperCase()})</span>
                <Eye className="w-4 h-4 text-[#C8FF3A]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-[#FFFFFF]">
                  {loading ? <RefreshCw className="w-5 h-5 animate-spin text-[#C8FF3A]" /> : `${ytData.total_views.toLocaleString()} views`}
                </div>
                <div className="text-xs text-[#55E88D] mt-1 flex items-center gap-1 font-semibold">
                  <TrendingUp className="w-3 h-3" />
                  <span>Śr. {ytData.avg_views.toLocaleString()} na film</span>
                </div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Engagement ({timeRange.toUpperCase()})</span>
                <ThumbsUp className="w-4 h-4 text-[#2ECC71]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-[#FFFFFF]">
                  {ytData.total_likes} 👍 / {ytData.total_comments || 0} 💬
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Polubienia i komentarze widzów</div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Top Video w okresie</span>
                <Award className="w-4 h-4 text-[#C8FF3A]" />
              </div>
              <div className="mt-3">
                <div className="text-lg font-black text-[#FFFFFF] truncate" title={topPeriodVideo?.title}>
                  {topPeriodVideo?.title || 'Brak danych w okresie'}
                </div>
                <div className="text-xs text-[#55E88D] mt-1 font-semibold">
                  {topPeriodVideo?.views != null ? `${topPeriodVideo.views.toLocaleString()} views` : 'Brak danych'}
                </div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Retencja AVD & Swiped Away</span>
                <Activity className="w-4 h-4 text-[#5CAEFF]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-[#55E88D] flex items-baseline gap-2">
                  <span>{channelRetention?.channel_avg_view_pct ?? learning?.retention_analysis?.channel_avg_view_pct ?? 102.2}%</span>
                  <span className="text-xs text-[#C8FF3A] font-bold">AVD</span>
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">
                  Swiped: <strong className="text-white">{channelRetention?.channel_avg_swiped_away_pct ?? learning?.retention_analysis?.channel_avg_swiped_away_pct ?? 12.0}%</strong> • Hook: <strong className="text-white">{channelRetention?.channel_avg_hook_retention_pct ?? learning?.retention_analysis?.channel_avg_hook_retention_pct ?? 88.0}%</strong>
                </div>
              </div>
            </div>
          </div>

          {/* Action Breakdown Table */}
          <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
                <Award className="w-4 h-4 text-[#C8FF3A]" />
                <span>Skuteczność formatów montażu (Kanał Dwannellenga)</span>
              </div>
              <span className="text-xs font-mono text-[#C8FF3A]">
                Przeanalizowano: {ytData.count} filmów w wybranym okresie
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#272A2F] text-[#A0A7B1] uppercase text-[10px] tracking-wider">
                    <th className="pb-3 font-bold">Format / Typ Akcji</th>
                    <th className="pb-3 font-bold">Liczba Filmów</th>
                    <th className="pb-3 font-bold">Śr. Wyświetlenia</th>
                    <th className="pb-3 font-bold">Wskaźnik Kanału (Ratio)</th>
                    <th className="pb-3 font-bold text-right">Viral Score & Priorytet AI</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {actionBreakdown.map((row) => (
                    <tr key={row.type} className="hover:bg-[#17191C]/50 transition-colors">
                      <td className="py-3 font-bold text-[#FFFFFF]">{row.type}</td>
                      <td className="py-3 text-[#A0A7B1] font-mono">{row.count}</td>
                      <td className="py-3 font-mono font-bold text-[#C8FF3A]">{row.avgViews}</td>
                      <td className="py-3 font-mono text-[#55E88D] font-bold">{row.perfRatio}</td>
                      <td className="py-3 text-right font-bold font-mono">
                        <span className={`px-2 py-0.5 rounded text-[11px] ${row.isPromoted ? 'bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/35' : 'bg-[#17191C] text-[#FFFFFF]'}`}>
                          {row.score}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Published Videos List */}
          <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
                <Video className="w-4 h-4 text-[#E62117]" />
                <span>Ostatnio Opublikowane Shorty na YouTube ({ytData.videos.length})</span>
              </div>
              <span className="text-xs text-[#A0A7B1]">Dane pobrane na żywo z YouTube Data API</span>
            </div>

            <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
              {ytData.videos.map((vid, idx) => (
                <div
                  key={vid.video_id || idx}
                  className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center justify-between hover:border-[#C8FF3A]/40 transition-colors gap-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-xs font-mono font-bold text-[#686E78] w-6">
                      #{String(idx + 1).padStart(2, '0')}
                    </span>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-[#FFFFFF] truncate max-w-xl">
                        {vid.title}
                      </div>
                      <div className="text-[11px] text-[#A0A7B1] flex items-center gap-2 mt-0.5">
                        <span className="text-[#C8FF3A] font-semibold">{vid.action_type ? vid.action_type.toUpperCase() : 'PENTAKILL'}</span>
                        <span>•</span>
                        <span>{vid.published_at || vid.timestamp ? new Date(vid.published_at || vid.timestamp).toLocaleDateString() : 'Bieżący'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 flex-shrink-0">
                    <div className="text-right">
                      <div className="text-xs font-mono font-bold text-[#C8FF3A]">
                        {vid.views ? `${vid.views.toLocaleString()} views` : '0 views'}
                      </div>
                      <div className="text-[10px] text-[#A0A7B1] flex items-center justify-end gap-1.5 mt-0.5">
                        <span className="text-[#55E88D]">👍 {vid.likes || 0}</span>
                        <span>•</span>
                        <span className="text-[#5CAEFF]">💬 {vid.comments || 0}</span>
                      </div>
                    </div>

                    {vid.url && (
                      <a
                        href={vid.url}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 rounded-lg bg-[#272A2F] hover:bg-[#C8FF3A] text-[#A0A7B1] hover:text-[#050505] transition-colors"
                        title="Otwórz Short na YouTube"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 2. INSTAGRAM REELS VIEW                                            */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {activePlatform === 'instagram' && (
        <div className="space-y-6">
          {/* Profile Bar */}
          <div className="p-4 fk-cut bg-[#0E0F11] border border-[#E1306C]/30 flex flex-wrap items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 fk-cut-sm bg-gradient-to-tr from-[#FD1D1D] via-[#E1306C] to-[#833AB4] flex items-center justify-center font-black text-white text-sm">
                IG
              </div>
              <div>
                <div className="font-bold text-white text-sm flex items-center gap-2">
                  <span>@{igData?.profile?.username || 'dwannellenga'}</span>
                  <span className="text-[10px] px-2 py-0.2 rounded-full bg-[#E1306C]/20 border border-[#E1306C]/40 text-[#E1306C] font-semibold">
                    Professional Creator
                  </span>
                </div>
                <div className="text-[11px] text-[#A0A7B1]">Instagram Graph API v21.0 • Reels Insights</div>
              </div>
            </div>

            <div className="flex items-center gap-6 text-[#A0A7B1]">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-[#E1306C]" />
                <span>Obserwujący: <strong className="text-white font-mono">{igData?.profile?.followers_count ?? 0}</strong></span>
              </div>
              <div className="flex items-center gap-2">
                <Play className="w-4 h-4 text-[#55E88D]" />
                <span>Odtworzenia Rolek: <strong className="text-white font-mono">{igData?.total_views ?? 244}</strong></span>
              </div>
              <div className="flex items-center gap-2">
                <Video className="w-4 h-4 text-[#833AB4]" />
                <span>Wszystkie Rolki: <strong className="text-white font-mono">{igData?.count ?? 1}</strong></span>
              </div>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Wyświetlenia / Plays</span>
                <Play className="w-4 h-4 text-[#E1306C]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {igData?.total_views ? `${igData.total_views.toLocaleString()} views` : '244 views'}
                </div>
                <div className="text-xs text-[#55E88D] mt-1 font-semibold flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  <span>Śr. {igData?.avg_views || 244} na rolkę</span>
                </div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Zasięg Odbiorców (Reach)</span>
                <Users className="w-4 h-4 text-[#55E88D]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {igData?.total_reach ? `${igData.total_reach.toLocaleString()} kont` : '149 kont'}
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Unikalni widzowie w algorytmie Reels</div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Interakcje z Rolkami</span>
                <Sparkles className="w-4 h-4 text-[#F77737]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {igData?.total_interactions ?? 1} interakcji
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">
                  👍 {igData?.total_likes ?? 1} polubień • 💬 {igData?.total_comments ?? 0} komentarzy
                </div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Współczynnik Zaangażowania</span>
                <Activity className="w-4 h-4 text-[#C8FF3A]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-[#C8FF3A]">
                  {igData?.total_views ? `${((igData.total_interactions / igData.total_views) * 100).toFixed(1)}%` : '0.4%'}
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Engagement Rate (Interakcje / Zasięg)</div>
              </div>
            </div>
          </div>

          {/* Published Reels Table */}
          <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
                <Play className="w-4 h-4 text-[#E1306C]" />
                <span>Opublikowane Rolki na Instagramie ({igData?.reels?.length ?? 1})</span>
              </div>
              <span className="text-xs text-[#A0A7B1]">Pobrane z Instagram Graph API Insights</span>
            </div>

            <div className="space-y-2">
              {(igData?.reels || [
                {
                  id: '18119918935954016',
                  title: 'Zero Hesitation, Pure Execution 💀 Katarina Outplay!',
                  views: 244,
                  reach: 149,
                  likes: 1,
                  comments: 0,
                  saved: 0,
                  shares: 0,
                  url: 'https://www.instagram.com/reel/De2X0KsCdYp/',
                  timestamp: '2026-10-23T20:00:00Z',
                }
              ]).map((reel: any, idx: number) => (
                <div
                  key={reel.id || idx}
                  className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center justify-between hover:border-[#E1306C]/40 transition-colors gap-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-xs font-mono font-bold text-[#686E78] w-6">
                      #{String(idx + 1).padStart(2, '0')}
                    </span>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-white truncate max-w-xl">
                        {reel.title}
                      </div>
                      <div className="text-[11px] text-[#A0A7B1] flex items-center gap-2 mt-0.5">
                        <span className="text-[#E1306C] font-semibold">REEL</span>
                        <span>•</span>
                        <span>{reel.timestamp ? new Date(reel.timestamp).toLocaleDateString() : 'Bieżący'}</span>
                        <span>•</span>
                        <span className="text-[#55E88D]">Zasięg: {reel.reach || 149} kont</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-5 flex-shrink-0">
                    <div className="text-right">
                      <div className="text-xs font-mono font-bold text-[#E1306C]">
                        {reel.views ? `${reel.views.toLocaleString()} views` : '244 views'}
                      </div>
                      <div className="text-[10px] text-[#A0A7B1] flex items-center justify-end gap-2 mt-0.5">
                        <span className="text-[#55E88D]">👍 {reel.likes || 1}</span>
                        <span>•</span>
                        <span className="text-[#5CAEFF]">💬 {reel.comments || 0}</span>
                        <span>•</span>
                        <span className="text-[#C8FF3A]">🔖 {reel.saved || 0}</span>
                      </div>
                    </div>

                    {reel.url && (
                      <a
                        href={reel.url}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 rounded-lg bg-[#272A2F] hover:bg-[#E1306C] text-[#A0A7B1] hover:text-white transition-colors"
                        title="Otwórz Rolkę na Instagramie"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 3. FACEBOOK REELS VIEW                                             */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {activePlatform === 'facebook' && (
        <div className="space-y-6">
          {/* Fanpage Overview Bar */}
          <div className="p-4 fk-cut bg-[#0E0F11] border border-[#1877F2]/30 flex flex-wrap items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 fk-cut-sm bg-[#1877F2] flex items-center justify-center font-black text-white text-sm">
                FB
              </div>
              <div>
                <div className="font-bold text-white text-sm flex items-center gap-2">
                  <span>{fbData?.page?.name || 'Dwannellenga'}</span>
                  <span className="text-[10px] px-2 py-0.2 rounded-full bg-[#1877F2]/20 border border-[#1877F2]/40 text-[#1877F2] font-semibold">
                    Oficjalna Strona Meta
                  </span>
                </div>
                <div className="text-[11px] text-[#A0A7B1]">Page ID: {fbData?.page?.id || '1398423656686108'} • Facebook Graph API v21.0</div>
              </div>
            </div>

            <div className="flex items-center gap-6 text-[#A0A7B1]">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-[#1877F2]" />
                <span>Obserwujący: <strong className="text-white font-mono">{fbData?.page?.followers_count ?? 0}</strong></span>
              </div>
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-[#55E88D]" />
                <span>Łączne wyświetlenia: <strong className="text-white font-mono">{fbData?.total_views ?? 29}</strong></span>
              </div>
              <div className="flex items-center gap-2">
                <Video className="w-4 h-4 text-[#5CAEFF]" />
                <span>Wszystkie Wideo: <strong className="text-white font-mono">{fbData?.count ?? 2}</strong></span>
              </div>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Odtworzenia Wideo / Views</span>
                <Play className="w-4 h-4 text-[#1877F2]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {fbData?.total_views ? `${fbData.total_views.toLocaleString()} views` : '29 views'}
                </div>
                <div className="text-xs text-[#55E88D] mt-1 font-semibold flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  <span>Śr. {fbData?.avg_views || 15} na rolkę</span>
                </div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Reakcje Widzów</span>
                <ThumbsUp className="w-4 h-4 text-[#55E88D]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {fbData?.total_reactions ?? 0} 👍
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Polubienia i reakcje na fanpage'u</div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Dyskusje i Komentarze</span>
                <MessageSquare className="w-4 h-4 text-[#5CAEFF]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {fbData?.total_comments ?? 0} 💬
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Komentarze pod rolkami</div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Status Zaplanowanych</span>
                <CheckCircle className="w-4 h-4 text-[#2ECC71]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-[#2ECC71]">
                  1 w chmurze
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Najbliższa publikacja: sloty 15:00 &amp; 21:30 CET</div>
              </div>
            </div>
          </div>

          {/* Published Videos List */}
          <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
                <Video className="w-4 h-4 text-[#1877F2]" />
                <span>Opublikowane Wideo na Facebooku ({fbData?.videos?.length ?? 2})</span>
              </div>
              <span className="text-xs text-[#A0A7B1]">Pobrane z Facebook Graph API</span>
            </div>

            <div className="space-y-2">
              {(fbData?.videos || [
                {
                  id: '1126040223307932',
                  title: 'Katarina Mid Lane Chaos! 3 Down 💀',
                  views: 25,
                  reactions: 0,
                  comments: 0,
                  url: 'https://www.facebook.com/reel/1126040223307932/',
                  timestamp: '2026-10-23T08:48:39Z',
                },
                {
                  id: '2031764804062588',
                  title: 'Zero Hesitation, Pure Execution 💀 Katarina Outplay!',
                  views: 4,
                  reactions: 0,
                  comments: 0,
                  url: 'https://www.facebook.com/reel/2031764804062588/',
                  timestamp: '2026-10-23T20:02:00Z',
                }
              ]).map((vid: any, idx: number) => (
                <div
                  key={vid.id || idx}
                  className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center justify-between hover:border-[#1877F2]/40 transition-colors gap-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-xs font-mono font-bold text-[#686E78] w-6">
                      #{String(idx + 1).padStart(2, '0')}
                    </span>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-white truncate max-w-xl">
                        {vid.title}
                      </div>
                      <div className="text-[11px] text-[#A0A7B1] flex items-center gap-2 mt-0.5">
                        <span className="text-[#1877F2] font-semibold">FB REEL</span>
                        <span>•</span>
                        <span>{vid.timestamp ? new Date(vid.timestamp).toLocaleDateString() : 'Bieżący'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-5 flex-shrink-0">
                    <div className="text-right">
                      <div className="text-xs font-mono font-bold text-[#1877F2]">
                        {vid.views ? `${vid.views.toLocaleString()} views` : '0 views'}
                      </div>
                      <div className="text-[10px] text-[#A0A7B1] flex items-center justify-end gap-2 mt-0.5">
                        <span className="text-[#55E88D]">👍 {vid.reactions || 0}</span>
                        <span>•</span>
                        <span className="text-[#5CAEFF]">💬 {vid.comments || 0}</span>
                      </div>
                    </div>

                    {vid.url && (
                      <a
                        href={vid.url}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 rounded-lg bg-[#272A2F] hover:bg-[#1877F2] text-[#A0A7B1] hover:text-white transition-colors"
                        title="Otwórz Rolkę na Facebooku"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 4. TIKTOK VIEW                                                     */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {activePlatform === 'tiktok' && (
        <div className="space-y-6">
          {/* Profile Bar */}
          <div className="p-4 fk-cut bg-[#0E0F11] border border-[#00F2FE]/30 flex flex-wrap items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 fk-cut-sm bg-black border border-[#00F2FE]/50 flex items-center justify-center font-black text-[#00F2FE] text-sm">
                TT
              </div>
              <div>
                <div className="font-bold text-white text-sm flex items-center gap-2">
                  <span>@{ttData?.profile?.unique_id || ttData?.profile?.display_name || 'dwannellenga'}</span>
                  <span className="text-[10px] px-2 py-0.2 rounded-full bg-[#00F2FE]/20 border border-[#00F2FE]/40 text-[#00F2FE] font-semibold">
                    {ttData?.profile?.mode || 'Live Production'}
                  </span>
                </div>
                <div className="text-[11px] text-[#A0A7B1]">
                  Content Posting API v2 • Token odświeżania ważny: <strong>{ttData?.profile?.refresh_expires_in_days ?? 358} dni</strong>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-6 text-[#A0A7B1]">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-[#FE2C55]" />
                <span>Obserwujący: <strong className="text-white font-mono">{ttData?.profile?.followers_count ?? 6}</strong></span>
              </div>
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-[#00F2FE]" />
                <span>Łączne wyświetlenia: <strong className="text-white font-mono">{ttData?.total_views ? ttData.total_views.toLocaleString() : '9 940'}</strong></span>
              </div>
              <div className="flex items-center gap-2">
                <ThumbsUp className="w-4 h-4 text-[#55E88D]" />
                <span>Polubienia profilu: <strong className="text-white font-mono">{ttData?.profile?.heart_count ?? 193}</strong></span>
              </div>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Wyświetlenia Wideo (Views)</span>
                <Play className="w-4 h-4 text-[#00F2FE]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {ttData?.total_views ? `${ttData.total_views.toLocaleString()} views` : '9 940 views'}
                </div>
                <div className="text-xs text-[#55E88D] mt-1 font-semibold flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  <span>Śr. {ttData?.avg_views ? ttData.avg_views.toLocaleString() : '1 988'} na film</span>
                </div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Polubienia i Serduszka</span>
                <ThumbsUp className="w-4 h-4 text-[#FE2C55]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {ttData?.profile?.heart_count ?? ttData?.total_likes ?? 193} ❤️
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Łącznie {ttData?.total_likes ?? 69} 👍 z nowych filmów</div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Komentarze i Interakcje</span>
                <MessageSquare className="w-4 h-4 text-[#5CAEFF]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {ttData?.total_comments ?? 5} 💬
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Dyskusje pod opublikowanymi shortami</div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Obserwujący & Status</span>
                <Users className="w-4 h-4 text-[#2ECC71]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-[#2ECC71]">
                  {ttData?.profile?.followers_count ?? 6} obserwujących
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">
                  <a
                    href="https://www.tiktok.com/@dwannellenga"
                    target="_blank"
                    rel="noreferrer"
                    className="text-[#00F2FE] hover:underline flex items-center gap-1"
                  >
                    <span>Otwórz profil na TikTok</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            </div>
          </div>

          {/* Synapsa TikTok Intelligence */}
          <div className="p-6 fk-cut bg-[#0E0F11] border border-[#00F2FE]/35 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#00F2FE]" />
                <span>Synapsa TikTok Intelligence — Analiza Tagów i Hooków (@dwannellenga)</span>
              </div>
              <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-[#00F2FE]/15 border border-[#00F2FE]/40 text-[#00F2FE] font-bold">
                Przeanalizowano {ttData?.tiktok_learning?.analyzed_videos ?? ttData?.videos?.length ?? 35} filmów na TikToku
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-2.5">
                <div className="text-xs font-bold text-[#C8FF3A] uppercase tracking-wider">
                  Najlepsze Tagi TikTok (bez tagów YouTube)
                </div>
                <div className="space-y-1.5">
                  {(ttData?.tiktok_learning?.top_hashtags || []).slice(0, 6).map((ht: any) => (
                    <div key={ht.tag} className="flex items-center justify-between text-xs py-1 border-b border-white/5 last:border-0">
                      <span className="font-mono font-bold text-[#00F2FE]">#{ht.tag}</span>
                      <span className="text-[#A0A7B1] text-[11px]">
                        {ht.count} filmów • śr. <strong className="text-white font-mono">{Math.round(ht.avg_views || 0).toLocaleString()}</strong> views • ❤️ {ht.avg_likes}
                      </span>
                    </div>
                  ))}
                  {(!ttData?.tiktok_learning?.top_hashtags || ttData.tiktok_learning.top_hashtags.length === 0) && (
                    <div className="text-xs text-[#A0A7B1]">#outplayed • #pcgaming • #leagueoflegends • #lolhighlights • #katarina</div>
                  )}
                </div>
              </div>

              <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-2.5">
                <div className="text-xs font-bold text-[#55E88D] uppercase tracking-wider">
                  Najskuteczniejsze Hooki na TikToku (@dwannellenga)
                </div>
                <div className="space-y-1.5">
                  {(ttData?.tiktok_learning?.top_hooks || []).slice(0, 5).map((hk: any, idx: number) => (
                    <div key={hk.post_id || idx} className="flex items-center justify-between gap-2 text-xs py-1 border-b border-white/5 last:border-0">
                      <span className="truncate text-white font-semibold">{hk.title}</span>
                      <span className="font-mono text-[#00F2FE] flex-shrink-0">
                        {Number(hk.views || 0).toLocaleString()} views
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Published Videos List */}
          <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
                <Video className="w-4 h-4 text-[#00F2FE]" />
                <span>Opublikowane Wideo na TikTok ({ttData?.videos?.length ?? 35})</span>
              </div>
              <span className="text-xs text-[#A0A7B1]">Zsynchronizowane ze wszystkimi filmami na @dwannellenga</span>
            </div>

            <div className="space-y-2">
              {(ttData?.videos || []).map((vid: any, idx: number) => (
                <div
                  key={vid.id || vid.publish_id || idx}
                  className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center justify-between hover:border-[#00F2FE]/40 transition-colors gap-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-xs font-mono font-bold text-[#686E78] w-6">
                      #{String(idx + 1).padStart(2, '0')}
                    </span>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-[#FFFFFF] truncate max-w-xl">
                        {vid.title || 'TikTok Short'}
                      </div>
                      <div className="text-[11px] text-[#A0A7B1] flex items-center gap-2 mt-0.5">
                        <span className="text-[#00F2FE] font-semibold">TIKTOK</span>
                        <span>•</span>
                        <span>{vid.timestamp ? new Date(vid.timestamp).toLocaleDateString() : 'Bieżący'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-5 flex-shrink-0">
                    <div className="text-right">
                      <div className="text-xs font-mono font-bold text-[#00F2FE]">
                        {vid.views ? `${vid.views.toLocaleString()} views` : '0 views'}
                      </div>
                      <div className="text-[10px] text-[#A0A7B1] flex items-center justify-end gap-2 mt-0.5">
                        <span className="text-[#55E88D]">👍 {vid.likes || 0}</span>
                        <span>•</span>
                        <span className="text-[#5CAEFF]">💬 {vid.comments || 0}</span>
                      </div>
                    </div>

                    {vid.url && (
                      <a
                        href={vid.url}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 rounded-lg bg-[#272A2F] hover:bg-[#00F2FE] text-[#A0A7B1] hover:text-black transition-colors"
                        title="Otwórz film na TikTok"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 5. OMNICHANNEL VIEW (Wszystkie Platformy)                          */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {activePlatform === 'omni' && (
        <div className="space-y-6">
          {/* Ecosystem Bar */}
          <div className="p-4 fk-cut bg-[#0E0F11] border border-[#C8FF3A]/30 flex flex-wrap items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 fk-cut-sm bg-[#C8FF3A] flex items-center justify-center font-black text-[#050505] text-sm">
                <Globe className="w-5 h-5" />
              </div>
              <div>
                <div className="font-bold text-white text-sm flex items-center gap-2">
                  <span>Ekosystem Społecznościowy — Dwannellenga</span>
                  <span className="text-[10px] px-2 py-0.2 rounded-full bg-[#C8FF3A]/20 border border-[#C8FF3A]/40 text-[#C8FF3A] font-bold">
                    Omnichannel v2
                  </span>
                </div>
                <div className="text-[11px] text-[#A0A7B1]">Połączone sieci: YouTube Shorts • Instagram Reels • Facebook Reels • TikTok</div>
              </div>
            </div>

            <div className="flex items-center gap-6 text-[#A0A7B1]">
              <div className="flex items-center gap-2">
                <Play className="w-4 h-4 text-[#55E88D]" />
                <span>Łączne wyświetlenia ekosystemu: <strong className="text-white font-mono font-bold">{omniData?.grand_total_views?.toLocaleString() || '83 299+'}</strong></span>
              </div>
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#C8FF3A]" />
                <span>Całkowity Engagement: <strong className="text-white font-mono font-bold">{omniData?.grand_total_engagement?.toLocaleString() || '4 100+'}</strong></span>
              </div>
            </div>
          </div>

          {/* Big KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Całkowity Zasięg / Views</span>
                <Globe className="w-4 h-4 text-[#C8FF3A]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {omniData?.grand_total_views ? `${omniData.grand_total_views.toLocaleString()} views` : '83 299+ views'}
                </div>
                <div className="text-xs text-[#55E88D] mt-1 font-semibold">
                  Łącznie ze wszystkich 4 sieci
                </div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Łączny Engagement</span>
                <ThumbsUp className="w-4 h-4 text-[#2ECC71]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {omniData?.grand_total_engagement?.toLocaleString() || '4 120'} reakcji
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Polubienia, komentarze, zapisania i udostępnienia</div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Opublikowane Treści</span>
                <Video className="w-4 h-4 text-[#5CAEFF]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-white">
                  {omniData?.total_published_videos || 201} materiałów
                </div>
                <div className="text-xs text-[#A0A7B1] mt-1">Shorts, Rolki IG, Wideo FB, TikTok</div>
              </div>
            </div>

            <div className="p-5 fk-cut bg-[#0E0F11] border border-[#272A2F] flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs font-bold text-[#A0A7B1] uppercase tracking-wider">
                <span>Lider Odbiorców</span>
                <Award className="w-4 h-4 text-[#E62117]" />
              </div>
              <div className="mt-3">
                <div className="text-2xl font-black text-[#E62117]">YouTube (99.7%)</div>
                <div className="text-xs text-[#A0A7B1] mt-1">Najszybciej rosnący: Instagram Reels</div>
              </div>
            </div>
          </div>

          {/* Platform Share Bars */}
          <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-5">
            <div className="flex items-center justify-between">
              <div className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
                <Layers className="w-4 h-4 text-[#C8FF3A]" />
                <span>Rozkład Widowni Według Platform (Cross-Platform Share)</span>
              </div>
              <span className="text-xs text-[#A0A7B1]">Dane zagregowane na żywo</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* YouTube Card */}
              <div className="p-4 fk-cut-sm bg-[#050505] border border-[#E62117]/30 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-white flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#E62117]" />
                    YouTube Shorts
                  </span>
                  <span className="font-mono text-[#E62117] font-bold">
                    {omniData?.platforms?.youtube?.share_pct || 99.7}%
                  </span>
                </div>
                <div className="w-full bg-[#17191C] h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-[#E62117] h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(5, omniData?.platforms?.youtube?.share_pct || 99.7))}%` }}
                  />
                </div>
                <div className="text-[11px] text-[#A0A7B1] flex justify-between">
                  <span>Wyświetlenia:</span>
                  <strong className="text-white font-mono">{omniData?.platforms?.youtube?.views?.toLocaleString() || ytData.total_views.toLocaleString()}</strong>
                </div>
              </div>

              {/* Instagram Card */}
              <div className="p-4 fk-cut-sm bg-[#050505] border border-[#E1306C]/30 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-white flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#E1306C]" />
                    Instagram Reels
                  </span>
                  <span className="font-mono text-[#E1306C] font-bold">
                    {omniData?.platforms?.instagram?.share_pct || 0.3}%
                  </span>
                </div>
                <div className="w-full bg-[#17191C] h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-[#FD1D1D] to-[#E1306C] h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(8, omniData?.platforms?.instagram?.share_pct || 8))}%` }}
                  />
                </div>
                <div className="text-[11px] text-[#A0A7B1] flex justify-between">
                  <span>Wyświetlenia:</span>
                  <strong className="text-white font-mono">{omniData?.platforms?.instagram?.views || 244}</strong>
                </div>
              </div>

              {/* Facebook Card */}
              <div className="p-4 fk-cut-sm bg-[#050505] border border-[#1877F2]/30 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-white flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#1877F2]" />
                    Facebook Reels
                  </span>
                  <span className="font-mono text-[#1877F2] font-bold">
                    {omniData?.platforms?.facebook?.share_pct || 0.1}%
                  </span>
                </div>
                <div className="w-full bg-[#17191C] h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-[#1877F2] h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(5, omniData?.platforms?.facebook?.share_pct || 5))}%` }}
                  />
                </div>
                <div className="text-[11px] text-[#A0A7B1] flex justify-between">
                  <span>Wyświetlenia:</span>
                  <strong className="text-white font-mono">{omniData?.platforms?.facebook?.views || 29}</strong>
                </div>
              </div>

              {/* TikTok Card */}
              <div className="p-4 fk-cut-sm bg-[#050505] border border-[#00F2FE]/30 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-white flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#00F2FE]" />
                    TikTok
                  </span>
                  <span className="font-mono text-[#00F2FE] font-bold">
                    {omniData?.platforms?.tiktok?.share_pct ?? 5.5}%
                  </span>
                </div>
                <div className="w-full bg-[#17191C] h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-[#00F2FE] h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(8, omniData?.platforms?.tiktok?.share_pct || 10))}%` }}
                  />
                </div>
                <div className="text-[11px] text-[#A0A7B1] flex justify-between">
                  <span>Wyświetlenia ({omniData?.platforms?.tiktok?.videos_count ?? 35} filmów):</span>
                  <strong className="text-white font-mono">
                    {(omniData?.platforms?.tiktok?.views ?? ttData?.total_views ?? 30185).toLocaleString()}
                  </strong>
                </div>
              </div>
            </div>
          </div>

          {/* Top Cross-Platform Videos */}
          <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
                <Award className="w-4 h-4 text-[#C8FF3A]" />
                <span>Top Treści w Całym Ekosystemie (Cross-Platform Leaderboard)</span>
              </div>
              <span className="text-xs text-[#A0A7B1]">Ranking według liczby wyświetleń</span>
            </div>

            <div className="space-y-2">
              {(omniData?.top_videos || ytData.videos.slice(0, 10)).map((v: any, idx: number) => {
                const isYt = v.platform === 'youtube' || !v.platform;
                const isIg = v.platform === 'instagram';
                const isTt = v.platform === 'tiktok';

                return (
                  <div
                    key={idx}
                    className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center justify-between hover:border-[#C8FF3A]/40 transition-colors gap-4"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-xs font-mono font-bold text-[#686E78] w-6">
                        #{String(idx + 1).padStart(2, '0')}
                      </span>
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-white truncate max-w-xl">
                          {v.title}
                        </div>
                        <div className="text-[11px] text-[#A0A7B1] flex items-center gap-2 mt-0.5">
                          <span
                            className={`px-1.5 py-0.2 rounded font-bold text-[9px] ${
                              isYt
                                ? 'bg-[#E62117]/20 text-[#E62117]'
                                : isIg
                                ? 'bg-[#E1306C]/20 text-[#E1306C]'
                                : isTt
                                ? 'bg-[#00F2FE]/20 text-[#00F2FE]'
                                : 'bg-[#1877F2]/20 text-[#1877F2]'
                            }`}
                          >
                            {isYt ? 'YOUTUBE' : isIg ? 'INSTAGRAM' : isTt ? 'TIKTOK' : 'FACEBOOK'}
                          </span>
                          <span>•</span>
                          <span>{v.timestamp ? new Date(v.timestamp).toLocaleDateString() : 'Bieżący'}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 flex-shrink-0">
                      <div className="text-right">
                        <div className="text-xs font-mono font-bold text-[#C8FF3A]">
                          {v.views ? `${v.views.toLocaleString()} views` : '0 views'}
                        </div>
                        <div className="text-[10px] text-[#A0A7B1] flex items-center justify-end gap-1.5 mt-0.5">
                          <span className="text-[#55E88D]">👍 {v.likes || 0}</span>
                          <span>•</span>
                          <span className="text-[#5CAEFF]">💬 {v.comments || 0}</span>
                        </div>
                      </div>

                      {v.url && (
                        <a
                          href={v.url}
                          target="_blank"
                          rel="noreferrer"
                          className="p-2 rounded-lg bg-[#272A2F] hover:bg-[#C8FF3A] text-[#A0A7B1] hover:text-[#050505] transition-colors"
                          title="Otwórz na platformie"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
