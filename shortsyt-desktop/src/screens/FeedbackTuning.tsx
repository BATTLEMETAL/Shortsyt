import React, { useState, useEffect, useRef } from 'react';
import {
  SlidersHorizontal,
  Save,
  MessageSquare,
  Sparkles,
  Volume2,
  Camera,
  Scissors,
  CheckCircle2,
  ThumbsUp,
  Cpu,
  Zap,
  RotateCcw
} from 'lucide-react';
import { apiGetTuningConfig, apiSaveTuningConfig } from '../lib/api';

export interface TuningProfile {
  pacing: 'aggressive' | 'balanced' | 'cinematic' | 'custom';
  zoomAggression: number; // 1.05 - 1.35
  slowmoDuration: number; // 0.8s - 2.5s
  musicBalance: number;   // 0.3 - 1.0
  gameSoundBalance: number; // 0.2 - 1.0
  titleTone: 'hype' | 'narrative' | 'meme';
  userNotes: string;
}

const PACING_PRESETS = {
  aggressive: {
    zoomAggression: 1.30,
    slowmoDuration: 0.9,
    musicBalance: 0.90,
    gameSoundBalance: 0.50,
    titleTone: 'hype' as const,
    userNotes: 'Ekstremalnie Szybkie: natychmiastowe wejście w akcję (0.5s przed walką), mocny zoom-punch 1.30x przy każdym killu, głośna muzyka Phonk/NCS i agresywne tytuły pod CTR (INSANE / UNSTOPPABLE 🔥).',
  },
  balanced: {
    zoomAggression: 1.20,
    slowmoDuration: 1.4,
    musicBalance: 0.85,
    gameSoundBalance: 0.65,
    titleTone: 'narrative' as const,
    userNotes: 'Standard Dwannellenga (v25): 1.5s hook, płynne slow-mo na decydujący cios, zbalansowane audio i angażujące pytanie w komentarzach (Storytelling & Clutch 🧠).',
  },
  cinematic: {
    zoomAggression: 1.10,
    slowmoDuration: 2.2,
    musicBalance: 0.70,
    gameSoundBalance: 0.80,
    titleTone: 'narrative' as const,
    userNotes: 'Cinematic Outplay: dłuższy kontekst walki 1v3/1v5, kinowe ruchy kamery, dramatyczny bass-drop i wyraziste kinowe zwolnienie tempa w kulminacji 🎬.',
  },
};

const TONE_PROMPTS: Record<string, string> = {
  hype: 'Hype & High Energy: agresywny hook w pierwszych 1.5s, mocne słowa kluczowe (INSANE, PENTAKILL, UNSTOPPABLE), wykrzykniki i emoji 🔥💥💀. Tytuły krótkie, zoptymalizowane pod CTR na telefonach.',
  narrative: 'Storytelling & Clutch: fokus na historię (np. "They cornered her... Bad idea."), wyeksponowanie momentu zwrotnego 1v3/1v5 i opisu sytuacji w League of Legends. Pytanie na końcu angażujące w komentarzach.',
  meme: 'Meme & Casual Gaming: fokus na humor, ironię, outplay przeciwnika (np. "Thought they had me 😏", "Enemy team forgot who I was 💀"). Angażujące, streamerskie podsumowanie akcji.',
};

const DEFAULT_TUNING: TuningProfile = {
  pacing: 'balanced',
  zoomAggression: 1.20,
  slowmoDuration: 1.4,
  musicBalance: 0.85,
  gameSoundBalance: 0.65,
  titleTone: 'narrative',
  userNotes: PACING_PRESETS.balanced.userNotes,
};

export default function FeedbackTuning() {
  const [profile, setProfile] = useState<TuningProfile>(DEFAULT_TUNING);
  const [isSaved, setIsSaved] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const profileRef = useRef<TuningProfile>(DEFAULT_TUNING);
  const isInitialLoad = useRef(true);

  // Synchronizacja refa z profilem
  useEffect(() => {
    profileRef.current = profile;
  }, [profile]);

  // Funkcja natychmiastowego zapisu do backendu i storage
  const persistDirectly = async (p: TuningProfile) => {
    try {
      localStorage.setItem('tuning_profile', JSON.stringify(p));
      if (window.electronStore) {
        await window.electronStore.set('tuning_profile', p).catch(() => {});
      }
      await apiSaveTuningConfig(p);
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2500);
    } catch (e) {
      console.warn('Błąd bezpośredniego zapisu:', e);
    }
  };

  useEffect(() => {
    async function load() {
      try {
        const remote = await apiGetTuningConfig();
        if (remote && remote.pacing) {
          setProfile(remote);
          profileRef.current = remote;
          setLoading(false);
          return;
        }
      } catch (e) {
        console.warn('Nie udało się pobrać konfiguracji z backendu, wczytuję lokalną:', e);
      }

      if (window.electronStore) {
        try {
          const stored = await window.electronStore.get('tuning_profile', DEFAULT_TUNING);
          if (stored) {
            setProfile(stored);
            profileRef.current = stored;
          }
        } catch {
          // ignore
        }
      } else {
        const stored = localStorage.getItem('tuning_profile');
        if (stored) {
          const parsed = JSON.parse(stored);
          setProfile(parsed);
          profileRef.current = parsed;
        }
      }
      setLoading(false);
    }
    load().then(() => { isInitialLoad.current = false; });

    // Przy odmontowaniu komponentu (np. kliknięcie innej zakładki w menu) natychmiast zapisz
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      if (!isInitialLoad.current && profileRef.current) {
        apiSaveTuningConfig(profileRef.current).catch(() => {});
      }
    };
  }, []);

  const handleSelectPacing = async (pacingId: 'aggressive' | 'balanced' | 'cinematic') => {
    const preset = PACING_PRESETS[pacingId];
    const newProfile: TuningProfile = {
      pacing: pacingId,
      zoomAggression: preset.zoomAggression,
      slowmoDuration: preset.slowmoDuration,
      musicBalance: preset.musicBalance,
      gameSoundBalance: preset.gameSoundBalance,
      titleTone: preset.titleTone,
      userNotes: preset.userNotes,
    };
    setProfile(newProfile);
    profileRef.current = newProfile;
    // Zapis natychmiastowy przy kliknięciu presetu
    await persistDirectly(newProfile);
  };

  const handleSelectTone = async (toneId: 'hype' | 'narrative' | 'meme') => {
    const newProfile: TuningProfile = {
      ...profileRef.current,
      titleTone: toneId,
      userNotes: TONE_PROMPTS[toneId] || profileRef.current.userNotes,
    };
    setProfile(newProfile);
    profileRef.current = newProfile;
    await persistDirectly(newProfile);
  };

  const handleSliderChange = (key: keyof TuningProfile, value: number) => {
    const newProfile: TuningProfile = {
      ...profileRef.current,
      [key]: value,
      pacing: 'custom',
    };
    setProfile(newProfile);
    profileRef.current = newProfile;

    // Natychmiast do localStorage
    localStorage.setItem('tuning_profile', JSON.stringify(newProfile));

    // Debounce do backendu (400ms)
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      apiSaveTuningConfig(newProfile).catch(() => {});
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2000);
    }, 400);
  };

  const handleNotesChange = (val: string) => {
    const newProfile: TuningProfile = {
      ...profileRef.current,
      userNotes: val,
    };
    setProfile(newProfile);
    profileRef.current = newProfile;

    localStorage.setItem('tuning_profile', JSON.stringify(newProfile));
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      apiSaveTuningConfig(newProfile).catch(() => {});
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2000);
    }, 500);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    await persistDirectly(profile);
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2438]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
            <SlidersHorizontal className="w-6 h-6 text-[#C89B3C]" />
            <span>Dostrajanie Stylu Montażu & Feedback AI</span>
          </h1>
          <p className="text-xs text-[#8B8FA8] mt-1 font-medium">
            Spersonalizuj zachowanie algorytmów kamery, dźwięku, cięcia i promptów Gemini pod Twój unikalny styl kanału Dwannellenga
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#121624] border border-[#C89B3C]/40 text-xs">
            <span className="text-[#8B8FA8]">Aktywny profil:</span>
            <span className="text-[#C89B3C] font-black">
              {profile.pacing === 'aggressive' ? 'Ekstremalnie Szybkie 🔥 (10-13s)' :
               profile.pacing === 'balanced' ? 'Zbalansowane ✅ (14-17s)' :
               profile.pacing === 'cinematic' ? 'Cinematic 🎬 (20-25s)' : 'Własny ⚙️'}
            </span>
          </div>
          {isSaved && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#2ECC71]/20 border border-[#2ECC71]/50 text-[#55E88D] text-xs font-bold animate-fade-in shadow-md shadow-[#2ECC71]/10">
              <CheckCircle2 className="w-4 h-4" />
              <span>Zapisano w silniku!</span>
            </div>
          )}
        </div>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Section 1: Pacing & Montaż */}
        <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-xl space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-bold text-[#E4D6B5]">
              <Scissors className="w-4 h-4 text-[#C89B3C]" />
              <span>Tryb Dynamiki & Presety Montażu (Pacing)</span>
            </div>
            {profile.pacing === 'custom' && (
              <span className="text-[11px] bg-[#C89B3C]/20 border border-[#C89B3C]/40 text-[#C89B3C] font-bold px-2 py-0.5 rounded-md">
                Własne parametry (Ręczne dostrojenie)
              </span>
            )}
          </div>

          {/* 3 Main Presets */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[
              { id: 'aggressive', title: 'Ekstremalnie Szybkie 🔥', desc: 'Zoom 1.30x, SlowMo 0.9s, Muzyka 90% — natychmiastowy hook' },
              { id: 'balanced', title: 'Zbalansowane (Dwannellenga v25) ✅', desc: 'Zoom 1.20x, SlowMo 1.4s, Muzyka 85% — optymalna retencja' },
              { id: 'cinematic', title: 'Cinematic Outplay 🎬', desc: 'Zoom 1.10x, SlowMo 2.2s, Gra 80% — kinowy bass drop i budowanie napięcia' },
            ].map((opt) => (
              <div
                key={opt.id}
                onClick={() => handleSelectPacing(opt.id as any)}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  profile.pacing === opt.id
                    ? 'bg-[#C89B3C]/15 border-[#C89B3C] shadow-md shadow-[#C89B3C]/10'
                    : 'bg-[#0A0E1A] border-[#1E2438] hover:border-[#8B8FA8]/40'
                }`}
              >
                <div className="text-xs font-black text-[#E4D6B5] flex items-center justify-between">
                  <span>{opt.title}</span>
                  {profile.pacing === opt.id && <span className="w-2 h-2 rounded-full bg-[#C89B3C]" />}
                </div>
                <div className="text-[11px] text-[#8B8FA8] mt-1.5 leading-relaxed">{opt.desc}</div>
              </div>
            ))}
          </div>

          {/* Sliders (Ręczna zmiana parametrów) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-3 border-t border-[#1E2438]">
            <div>
              <div className="flex justify-between text-xs font-semibold mb-1.5">
                <span className="text-[#8B8FA8]">Siła Zoom-Punch (Kill Impact):</span>
                <span className="font-mono text-[#C89B3C] font-bold">{profile.zoomAggression.toFixed(2)}x</span>
              </div>
              <input
                type="range"
                min="1.05"
                max="1.35"
                step="0.05"
                value={profile.zoomAggression}
                onChange={(e) => handleSliderChange('zoomAggression', parseFloat(e.target.value))}
                className="w-full accent-[#C89B3C] cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-[#50546A] mt-1">
                <span>Subtelny (1.05x)</span>
                <span>Mocny LoL Punch (1.35x)</span>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs font-semibold mb-1.5">
                <span className="text-[#8B8FA8]">Długość Slow-Mo na Peak Action:</span>
                <span className="font-mono text-[#C89B3C] font-bold">{profile.slowmoDuration.toFixed(1)}s</span>
              </div>
              <input
                type="range"
                min="0.8"
                max="2.5"
                step="0.1"
                value={profile.slowmoDuration}
                onChange={(e) => handleSliderChange('slowmoDuration', parseFloat(e.target.value))}
                className="w-full accent-[#C89B3C] cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-[#50546A] mt-1">
                <span>Szybkie (0.8s)</span>
                <span>Dramatyczne (2.5s)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Section 2: Audio & Title Tone */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Audio Mixing */}
          <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-xl space-y-4">
            <div className="flex items-center gap-2 text-sm font-bold text-[#E4D6B5]">
              <Volume2 className="w-4 h-4 text-[#2ECC71]" />
              <span>Balans Dźwięku (Muzyka vs Gra)</span>
            </div>

            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-xs font-semibold mb-1.5">
                  <span className="text-[#8B8FA8]">Głośność Muzyki NCS / Phonk:</span>
                  <span className="font-mono text-[#55E88D] font-bold">{Math.round(profile.musicBalance * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0.3"
                  max="1.0"
                  step="0.05"
                  value={profile.musicBalance}
                  onChange={(e) => handleSliderChange('musicBalance', parseFloat(e.target.value))}
                  className="w-full accent-[#2ECC71] cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs font-semibold mb-1.5">
                  <span className="text-[#8B8FA8]">Dźwięk Gry (VFX / Announcer / Kills):</span>
                  <span className="font-mono text-[#4FA3F7] font-bold">{Math.round(profile.gameSoundBalance * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="1.0"
                  step="0.05"
                  value={profile.gameSoundBalance}
                  onChange={(e) => handleSliderChange('gameSoundBalance', parseFloat(e.target.value))}
                  className="w-full accent-[#2A7FD4] cursor-pointer"
                />
              </div>
            </div>
          </div>

          {/* AI Title Style */}
          <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-xl space-y-4">
            <div className="flex items-center gap-2 text-sm font-bold text-[#E4D6B5]">
              <Sparkles className="w-4 h-4 text-[#C89B3C]" />
              <span>Ton Generowania Tytułów i Hashtagów</span>
            </div>

            <div className="space-y-2">
              {[
                { id: 'hype', title: 'Hype & High Energy 💥', desc: 'Emocjonalne, wykrzyknikowe, maksymalny scroll-stop na telefonach' },
                { id: 'narrative', title: 'Storytelling & Clutch 🧠', desc: 'Opowiadające historię odwrócenia losów gry (Dwannellenga Standard)' },
                { id: 'meme', title: 'Meme & Casual Gaming 💀', desc: 'Lekki styl, ironiczne komentarze, styl streamerski' },
              ].map((t) => (
                <div
                  key={t.id}
                  onClick={() => handleSelectTone(t.id as any)}
                  className={`p-3 rounded-xl border cursor-pointer transition-all ${
                    profile.titleTone === t.id
                      ? 'bg-[#C89B3C]/15 border-[#C89B3C]'
                      : 'bg-[#0A0E1A] border-[#1E2438] hover:border-white/20'
                  }`}
                >
                  <div className="text-xs font-bold text-[#E4D6B5] flex items-center justify-between">
                    <span>{t.title}</span>
                    {profile.titleTone === t.id && <span className="w-2 h-2 rounded-full bg-[#C89B3C]" />}
                  </div>
                  <div className="text-[10px] text-[#8B8FA8] mt-0.5">{t.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Section 3: User Direct Instructions / Prompt Feedback */}
        <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-xl space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-[#E4D6B5]">
            <MessageSquare className="w-4 h-4 text-[#C89B3C]" />
            <span>Wskazówki dla Agenta AI (Prompt Context & Feedback)</span>
          </div>

          <div>
            <label className="text-xs text-[#8B8FA8] font-semibold block mb-2">
              Wytyczne przekazywane bezpośrednio do generatora metadanych i promptów kanału Dwannellenga (aktualizują się przy zmianie tonu):
            </label>
            <textarea
              rows={3}
              value={profile.userNotes}
              onChange={(e) => handleNotesChange(e.target.value)}
              placeholder="np. Dodawaj zawsze nazwę skina do opisu, preferuj utwory z mocnym dropem basu, wyłączaj intro jeśli akcja zaczyna się od razu..."
              className="w-full p-3.5 rounded-xl bg-[#0A0E1A] border border-[#1E2438] text-xs text-[#E4D6B5] focus:outline-none focus:border-[#C89B3C] font-mono leading-relaxed"
            />
          </div>

          <div className="flex items-center justify-end pt-2">
            <button
              type="submit"
              className="px-6 py-2.5 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] text-xs font-black transition-colors flex items-center gap-2 shadow-lg shadow-[#C89B3C]/20"
            >
              <Save className="w-4 h-4" />
              <span>Zapisz Mój Profil Stylu</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
