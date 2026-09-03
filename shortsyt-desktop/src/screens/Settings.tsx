import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  getServerUrl, setServerUrl, getJwtToken, clearJwtToken,
  apiLogin, apiHealthCheck, apiGetYtTokenStatus, apiGetYtAuthUrl,
  apiGetHardwareInfo, apiRunBenchmarkScan,
  DEFAULT_URL, YtTokenStatusResponse, HardwareProfile,
} from '../lib/api';
import {
  Settings as SettingsIcon, Save, KeyRound, Server, Check, AlertCircle,
  Trash2, Youtube, RefreshCw, ExternalLink, ShieldCheck, ShieldAlert, ShieldOff, Copy,
} from 'lucide-react';

export default function Settings() {
  const [url, setUrl] = useState<string>(DEFAULT_URL);
  const [password, setPassword] = useState<string>('');
  const [token, setToken] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [healthStatus, setHealthStatus] = useState<boolean | null>(null);

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
    try { const s = await apiGetYtTokenStatus(); setYtStatus(s); return s; }
    catch { setYtStatus(null); return null; }
    finally { setYtLoading(false); }
  }, [token]);

  useEffect(() => { fetchYtStatus(); }, [fetchYtStatus]);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  useEffect(() => () => stopPolling(), []);

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
      setYtMsg({ type: 'success', text: 'Link wygenerowany! Zaloguj sie na Dwannellenga w Opera GX / przegladarce.' });

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
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      {/* Header */}
      <div className="pb-4 border-b border-[#1E2438]">
        <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
          <SettingsIcon className="w-6 h-6 text-[#C89B3C]" /><span>Ustawienia Systemu</span>
        </h1>
        <p className="text-xs text-[#8B8FA8] mt-1 font-medium">Konfiguracja backendu, JWT i YouTube OAuth</p>
      </div>

      {/* Alert JWT */}
      {statusMsg && (
        <div className={`p-4 rounded-xl border text-xs flex items-center gap-2 ${statusMsg.type === 'success' ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]' : 'bg-[#E84040]/10 border-[#E84040]/30 text-[#FF6060]'}`}>
          {statusMsg.type === 'success' ? <Check className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          <span className="font-semibold">{statusMsg.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Server URL */}
        <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] space-y-4">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#E4D6B5]">
            <Server className="w-4 h-4 text-[#2A7FD4]" /><span>FastAPI Server URL</span>
          </div>
          <form onSubmit={handleSaveUrl} className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-[#8B8FA8] block mb-1.5">Adres API Backend</label>
              <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://localhost:8765"
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-mono text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]" />
              <span className="text-[11px] text-[#50546A] mt-1 block">Domyslny port: 8765</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${healthStatus === true ? 'bg-[#2ECC71]' : healthStatus === false ? 'bg-[#E84040]' : 'bg-[#8B8FA8]'}`} />
                <span className="text-xs text-[#8B8FA8]">{healthStatus === true ? 'Serwer dostepny' : healthStatus === false ? 'Brak odpowiedzi' : 'Sprawdzanie...'}</span>
              </div>
              <button type="submit" disabled={isSaving} className="px-4 py-2 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-bold flex items-center gap-1.5">
                <Save className="w-3.5 h-3.5" /><span>Zapisz URL</span>
              </button>
            </div>
          </form>
        </div>

        {/* JWT */}
        <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] space-y-4">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#E4D6B5]">
            <KeyRound className="w-4 h-4 text-[#C89B3C]" /><span>Autoryzacja (JWT)</span>
          </div>
          {token ? (
            <div className="space-y-4">
              <div className="p-3.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438]">
                <div className="text-xs text-[#8B8FA8] font-semibold">Stan:</div>
                <div className="text-xs font-bold text-[#55E88D] mt-0.5">ZALOGOWANO</div>
                <div className="text-[10px] font-mono text-[#50546A] truncate mt-1">{token}</div>
              </div>
              <button onClick={handleLogout} className="px-4 py-2 rounded-xl bg-[#E84040]/15 hover:bg-[#E84040]/25 border border-[#E84040]/30 text-[#FF6060] text-xs font-bold flex items-center gap-1.5">
                <Trash2 className="w-3.5 h-3.5" /><span>Wyloguj</span>
              </button>
            </div>
          ) : (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-[#8B8FA8] block mb-1.5">Haslo API</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="shortsyt2026"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-mono text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]" />
              </div>
              <button type="submit" disabled={isSaving || !password} className="w-full py-2.5 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-bold flex items-center justify-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5" /><span>Zaloguj i wygeneruj JWT</span>
              </button>
            </form>
          )}
        </div>
      </div>

      {/* ── YouTube OAuth ─────────────────────────────────────── */}
      <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#E4D6B5]">
            <Youtube className="w-4 h-4 text-[#FF0000]" />
            <span>YouTube OAuth — Token kanalu Dwannellenga</span>
          </div>
          <button onClick={() => fetchYtStatus()} disabled={ytLoading || ytAuthorizing}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#0A0E1A] border border-[#1E2438] text-xs text-[#8B8FA8] hover:text-[#E4D6B5] disabled:opacity-40">
            <RefreshCw className={`w-3 h-3 ${ytLoading ? 'animate-spin' : ''}`} /> Odswiez
          </button>
        </div>

        {/* Status badge */}
        <div className="p-3.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] flex items-center justify-between gap-3 flex-wrap">
          {ytLoading ? (
            <span className="text-xs text-[#8B8FA8] flex items-center gap-1"><RefreshCw className="w-3 h-3 animate-spin" /> Sprawdzam...</span>
          ) : !ytStatus || !ytStatus.has_token ? (
            <span className="flex items-center gap-1.5 text-xs font-bold text-[#FF6060]"><ShieldOff className="w-4 h-4" /> Brak tokenu — wymagana autoryzacja</span>
          ) : !ytStatus.is_valid ? (
            <span className="flex items-center gap-1.5 text-xs font-bold text-[#FFB347]"><ShieldAlert className="w-4 h-4" /> Token wygasl — odnow autoryzacje</span>
          ) : (
            <span className={`flex items-center gap-1.5 text-xs font-bold ${ytStatus.days_remaining !== null && ytStatus.days_remaining < 7 ? 'text-[#FFB347]' : 'text-[#55E88D]'}`}>
              <ShieldCheck className="w-4 h-4" /> Token aktywny
              {ytStatus.days_remaining !== null && <span>&nbsp;(wygasa za {ytStatus.days_remaining} dni)</span>}
              {ytStatus.can_refresh && <span className="text-[#8B8FA8] font-normal">&nbsp;&#8226; auto-refresh OK</span>}
            </span>
          )}
          {ytStatus?.expires_at && (
            <span className="text-[10px] font-mono text-[#50546A]">{new Date(ytStatus.expires_at).toLocaleString()}</span>
          )}
        </div>

        {/* Scopes */}
        <div className="text-[11px] text-[#50546A] bg-[#0A0E1A] rounded-lg px-3 py-2">
          <span className="font-semibold text-[#8B8FA8]">Scopes:</span>{' '}
          youtube.upload &#8226; youtube.readonly &#8226; <span className="text-[#C89B3C]">youtube.force-ssl</span> (pinned comments)
        </div>

        {/* YT message */}
        {ytMsg && (
          <div className={`p-3.5 rounded-xl border text-xs flex items-start gap-2 ${ytMsg.type === 'success' ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]' : 'bg-[#E84040]/10 border-[#E84040]/30 text-[#FF6060]'}`}>
            {ytMsg.type === 'success' ? <Check className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
            <span className="font-semibold">{ytMsg.text}</span>
          </div>
        )}

        {/* Auth flow UI */}
        {ytAuthorizing ? (
          /* Waiting for callback */
          <div className="p-5 rounded-xl bg-[#0A0E1A] border border-[#C89B3C]/40 space-y-4">
            <div className="flex items-center gap-3">
              <RefreshCw className="w-5 h-5 text-[#C89B3C] animate-spin flex-shrink-0" />
              <div>
                <p className="text-xs font-bold text-[#E4D6B5]">Czekam na autoryzacje w przegladarce (Opera GX)...</p>
                <p className="text-[11px] text-[#8B8FA8] mt-0.5">
                  Zaloguj sie na <strong>Dwannellenga</strong> i zaakceptuj uprawnienia. Po zalogowaniu token zapisze sie automatycznie.
                </p>
              </div>
            </div>

            {/* Direct copy section for Opera GX */}
            {currentAuthUrl && (
              <div className="p-3.5 rounded-xl bg-[#121624] border border-[#1E2438] space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-[#C89B3C]">
                    🔗 Jesli Opera GX nie otworzyla sie sama — skopiuj link ponizej:
                  </span>
                  <button onClick={handleCopyUrl}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-bold transition-all">
                    {copied ? <Check className="w-3.5 h-3.5 text-[#0A0E1A]" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copied ? 'Skopiowano!' : 'Kopiuj link do Opera GX'}</span>
                  </button>
                </div>
                <input type="text" readOnly value={currentAuthUrl} onClick={(e) => (e.target as HTMLInputElement).select()}
                  className="w-full px-3 py-2 rounded-lg bg-[#0A0E1A] border border-[#1E2438] text-[11px] font-mono text-[#8B8FA8] focus:outline-none focus:border-[#C89B3C] select-all" />
              </div>
            )}

            <div className="flex gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-[#1E2438] overflow-hidden">
                <div className="h-full bg-[#C89B3C] animate-pulse rounded-full" style={{ width: '70%' }} />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <button onClick={handleCancelAuth}
                className="text-xs text-[#8B8FA8] hover:text-[#FF6060] transition-colors">
                Anuluj autoryzacje
              </button>
              <span className="text-[11px] text-[#50546A]">Backend nasluchuje w tle</span>
            </div>
          </div>
        ) : (
          /* Start auth button */
          <div className="space-y-3">
            <p className="text-xs text-[#8B8FA8]">
              {ytStatus?.is_valid
                ? 'Token aktywny. Kliknij "Odnow" aby wymusic ponowna autoryzacje (force-ssl dla pinned comments).'
                : 'Kliknij ponizej — wygeneruje sie link autoryzacyjny. Mozesz go skopiowac i otworzyc w Opera GX.'}
            </p>
            <button onClick={handleYtStartAuth} disabled={ytLoading || !token}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#FF0000]/90 hover:bg-[#FF0000] disabled:opacity-50 text-white text-xs font-bold shadow-md shadow-[#FF0000]/20 transition-colors">
              <Youtube className="w-3.5 h-3.5" />
              {ytStatus?.is_valid ? 'Odnow token YouTube' : 'Autoryzuj kanal YouTube'}
              <ExternalLink className="w-3 h-3 ml-1 opacity-70" />
            </button>
            {!token && <p className="text-[11px] text-[#FFB347]">Musisz byc zalogowany (JWT) aby autoryzowac YouTube.</p>}
          </div>
        )}
      </div>

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
    <div className="p-6 rounded-2xl bg-[#0E1220] border border-[#1E2438] space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-[#1E2438]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#C89B3C]/10 border border-[#C89B3C]/30 flex items-center justify-center">
            <RefreshCw className="w-4 h-4 text-[#C89B3C]" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-[#E4D6B5] flex items-center gap-2">
              Skaner Systemu i Optymalizacja Sprzętowa
              {profile?.tier === 'high' && (
                <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-black">
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
            <p className="text-[11px] text-[#8B8FA8]">
              Automatyczne dopasowanie enkoderów FFmpeg, wątków i próbkowania OCR pod wydajność Twojego komputera
            </p>
          </div>
        </div>

        <button
          onClick={handleRunScan}
          disabled={scanning}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-[#C89B3C] to-[#E5C269] hover:from-[#B58B32] hover:to-[#D4B25B] text-[#0A0E1A] font-bold text-xs shadow-md shadow-[#C89B3C]/10 transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
          {scanning ? 'Skanowanie PC...' : '⚡ Skanuj System i Zoptymalizuj'}
        </button>
      </div>

      {msg && (
        <div className={`p-3.5 rounded-xl border text-xs flex items-center gap-2 ${
          msg.type === 'success' ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]' : 'bg-[#E84040]/10 border-[#E84040]/30 text-[#FF6060]'
        }`}>
          {msg.type === 'success' ? <Check className="w-4 h-4 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 flex-shrink-0" />}
          <span className="font-semibold">{msg.text}</span>
        </div>
      )}

      {profile && profile.hardware ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* CPU */}
            <div className="p-3.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] space-y-1">
              <span className="text-[10px] font-semibold text-[#8B8FA8] uppercase tracking-wider">Procesor (CPU)</span>
              <p className="text-xs font-bold text-[#E4D6B5] line-clamp-1">{profile.hardware.cpu_name}</p>
              <span className="text-[11px] text-cyan-400 font-medium">{profile.hardware.cpu_cores} wątków logicznych</span>
            </div>

            {/* GPU */}
            <div className="p-3.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] space-y-1">
              <span className="text-[10px] font-semibold text-[#8B8FA8] uppercase tracking-wider">Karta Graficzna (GPU)</span>
              <p className="text-xs font-bold text-[#E4D6B5] line-clamp-1">{profile.hardware.gpu_name}</p>
              <span className="text-[11px] text-amber-400 font-medium">VRAM: {profile.hardware.vram_gb} GB ({profile.hardware.detected_encoder})</span>
            </div>

            {/* RAM */}
            <div className="p-3.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] space-y-1">
              <span className="text-[10px] font-semibold text-[#8B8FA8] uppercase tracking-wider">Pamięć RAM</span>
              <p className="text-xs font-bold text-[#E4D6B5]">{profile.hardware.ram_total_gb} GB Total</p>
              <span className="text-[11px] text-emerald-400 font-medium">Dostępne: {profile.hardware.ram_available_gb} GB</span>
            </div>

            {/* Tuned Settings */}
            <div className="p-3.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] space-y-1">
              <span className="text-[10px] font-semibold text-[#8B8FA8] uppercase tracking-wider">Aktywny Enkoder</span>
              <p className="text-xs font-bold text-[#C89B3C]">{profile.tuned_settings.encoder.toUpperCase()}</p>
              <span className="text-[11px] text-slate-400 font-medium">{profile.tuned_settings.render_fps} FPS • max jakość</span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-[#121624] border border-[#1E2438] text-[11px] text-[#8B8FA8] flex items-center justify-between">
            <span>
              💡 <strong>Opis konfiguracji:</strong> {profile.tier_description}
            </span>
            <span className="text-[#50546A] hidden md:inline">
              Ostatni skan: {new Date(profile.scanned_at).toLocaleString('pl-PL')}
            </span>
          </div>
        </div>
      ) : (
        <div className="text-center py-6 text-xs text-[#8B8FA8]">
          Kliknij "Skanuj System", aby automatycznie przeanalizować podzespoły i dobrać optymalne parametry.
        </div>
      )}
    </div>
  );
}

