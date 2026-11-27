import React, { useEffect, useState } from 'react';
import { RefreshCw, Check, AlertCircle } from 'lucide-react';
import { apiGetHardwareInfo, apiRunBenchmarkScan, HardwareProfile } from '../../lib/api';

export default function HardwareScannerCard() {
  const [profile, setProfile] = useState<HardwareProfile | any>(null);
  const [, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadInfo = async () => {
    try {
      setLoading(true);
      const data = await apiGetHardwareInfo();
      setProfile(data);
    } catch (e: any) {
      console.warn('[Settings] HardwareScanner loadInfo error:', e);
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
