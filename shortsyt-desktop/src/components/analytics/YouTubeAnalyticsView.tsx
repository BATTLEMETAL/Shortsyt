import React from 'react';
import {
  Users, Eye, Video, RefreshCw, TrendingUp, ThumbsUp, Award, Activity, ExternalLink,
} from 'lucide-react';
import { ChannelRetentionOverview, LearningDirective } from '../../lib/api';
import { FormatRow, VideoMetric, YouTubeAnalyticsState } from './analyticsHelpers';

interface YouTubeAnalyticsViewProps {
  ytData: YouTubeAnalyticsState;
  timeRange: '7d' | '30d' | 'all';
  loading: boolean;
  topPeriodVideo?: VideoMetric;
  channelRetention: ChannelRetentionOverview | null;
  learning: LearningDirective | null;
  actionBreakdown: FormatRow[];
}

export default function YouTubeAnalyticsView({
  ytData,
  timeRange,
  loading,
  topPeriodVideo,
  channelRetention,
  learning,
  actionBreakdown,
}: YouTubeAnalyticsViewProps) {
  return (
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
  );
}
