import React, { useState, useEffect } from 'react';
import {
  apiGetAnalytics, apiGetLearningStatus, apiGetChannelRetention,
  apiGetSocialAnalytics,
  LearningDirective, ChannelRetentionOverview,
} from '../lib/api';
import {
  BarChart3, Download, RefreshCw, CheckCircle, Globe,
} from 'lucide-react';
import {
  PlatformTab, YouTubeAnalyticsState, computeActionBreakdown, exportAnalyticsCSV,
} from '../components/analytics/analyticsHelpers';
import YouTubeAnalyticsView from '../components/analytics/YouTubeAnalyticsView';
import InstagramAnalyticsView from '../components/analytics/InstagramAnalyticsView';
import FacebookAnalyticsView from '../components/analytics/FacebookAnalyticsView';
import TikTokAnalyticsView from '../components/analytics/TikTokAnalyticsView';
import OmnichannelAnalyticsView from '../components/analytics/OmnichannelAnalyticsView';

export default function Analytics() {
  const [activePlatform, setActivePlatform] = useState<PlatformTab>('youtube');
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | 'all'>('30d');
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const [ytData, setYtData] = useState<YouTubeAnalyticsState>({
    count: 0,
    total_views: 0,
    total_likes: 0,
    total_comments: 0,
    avg_views: 0,
    videos: [],
  });

  const [igData, setIgData] = useState<any>(null);
  const [fbData, setFbData] = useState<any>(null);
  const [ttData, setTtData] = useState<any>(null);
  const [omniData, setOmniData] = useState<any>(null);

  const [learning, setLearning] = useState<LearningDirective | null>(null);
  const [channelRetention, setChannelRetention] = useState<ChannelRetentionOverview | null>(null);

  const fetchYouTubeAnalytics = async (range: '7d' | '30d' | 'all', forceRefresh: boolean = false) => {
    try {
      const res = await apiGetAnalytics(range, forceRefresh);
      if (res && res.videos) setYtData(res);
    } catch (err) {
      console.warn('YouTube analytics fetch error:', err);
    }
  };

  const fetchSocialAnalytics = async (platform: PlatformTab, forceRefresh: boolean = false) => {
    try {
      if (platform === 'instagram') {
        setIgData(await apiGetSocialAnalytics('instagram', forceRefresh));
      } else if (platform === 'facebook') {
        setFbData(await apiGetSocialAnalytics('facebook', forceRefresh));
      } else if (platform === 'tiktok') {
        setTtData(await apiGetSocialAnalytics('tiktok', forceRefresh));
      } else if (platform === 'omni') {
        setOmniData(await apiGetSocialAnalytics('all', forceRefresh));
      }
    } catch (err) {
      console.warn(`Social analytics error (${platform}):`, err);
    }
  };

  const loadActiveData = async (forceRefresh: boolean = false) => {
    if (forceRefresh) setRefreshing(true);
    else setLoading(true);

    if (activePlatform === 'youtube') {
      await fetchYouTubeAnalytics(timeRange, forceRefresh);
      try {
        const learnRes = await apiGetLearningStatus();
        if (learnRes?.directive) setLearning(learnRes.directive);
      } catch (err) {
        console.warn('[Analytics] apiGetLearningStatus error:', err);
      }
      try {
        const retRes = await apiGetChannelRetention();
        if (retRes?.data) setChannelRetention(retRes.data);
      } catch (err) {
        console.warn('[Analytics] apiGetChannelRetention error:', err);
      }
    } else {
      await fetchSocialAnalytics(activePlatform, forceRefresh);
    }

    setLoading(false);
    setRefreshing(false);
  };

  useEffect(() => {
    loadActiveData();
  }, [activePlatform, timeRange]);

  const { actionBreakdown, topPeriodVideo } = computeActionBreakdown(
    ytData.videos,
    ytData.avg_views,
    ytData.top_videos,
    learning
  );

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
              onClick={() => exportAnalyticsCSV(activePlatform, ytData, igData, fbData, omniData)}
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

      {activePlatform === 'youtube' && (
        <YouTubeAnalyticsView
          ytData={ytData}
          timeRange={timeRange}
          loading={loading}
          topPeriodVideo={topPeriodVideo}
          channelRetention={channelRetention}
          learning={learning}
          actionBreakdown={actionBreakdown}
        />
      )}
      {activePlatform === 'instagram' && <InstagramAnalyticsView igData={igData} />}
      {activePlatform === 'facebook' && <FacebookAnalyticsView fbData={fbData} />}
      {activePlatform === 'tiktok' && <TikTokAnalyticsView ttData={ttData} />}
      {activePlatform === 'omni' && (
        <OmnichannelAnalyticsView omniData={omniData} ytData={ytData} ttData={ttData} />
      )}
    </div>
  );
}
