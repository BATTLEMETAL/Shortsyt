import React, { useState, useEffect } from 'react';
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
} from 'lucide-react';

interface TuningProfile {
  pacing: 'aggressive' | 'balanced' | 'cinematic';
  zoomAggression: number; // 1.05 - 1.30
  slowmoDuration: number; // 0.8s - 2.5s
  musicBalance: number;   // 0.4 - 1.0
  gameSoundBalance: number; // 0.3 - 0.9
  titleTone: 'hype' | 'narrative' | 'meme';
  userNotes: string;
}

const DEFAULT_TUNING: TuningProfile = {
  pacing: 'aggressive',
  zoomAggression: 1.20,
  slowmoDuration: 1.5,
  musicBalance: 0.85,
  gameSoundBalance: 0.60,
  titleTone: 'hype',
  userNotes: 'Fokus na wyrazisty slow-mo w momencie 5. killa, dynamiczny hook w pierwszych 1.5s.',
};

export default function FeedbackTuning() {
  const [profile, setProfile] = useState<TuningProfile>(DEFAULT_TUNING);
  const [isSaved, setIsSaved] = useState<boolean>(false);

  useEffect(() => {
    // Load from electron store / localStorage if present
    async function load() {
      if (window.electronStore) {
        try {
          const stored = await window.electronStore.get('tuning_profile', DEFAULT_TUNING);
          if (stored) setProfile(stored);
        } catch {
          // ignore
        }
      } else {
        const stored = localStorage.getItem('tuning_profile');
        if (stored) setProfile(JSON.parse(stored));
      }
    }
    load();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (window.electronStore) {
      await window.electronStore.set('tuning_profile', profile);
    } else {
      localStorage.setItem('tuning_profile', JSON.stringify(profile));
    }
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 3000);
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
            Spersonalizuj zachowanie algorytmów kamery, dźwięku, cięcia i promptów Gemini pod Twój unikalny styl kanału
          </p>
        </div>

        {isSaved && (
          <div className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#2ECC71]/15 border border-[#2ECC71]/40 text-[#55E88D] text-xs font-bold animate-fade-in">
            <CheckCircle2 className="w-4 h-4" />
            <span>Preferencje zapisane w pipeline!</span>
          </div>
        )}
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Section 1: Pacing & Montaż */}
        <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] shadow-xl space-y-5">
          <div className="flex items-center gap-2 text-sm font-bold text-[#E4D6B5]">
            <Scissors className="w-4 h-4 text-[#C89B3C]" />
            <span>Tempo & Dynamika Cięcia (Pacing)</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[
              { id: 'aggressive', title: 'Ekstremalnie Szybkie 🔥', desc: 'Brak chodzenia, wejście 0.5s przed walką, natychmiastowy hook' },
              { id: 'balanced', title: 'Zbalansowane (v25) ✅', desc: 'Krótki 2s build-up, płynne slow-mo na decydujący cios' },
              { id: 'cinematic', title: 'Cinematic Outplay 🎬', desc: 'Dłuższy kontekst sytuacji, płynne przejścia, wolniejsze ruchy' },
            ].map((opt) => (
              <div
                key={opt.id}
                onClick={() => setProfile({ ...profile, pacing: opt.id as any })}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  profile.pacing === opt.id
                    ? 'bg-[#C89B3C]/15 border-[#C89B3C] shadow-md'
                    : 'bg-[#0A0E1A] border-[#1E2438] hover:border-[#8B8FA8]/40'
                }`}
              >
                <div className="text-xs font-black text-[#E4D6B5]">{opt.title}</div>
                <div className="text-[11px] text-[#8B8FA8] mt-1">{opt.desc}</div>
              </div>
            ))}
          </div>

          {/* Sliders */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
            <div>
              <div className="flex justify-between text-xs font-semibold mb-1.5">
                <span className="text-[#8B8FA8]">Siła Zoom-Punch (Kill Impact):</span>
                <span className="font-mono text-[#C89B3C]">{profile.zoomAggression}x</span>
              </div>
              <input
                type="range"
                min="1.05"
                max="1.35"
                step="0.05"
                value={profile.zoomAggression}
                onChange={(e) => setProfile({ ...profile, zoomAggression: parseFloat(e.target.value) })}
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
                <span className="font-mono text-[#C89B3C]">{profile.slowmoDuration}s</span>
              </div>
              <input
                type="range"
                min="0.8"
                max="2.5"
                step="0.1"
                value={profile.slowmoDuration}
                onChange={(e) => setProfile({ ...profile, slowmoDuration: parseFloat(e.target.value) })}
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
                  <span className="text-[#8B8FA8]">Głośność Muzyki NCS:</span>
                  <span className="font-mono text-[#55E88D]">{Math.round(profile.musicBalance * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0.3"
                  max="1.0"
                  step="0.05"
                  value={profile.musicBalance}
                  onChange={(e) => setProfile({ ...profile, musicBalance: parseFloat(e.target.value) })}
                  className="w-full accent-[#2ECC71] cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs font-semibold mb-1.5">
                  <span className="text-[#8B8FA8]">Oryginalny Dźwięk Gry (VFX / Announcer):</span>
                  <span className="font-mono text-[#4FA3F7]">{Math.round(profile.gameSoundBalance * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="1.0"
                  step="0.05"
                  value={profile.gameSoundBalance}
                  onChange={(e) => setProfile({ ...profile, gameSoundBalance: parseFloat(e.target.value) })}
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
                { id: 'hype', title: 'Hype & High Energy 💥', desc: 'Emocjonalne, wykrzyknikowe, zatrzymujące scroll na feedzie' },
                { id: 'narrative', title: 'Storytelling & Clutch 🧠', desc: 'Opowiadające krótką historię odwrócenia losów gry' },
                { id: 'meme', title: 'Meme & Casual Gaming 💀', desc: 'Lekki styl, ironiczne komentarze, styl streamerski' },
              ].map((t) => (
                <div
                  key={t.id}
                  onClick={() => setProfile({ ...profile, titleTone: t.id as any })}
                  className={`p-3 rounded-xl border cursor-pointer transition-all ${
                    profile.titleTone === t.id
                      ? 'bg-[#C89B3C]/15 border-[#C89B3C]'
                      : 'bg-[#0A0E1A] border-[#1E2438] hover:border-white/20'
                  }`}
                >
                  <div className="text-xs font-bold text-[#E4D6B5]">{t.title}</div>
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
              Wpisz specyficzne wytyczne, które mają być automatycznie przekazywane do pipeline&apos;u i promptów Gemini:
            </label>
            <textarea
              rows={3}
              value={profile.userNotes}
              onChange={(e) => setProfile({ ...profile, userNotes: e.target.value })}
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
