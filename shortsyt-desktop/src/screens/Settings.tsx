import React, { useEffect, useState } from 'react';
import {
  getServerUrl,
  setServerUrl,
  getJwtToken,
  setJwtToken,
  clearJwtToken,
  apiLogin,
  apiHealthCheck,
  DEFAULT_URL,
} from '../lib/api';
import { Settings as SettingsIcon, Save, KeyRound, Server, Check, AlertCircle, Trash2 } from 'lucide-react';

export default function Settings() {
  const [url, setUrl] = useState<string>(DEFAULT_URL);
  const [password, setPassword] = useState<string>('');
  const [token, setToken] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [healthStatus, setHealthStatus] = useState<boolean | null>(null);

  useEffect(() => {
    async function load() {
      const u = await getServerUrl();
      setUrl(u);
      const t = await getJwtToken();
      setToken(t);
      const h = await apiHealthCheck(u);
      setHealthStatus(h.ok);
    }
    load();
  }, []);

  const handleSaveUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setStatusMsg(null);
    try {
      await setServerUrl(url);
      const h = await apiHealthCheck(url);
      setHealthStatus(h.ok);
      setStatusMsg({
        type: h.ok ? 'success' : 'error',
        text: h.ok ? 'URL serwera zapisany i pomyślnie połączony!' : 'URL zapisany, ale serwer nie odpowiada.',
      });
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Błąd zapisu URL' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) return;
    setIsSaving(true);
    setStatusMsg(null);
    try {
      const newToken = await apiLogin(password);
      setToken(newToken);
      setPassword('');
      setStatusMsg({ type: 'success', text: 'Zalogowano pomyślnie! Nowy token JWT zapisany.' });
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.response?.data?.detail || 'Błąd logowania (nieprawidłowe hasło)' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleLogout = async () => {
    await clearJwtToken();
    setToken(null);
    setStatusMsg({ type: 'success', text: 'Wylogowano. Token usunięty z magazynu.' });
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      {/* Header */}
      <div className="pb-4 border-b border-[#1E2438]">
        <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
          <SettingsIcon className="w-6 h-6 text-[#C89B3C]" />
          <span>Ustawienia Systemu</span>
        </h1>
        <p className="text-xs text-[#8B8FA8] mt-1 font-medium">
          Konfiguracja połączenia z backendem FastAPI oraz uwierzytelnianie
        </p>
      </div>

      {/* Message alert */}
      {statusMsg && (
        <div
          className={`p-4 rounded-xl border text-xs flex items-center gap-2 ${
            statusMsg.type === 'success'
              ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]'
              : 'bg-[#E84040]/10 border-[#E84040]/30 text-[#FF6060]'
          }`}
        >
          {statusMsg.type === 'success' ? <Check className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          <span className="font-semibold">{statusMsg.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* URL Configuration */}
        <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-lg space-y-4">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#E4D6B5]">
            <Server className="w-4 h-4 text-[#2A7FD4]" />
            <span>FastAPI Server URL</span>
          </div>

          <form onSubmit={handleSaveUrl} className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-[#8B8FA8] block mb-1.5">
                Adres API Backend
              </label>
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="http://localhost:8765"
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-mono text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"
              />
              <span className="text-[11px] text-[#50546A] mt-1 block">
                Domyślny port: 8765. Wpisz pełny URL wraz z protokołem (http://).
              </span>
            </div>

            <div className="flex items-center justify-between pt-2">
              <div className="flex items-center gap-2">
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    healthStatus === true
                      ? 'bg-[#2ECC71]'
                      : healthStatus === false
                      ? 'bg-[#E84040]'
                      : 'bg-[#8B8FA8]'
                  }`}
                />
                <span className="text-xs font-medium text-[#8B8FA8]">
                  {healthStatus === true
                    ? 'Serwer dostępny'
                    : healthStatus === false
                    ? 'Brak odpowiedzi'
                    : 'Sprawdzanie...'}
                </span>
              </div>

              <button
                type="submit"
                disabled={isSaving}
                className="px-4 py-2 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-bold transition-colors flex items-center gap-1.5 shadow-md shadow-[#C89B3C]/10"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Zapisz URL</span>
              </button>
            </div>
          </form>
        </div>

        {/* Auth / JWT Configuration */}
        <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-lg space-y-4">
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#E4D6B5]">
            <KeyRound className="w-4 h-4 text-[#C89B3C]" />
            <span>Autoryzacja (JWT Token)</span>
          </div>

          {token ? (
            <div className="space-y-4">
              <div className="p-3.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438]">
                <div className="text-xs text-[#8B8FA8] font-semibold">Aktualny stan:</div>
                <div className="text-xs font-bold text-[#55E88D] mt-0.5">ZALOGOWANO (Token aktywny w store)</div>
                <div className="text-[10px] font-mono text-[#50546A] truncate mt-1">{token}</div>
              </div>

              <button
                type="button"
                onClick={handleLogout}
                className="px-4 py-2 rounded-xl bg-[#E84040]/15 hover:bg-[#E84040]/25 border border-[#E84040]/30 text-[#FF6060] text-xs font-bold transition-colors flex items-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Wyloguj i usuń token</span>
              </button>
            </div>
          ) : (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-[#8B8FA8] block mb-1.5">
                  Hasło API (API_PASSWORD z .env)
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="np. shortsyt2026"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs font-mono text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C]"
                />
              </div>

              <button
                type="submit"
                disabled={isSaving || !password}
                className="w-full py-2.5 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-bold transition-colors flex items-center justify-center gap-1.5 shadow-md shadow-[#C89B3C]/10"
              >
                <KeyRound className="w-3.5 h-3.5" />
                <span>Zaloguj i wygeneruj JWT</span>
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
