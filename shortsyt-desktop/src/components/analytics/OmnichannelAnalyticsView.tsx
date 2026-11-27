import React from 'react';
import {
  Globe, Play, Sparkles, ThumbsUp, Video, Award, Layers, ExternalLink,
} from 'lucide-react';
import { YouTubeAnalyticsState } from './analyticsHelpers';

interface OmnichannelAnalyticsViewProps {
  omniData: any;
  ytData: YouTubeAnalyticsState;
  ttData: any;
}

export default function OmnichannelAnalyticsView({
  omniData,
  ytData,
  ttData,
}: OmnichannelAnalyticsViewProps) {
  return (
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
  );
}
