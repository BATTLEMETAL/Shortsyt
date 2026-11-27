import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  getServerUrl, setServerUrl, getJwtToken, clearJwtToken,
  apiLogin, apiHealthCheck, apiGetYtTokenStatus, apiGetYtAuthUrl,
  DEFAULT_URL, YtTokenStatusResponse, apiListAccounts,
} from '../lib/api';
import {
  Settings as SettingsIcon, Save, KeyRound, Server, Check, AlertCircle,
  Trash2, Youtube, RefreshCw, ExternalLink, ShieldCheck, ShieldAlert, ShieldOff, Copy,
} from 'lucide-react';
import HardwareScannerCard from '../components/settings/HardwareScannerCard';
import AccountsManagerCard from '../components/settings/AccountsManagerCard';
import RemoteAccessCard from '../components/settings/RemoteAccessCard';
import SocialConnectionsSection from '../components/settings/SocialConnectionsSection';

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
    try {
      const s = await apiGetYtTokenStatus();
      setYtStatus(s);
      return s;
    } catch (err) {
      console.warn('[Settings] fetchYtStatus error:', err);
      setYtStatus(null);
      return null;
    } finally {
      setYtLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchYtStatus(); }, [fetchYtStatus]);

  useEffect(() => {
    if (!token) return;
    apiListAccounts()
      .then((res) => {
        const active = res.accounts.find((a) => a.account_id === res.active_account_id) || res.accounts[0];
        if (active) setActiveAccountLabel(active.display_name);
      })
      .catch((err) => {
        console.warn('[Settings] apiListAccounts error:', err);
      });
  }, [token]);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  useEffect(() => () => { stopPolling(); }, []);

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

      if (window.electronApp?.openExternal) {
        window.electronApp.openExternal(authUrl).catch((err) => {
          console.warn('[Settings] YouTube openExternal error:', err);
        });
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
        } catch (err) {
          console.warn('[Settings] YouTube OAuth poll error:', err);
        }
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

      {/* ── Multi-Platform Social Accounts (TikTok, Instagram, Facebook) ── */}
      <SocialConnectionsSection tokenReady={!!token} />

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
