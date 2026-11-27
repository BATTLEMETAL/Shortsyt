import React, { useCallback, useEffect, useState } from 'react';
import {
  Smartphone, RefreshCw, AlertCircle, Wifi, Copy, Globe, ExternalLink,
} from 'lucide-react';
import {
  apiGetRemoteAccess, apiStartRemoteTunnel, apiStopRemoteTunnel, RemoteAccessStatus,
} from '../../lib/api';

export default function RemoteAccessCard({ tokenReady }: { tokenReady: boolean }) {
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
