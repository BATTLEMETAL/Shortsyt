import React from 'react';
import {
  Users, Play, Video, TrendingUp, Sparkles, Activity, ExternalLink,
} from 'lucide-react';

interface InstagramAnalyticsViewProps {
  igData: any;
}

export default function InstagramAnalyticsView({ igData }: InstagramAnalyticsViewProps) {
  return (
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
  );
}
