import React, { useEffect, useState } from 'react';
import {
  Compass,
  Play,
  ShieldCheck,
  Sparkles,
  RefreshCw,
  Video,
  ExternalLink,
  Camera,
  Scissors,
  Clock,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import {
  apiGetNicheResearch,
  apiListNicheResearches,
  apiRenderPitchMockup,
  apiResearchMediaUrl,
  apiRunNicheResearch,
  NicheResearchBlueprint,
  NicheResearchListItem,
  NicheResearchRequest,
} from '../lib/api';

export default function NicheResearch() {
  const [nicheQuery, setNicheQuery] = useState('budka z kebabem');
  const [nichePreset, setNichePreset] = useState<NicheResearchRequest['niche_preset']>('FOOD_GASTRO');
  const [businessName, setBusinessName] = useState('Kebab u Mistrza');
  const [city, setCity] = useState('Świdnica');
  const [offer, setOffer] = useState('Świeże mięso z rożna, domowy sos czosnkowy i chrupiąca pita');
  const [cta, setCta] = useState('Wpadnij dziś po swój zestaw');
  const [referenceUrl, setReferenceUrl] = useState('');
  const [useSynapsa, setUseSynapsa] = useState(true);

  const [runningResearch, setRunningResearch] = useState(false);
  const [renderingMockup, setRenderingMockup] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [history, setHistory] = useState<NicheResearchListItem[]>([]);
  const [blueprint, setBlueprint] = useState<NicheResearchBlueprint | null>(null);
  const [previewVideoUrl, setPreviewVideoUrl] = useState<string | null>(null);
  const [pitchHtmlUrl, setPitchHtmlUrl] = useState<string | null>(null);

  const refreshMediaUrls = async (bp: NicheResearchBlueprint | null) => {
    if (!bp) {
      setPreviewVideoUrl(null);
      setPitchHtmlUrl(null);
      return;
    }
    if (bp.preview_video_filename) {
      const url = await apiResearchMediaUrl(bp.preview_video_filename);
      setPreviewVideoUrl(`${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`);
    } else {
      setPreviewVideoUrl(null);
    }
    if (bp.pitch_html_filename) {
      const hUrl = await apiResearchMediaUrl(bp.pitch_html_filename);
      setPitchHtmlUrl(hUrl);
    } else {
      setPitchHtmlUrl(null);
    }
  };

  const loadHistory = async (autoOpenFirst: boolean = false) => {
    try {
      const res = await apiListNicheResearches();
      setHistory(res.items || []);
      if (autoOpenFirst && res.items?.length && !blueprint) {
        const detail = await apiGetNicheResearch(res.items[0].slug);
        setBlueprint(detail.blueprint);
        await refreshMediaUrls(detail.blueprint);
      }
    } catch (err) {
      console.warn('[NicheResearch] Błąd ładowania historii researchu:', err);
    }
  };

  useEffect(() => {
    loadHistory(true);
  }, []);

  const handleRunResearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setErrorMsg(null);
    setRunningResearch(true);
    try {
      const res = await apiRunNicheResearch({
        niche_query: nicheQuery.trim(),
        business_name: businessName.trim(),
        city: city.trim(),
        offer: offer.trim(),
        cta: cta.trim(),
        niche_preset: nichePreset,
        reference_url: referenceUrl.trim() || undefined,
        analyze_video_count: 1,
        use_synapsa: useSynapsa,
      });
      setBlueprint(res.blueprint);
      await refreshMediaUrls(res.blueprint);
      await loadHistory(false);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Błąd researchu niszy');
    } finally {
      setRunningResearch(false);
    }
  };

  const handleRenderPreview = async () => {
    if (!blueprint?.slug) return;
    setErrorMsg(null);
    setRenderingMockup(true);
    try {
      const res = await apiRenderPitchMockup(blueprint.slug);
      const updated: NicheResearchBlueprint = {
        ...blueprint,
        preview_video_filename: res.preview_video_filename,
        pitch_html_filename: res.pitch_html_filename || blueprint.pitch_html_filename,
      };
      setBlueprint(updated);
      await refreshMediaUrls(updated);
      await loadHistory(false);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Błąd renderowania podglądu 9:16');
    } finally {
      setRenderingMockup(false);
    }
  };

  const handleSelectHistory = async (slug: string) => {
    setErrorMsg(null);
    try {
      const detail = await apiGetNicheResearch(slug);
      setBlueprint(detail.blueprint);
      setNicheQuery(detail.blueprint.niche_query);
      setBusinessName(detail.blueprint.client_profile.business_name);
      setCity(detail.blueprint.client_profile.city);
      setOffer(detail.blueprint.client_profile.offer);
      setCta(detail.blueprint.client_profile.cta);
      await refreshMediaUrls(detail.blueprint);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'Nie udało się załadować zapisanego researchu');
    }
  };

  const yt = blueprint?.comparison?.youtube_pattern;
  const cl = blueprint?.comparison?.client_original_plan;
  const origScore = blueprint?.originality_report?.originality_score_pct ?? 100;

  return (
    <div className="space-y-6 text-[#FFFFFF]">
      {/* Nagłówek */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-[#272A2F] pb-5">
        <div>
          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.16em] text-[#C8FF3A]">
            <Compass className="w-4 h-4" />
            DFY Service Studio · Własny RTX 3060 + Synapsa
          </div>
          <h1 className="text-2xl md:text-3xl font-black tracking-tight mt-1">
            Research Niszy YT &amp; Podgląd Pitch 9:16 dla Klienta
          </h1>
          <p className="text-sm text-[#A0A7B1] mt-1">
            Dekonstrukcja prawdziwego montażu z YouTube + oryginalna adaptacja Synapsy (blokada plagiatu) + gotowy podgląd wideo 9:16 przed pozyskaniem nagrań klienta.
          </p>
        </div>
        {blueprint && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#17191C] border border-[#C8FF3A]/50 text-[#C8FF3A] text-xs font-extrabold fk-cut-sm">
              <ShieldCheck className="w-4 h-4" />
              ANTY-PLAGIAT: {origScore.toFixed(1)}% ORYGINALNOŚCI
            </span>
            {pitchHtmlUrl && (
              <a
                href={pitchHtmlUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#272A2F] hover:bg-[#32363D] text-xs font-bold fk-cut-sm"
              >
                <ExternalLink className="w-3.5 h-3.5 text-[#C8FF3A]" />
                Otwórz Kartę Pitch HTML
              </a>
            )}
          </div>
        )}
      </div>

      {/* Formularz + Historia */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <form onSubmit={handleRunResearch} className="xl:col-span-2 bg-[#0E0F11] border border-[#272A2F] p-5 fk-cut space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-[#A0A7B1] mb-1">
                Nisza / Fraza YouTube Shorts
              </label>
              <input
                value={nicheQuery}
                onChange={(e) => setNicheQuery(e.target.value)}
                placeholder="np. budka z kebabem / manicure hybrydowy"
                className="w-full bg-[#17191C] border border-[#272A2F] px-3 py-2 text-sm focus:border-[#C8FF3A] outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-[#A0A7B1] mb-1">
                Preset Branżowy
              </label>
              <select
                value={nichePreset}
                onChange={(e) => setNichePreset(e.target.value as any)}
                className="w-full bg-[#17191C] border border-[#272A2F] px-3 py-2 text-sm focus:border-[#C8FF3A] outline-none"
              >
                <option value="FOOD_GASTRO">FOOD_GASTRO (Kebab / Gastro / Street Food)</option>
                <option value="NAILS_BEAUTY">NAILS_BEAUTY (Paznokcie / Kosmetyka)</option>
                <option value="PRODUCT_ECOMMERCE_AD">PRODUCT_ECOMMERCE_AD (Produkt / Sklep)</option>
                <option value="EXPERT_BRAND_SHORT">EXPERT_BRAND_SHORT (Ekspert / B2B)</option>
                <option value="AUTO">AUTO (Wykryj z frazy)</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-[#A0A7B1] mb-1">
                Nazwa Biznesu Klienta
              </label>
              <input
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                placeholder="np. Kebab u Mistrza"
                className="w-full bg-[#17191C] border border-[#272A2F] px-3 py-2 text-sm focus:border-[#C8FF3A] outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-[#A0A7B1] mb-1">
                Miasto / Lokalizacja
              </label>
              <input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="np. Świdnica"
                className="w-full bg-[#17191C] border border-[#272A2F] px-3 py-2 text-sm focus:border-[#C8FF3A] outline-none"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-[11px] font-bold uppercase tracking-wider text-[#A0A7B1] mb-1">
                Wyróżnik / Oferta Klienta
              </label>
              <input
                value={offer}
                onChange={(e) => setOffer(e.target.value)}
                className="w-full bg-[#17191C] border border-[#272A2F] px-3 py-2 text-sm focus:border-[#C8FF3A] outline-none"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-[#A0A7B1] mb-1">
                CTA końcowe (Wezwanie do działania)
              </label>
              <input
                value={cta}
                onChange={(e) => setCta(e.target.value)}
                className="w-full bg-[#17191C] border border-[#272A2F] px-3 py-2 text-sm focus:border-[#C8FF3A] outline-none"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-[#A0A7B1] mb-1">
                Opcjonalny link do konkretnego filmu YT jako wzorzec
              </label>
              <input
                value={referenceUrl}
                onChange={(e) => setReferenceUrl(e.target.value)}
                placeholder="https://youtube.com/shorts/..."
                className="w-full bg-[#17191C] border border-[#272A2F] px-3 py-2 text-sm focus:border-[#C8FF3A] outline-none"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-[#272A2F]">
            <label className="inline-flex items-center gap-2 text-xs text-[#A0A7B1] cursor-pointer">
              <input
                type="checkbox"
                checked={useSynapsa}
                onChange={(e) => setUseSynapsa(e.target.checked)}
                className="accent-[#C8FF3A]"
              />
              Użyj lokalnej Synapsy (Qwen2.5-7B na RTX 3060) + twardy filtr PL / Anty-Plagiat
            </label>

            <div className="flex flex-wrap gap-2.5">
              <button
                type="submit"
                disabled={runningResearch}
                className="fk-btn bg-[#C8FF3A] text-[#050505] font-black text-xs px-4 py-2.5 inline-flex items-center gap-2 disabled:opacity-50"
              >
                {runningResearch ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                {runningResearch ? 'Analizuję YT + Synapsę...' : 'Zbadaj niszę YT + Dopasuj Synapsę'}
              </button>
              <button
                type="button"
                onClick={handleRenderPreview}
                disabled={!blueprint || renderingMockup}
                className="fk-btn bg-[#272A2F] hover:bg-[#34383F] text-[#FFFFFF] font-extrabold text-xs px-4 py-2.5 inline-flex items-center gap-2 disabled:opacity-40"
              >
                {renderingMockup ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Video className="w-4 h-4 text-[#C8FF3A]" />}
                {renderingMockup ? 'Renderuję 9:16...' : 'Generuj podgląd wideo 9:16'}
              </button>
            </div>
          </div>

          {errorMsg && (
            <div className="bg-[#2B1215] border border-[#FF5C5C]/50 px-3 py-2 text-xs text-[#FFB3B3] flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {errorMsg}
            </div>
          )}
        </form>

        {/* Zapisane blueprinty */}
        <div className="bg-[#0E0F11] border border-[#272A2F] p-5 fk-cut flex flex-col">
          <div className="text-xs font-extrabold uppercase tracking-wider text-[#A0A7B1] mb-3">
            Zapisane Researchy ({history.length})
          </div>
          <div className="space-y-2 overflow-y-auto max-h-64 pr-1">
            {history.length === 0 && (
              <div className="text-xs text-[#686E78]">Brak zapisanych nisz — uruchom pierwszy research po lewej.</div>
            )}
            {history.map((item) => (
              <button
                key={item.slug}
                onClick={() => handleSelectHistory(item.slug)}
                className={`w-full text-left p-3 border transition-colors fk-cut-sm ${
                  blueprint?.slug === item.slug
                    ? 'bg-[#17191C] border-[#C8FF3A]'
                    : 'bg-[#121417] border-[#272A2F] hover:border-[#4B515C]'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-bold truncate">{item.business_name}</span>
                  <span className="text-[10px] font-black px-1.5 py-0.5 bg-[#272A2F] text-[#C8FF3A]">
                    {item.originality_score_pct.toFixed(0)}% orig
                  </span>
                </div>
                <div className="text-[11px] text-[#A0A7B1] truncate mt-0.5">
                  {item.niche_query} · {item.city || 'Polska'} {item.has_preview_video ? '· MP4 OK' : ''}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Główna sekcja porównawcza + podgląd 9:16 */}
      {blueprint && yt && cl && (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
          {/* Kolumna lewa i środek: Porównanie + Storyboard */}
          <div className="xl:col-span-8 space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Wzorzec YT */}
              <div className="bg-[#0E0F11] border border-[#272A2F] p-5 fk-cut space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-extrabold uppercase tracking-wider text-[#FF7A59]">
                    Wzorzec z YouTube (Struktura)
                  </span>
                  <Scissors className="w-4 h-4 text-[#FF7A59]" />
                </div>
                <div className="text-sm font-bold leading-snug">{yt.title}</div>
                <div className="text-xs text-[#A0A7B1]">
                  Kanał: <span className="text-white font-semibold">{yt.channel}</span> · Wyśw.:{' '}
                  <span className="text-[#C8FF3A] font-bold">{yt.views.toLocaleString()}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-[#272A2F] text-center">
                  <div className="bg-[#17191C] p-2">
                    <div className="text-[10px] text-[#A0A7B1]">CZAS</div>
                    <div className="text-sm font-black">{yt.duration_s}s</div>
                  </div>
                  <div className="bg-[#17191C] p-2">
                    <div className="text-[10px] text-[#A0A7B1]">TEMPO CIĘĆ</div>
                    <div className="text-sm font-black">{yt.cuts_per_10s}/10s</div>
                  </div>
                  <div className="bg-[#17191C] p-2">
                    <div className="text-[10px] text-[#A0A7B1]">ŚR. UJĘCIE</div>
                    <div className="text-sm font-black">{yt.avg_shot_len_s}s</div>
                  </div>
                </div>
                <ul className="space-y-1.5 text-xs text-[#C7CDD6] list-disc pl-4">
                  {blueprint.what_works_summary_pl.map((s, idx) => (
                    <li key={idx}>{s}</li>
                  ))}
                </ul>
                {yt.url && (
                  <a
                    href={yt.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs font-bold text-[#C8FF3A] hover:underline"
                  >
                    <ExternalLink className="w-3.5 h-3.5" /> Zobacz oryginał na YouTube
                  </a>
                )}
              </div>

              {/* Oryginalny projekt Synapsy */}
              <div className="bg-[#0E0F11] border border-[#C8FF3A]/40 p-5 fk-cut space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-extrabold uppercase tracking-wider text-[#C8FF3A]">
                    Twój Oryginalny Projekt ({blueprint.synapsa_source})
                  </span>
                  <ShieldCheck className="w-4 h-4 text-[#C8FF3A]" />
                </div>
                <div className="bg-[#17191C] border border-[#272A2F] p-2.5">
                  <div className="text-[10px] text-[#A0A7B1] uppercase">Hook 0–1.5s na ekranie</div>
                  <div className="text-base font-black text-[#C8FF3A] mt-0.5">{blueprint.opening_hook_pl}</div>
                </div>
                <div className="text-xs font-bold uppercase text-[#A0A7B1]">
                  5 oryginalnych tytułów PL (Anty-Plagiat {origScore.toFixed(1)}%):
                </div>
                <ul className="space-y-1.5 text-xs">
                  {blueprint.original_titles_pl.map((t, idx) => (
                    <li key={idx} className="flex items-start gap-2 bg-[#14161A] px-2.5 py-1.5 border border-[#272A2F]">
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#C8FF3A] mt-0.5 flex-shrink-0" />
                      <span>{t}</span>
                    </li>
                  ))}
                </ul>
                <div className="text-xs text-[#A0A7B1]">
                  <span className="font-bold text-white">Opis + CTA:</span> {blueprint.caption_pl}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {blueprint.hashtags_pl.map((h) => (
                    <span key={h} className="text-[11px] px-2 py-0.5 bg-[#17191C] text-[#C8FF3A] border border-[#272A2F]">
                      {h}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Storyboard + Checklista nagrań telefonem */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-[#0E0F11] border border-[#272A2F] p-5 fk-cut">
                <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-[#C8FF3A] mb-3">
                  <Clock className="w-4 h-4" />
                  Storyboard Ujęcie-po-Ujęciu ({cl.duration_s}s)
                </div>
                <div className="space-y-2.5">
                  {blueprint.storyboard.map((s) => (
                    <div key={s.step} className="bg-[#14161A] border border-[#272A2F] p-3">
                      <div className="flex items-center justify-between text-xs font-black">
                        <span className="text-[#C8FF3A]">
                          #{s.step} · {s.role}
                        </span>
                        <span className="text-[#A0A7B1] tabular-nums">
                          {s.start_s.toFixed(1)}s–{s.end_s.toFixed(1)}s ({s.duration_s.toFixed(1)}s)
                        </span>
                      </div>
                      <div className="text-xs font-bold text-white mt-1">{s.overlay_text_pl}</div>
                      <div className="text-[11px] text-[#C7CDD6] mt-0.5">{s.visual_plan_pl}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-[#0E0F11] border border-[#272A2F] p-5 fk-cut">
                <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-[#C8FF3A] mb-3">
                  <Camera className="w-4 h-4" />
                  Co Ma Nagrać Klient Telefonem (9:16)
                </div>
                <ul className="space-y-2 text-xs text-[#E4E7EC]">
                  {blueprint.client_shot_list.map((line, i) => (
                    <li key={i} className="bg-[#14161A] border border-[#272A2F] p-2.5">
                      {line}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Kolumna prawa: Odtwarzacz 9:16 dla klienta */}
          <div className="xl:col-span-4 bg-[#0E0F11] border border-[#272A2F] p-5 fk-cut flex flex-col items-center">
            <div className="w-full flex items-center justify-between mb-3">
              <span className="text-xs font-extrabold uppercase tracking-wider text-[#C8FF3A]">
                Podgląd Pitch 9:16 (MP4)
              </span>
              {previewVideoUrl && (
                <span className="text-[11px] text-[#A0A7B1] font-bold">1080×1920</span>
              )}
            </div>

            {previewVideoUrl ? (
              <video
                key={previewVideoUrl}
                src={previewVideoUrl}
                controls
                playsInline
                className="w-full max-w-[320px] aspect-[9/16] bg-black border border-[#272A2F] rounded"
              />
            ) : (
              <div className="w-full max-w-[320px] aspect-[9/16] bg-[#14161A] border border-dashed border-[#383D47] flex flex-col items-center justify-center p-6 text-center space-y-3">
                <Play className="w-10 h-10 text-[#C8FF3A]" />
                <div className="text-sm font-bold">Brak wyrenderowanego wideo pitch</div>
                <p className="text-xs text-[#A0A7B1]">
                  Kliknij „Generuj podgląd wideo 9:16”, aby zobaczyć gotowy animatic w rytmie wzorca YT dla klienta.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
