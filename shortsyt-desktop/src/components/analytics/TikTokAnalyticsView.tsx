import React from 'react';
import {
  Users, Eye, ThumbsUp, Play, TrendingUp, MessageSquare, ExternalLink, Sparkles, Video,
} from 'lucide-react';

interface TikTokAnalyticsViewProps {
  ttData: any;
}

export default function TikTokAnalyticsView({ ttData }: TikTokAnalyticsViewProps) {
  return (
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
  );
}
