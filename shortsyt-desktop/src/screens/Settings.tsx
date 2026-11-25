import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  getServerUrl, setServerUrl, getJwtToken, clearJwtToken,
  apiLogin, apiHealthCheck, apiGetYtTokenStatus, apiGetYtAuthUrl,
  apiGetHardwareInfo, apiRunBenchmarkScan,
  apiGetTikTokStatus, apiGetTikTokUserInfo, apiStartTikTokOAuth, apiExchangeTikTokCode, apiGetInstagramStatus, apiGetFacebookStatus, apiSetupMetaToken, TikTokStatus, TikTokUserInfo, InstagramStatus, FacebookStatus,
  DEFAULT_URL, YtTokenStatusResponse, HardwareProfile,
  apiListAccounts, apiUpsertAccount, apiSelectAccount, apiDeleteAccount, AccountProfile, ContentModePreset,
  apiGetRemoteAccess, apiStartRemoteTunnel, apiStopRemoteTunnel, RemoteAccessStatus,
} from '../lib/api';
import {
  Settings as SettingsIcon, Save, KeyRound, Server, Check, AlertCircle,
  Trash2, Youtube, RefreshCw, ExternalLink, ShieldCheck, ShieldAlert, ShieldOff, Copy,
  Instagram, Share2, Video, Users, Plus, Smartphone, Wifi, Globe, Edit3,
} from 'lucide-react';

export default function Settings() {
  const [url, setUrl] = useState<string>(DEFAULT_URL);
  const [password, setPassword] = useState<string>('');
  const [token, setToken] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [healthStatus, setHealthStatus] = useState<boolean | null>(null);
  const [activeAccountLabel, setActiveAccountLabel] = useState<string>('Dwannellenga');

  // YouTube OAuth
  const [ytStatus, setYtStatus] = useState<YtTokenStatusResponse | null>(null);
  const [ytLoading, setYtLoading] = useState(false);
  const [ytAuthorizing, setYtAuthorizing] = useState(false);
  const [currentAuthUrl, setCurrentAuthUrl] = useState<string>('');
  const [copied, setCopied] = useState(false);
  const [ytMsg, setYtMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Multi-Platform Social Tokens
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

  const fetchSocialStatus = useCallback(async () => {
    if (!token) return;
    setSocialLoading(true);
    try {
      const [tt, ttUser, ig, fb] = await Promise.all([
        apiGetTikTokStatus().catch(() => null),
        apiGetTikTokUserInfo().catch(() => null),
        apiGetInstagramStatus().catch(() => null),
        apiGetFacebookStatus().catch(() => null),
      ]);
      setTtStatus(tt);
      setTtUserInfo(ttUser);
      setIgStatus(ig);
      setFbStatus(fb);
    } catch {
      // ignore
    } finally {
      setSocialLoading(false);
    }
  }, [token]);

  // Meta Token Setup (Facebook Page & Instagram)
  const [metaTokenInput, setMetaTokenInput] = useState<string>('');
  const [metaSubmitting, setMetaSubmitting] = useState<boolean>(false);
  const [metaResult, setMetaResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const handleSetupMeta = async () => {
    if (!metaTokenInput.trim()) return;
    setMetaSubmitting(true);
    setMetaResult(null);
    try {
      const res = await apiSetupMetaToken(metaTokenInput.trim());
      setMetaResult({ ok: true, msg: res.message || "Token Meta pomyślnie zaktualizowany!" });
      setMetaTokenInput('');
      fetchSocialStatus();
    } catch (e: any) {
      setMetaResult({ ok: false, msg: e.response?.data?.detail || e.message || "Błąd autoryzacji Meta" });
    } finally {
      setMetaSubmitting(false);
    }
  };

  useEffect(() => {
    fetchSocialStatus();
  }, [fetchSocialStatus]);

  useEffect(() => {
    async function load() {
      const u = await getServerUrl(); setUrl(u);
      const t = await getJwtToken(); setToken(t);
      const h = await apiHealthCheck(u); setHealthStatus(h.ok);
    }
    load();
  }, []);

  const fetchYtStatus = useCallback(async () => {
    if (!token) return;
    setYtLoading(true);
    try { const s = await apiGetYtTokenStatus(); setYtStatus(s); return s; }
    catch { setYtStatus(null); return null; }
    finally { setYtLoading(false); }
  }, [token]);

  useEffect(() => { fetchYtStatus(); }, [fetchYtStatus]);

  useEffect(() => {
    if (!token) return;
    apiListAccounts()
      .then((res) => {
        const active = res.accounts.find((a) => a.account_id === res.active_account_id) || res.accounts[0];
        if (active) setActiveAccountLabel(active.display_name);
      })
      .catch(() => {});
  }, [token]);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const stopTtPolling = () => {
    if (ttPollRef.current) { clearInterval(ttPollRef.current); ttPollRef.current = null; }
  };

  useEffect(() => () => { stopPolling(); stopTtPolling(); }, []);

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
        window.electronApp.openExternal(res.auth_url).catch(() => {});
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
        } catch {
          // ignore transient poll error
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

  const handleSaveUrl = async (e: React.FormEvent) => {
    e.preventDefault(); setIsSaving(true); setStatusMsg(null);
    try {
      await setServerUrl(url);
      const h = await apiHealthCheck(url); setHealthStatus(h.ok);
      setStatusMsg({ type: h.ok ? 'success' : 'error', text: h.ok ? 'URL serwera zapisany!' : 'Serwer nie odpowiada.' });
    } catch (err: any) { setStatusMsg({ type: 'error', text: err.message || 'Blad zapisu URL' }); }
    finally { setIsSaving(false); }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault(); if (!password) return;
    setIsSaving(true); setStatusMsg(null);
    try {
      const newToken = await apiLogin(password);
      setToken(newToken); setPassword('');
      setStatusMsg({ type: 'success', text: 'Zalogowano! Token JWT zapisany.' });
    } catch (err: any) { setStatusMsg({ type: 'error', text: err.response?.data?.detail || 'Blad logowania' }); }
    finally { setIsSaving(false); }
  };

  const handleLogout = async () => {
    await clearJwtToken(); setToken(null);
    setStatusMsg({ type: 'success', text: 'Wylogowano. Token usuniety.' });
  };

  const handleYtStartAuth = async () => {
    setYtMsg(null); setYtLoading(true); stopPolling(); setCopied(false);
    try {
      const authUrl = await apiGetYtAuthUrl();
      setCurrentAuthUrl(authUrl);

      // Sprobuj otworzyc przez Electron shell
      if (window.electronApp?.openExternal) {
        window.electronApp.openExternal(authUrl).catch(() => {});
      } else {
        window.open(authUrl, '_blank');
      }

      setYtAuthorizing(true);
      setYtMsg({ type: 'success', text: `Link wygenerowany! Zaloguj sie na ${activeAccountLabel} w przegladarce.` });

      let attempts = 0;
      pollRef.current = setInterval(async () => {
        attempts++;
        if (attempts > 120) {
          stopPolling(); setYtAuthorizing(false);
          setYtMsg({ type: 'error', text: 'Timeout autoryzacji (5 min). Sprobuj ponownie.' });
          return;
        }
        try {
          const s = await apiGetYtTokenStatus();
          if (s?.is_valid) {
            stopPolling(); setYtAuthorizing(false); setYtStatus(s);
            setYtMsg({ type: 'success', text: '✅ Token YouTube zapisany! Autoryzacja zakonczona sukcesem.' });
          }
        } catch { /* ignore poll errors */ }
      }, 2500);

    } catch (e: any) {
      setYtMsg({ type: 'error', text: 'Blad: ' + (e.message || String(e)) });
    } finally {
      setYtLoading(false);
    }
  };

  const handleCopyUrl = () => {
    if (currentAuthUrl) {
      navigator.clipboard.writeText(currentAuthUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    }
  };

  const handleCancelAuth = () => {
    stopPolling(); setYtAuthorizing(false);
    setYtMsg(null);
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#050505] p-6 lg:p-8 space-y-6 text-[#FFFFFF]">
      {/* Header */}
      <div className="pb-4 border-b border-[#272A2F]">
        <h1 className="text-2xl font-black tracking-tight text-[#FFFFFF] flex items-center gap-2.5">
          <SettingsIcon className="w-6 h-6 text-[#C8FF3A]" /><span>Ustawienia Systemu</span>
        </h1>
        <p className="text-xs text-[#A0A7B1] mt-1 font-medium">Konfiguracja backendu, JWT i YouTube OAuth</p>
      </div>

      {/* Alert JWT */}
      {statusMsg && (
        <div className={`p-4 fk-cut-sm border text-xs flex items-center gap-2 ${statusMsg.type === 'success' ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]' : 'bg-[#FF5C5C]/10 border-[#FF5C5C]/30 text-[#FF5C5C]'}`}>
          {statusMsg.type === 'success' ? <Check className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          <span className="font-semibold">{statusMsg.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Server URL */}
        <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#FFFFFF]">
            <Server className="w-4 h-4 text-[#5CAEFF]" /><span>FastAPI Server URL</span>
          </div>
          <form onSubmit={handleSaveUrl} className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-[#A0A7B1] block mb-1.5">Adres API Backend</label>
              <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://localhost:8765"
                className="w-full px-3.5 py-2.5 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-mono text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]" />
              <span className="text-[11px] text-[#686E78] mt-1 block">Domyslny port: 8765</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${healthStatus === true ? 'bg-[#2ECC71]' : healthStatus === false ? 'bg-[#FF5C5C]' : 'bg-[#A0A7B1]'}`} />
                <span className="text-xs text-[#A0A7B1]">{healthStatus === true ? 'Serwer dostepny' : healthStatus === false ? 'Brak odpowiedzi' : 'Sprawdzanie...'}</span>
              </div>
              <button type="submit" disabled={isSaving} className="px-4 py-2 fk-cut-sm bg-[#C8FF3A] hover:bg-[#C8FF3A] text-[#050505] text-xs font-bold flex items-center gap-1.5">
                <Save className="w-3.5 h-3.5" /><span>Zapisz URL</span>
              </button>
            </div>
          </form>
        </div>

        {/* JWT */}
        <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-4">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#FFFFFF]">
            <KeyRound className="w-4 h-4 text-[#C8FF3A]" /><span>Autoryzacja (JWT)</span>
          </div>
          {token ? (
            <div className="space-y-4">
              <div className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F]">
                <div className="text-xs text-[#A0A7B1] font-semibold">Stan:</div>
                <div className="text-xs font-bold text-[#55E88D] mt-0.5">ZALOGOWANO</div>
                <div className="text-[10px] font-mono text-[#686E78] truncate mt-1">{token}</div>
              </div>
              <button onClick={handleLogout} className="px-4 py-2 fk-cut-sm bg-[#FF5C5C]/15 hover:bg-[#FF5C5C]/25 border border-[#FF5C5C]/30 text-[#FF5C5C] text-xs font-bold flex items-center gap-1.5">
                <Trash2 className="w-3.5 h-3.5" /><span>Wyloguj</span>
              </button>
            </div>
          ) : (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-[#A0A7B1] block mb-1.5">Haslo API</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="shortsyt2026"
                  className="w-full px-3.5 py-2.5 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-mono text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]" />
              </div>
              <button type="submit" disabled={isSaving || !password} className="w-full py-2.5 fk-cut-sm bg-[#C8FF3A] hover:bg-[#C8FF3A] text-[#050505] text-xs font-bold flex items-center justify-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5" /><span>Zaloguj i wygeneruj JWT</span>
              </button>
            </form>
          )}
        </div>
      </div>

      {/* ── YouTube OAuth ─────────────────────────────────────── */}
      <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#FFFFFF]">
            <Youtube className="w-4 h-4 text-[#FF0000]" />
            <span>YouTube OAuth — Token kanału: {activeAccountLabel}</span>
          </div>
          <button onClick={() => fetchYtStatus()} disabled={ytLoading || ytAuthorizing}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF] disabled:opacity-40">
            <RefreshCw className={`w-3 h-3 ${ytLoading ? 'animate-spin' : ''}`} /> Odswiez
          </button>
        </div>

        {/* Status badge */}
        <div className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] flex items-center justify-between gap-3 flex-wrap">
          {ytLoading ? (
            <span className="text-xs text-[#A0A7B1] flex items-center gap-1"><RefreshCw className="w-3 h-3 animate-spin" /> Sprawdzam...</span>
          ) : !ytStatus || !ytStatus.has_token ? (
            <span className="flex items-center gap-1.5 text-xs font-bold text-[#FF5C5C]"><ShieldOff className="w-4 h-4" /> Brak tokenu — wymagana autoryzacja</span>
          ) : !ytStatus.is_valid ? (
            <span className="flex items-center gap-1.5 text-xs font-bold text-[#FFB347]"><ShieldAlert className="w-4 h-4" /> Token wygasl — odnow autoryzacje</span>
          ) : (
            <span className={`flex items-center gap-1.5 text-xs font-bold ${ytStatus.days_remaining !== null && ytStatus.days_remaining < 7 ? 'text-[#FFB347]' : 'text-[#55E88D]'}`}>
              <ShieldCheck className="w-4 h-4" /> Token aktywny
              {ytStatus.days_remaining !== null && <span>&nbsp;(wygasa za {ytStatus.days_remaining} dni)</span>}
              {ytStatus.can_refresh && <span className="text-[#A0A7B1] font-normal">&nbsp;&#8226; auto-refresh OK</span>}
            </span>
          )}
          {ytStatus?.expires_at && (
            <span className="text-[10px] font-mono text-[#686E78]">{new Date(ytStatus.expires_at).toLocaleString()}</span>
          )}
        </div>

        {/* Scopes */}
        <div className="text-[11px] text-[#686E78] bg-[#050505] rounded-lg px-3 py-2">
          <span className="font-semibold text-[#A0A7B1]">Scopes:</span>{' '}
          youtube.upload &#8226; youtube.readonly &#8226; <span className="text-[#C8FF3A]">youtube.force-ssl</span> (pinned comments)
        </div>

        {/* YT message */}
        {ytMsg && (
          <div className={`p-3.5 fk-cut-sm border text-xs flex items-start gap-2 ${ytMsg.type === 'success' ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]' : 'bg-[#FF5C5C]/10 border-[#FF5C5C]/30 text-[#FF5C5C]'}`}>
            {ytMsg.type === 'success' ? <Check className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
            <span className="font-semibold">{ytMsg.text}</span>
          </div>
        )}

        {/* Auth flow UI */}
        {ytAuthorizing ? (
          /* Waiting for callback */
          <div className="p-5 fk-cut-sm bg-[#050505] border border-[#C8FF3A]/40 space-y-4">
            <div className="flex items-center gap-3">
              <RefreshCw className="w-5 h-5 text-[#C8FF3A] animate-spin flex-shrink-0" />
              <div>
                <p className="text-xs font-bold text-[#FFFFFF]">Czekam na autoryzacje w przegladarce (Opera GX)...</p>
                <p className="text-[11px] text-[#A0A7B1] mt-0.5">
                  Zaloguj się na konto <strong>{activeAccountLabel}</strong> i zaakceptuj uprawnienia. Po zalogowaniu token zapisze się automatycznie.
                </p>
              </div>
            </div>

            {/* Direct copy section for Opera GX */}
            {currentAuthUrl && (
              <div className="p-3.5 fk-cut-sm bg-[#0E0F11] border border-[#272A2F] space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-[#C8FF3A]">
                    🔗 Jesli Opera GX nie otworzyla sie sama — skopiuj link ponizej:
                  </span>
                  <button onClick={handleCopyUrl}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#C8FF3A] hover:bg-[#C8FF3A] text-[#050505] text-xs font-bold transition-all">
                    {copied ? <Check className="w-3.5 h-3.5 text-[#050505]" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copied ? 'Skopiowano!' : 'Kopiuj link do Opera GX'}</span>
                  </button>
                </div>
                <input type="text" readOnly value={currentAuthUrl} onClick={(e) => (e.target as HTMLInputElement).select()}
                  className="w-full px-3 py-2 rounded-lg bg-[#050505] border border-[#272A2F] text-[11px] font-mono text-[#A0A7B1] focus:outline-none focus:border-[#C8FF3A] select-all" />
              </div>
            )}

            <div className="flex gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-[#272A2F] overflow-hidden">
                <div className="h-full bg-[#C8FF3A] animate-pulse rounded-full" style={{ width: '70%' }} />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <button onClick={handleCancelAuth}
                className="text-xs text-[#A0A7B1] hover:text-[#FF5C5C] transition-colors">
                Anuluj autoryzacje
              </button>
              <span className="text-[11px] text-[#686E78]">Backend nasluchuje w tle</span>
            </div>
          </div>
        ) : (
          /* Start auth button */
          <div className="space-y-3">
            <p className="text-xs text-[#A0A7B1]">
              {ytStatus?.is_valid
                ? 'Token aktywny. Kliknij "Odnow" aby wymusic ponowna autoryzacje (force-ssl dla pinned comments).'
                : 'Kliknij ponizej — wygeneruje sie link autoryzacyjny. Mozesz go skopiowac i otworzyc w Opera GX.'}
            </p>
            <button onClick={handleYtStartAuth} disabled={ytLoading || !token}
              className="flex items-center gap-2 px-4 py-2.5 fk-cut-sm bg-[#FF0000]/90 hover:bg-[#FF0000] disabled:opacity-50 text-white text-xs font-bold transition-colors">
              <Youtube className="w-3.5 h-3.5" />
              {ytStatus?.is_valid ? 'Odnow token YouTube' : 'Autoryzuj kanal YouTube'}
              <ExternalLink className="w-3 h-3 ml-1 opacity-70" />
            </button>
            {!token && <p className="text-[11px] text-[#FFB347]">Musisz byc zalogowany (JWT) aby autoryzowac YouTube.</p>}
          </div>
        )}
      </div>

      {/* ── Multi-Platform Social Accounts (TikTok & Instagram) ── */}
      <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#FFFFFF]">
            <Share2 className="w-4 h-4 text-[#C8FF3A]" />
            <span>Multi-Platform — TikTok, Instagram & Facebook Page</span>
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
                  alt={ttUserInfo.display_name || "TikTok profile"}
                  className="w-8 h-8 rounded-full object-cover border border-[#00F2FE]/50 shrink-0"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-[#FE2C55]/20 border border-[#FE2C55]/40 text-[#FFFFFF] flex items-center justify-center font-black text-xs shrink-0">
                  {(ttUserInfo?.display_name || "DW").slice(0, 2).toUpperCase()}
                </div>
              )}
              <div className="min-w-0">
                <div className="text-xs font-bold text-[#C8FF3A] truncate">
                  {ttUserInfo?.ok && ttUserInfo.display_name ? ttUserInfo.display_name : "Dwannellenga"}
                </div>
                <div className="text-[10px] text-[#A0A7B1] font-mono truncate">
                  @dwannellenga • user.info.basic
                </div>
              </div>
            </div>
            <div className="text-[11px] text-[#A0A7B1] space-y-1 font-mono">
              <div>Scopes: <span className="text-[#00F2FE]">user.info.basic, video.upload, video.publish</span></div>
              <div>
                Status:{" "}
                <span className={`font-sans font-semibold ${ttAuthorizing ? "text-[#FFB347]" : ttStatus?.valid ? "text-[#55E88D]" : "text-[#FFFFFF]"}`}>
                  {ttAuthorizing
                    ? "Oczekiwanie na callback http://localhost:8180/callback..."
                    : (ttStatus?.message || "Sprawdzam...")}
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
              disabled={!token}
              className="w-full py-2 px-3 fk-cut-sm bg-[#FE2C55]/90 hover:bg-[#FE2C55] disabled:opacity-50 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
            >
              <Video className="w-3.5 h-3.5" />
              <span>{ttAuthorizing ? "Ponów autoryzację TikTok OAuth 2.0" : "Connect / Authorize TikTok OAuth 2.0"}</span>
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
                      <span>{ttCopiedUrl ? "Skopiowano link" : "Kopiuj URL OAuth"}</span>
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
                    {ttCodeSubmitting ? "..." : "Zatwierdź kod"}
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
              <div>Konto: <span className="text-[#FFFFFF] font-sans">@{igStatus?.username || "dwannellenga"}</span></div>
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
              <div>Fanpage: <span className="text-[#FFFFFF] font-sans">{fbStatus?.page_name || "Dwannellenga"}</span></div>
              {fbStatus?.page_id && (
                <div>Page ID: <span className="text-[#1877F2]">{fbStatus.page_id}</span></div>
              )}
              <div className="text-[10px] text-[#55E88D] font-sans">Meta Graph API v19.0 (Reels & Video)</div>
            </div>
          </div>
        </div>

        {/* ── META RE-AUTHORIZATION FORM (FB + IG) ── */}
        <div className="mt-4 p-4 fk-cut-sm bg-[#050505] border border-[#C8FF3A]/30 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-[#C8FF3A]" />
              <span className="text-xs font-bold text-[#FFFFFF]">Odśwież Token Meta (Facebook & Instagram)</span>
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
              {metaSubmitting ? "Weryfikuję..." : "Zapisz i Autoryzuj"}
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

      {/* ── SEKCJA MULTI-ACCOUNT & WYTYCZNE KONTENTU ── */}
      <AccountsManagerCard
        tokenReady={!!token}
        onAccountSwitched={(acc) => {
          setActiveAccountLabel(acc.display_name);
          fetchYtStatus();
          window.dispatchEvent(new Event('account-changed'));
        }}
      />

      {/* ── SEKCJA ZDALNEGO STEROWANIA Z TELEFONU (MOBILE PILOT) ── */}
      <RemoteAccessCard tokenReady={!!token} />

      {/* ── SEKCJA SKANERA SPRZĘTU I AUTO-TUNINGU ── */}
      <HardwareScannerCard />
    </div>
  );
}

function HardwareScannerCard() {
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadInfo = async () => {
    try {
      setLoading(true);
      const data = await apiGetHardwareInfo();
      setProfile(data);
    } catch (e: any) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInfo();
  }, []);

  const handleRunScan = async () => {
    try {
      setScanning(true);
      setMsg(null);
      const res = await apiRunBenchmarkScan();
      setProfile(res.profile);
      setMsg({ type: 'success', text: `⚡ Skan zakończony! Zoptymalizowano parametry dla profilu: ${res.profile?.tier_label}` });
    } catch (e: any) {
      setMsg({ type: 'error', text: `Błąd skanowania: ${e.message}` });
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-[#272A2F]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#C8FF3A]/10 border border-[#C8FF3A]/30 flex items-center justify-center">
            <RefreshCw className="w-4 h-4 text-[#C8FF3A]" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-[#FFFFFF] flex items-center gap-2">
              Skaner Systemu i Optymalizacja Sprzętowa
              {profile?.tier === 'high' && (
                <span className="px-2 py-0.5 rounded bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/35 text-[10px] font-black">
                  🚀 HIGH-END
                </span>
              )}
              {profile?.tier === 'medium' && (
                <span className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-[10px] font-black">
                  ⚡ BALANCED
                </span>
              )}
              {profile?.tier === 'low' && (
                <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-black">
                  🛡️ ECO-PC
                </span>
              )}
            </h2>
            <p className="text-[11px] text-[#A0A7B1]">
              Automatyczne dopasowanie enkoderów FFmpeg, wątków i próbkowania OCR pod wydajność Twojego komputera
            </p>
          </div>
        </div>

        <button
          onClick={handleRunScan}
          disabled={scanning}
          className="flex items-center gap-2 px-4 py-2.5 fk-cut-sm fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] font-bold text-xs transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
          {scanning ? 'Skanowanie PC...' : '⚡ Skanuj System i Zoptymalizuj'}
        </button>
      </div>

      {msg && (
        <div className={`p-3.5 fk-cut-sm border text-xs flex items-center gap-2 ${
          msg.type === 'success' ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]' : 'bg-[#FF5C5C]/10 border-[#FF5C5C]/30 text-[#FF5C5C]'
        }`}>
          {msg.type === 'success' ? <Check className="w-4 h-4 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 flex-shrink-0" />}
          <span className="font-semibold">{msg.text}</span>
        </div>
      )}

      {profile && profile.hardware ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* CPU */}
            <div className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-1">
              <span className="text-[10px] font-semibold text-[#A0A7B1] uppercase tracking-wider">Procesor (CPU)</span>
              <p className="text-xs font-bold text-[#FFFFFF] line-clamp-1">{profile.hardware.cpu_name}</p>
              <span className="text-[11px] text-cyan-400 font-medium">{profile.hardware.cpu_cores} wątków logicznych</span>
            </div>

            {/* GPU */}
            <div className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-1">
              <span className="text-[10px] font-semibold text-[#A0A7B1] uppercase tracking-wider">Karta Graficzna (GPU)</span>
              <p className="text-xs font-bold text-[#FFFFFF] line-clamp-1">{profile.hardware.gpu_name}</p>
              <span className="text-[11px] text-[#C8FF3A] font-medium">VRAM: {profile.hardware.vram_gb} GB ({profile.hardware.detected_encoder})</span>
            </div>

            {/* RAM */}
            <div className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-1">
              <span className="text-[10px] font-semibold text-[#A0A7B1] uppercase tracking-wider">Pamięć RAM</span>
              <p className="text-xs font-bold text-[#FFFFFF]">{profile.hardware.ram_total_gb} GB Total</p>
              <span className="text-[11px] text-emerald-400 font-medium">Dostępne: {profile.hardware.ram_available_gb} GB</span>
            </div>

            {/* Tuned Settings */}
            <div className="p-3.5 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-1">
              <span className="text-[10px] font-semibold text-[#A0A7B1] uppercase tracking-wider">Aktywny Enkoder</span>
              <p className="text-xs font-bold text-[#C8FF3A]">{profile.tuned_settings.encoder.toUpperCase()}</p>
              <span className="text-[11px] text-[#A0A7B1] font-medium">{profile.tuned_settings.render_fps} FPS • max jakość</span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-[#0E0F11] border border-[#272A2F] text-[11px] text-[#A0A7B1] flex items-center justify-between">
            <span>
              💡 <strong>Opis konfiguracji:</strong> {profile.tier_description}
            </span>
            <span className="text-[#686E78] hidden md:inline">
              Ostatni skan: {new Date(profile.scanned_at).toLocaleString('pl-PL')}
            </span>
          </div>
        </div>
      ) : (
        <div className="text-center py-6 text-xs text-[#A0A7B1]">
          Kliknij "Skanuj System", aby automatycznie przeanalizować podzespoły i dobrać optymalne parametry.
        </div>
      )}
    </div>
  );
}

interface AccountsManagerCardProps {
  tokenReady: boolean;
  onAccountSwitched: (acc: AccountProfile) => void;
}

interface AccountFormState {
  account_id?: string;
  display_name: string;
  handle: string;
  content_mode: string;
  language: string;
  peak_hours_text: string;
  brand_voice: string;
  value_proposition: string;
  target_audience: string;
  cta_text: string;
  cta_url: string;
  location: string;
  phone: string;
  hashtags_text: string;
  forbidden_text: string;
}

const EMPTY_ACCOUNT_FORM: AccountFormState = {
  display_name: '',
  handle: '',
  content_mode: 'PRODUCT_ECOMMERCE_AD',
  language: 'pl',
  peak_hours_text: '15:00, 21:30',
  brand_voice: '',
  value_proposition: '',
  target_audience: '',
  cta_text: '',
  cta_url: '',
  location: '',
  phone: '',
  hashtags_text: '#shorts',
  forbidden_text: '',
};

function AccountsManagerCard({ tokenReady, onAccountSwitched }: AccountsManagerCardProps) {
  const [accounts, setAccounts] = useState<AccountProfile[]>([]);
  const [activeId, setActiveId] = useState<string>('');
  const [presets, setPresets] = useState<Record<string, ContentModePreset>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [showForm, setShowForm] = useState<boolean>(false);
  const [form, setForm] = useState<AccountFormState>(EMPTY_ACCOUNT_FORM);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadAccounts = useCallback(async () => {
    if (!tokenReady) return;
    setLoading(true);
    try {
      const res = await apiListAccounts();
      setAccounts(res.accounts || []);
      setActiveId(res.active_account_id || '');
      setPresets(res.presets || {});
    } catch (e: any) {
      setMsg({ type: 'error', text: e?.response?.data?.detail || 'Nie udało się pobrać listy kont.' });
    } finally {
      setLoading(false);
    }
  }, [tokenReady]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const applyPresetToNewForm = (mode: string) => {
    const p = presets[mode];
    if (!p) {
      setForm((prev) => ({ ...prev, content_mode: mode }));
      return;
    }
    setForm((prev) => ({
      ...prev,
      content_mode: mode,
      language: p.language || prev.language,
      peak_hours_text: (p.peak_hours_cet || []).join(', '),
      brand_voice: p.brand_voice || '',
      value_proposition: p.value_proposition || '',
      cta_text: p.cta_text || '',
      cta_url: p.cta_url || '',
      hashtags_text: (p.mandatory_hashtags || []).join(', '),
      forbidden_text: (p.forbidden_words || []).join(', '),
    }));
  };

  const startNewAccount = () => {
    setMsg(null);
    const defaultMode = 'PRODUCT_ECOMMERCE_AD';
    const p = presets[defaultMode];
    setForm({
      ...EMPTY_ACCOUNT_FORM,
      content_mode: defaultMode,
      language: p?.language || 'pl',
      peak_hours_text: (p?.peak_hours_cet || ['15:00', '21:30']).join(', '),
      brand_voice: p?.brand_voice || '',
      value_proposition: p?.value_proposition || '',
      cta_text: p?.cta_text || '',
      hashtags_text: (p?.mandatory_hashtags || ['#shorts']).join(', '),
      forbidden_text: (p?.forbidden_words || []).join(', '),
    });
    setShowForm(true);
  };

  const startEditAccount = (acc: AccountProfile) => {
    setMsg(null);
    setForm({
      account_id: acc.account_id,
      display_name: acc.display_name || '',
      handle: acc.handle || '',
      content_mode: acc.content_mode || 'GAMING_HIGHLIGHTS',
      language: acc.language || 'pl',
      peak_hours_text: (acc.peak_hours_cet || []).join(', '),
      brand_voice: acc.brand_voice || '',
      value_proposition: acc.value_proposition || '',
      target_audience: acc.target_audience || '',
      cta_text: acc.cta_text || '',
      cta_url: acc.cta_url || '',
      location: acc.location || '',
      phone: acc.phone || '',
      hashtags_text: (acc.mandatory_hashtags || []).join(', '),
      forbidden_text: (acc.forbidden_words || []).join(', '),
    });
    setShowForm(true);
  };

  const handleSelect = async (accountId: string) => {
    setMsg(null);
    try {
      const res = await apiSelectAccount(accountId);
      setActiveId(res.active_account.account_id);
      await loadAccounts();
      onAccountSwitched(res.active_account);
      setMsg({ type: 'success', text: `Aktywowano konto: ${res.active_account.display_name}. Teraz możesz autoryzować/sprawdzić token YT powyżej.` });
    } catch (e: any) {
      setMsg({ type: 'error', text: e?.response?.data?.detail || 'Błąd przełączania konta.' });
    }
  };

  const handleDelete = async (acc: AccountProfile) => {
    setMsg(null);
    try {
      await apiDeleteAccount(acc.account_id);
      await loadAccounts();
      setMsg({ type: 'success', text: `Usunięto konto: ${acc.display_name}` });
    } catch (e: any) {
      setMsg({ type: 'error', text: e?.response?.data?.detail || 'Nie można usunąć tego konta.' });
    }
  };

  const handleSaveForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.display_name.trim()) {
      setMsg({ type: 'error', text: 'Podaj nazwę kanału / klienta.' });
      return;
    }
    setSaving(true);
    setMsg(null);
    const parseList = (raw: string) =>
      raw
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    const parseCommaList = (raw: string) =>
      raw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

    try {
      const res = await apiUpsertAccount({
        account_id: form.account_id,
        display_name: form.display_name.trim(),
        handle: form.handle.trim(),
        content_mode: form.content_mode,
        language: form.language,
        peak_hours_cet: parseCommaList(form.peak_hours_text),
        brand_voice: form.brand_voice.trim(),
        value_proposition: form.value_proposition.trim(),
        target_audience: form.target_audience.trim(),
        cta_text: form.cta_text.trim(),
        cta_url: form.cta_url.trim(),
        location: form.location.trim(),
        phone: form.phone.trim(),
        mandatory_hashtags: parseList(form.hashtags_text),
        forbidden_words: parseCommaList(form.forbidden_text),
        set_active: true,
      });
      setShowForm(false);
      await loadAccounts();
      onAccountSwitched(res.account);
      setMsg({ type: 'success', text: `Zapisano i aktywowano profil: ${res.account.display_name}` });
    } catch (e: any) {
      setMsg({ type: 'error', text: e?.response?.data?.detail || 'Błąd zapisu konta.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#FFFFFF]">
            <Users className="w-4 h-4 text-[#C8FF3A]" />
            <span>Multi-Account &amp; Wytyczne Kontentu (Klienci / Sandbox YT)</span>
          </div>
          <p className="text-[11px] text-[#A0A7B1] mt-1">
            Przełączaj między kanałem gamingowym, kontem testowym (Sandbox) i klientami (salon, e-commerce). Generator metadanych i token YouTube dopasują się automatycznie.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadAccounts}
            disabled={loading || !tokenReady}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF] disabled:opacity-40"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Odśwież
          </button>
          <button
            type="button"
            onClick={showForm ? () => setShowForm(false) : startNewAccount}
            disabled={!tokenReady}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#C8FF3A] text-[#050505] text-xs font-extrabold hover:bg-[#d6ff66] disabled:opacity-40"
          >
            <Plus className="w-3.5 h-3.5" /> {showForm ? 'Zamknij formularz' : 'Dodaj Konto / Klienta'}
          </button>
        </div>
      </div>

      {!tokenReady && (
        <div className="p-3 bg-[#050505] border border-[#272A2F] text-xs text-[#A0A7B1]">
          Zaloguj się tokenem JWT powyżej, aby zarządzać kontami.
        </div>
      )}

      {msg && (
        <div className={`p-3 fk-cut-sm border text-xs flex items-start gap-2 ${msg.type === 'success' ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]' : 'bg-[#FF5C5C]/10 border-[#FF5C5C]/30 text-[#FF5C5C]'}`}>
          {msg.type === 'success' ? <Check className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
          <span className="font-semibold">{msg.text}</span>
        </div>
      )}

      {/* Account List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {accounts.map((acc) => {
          const isActive = acc.account_id === activeId || acc.is_active;
          return (
            <div
              key={acc.account_id}
              className={`p-4 fk-cut-sm bg-[#050505] border space-y-2.5 ${
                isActive ? 'border-[#C8FF3A]' : 'border-[#272A2F]'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-extrabold text-[#FFFFFF] truncate">{acc.display_name}</span>
                    {isActive && (
                      <span className="px-1.5 py-0.5 text-[10px] font-extrabold bg-[#C8FF3A] text-[#050505]">
                        AKTYWNE
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-[#686E78] font-mono mt-0.5">
                    {acc.handle || acc.account_id} · {acc.content_mode} · {acc.language?.toUpperCase()}
                  </div>
                </div>
                <span
                  className={`flex items-center gap-1 text-[10px] font-bold flex-shrink-0 ${
                    acc.yt_token_exists ? 'text-[#55E88D]' : 'text-[#FFB347]'
                  }`}
                >
                  {acc.yt_token_exists ? <ShieldCheck className="w-3.5 h-3.5" /> : <ShieldOff className="w-3.5 h-3.5" />}
                  {acc.yt_token_exists ? 'Token YT OK' : 'Brak tokenu YT'}
                </span>
              </div>

              <div className="text-[11px] text-[#A0A7B1] space-y-1">
                {acc.value_proposition && <div className="line-clamp-2"><span className="text-[#686E78]">Cel/Nisza:</span> {acc.value_proposition}</div>}
                {acc.brand_voice && <div><span className="text-[#686E78]">Styl:</span> {acc.brand_voice}</div>}
                <div>
                  <span className="text-[#686E78]">Sloty CET:</span> {(acc.peak_hours_cet || []).join(' & ') || '15:00 & 21:30'}
                  {acc.location ? ` · 📍 ${acc.location}` : ''}
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1 flex-wrap">
                {!isActive && (
                  <button
                    type="button"
                    onClick={() => handleSelect(acc.account_id)}
                    className="px-2.5 py-1 bg-[#C8FF3A]/15 border border-[#C8FF3A]/50 text-[#C8FF3A] text-[11px] font-bold hover:bg-[#C8FF3A]/25"
                  >
                    Aktywuj
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => startEditAccount(acc)}
                  className="flex items-center gap-1 px-2.5 py-1 bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1] text-[11px] font-semibold hover:text-[#FFFFFF]"
                >
                  <Edit3 className="w-3 h-3" /> Wytyczne
                </button>
                {!acc.builtin && (
                  <button
                    type="button"
                    onClick={() => handleDelete(acc)}
                    className="flex items-center gap-1 px-2 py-1 bg-[#FF5C5C]/10 border border-[#FF5C5C]/30 text-[#FF5C5C] text-[11px] font-semibold hover:bg-[#FF5C5C]/20 ml-auto"
                  >
                    <Trash2 className="w-3 h-3" /> Usuń
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Add / Edit Account & Guidelines Form */}
      {showForm && (
        <form onSubmit={handleSaveForm} className="p-4 fk-cut-sm bg-[#050505] border border-[#C8FF3A]/40 space-y-4">
          <div className="text-xs font-extrabold text-[#C8FF3A] uppercase tracking-wider">
            {form.account_id ? `Edycja profilu i wytycznych (${form.account_id})` : 'Nowe Konto / Klient + Wytyczne Kontentu'}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Nazwa kanału / klienta *</label>
              <input
                type="text"
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                placeholder="np. Sklep BioBeauty / Konto Sandbox #2"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Handle / Link (@kanał)</label>
              <input
                type="text"
                value={form.handle}
                onChange={(e) => setForm({ ...form, handle: e.target.value })}
                placeholder="np. @salonprettywoman"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Szablon / Typ kontentu</label>
              <select
                value={form.content_mode}
                onChange={(e) => {
                  const mode = e.target.value;
                  if (!form.account_id) {
                    applyPresetToNewForm(mode);
                  } else {
                    setForm({ ...form, content_mode: mode });
                  }
                }}
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              >
                {Object.entries(presets).length > 0 ? (
                  Object.entries(presets).map(([key, p]) => (
                    <option key={key} value={key}>{p.label}</option>
                  ))
                ) : (
                  <>
                    <option value="PRODUCT_ECOMMERCE_AD">Reklama Produktu / E-commerce</option>
                    <option value="BEAUTY_SALON_SERVICE">Salon Beauty / Usługi Lokalne</option>
                    <option value="GAMING_HIGHLIGHTS">Gaming / Sandbox Highlights</option>
                    <option value="EXPERT_BRAND_SHORT">Marka Osobista / Ekspert</option>
                  </>
                )}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[11px] text-[#A0A7B1] mb-1">Język</label>
                <select
                  value={form.language}
                  onChange={(e) => setForm({ ...form, language: e.target.value })}
                  className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
                >
                  <option value="pl">PL (Polski)</option>
                  <option value="en">EN (English)</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] text-[#A0A7B1] mb-1">Sloty publikacji (CET)</label>
                <input
                  type="text"
                  value={form.peak_hours_text}
                  onChange={(e) => setForm({ ...form, peak_hours_text: e.target.value })}
                  placeholder="15:00, 21:30"
                  className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
                />
              </div>
            </div>

            <div className="md:col-span-2">
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Główna obietnica / Nisza / Produkt (Value Proposition)</label>
              <input
                type="text"
                value={form.value_proposition}
                onChange={(e) => setForm({ ...form, value_proposition: e.target.value })}
                placeholder="np. Afroloki i metamorfozy w 3h / Szybki blender turystyczny USB-C"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Ton i styl komunikacji (Brand Voice)</label>
              <input
                type="text"
                value={form.brand_voice}
                onChange={(e) => setForm({ ...form, brand_voice: e.target.value })}
                placeholder="np. Konkretny, problem -> efekt, bez lania wody"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>
            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Grupa docelowa</label>
              <input
                type="text"
                value={form.target_audience}
                onChange={(e) => setForm({ ...form, target_audience: e.target.value })}
                placeholder="np. Kobiety 25-45, PL / Dolny Śląsk"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">CTA (Wezwanie do działania)</label>
              <input
                type="text"
                value={form.cta_text}
                onChange={(e) => setForm({ ...form, cta_text: e.target.value })}
                placeholder="np. Zarezerwuj wizytę / Link w bio 👇"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>
            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Link CTA / Sklep</label>
              <input
                type="text"
                value={form.cta_url}
                onChange={(e) => setForm({ ...form, cta_url: e.target.value })}
                placeholder="https://..."
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Lokalizacja / Adres (opcjonalnie dla salonu)</label>
              <input
                type="text"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder="np. ul. Ofiar Oświęcimskich 28, Świdnica"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>
            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Telefon kontaktowy (opcjonalnie)</label>
              <input
                type="text"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="np. 788-945-643"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>

            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Obowiązkowe hashtagi (oddzielone spacją/przecinkiem)</label>
              <input
                type="text"
                value={form.hashtags_text}
                onChange={(e) => setForm({ ...form, hashtags_text: e.target.value })}
                placeholder="#shorts, #produkt, #recenzja"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>
            <div>
              <label className="block text-[11px] text-[#A0A7B1] mb-1">Słowa zakazane (np. Katarina, Pentakill)</label>
              <input
                type="text"
                value={form.forbidden_text}
                onChange={(e) => setForm({ ...form, forbidden_text: e.target.value })}
                placeholder="Katarina, League of Legends"
                className="w-full px-3 py-2 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#FFFFFF]"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="px-3 py-1.5 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF]"
            >
              Anuluj
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-1.5 bg-[#C8FF3A] text-[#050505] text-xs font-extrabold hover:bg-[#d6ff66] disabled:opacity-50"
            >
              {saving ? 'Zapisywanie...' : 'Zapisz Profil & Wytyczne'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function RemoteAccessCard({ tokenReady }: { tokenReady: boolean }) {
  const [status, setStatus] = useState<RemoteAccessStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [toggling, setToggling] = useState<boolean>(false);
  const [copiedKey, setCopiedKey] = useState<string>('');
  const [err, setErr] = useState<string>('');

  const loadRemote = useCallback(async () => {
    if (!tokenReady) return;
    setLoading(true);
    setErr('');
    try {
      const data = await apiGetRemoteAccess();
      setStatus(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Nie udało się pobrać statusu zdalnego dostępu.');
    } finally {
      setLoading(false);
    }
  }, [tokenReady]);

  useEffect(() => {
    loadRemote();
  }, [loadRemote]);

  const handleCopy = (key: string, value: string) => {
    navigator.clipboard.writeText(value);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(''), 2500);
  };

  const handleStartTunnel = async () => {
    setToggling(true);
    setErr('');
    try {
      const data = await apiStartRemoteTunnel();
      setStatus(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Błąd uruchamiania tunelu Cloudflare.');
    } finally {
      setToggling(false);
    }
  };

  const handleStopTunnel = async () => {
    setToggling(true);
    setErr('');
    try {
      const data = await apiStopRemoteTunnel();
      setStatus(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Błąd zatrzymywania tunelu.');
    } finally {
      setToggling(false);
    }
  };

  const activeMobileUrl = status?.tunnel_url || status?.primary_lan_url || '';

  return (
    <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#FFFFFF]">
            <Smartphone className="w-4 h-4 text-[#C8FF3A]" />
            <span>Zdalne Sterowanie z Telefonu (Mobile Pilot)</span>
          </div>
          <p className="text-[11px] text-[#A0A7B1] mt-1">
            Steruj aplikacją ze smartfona, gdy komputer działa: lokalnie po Wi-Fi (LAN) lub z dowolnego miejsca przez szyfrowany tunel HTTPS.
          </p>
        </div>
        <button
          type="button"
          onClick={loadRemote}
          disabled={loading || !tokenReady}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF] disabled:opacity-40"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Odśwież
        </button>
      </div>

      {err && (
        <div className="p-3 fk-cut-sm bg-[#FF5C5C]/10 border border-[#FF5C5C]/30 text-xs text-[#FF5C5C] flex items-start gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{err}</span>
        </div>
      )}

      {!tokenReady ? (
        <div className="p-3 bg-[#050505] border border-[#272A2F] text-xs text-[#A0A7B1]">
          Zaloguj się tokenem JWT powyżej, aby włączyć podgląd LAN i tunel HTTPS.
        </div>
      ) : status && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
          <div className="lg:col-span-2 space-y-3">
            {/* LAN / Wi-Fi Box */}
            <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-2">
              <div className="flex items-center gap-2 text-xs font-bold text-[#FFFFFF]">
                <Wifi className="w-3.5 h-3.5 text-[#55E88D]" />
                <span>Dostęp w domowym Wi-Fi (LAN)</span>
              </div>
              {status.lan_urls.length > 0 ? (
                <div className="space-y-1.5">
                  {status.lan_urls.map((u) => (
                    <div key={u} className="flex items-center justify-between gap-2 px-2.5 py-1.5 bg-[#0E0F11] border border-[#272A2F]">
                      <span className="text-xs font-mono text-[#C8FF3A] truncate">{u}</span>
                      <button
                        type="button"
                        onClick={() => handleCopy(u, u)}
                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold text-[#A0A7B1] hover:text-[#FFFFFF]"
                      >
                        <Copy className="w-3 h-3" /> {copiedKey === u ? 'Skopiowano' : 'Kopiuj'}
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs font-mono text-[#A0A7B1]">{status.primary_lan_url}</div>
              )}
            </div>

            {/* Cloudflare Quick Tunnel */}
            <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2 text-xs font-bold text-[#FFFFFF]">
                  <Globe className={`w-3.5 h-3.5 ${status.tunnel_active ? 'text-[#C8FF3A]' : 'text-[#686E78]'}`} />
                  <span>Tunel HTTPS poza domem (LTE / 5G · trycloudflare.com)</span>
                </div>
                {status.tunnel_active ? (
                  <button
                    type="button"
                    onClick={handleStopTunnel}
                    disabled={toggling}
                    className="px-3 py-1.5 bg-[#FF5C5C]/15 border border-[#FF5C5C]/40 text-[#FF5C5C] text-xs font-bold hover:bg-[#FF5C5C]/25 disabled:opacity-50"
                  >
                    {toggling ? 'Zatrzymywanie...' : 'Zatrzymaj Tunel'}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleStartTunnel}
                    disabled={toggling}
                    className="px-3 py-1.5 bg-[#C8FF3A] text-[#050505] text-xs font-extrabold hover:bg-[#d6ff66] disabled:opacity-50"
                  >
                    {toggling ? 'Uruchamiam tunel HTTPS...' : 'Uruchom Tunel HTTPS (LTE/5G)'}
                  </button>
                )}
              </div>

              {status.tunnel_active && status.tunnel_url ? (
                <div className="flex items-center justify-between gap-2 px-2.5 py-2 bg-[#0E0F11] border border-[#C8FF3A]/40">
                  <span className="text-xs font-mono text-[#C8FF3A] truncate">{status.tunnel_url}</span>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => handleCopy('tunnel', status.tunnel_url!)}
                      className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold text-[#A0A7B1] hover:text-[#FFFFFF]"
                    >
                      <Copy className="w-3 h-3" /> {copiedKey === 'tunnel' ? 'Skopiowano' : 'Kopiuj'}
                    </button>
                    <a
                      href={status.tunnel_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold text-[#C8FF3A] hover:underline"
                    >
                      <ExternalLink className="w-3 h-3" /> Otwórz
                    </a>
                  </div>
                </div>
              ) : (
                <div className="text-[11px] text-[#686E78]">
                  Kliknięcie pobierze lekki binarny klient `cloudflared` (jednorazowo, jeśli brak) i wystawi szyfrowany adres HTTPS na czas pracy komputera.
                </div>
              )}

              <div className="text-[11px] text-[#A0A7B1]">
                ℹ️ Przy pierwszym otwarciu na telefonie przejdź do <strong>Ustawienia → Autoryzacja API</strong> i zaloguj się hasłem API (`API_PASSWORD`), aby sesja na telefonie była autoryzowana tokenem JWT.
              </div>
            </div>
          </div>

          {/* QR Code */}
          <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] flex flex-col items-center justify-center text-center space-y-2.5">
            <span className="text-[11px] font-bold text-[#FFFFFF] uppercase tracking-wider">
              {status.tunnel_active ? 'QR · Tunel HTTPS (5G)' : 'QR · Domowe Wi-Fi'}
            </span>
            {activeMobileUrl ? (
              <img
                src={`https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(activeMobileUrl)}`}
                alt="QR code do otwarcia Flikcut na telefonie"
                className="w-36 h-36 bg-white p-1.5 rounded"
              />
            ) : null}
            <span className="text-[10px] text-[#686E78] font-mono break-all">{activeMobileUrl}</span>
          </div>
        </div>
      )}
    </div>
  );
}


