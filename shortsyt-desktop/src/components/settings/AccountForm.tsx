import React from 'react';
import { ContentModePreset } from '../../lib/api';

export interface AccountFormState {
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

export const EMPTY_ACCOUNT_FORM: AccountFormState = {
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

interface AccountFormProps {
  form: AccountFormState;
  setForm: React.Dispatch<React.SetStateAction<AccountFormState>>;
  presets: Record<string, ContentModePreset>;
  saving: boolean;
  onApplyPresetToNew: (mode: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
}

export default function AccountForm({
  form,
  setForm,
  presets,
  saving,
  onApplyPresetToNew,
  onSubmit,
  onCancel,
}: AccountFormProps) {
  return (
    <form onSubmit={onSubmit} className="p-4 fk-cut-sm bg-[#050505] border border-[#C8FF3A]/40 space-y-4">
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
                onApplyPresetToNew(mode);
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
          onClick={onCancel}
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
  );
}
