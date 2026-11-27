import React from 'react';
import {
  Users, Eye, Video, Play, TrendingUp, ThumbsUp, MessageSquare, CheckCircle, ExternalLink,
} from 'lucide-react';

interface FacebookAnalyticsViewProps {
  fbData: any;
}

export default function FacebookAnalyticsView({ fbData }: FacebookAnalyticsViewProps) {
  return (
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
  );
}
