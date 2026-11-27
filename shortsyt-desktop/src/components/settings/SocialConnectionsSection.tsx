import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Share2, RefreshCw, Video, ShieldCheck, ShieldOff, ShieldAlert, Copy,
  Instagram, KeyRound, ExternalLink,
} from 'lucide-react';
import {
  apiGetTikTokStatus, apiGetTikTokUserInfo, apiStartTikTokOAuth, apiExchangeTikTokCode,
  apiGetInstagramStatus, apiGetFacebookStatus, apiSetupMetaToken,
  TikTokStatus, TikTokUserInfo, InstagramStatus, FacebookStatus,
} from '../../lib/api';

export default function SocialConnectionsSection({ tokenReady }: { tokenReady: boolean }) {
  const [ttStatus, setTtStatus] = useState<TikTokStatus | null>(null);
  const [ttUserInfo, setTtUserInfo] = useState<TikTokUserInfo | null>(null);
  const [igStatus, setIgStatus] = useState<InstagramStatus | null>(null);
  const [fbStatus, setFbStatus] = useState<FacebookStatus | null>(null);
  const [socialLoading, setSocialLoading] = useState(false);
  const [ttAuthorizing, setTtAuthorizing] = useState(false);
  const [ttAuthUrl, setTtAuthUrl] = useState<string>('');
  const [ttAuthState, setTtAuthState] = useState<string>('');
  const [ttManualCode, setTtManualCode] = useState<string>('');
  const [ttCodeSubmitting, setTtCodeSubmitting] = useState<boolean>(false);
  const [ttCopiedUrl, setTtCopiedUrl] = useState<boolean>(false);
  const [ttAuthMsg, setTtAuthMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const ttPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [metaTokenInput, setMetaTokenInput] = useState<string>('');
  const [metaSubmitting, setMetaSubmitting] = useState<boolean>(false);
  const [metaResult, setMetaResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const fetchSocialStatus = useCallback(async () => {
    if (!tokenReady) return;
    setSocialLoading(true);
    try {
      const [tt, ttUser, ig, fb] = await Promise.all([
        apiGetTikTokStatus().catch((e) => { console.warn('[Settings] apiGetTikTokStatus:', e); return null; }),
        apiGetTikTokUserInfo().catch((e) => { console.warn('[Settings] apiGetTikTokUserInfo:', e); return null; }),
        apiGetInstagramStatus().catch((e) => { console.warn('[Settings] apiGetInstagramStatus:', e); return null; }),
        apiGetFacebookStatus().catch((e) => { console.warn('[Settings] apiGetFacebookStatus:', e); return null; }),
      ]);
      setTtStatus(tt);
      setTtUserInfo(ttUser);
      setIgStatus(ig);
      setFbStatus(fb);
    } catch (e) {
      console.warn('[Settings] fetchSocialStatus error:', e);
    } finally {
      setSocialLoading(false);
    }
  }, [tokenReady]);

  useEffect(() => {
    fetchSocialStatus();
  }, [fetchSocialStatus]);

  const stopTtPolling = () => {
    if (ttPollRef.current) {
      clearInterval(ttPollRef.current);
      ttPollRef.current = null;
    }
  };

  useEffect(() => () => { stopTtPolling(); }, []);

  const handleSetupMeta = async () => {
    if (!metaTokenInput.trim()) return;
    setMetaSubmitting(true);
    setMetaResult(null);
    try {
      const res = await apiSetupMetaToken(metaTokenInput.trim());
      setMetaResult({ ok: true, msg: res.message || 'Token Meta pomyślnie zaktualizowany!' });
      setMetaTokenInput('');
      fetchSocialStatus();
    } catch (e: any) {
      setMetaResult({ ok: false, msg: e.response?.data?.detail || e.message || 'Błąd autoryzacji Meta' });
    } finally {
      setMetaSubmitting(false);
    }
  };

  const handleStartTikTokOAuth = async () => {
    stopTtPolling();
    setTtAuthMsg(null);
    setTtCopiedUrl(false);
    setTtManualCode('');
    const wasValidBefore = Boolean(ttStatus?.valid);
    try {
      const res = await apiStartTikTokOAuth();
      setTtAuthUrl(res.auth_url);
      setTtAuthState(res.state);
      setTtAuthorizing(true);

      if (window.electronApp?.openExternal) {
        window.electronApp.openExternal(res.auth_url).catch((err) => {
          console.warn('[Settings] TikTok openExternal error:', err);
        });
      } else {
        window.open(res.auth_url, '_blank', 'noopener,noreferrer');
      }

      if (res.listener_error) {
        setTtAuthMsg({
          type: 'error',
          text: `${res.listener_error} Możesz wkleić kod autoryzacji ręcznie poniżej.`,
        });
      }

      let attempts = 0;
      ttPollRef.current = setInterval(async () => {
        attempts += 1;
        if (attempts > 60) {
          stopTtPolling();
          setTtAuthorizing(false);
          setTtAuthMsg({ type: 'error', text: 'Timeout autoryzacji TikTok (180 s). Spróbuj ponownie.' });
          return;
        }
        try {
          const s = await apiGetTikTokStatus();
          setTtStatus(s);
          const oauthSt = s?.oauth_state?.last_status;
          if (oauthSt === 'authorized' || (!wasValidBefore && s?.valid)) {
            stopTtPolling();
            setTtAuthorizing(false);
            setTtAuthMsg({ type: 'success', text: 'Autoryzacja TikTok OAuth 2.0 zakończona pomyślnie.' });
          } else if (oauthSt === 'error') {
            stopTtPolling();
            setTtAuthorizing(false);
            setTtAuthMsg({
              type: 'error',
              text: s?.oauth_state?.last_error || 'Błąd autoryzacji TikTok OAuth.',
            });
          }
        } catch (err) {
          console.warn('[Settings] TikTok OAuth poll error:', err);
        }
      }, 3000);
    } catch (e: any) {
      setTtAuthorizing(false);
      setTtAuthMsg({
        type: 'error',
        text: e.response?.data?.detail || e.message || 'Nie udało się rozpocząć OAuth TikTok.',
      });
    }
  };

  const handleCancelTikTokOAuth = () => {
    stopTtPolling();
    setTtAuthorizing(false);
  };

  const handleSubmitManualTtCode = async () => {
    const cleanCode = ttManualCode.trim();
    if (!cleanCode) return;
    setTtCodeSubmitting(true);
    setTtAuthMsg(null);
    try {
      await apiExchangeTikTokCode(cleanCode, ttAuthState || undefined);
      stopTtPolling();
      setTtAuthorizing(false);
      setTtManualCode('');
      await fetchSocialStatus();
      setTtAuthMsg({ type: 'success', text: 'Kod TikTok wymieniony na token OAuth 2.0.' });
    } catch (e: any) {
      setTtAuthMsg({
        type: 'error',
        text: e.response?.data?.detail || e.message || 'Błąd wymiany kodu TikTok.',
      });
    } finally {
      setTtCodeSubmitting(false);
    }
  };

  return (
    <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5 text-sm font-bold text-[#FFFFFF]">
          <Share2 className="w-4 h-4 text-[#C8FF3A]" />
          <span>Multi-Platform — TikTok, Instagram &amp; Facebook Page</span>
        </div>
        <button onClick={() => fetchSocialStatus()} disabled={socialLoading}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF] disabled:opacity-40">
          <RefreshCw className={`w-3 h-3 ${socialLoading ? 'animate-spin' : ''}`} /> Odswiez
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* TikTok Card */}
        <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Video className="w-4 h-4 text-[#00F2FE]" />
              <span className="text-xs font-bold text-[#FFFFFF]">TikTok (Shortsyt-Dev)</span>
            </div>
            {ttStatus?.valid ? (
              <span className="flex items-center gap-1 text-[11px] font-bold text-[#55E88D]">
                <ShieldCheck className="w-3.5 h-3.5" /> Aktywny
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[11px] font-bold text-[#FF5C5C]">
                <ShieldOff className="w-3.5 h-3.5" /> Wymagana autoryzacja
              </span>
            )}
          </div>
          <div className="flex items-center gap-2.5 p-2 rounded bg-[#0E0F11] border border-[#272A2F]">
            {ttUserInfo?.ok && ttUserInfo.avatar_url ? (
              <img
                src={ttUserInfo.avatar_url}
                alt={ttUserInfo.display_name || 'TikTok profile'}
                className="w-8 h-8 rounded-full object-cover border border-[#00F2FE]/50 shrink-0"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-[#FE2C55]/20 border border-[#FE2C55]/40 text-[#FFFFFF] flex items-center justify-center font-black text-xs shrink-0">
                {(ttUserInfo?.display_name || 'DW').slice(0, 2).toUpperCase()}
              </div>
            )}
            <div className="min-w-0">
              <div className="text-xs font-bold text-[#C8FF3A] truncate">
                {ttUserInfo?.ok && ttUserInfo.display_name ? ttUserInfo.display_name : 'Dwannellenga'}
              </div>
              <div className="text-[10px] text-[#A0A7B1] font-mono truncate">
                @dwannellenga • user.info.basic
              </div>
            </div>
          </div>
          <div className="text-[11px] text-[#A0A7B1] space-y-1 font-mono">
            <div>Scopes: <span className="text-[#00F2FE]">user.info.basic, video.upload, video.publish</span></div>
            <div>
              Status:{' '}
              <span className={`font-sans font-semibold ${ttAuthorizing ? 'text-[#FFB347]' : ttStatus?.valid ? 'text-[#55E88D]' : 'text-[#FFFFFF]'}`}>
                {ttAuthorizing
                  ? 'Oczekiwanie na callback http://localhost:8180/callback...'
                  : (ttStatus?.message || 'Sprawdzam...')}
              </span>
            </div>
            {ttStatus?.refresh_expires_in_days !== undefined && (
              <div>Waznosc tokenu: <span className="text-[#C8FF3A]">{ttStatus.refresh_expires_in_days} dni</span></div>
            )}
            {ttStatus?.open_id && (
              <div className="truncate text-[10px] text-[#686E78]">OpenID: {ttStatus.open_id}</div>
            )}
          </div>
          <button
            type="button"
            onClick={handleStartTikTokOAuth}
            disabled={!tokenReady}
            className="w-full py-2 px-3 fk-cut-sm bg-[#FE2C55]/90 hover:bg-[#FE2C55] disabled:opacity-50 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
          >
            <Video className="w-3.5 h-3.5" />
            <span>{ttAuthorizing ? 'Ponów autoryzację TikTok OAuth 2.0' : 'Connect / Authorize TikTok OAuth 2.0'}</span>
          </button>

          {ttAuthorizing && (
            <div className="p-2.5 fk-cut-sm bg-[#0E0F11] border border-[#00F2FE]/30 space-y-2 text-[11px]">
              <div className="text-[#A0A7B1]">
                Otwarto prawdziwe okno <span className="text-[#00F2FE] font-mono">tiktok.com/v2/auth/authorize</span> w przeglądarce (callback: <span className="font-mono text-[#FFFFFF]">localhost:8180/callback</span>).
              </div>
              <div className="flex items-center gap-2">
                {ttAuthUrl && (
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(ttAuthUrl);
                      setTtCopiedUrl(true);
                      setTimeout(() => setTtCopiedUrl(false), 2500);
                    }}
                    className="px-2 py-1 rounded bg-[#17191C] border border-[#272A2F] text-[#C8FF3A] text-[10px] font-bold flex items-center gap-1"
                  >
                    <Copy className="w-3 h-3" />
                    <span>{ttCopiedUrl ? 'Skopiowano link' : 'Kopiuj URL OAuth'}</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleCancelTikTokOAuth}
                  className="px-2 py-1 rounded bg-[#17191C] border border-[#272A2F] text-[#A0A7B1] hover:text-[#FFFFFF] text-[10px] font-semibold"
                >
                  Anuluj
                </button>
              </div>
              <div className="flex gap-1.5 pt-1">
                <input
                  type="text"
                  value={ttManualCode}
                  onChange={(e) => setTtManualCode(e.target.value)}
                  placeholder="Opcjonalnie: wklej code= z callbacku..."
                  className="flex-1 bg-[#050505] border border-[#272A2F] rounded px-2 py-1 text-[10px] text-[#FFFFFF] font-mono outline-none focus:border-[#00F2FE]"
                />
                <button
                  type="button"
                  onClick={handleSubmitManualTtCode}
                  disabled={ttCodeSubmitting || !ttManualCode.trim()}
                  className="px-2.5 py-1 rounded bg-[#00F2FE]/20 border border-[#00F2FE]/40 text-[#00F2FE] text-[10px] font-bold disabled:opacity-40"
                >
                  {ttCodeSubmitting ? '...' : 'Zatwierdź kod'}
                </button>
              </div>
            </div>
          )}

          {ttAuthMsg && (
            <div className={`p-2 rounded text-[11px] font-semibold ${ttAuthMsg.type === 'success' ? 'bg-[#55E88D]/15 text-[#55E88D] border border-[#55E88D]/30' : 'bg-[#FF5C5C]/15 text-[#FF5C5C] border border-[#FF5C5C]/30'}`}>
              {ttAuthMsg.text}
            </div>
          )}
        </div>

        {/* Instagram Card */}
        <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Instagram className="w-4 h-4 text-[#E1306C]" />
              <span className="text-xs font-bold text-[#FFFFFF]">Instagram Reels</span>
            </div>
            {igStatus?.valid ? (
              <span className="flex items-center gap-1 text-[11px] font-bold text-[#55E88D]">
                <ShieldCheck className="w-3.5 h-3.5" /> Aktywny (Wieczny)
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[11px] font-bold text-[#FF5C5C]">
                <ShieldOff className="w-3.5 h-3.5" /> Wymagana autoryzacja
              </span>
            )}
          </div>
          <div className="text-[11px] text-[#A0A7B1] space-y-1 font-mono">
            <div>Konto: <span className="text-[#FFFFFF] font-sans">@{igStatus?.username || 'dwannellenga'}</span></div>
            {igStatus?.instagram_account_id && (
              <div>IG ID: <span className="text-[#C8FF3A]">{igStatus.instagram_account_id}</span></div>
            )}
            <div className="text-[10px] text-[#55E88D] font-sans">Direct Meta Resumable Upload (rupload.facebook.com)</div>
          </div>
        </div>

        {/* Facebook Card */}
        <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Share2 className="w-4 h-4 text-[#1877F2]" />
              <span className="text-xs font-bold text-[#FFFFFF]">Facebook Page</span>
            </div>
            {fbStatus?.valid ? (
              <span className="flex items-center gap-1 text-[11px] font-bold text-[#55E88D]">
                <ShieldCheck className="w-3.5 h-3.5" /> Aktywny
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[11px] font-bold text-[#FF5C5C]">
                <ShieldOff className="w-3.5 h-3.5" /> Wymagana autoryzacja
              </span>
            )}
          </div>
          <div className="text-[11px] text-[#A0A7B1] space-y-1 font-mono">
            <div>Fanpage: <span className="text-[#FFFFFF] font-sans">{fbStatus?.page_name || 'Dwannellenga'}</span></div>
            {fbStatus?.page_id && (
              <div>Page ID: <span className="text-[#1877F2]">{fbStatus.page_id}</span></div>
            )}
            <div className="text-[10px] text-[#55E88D] font-sans">Meta Graph API v19.0 (Reels &amp; Video)</div>
          </div>
        </div>
      </div>

      {/* ── META RE-AUTHORIZATION FORM (FB + IG) ── */}
      <div className="mt-4 p-4 fk-cut-sm bg-[#050505] border border-[#C8FF3A]/30 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-[#C8FF3A]" />
            <span className="text-xs font-bold text-[#FFFFFF]">Odśwież Token Meta (Facebook &amp; Instagram)</span>
          </div>
          <a
            href="https://developers.facebook.com/tools/explorer/"
            target="_blank"
            rel="noreferrer"
            className="text-[11px] text-[#C8FF3A] hover:text-[#C8FF3A] flex items-center gap-1 font-semibold transition-colors"
          >
            <span>Graph API Explorer</span> <ExternalLink className="w-3 h-3" />
          </a>
        </div>
        <p className="text-[11px] text-[#A0A7B1] leading-relaxed">
          Wklej <strong>User Access Token</strong> z Meta Graph API Explorer. Aplikacja automatycznie wymieni go na wieczny token strony i autoryzuje jednocześnie <strong>Facebook Page (Dwannellenga)</strong> oraz <strong>Instagram Reels (@dwannellenga)</strong>.
        </p>
        <div className="flex gap-2">
          <input
            type="password"
            value={metaTokenInput}
            onChange={(e) => setMetaTokenInput(e.target.value)}
            placeholder="Wklej User Access Token (np. EAA...)..."
            className="flex-1 bg-[#0E0F11] border border-[#272A2F] rounded-lg px-3 py-2 text-xs text-[#FFFFFF] focus:border-[#C8FF3A] outline-none font-mono"
          />
          <button
            onClick={handleSetupMeta}
            disabled={metaSubmitting || !metaTokenInput.trim()}
            className="px-4 py-2 bg-[#C8FF3A] hover:bg-[#C8FF3A] disabled:opacity-50 text-[#050505] text-xs font-bold rounded-lg flex items-center gap-1.5 transition-colors whitespace-nowrap"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${metaSubmitting ? 'animate-spin' : ''}`} />
            {metaSubmitting ? 'Weryfikuję...' : 'Zapisz i Autoryzuj'}
          </button>
        </div>
        {metaResult && (
          <div className={`p-2.5 rounded-lg text-xs font-semibold flex items-center gap-2 ${metaResult.ok ? 'bg-[#55E88D]/15 text-[#55E88D] border border-[#55E88D]/30' : 'bg-[#FF5C5C]/15 text-[#FF5C5C] border border-[#FF5C5C]/30'}`}>
            {metaResult.ok ? <ShieldCheck className="w-4 h-4 shrink-0" /> : <ShieldAlert className="w-4 h-4 shrink-0" />}
            <span>{metaResult.msg}</span>
          </div>
        )}
      </div>
    </div>
  );
}
