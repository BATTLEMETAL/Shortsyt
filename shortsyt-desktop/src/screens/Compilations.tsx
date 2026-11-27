import React, { useEffect, useState } from 'react';
import {
  Clapperboard,
  Database,
  ExternalLink,
  Film,
  Image as ImageIcon,
  Play,
  RefreshCw,
  Send,
  Sparkles,
  Upload,
} from 'lucide-react';
import {
  apiBootstrapVault,
  apiCompilationMediaUrl,
  apiGetCompilationStatus,
  apiGetCompilationsVault,
  apiListCompilations,
  apiPublishCompilation,
  apiStartCompilationRender,
  apiSyncVault,
  CompilationRecord,
  CompilationsVaultResponse,
} from '../lib/api';

export default function Compilations() {
  const [vaultData, setVaultData] = useState<CompilationsVaultResponse | null>(null);
  const [compilations, setCompilations] = useState<CompilationRecord[]>([]);
  const [selected, setSelected] = useState<CompilationRecord | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);

  const [mode, setMode] = useState<'weekly' | 'monthly'>('weekly');
  const [champion, setChampion] = useState('Katarina');
  const [maxClips, setMaxClips] = useState(8);
  const [renderStatus, setRenderStatus] = useState<{ status: string; progress: number; step: string; error?: string | null }>({
    status: 'idle',
    progress: 0,
    step: '',
  });

  const [editTitle, setEditTitle] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [privacy, setPrivacy] = useState<'private' | 'unlisted' | 'public'>('private');
  const [publishAt, setPublishAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const loadAll = async () => {
    try {
      const [v, listRes] = await Promise.all([apiGetCompilationsVault(), apiListCompilations()]);
      setVaultData(v);
      setCompilations(listRes.items || []);
      if (!selected && listRes.items?.length) {
        selectComp(listRes.items[0]);
      }
    } catch (e: any) {
      setMsg(e?.message || 'Błąd ładowania kompilacji');
    }
  };

  const selectComp = async (rec: CompilationRecord) => {
    setSelected(rec);
    setEditTitle(rec.title || '');
    setEditDesc(rec.description || '');
    setVideoUrl(rec.video_exists ? await apiCompilationMediaUrl(rec.output_filename) : null);
    setThumbUrl(rec.thumbnail_exists && rec.thumbnail_filename ? await apiCompilationMediaUrl(rec.thumbnail_filename) : null);
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (renderStatus.status !== 'running') return;
    const t = setInterval(async () => {
      try {
        const st = await apiGetCompilationStatus();
        setRenderStatus(st);
        if (st.status === 'done' && st.latest) {
          await loadAll();
          await selectComp(st.latest);
        }
      } catch (err) {
        console.warn('[Compilations] Błąd pollingu kompilacji:', err);
      }
    }, 2500);
    return () => clearInterval(t);
  }, [renderStatus.status]);

  const handleBootstrap = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await apiBootstrapVault(champion, 12);
      setMsg(`Dodano ${r.bootstrap?.added ?? 0} klipów do approved/`);
      await loadAll();
    } catch (e: any) {
      setMsg(e?.message || 'Błąd zasilania skarbca');
    } finally {
      setBusy(false);
    }
  };

  const handleSyncVault = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await apiSyncVault();
      setMsg(`Promocja Vault: +${r.promotion?.promoted ?? 0} approved, -${r.promotion?.expired ?? 0} wygasłych`);
      await loadAll();
    } catch (e: any) {
      setMsg(e?.message || 'Błąd synchronizacji Vault');
    } finally {
      setBusy(false);
    }
  };

  const handleRender = async () => {
    setMsg(null);
    try {
      await apiStartCompilationRender({ mode, champion, max_clips: maxClips });
      setRenderStatus({ status: 'running', progress: 5, step: 'Uruchamianie...' });
    } catch (e: any) {
      setMsg(e?.message || 'Błąd startu kompilacji');
    }
  };

  const handlePublish = async () => {
    if (!selected) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await apiPublishCompilation({
        comp_id: selected.comp_id,
        output_filename: selected.output_filename,
        title: editTitle,
        description: editDesc,
        tags: selected.tags || [],
        thumbnail_filename: selected.thumbnail_filename,
        privacy,
        publish_at: publishAt.trim() || undefined,
      });
      setMsg(`Opublikowano film 16:9: ${res.url || res.video_id}`);
      await loadAll();
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || e?.message || 'Błąd publikacji filmu 16:9');
    } finally {
      setBusy(false);
    }
  };

  const counts = vaultData?.vault?.counts || { staging: 0, approved: 0, expired: 0, rendered: 0 };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#272A2F] pb-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight flex items-center gap-2.5">
            <Clapperboard className="w-6 h-6 text-[#C8FF3A]" />
            <span>Kompilacje Poziome 16:9</span>
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/30">
              LONG-FORM
            </span>
          </h1>
          <p className="text-sm text-[#8E94A0] mt-1">
            Skarbiec Viral Vault (hardlinki NTFS poza OneDrive), montaż tygodniowy 3–5 min / miesięczny 8–10 min i lejek Shorts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSyncVault}
            disabled={busy}
            className="px-3 py-2 rounded-lg bg-[#16181D] hover:bg-[#1E2128] border border-[#272A2F] text-xs font-bold flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5 text-[#C8FF3A]" />
            Sync Analityki
          </button>
          <button
            onClick={handleBootstrap}
            disabled={busy}
            className="px-3 py-2 rounded-lg bg-[#C8FF3A] hover:bg-[#b5eb2a] text-[#050505] text-xs font-extrabold flex items-center gap-1.5"
          >
            <Database className="w-3.5 h-3.5" />
            Zasil z Outplayed
          </button>
        </div>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-[#16181D] border border-[#C8FF3A]/40 text-xs text-[#E2E8F0]">
          {msg}
        </div>
      )}

      {/* Statystyki skarbca + generator */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-[#0E0F11] border border-[#272A2F] rounded-xl p-4 space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-[#8E94A0]">Viral Vault (NTFS Hardlink 0 B)</div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="bg-[#16181D] rounded-lg p-2.5 border border-[#272A2F]">
              <div className="text-xl font-extrabold text-[#C8FF3A]">{counts.approved}</div>
              <div className="text-[11px] text-[#8E94A0]">Approved</div>
            </div>
            <div className="bg-[#16181D] rounded-lg p-2.5 border border-[#272A2F]">
              <div className="text-xl font-extrabold text-amber-400">{counts.staging}</div>
              <div className="text-[11px] text-[#8E94A0]">Staging (&lt;24h)</div>
            </div>
            <div className="bg-[#16181D] rounded-lg p-2.5 border border-[#272A2F]">
              <div className="text-xl font-extrabold text-sky-400">{counts.rendered}</div>
              <div className="text-[11px] text-[#8E94A0]">Filmy 16:9</div>
            </div>
          </div>
          <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
            {(vaultData?.vault?.items || []).slice(0, 12).map((it) => (
              <div key={it.clip_id} className="text-xs bg-[#16181D] px-2.5 py-1.5 rounded border border-[#272A2F]/60 flex justify-between items-center">
                <span className="truncate max-w-[65%]">
                  <span className={it.state === 'approved' ? 'text-[#C8FF3A] font-bold' : 'text-amber-400 font-bold'}>
                    [{it.state}]
                  </span>{' '}
                  {it.champion} {it.action_type}
                </span>
                <span className="text-[11px] text-[#8E94A0] tabular-nums">{it.views || 0} wyśw.</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-[#0E0F11] border border-[#272A2F] rounded-xl p-4 space-y-3 lg:col-span-2">
          <div className="text-xs font-bold uppercase tracking-wider text-[#8E94A0] flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-[#C8FF3A]" />
            Generator Kompilacji 16:9 (1920x1080@60 + Cold Open + Ducking NCS)
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] text-[#8E94A0] mb-1">Tryb Długości</label>
              <select
                value={mode}
                onChange={(e) => {
                  const m = e.target.value as 'weekly' | 'monthly';
                  setMode(m);
                  setMaxClips(m === 'monthly' ? 24 : 8);
                }}
                className="w-full bg-[#16181D] border border-[#272A2F] rounded-lg px-3 py-2 text-xs"
              >
                <option value="weekly">Tygodniowy Sprint (3–5 min, bez rozdziałów)</option>
                <option value="monthly">Miesięczny Specjal (8–10 min, z rozdziałami)</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] text-[#8E94A0] mb-1">Bohater</label>
              <input
                value={champion}
                onChange={(e) => setChampion(e.target.value)}
                className="w-full bg-[#16181D] border border-[#272A2F] rounded-lg px-3 py-2 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] text-[#8E94A0] mb-1">Maks. klipów</label>
              <input
                type="number"
                min={2}
                max={36}
                value={maxClips}
                onChange={(e) => setMaxClips(Number(e.target.value || 8))}
                className="w-full bg-[#16181D] border border-[#272A2F] rounded-lg px-3 py-2 text-xs"
              />
            </div>
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={handleRender}
              disabled={renderStatus.status === 'running'}
              className="px-4 py-2.5 rounded-lg bg-[#C8FF3A] hover:bg-[#b5eb2a] disabled:opacity-50 text-[#050505] text-xs font-extrabold flex items-center gap-2"
            >
              <Play className="w-4 h-4" />
              {renderStatus.status === 'running' ? `Renderowanie ${renderStatus.progress}%...` : 'Wyrenderuj Kompilację 16:9 (ZERO Auto-Upload)'}
            </button>
            {renderStatus.step && (
              <span className="text-xs text-[#8E94A0] truncate">{renderStatus.step}</span>
            )}
          </div>
          {renderStatus.error && (
            <div className="text-xs text-red-400">Błąd renderu: {renderStatus.error}</div>
          )}
        </div>
      </div>

      {/* Podgląd wyrenderowanej kompilacji + miniatura 1280x720 + publikacja */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-[#0E0F11] border border-[#272A2F] rounded-xl p-4 space-y-2">
          <div className="text-xs font-bold uppercase tracking-wider text-[#8E94A0]">Wyrenderowane Filmy</div>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {compilations.map((c) => (
              <button
                key={c.comp_id}
                onClick={() => selectComp(c)}
                className={`w-full text-left p-2.5 rounded-lg border text-xs transition ${
                  selected?.comp_id === c.comp_id
                    ? 'bg-[#C8FF3A]/10 border-[#C8FF3A]/60'
                    : 'bg-[#16181D] border-[#272A2F] hover:border-[#3E434C]'
                }`}
              >
                <div className="font-bold truncate">{c.title || c.output_filename}</div>
                <div className="text-[11px] text-[#8E94A0] flex justify-between mt-1">
                  <span>{c.mode} • {c.clips_count} akcji • {Math.round(c.duration_s)}s</span>
                  <span className="uppercase">{c.status}</span>
                </div>
              </button>
            ))}
            {compilations.length === 0 && (
              <div className="text-xs text-[#8E94A0] py-4">Brak jeszcze kompilacji. Kliknij „Wyrenderuj Kompilację 16:9”.</div>
            )}
          </div>
        </div>

        <div className="bg-[#0E0F11] border border-[#272A2F] rounded-xl p-4 space-y-4 lg:col-span-2">
          {selected ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <div className="text-[11px] text-[#8E94A0] mb-1 flex items-center gap-1">
                    <Film className="w-3.5 h-3.5 text-[#C8FF3A]" /> Podgląd Wideo 16:9
                  </div>
                  {videoUrl ? (
                    <video src={videoUrl} controls className="w-full rounded-lg border border-[#272A2F] aspect-video bg-black" />
                  ) : (
                    <div className="aspect-video bg-[#16181D] rounded-lg flex items-center justify-center text-xs text-[#8E94A0]">Brak pliku MP4</div>
                  )}
                </div>
                <div>
                  <div className="text-[11px] text-[#8E94A0] mb-1 flex items-center gap-1">
                    <ImageIcon className="w-3.5 h-3.5 text-[#C8FF3A]" /> Miniatura 1280x720
                  </div>
                  {thumbUrl ? (
                    <img src={thumbUrl} alt="Miniatura 16:9" className="w-full rounded-lg border border-[#272A2F] aspect-video object-cover" />
                  ) : (
                    <div className="aspect-video bg-[#16181D] rounded-lg flex items-center justify-center text-xs text-[#8E94A0]">Brak miniatury</div>
                  )}
                </div>
              </div>

              <div className="space-y-2.5">
                <input
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  placeholder="Tytuł YouTube Long-Form (bez #shorts)"
                  className="w-full bg-[#16181D] border border-[#272A2F] rounded-lg px-3 py-2 text-xs font-semibold"
                />
                <textarea
                  rows={4}
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="w-full bg-[#16181D] border border-[#272A2F] rounded-lg px-3 py-2 text-xs"
                />
                <div className="flex flex-wrap items-center gap-3">
                  <select
                    value={privacy}
                    onChange={(e) => setPrivacy(e.target.value as any)}
                    className="bg-[#16181D] border border-[#272A2F] rounded-lg px-3 py-2 text-xs"
                  >
                    <option value="private">Private / Harmonogram</option>
                    <option value="unlisted">Niepubliczny (Test)</option>
                    <option value="public">Publiczny teraz</option>
                  </select>
                  <input
                    value={publishAt}
                    onChange={(e) => setPublishAt(e.target.value)}
                    placeholder="publishAt UTC np. 2026-11-28T18:00:00Z"
                    className="flex-1 min-w-[210px] bg-[#16181D] border border-[#272A2F] rounded-lg px-3 py-2 text-xs"
                  />
                  <button
                    onClick={handlePublish}
                    disabled={busy || !selected.video_exists}
                    className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-[#050505] text-xs font-extrabold flex items-center gap-1.5"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    Wyślij Film 16:9
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="text-xs text-[#8E94A0] py-12 text-center">Wybierz wyrenderowaną kompilację z listy po lewej.</div>
          )}
        </div>
      </div>

      {/* Lejek Shorts -> Related Video YT Studio */}
      <div className="bg-[#0E0F11] border border-[#272A2F] rounded-xl p-4 space-y-2.5">
        <div className="text-xs font-bold uppercase tracking-wider text-[#8E94A0] flex items-center gap-2">
          <Send className="w-3.5 h-3.5 text-[#C8FF3A]" />
          Lejek Shorts -&gt; Film 16:9 (YT Studio Related Video Links)
        </div>
        <p className="text-xs text-[#8E94A0]">{vaultData?.related_links?.api_limitation_note}</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {(vaultData?.related_links?.shorts || []).slice(0, 6).map((sh) => (
            <div key={sh.video_id} className="bg-[#16181D] border border-[#272A2F] rounded-lg px-3 py-2 flex items-center justify-between text-xs">
              <span className="truncate max-w-[70%]">{sh.title || sh.video_id}</span>
              <a
                href={sh.studio_edit_url}
                target="_blank"
                rel="noreferrer"
                className="text-[#C8FF3A] hover:underline flex items-center gap-1 font-bold shrink-0"
              >
                YT Studio <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
