import React, { useCallback, useEffect, useState } from 'react';
import {
  Users, RefreshCw, Plus, Check, AlertCircle, ShieldCheck, ShieldOff, Edit3, Trash2,
} from 'lucide-react';
import {
  apiListAccounts, apiUpsertAccount, apiSelectAccount, apiDeleteAccount,
  AccountProfile, ContentModePreset,
} from '../../lib/api';
import AccountForm, { AccountFormState, EMPTY_ACCOUNT_FORM } from './AccountForm';

interface AccountsManagerCardProps {
  tokenReady: boolean;
  onAccountSwitched: (acc: AccountProfile) => void;
}

export default function AccountsManagerCard({ tokenReady, onAccountSwitched }: AccountsManagerCardProps) {
  const [accounts, setAccounts] = useState<AccountProfile[]>([]);
  const [activeId, setActiveId] = useState<string>('');
  const [presets, setPresets] = useState<Record<string, ContentModePreset>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [showForm, setShowForm] = useState<boolean>(false);
  const [form, setForm] = useState<AccountFormState>(EMPTY_ACCOUNT_FORM);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadAccounts = useCallback(async () => {
    if (!tokenReady) return;
    setLoading(true);
    try {
      const res = await apiListAccounts();
      setAccounts(res.accounts || []);
      setActiveId(res.active_account_id || '');
      setPresets(res.presets || {});
    } catch (e: any) {
      setMsg({ type: 'error', text: e?.response?.data?.detail || 'Nie udało się pobrać listy kont.' });
    } finally {
      setLoading(false);
    }
  }, [tokenReady]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const applyPresetToNewForm = (mode: string) => {
    const p = presets[mode];
    if (!p) {
      setForm((prev) => ({ ...prev, content_mode: mode }));
      return;
    }
    setForm((prev) => ({
      ...prev,
      content_mode: mode,
      language: p.language || prev.language,
      peak_hours_text: (p.peak_hours_cet || []).join(', '),
      brand_voice: p.brand_voice || '',
      value_proposition: p.value_proposition || '',
      cta_text: p.cta_text || '',
      cta_url: p.cta_url || '',
      hashtags_text: (p.mandatory_hashtags || []).join(', '),
      forbidden_text: (p.forbidden_words || []).join(', '),
    }));
  };

  const startNewAccount = () => {
    setMsg(null);
    const defaultMode = 'PRODUCT_ECOMMERCE_AD';
    const p = presets[defaultMode];
    setForm({
      ...EMPTY_ACCOUNT_FORM,
      content_mode: defaultMode,
      language: p?.language || 'pl',
      peak_hours_text: (p?.peak_hours_cet || ['15:00', '21:30']).join(', '),
      brand_voice: p?.brand_voice || '',
      value_proposition: p?.value_proposition || '',
      cta_text: p?.cta_text || '',
      hashtags_text: (p?.mandatory_hashtags || ['#shorts']).join(', '),
      forbidden_text: (p?.forbidden_words || []).join(', '),
    });
    setShowForm(true);
  };

  const startEditAccount = (acc: AccountProfile) => {
    setMsg(null);
    setForm({
      account_id: acc.account_id,
      display_name: acc.display_name || '',
      handle: acc.handle || '',
      content_mode: acc.content_mode || 'GAMING_HIGHLIGHTS',
      language: acc.language || 'pl',
      peak_hours_text: (acc.peak_hours_cet || []).join(', '),
      brand_voice: acc.brand_voice || '',
      value_proposition: acc.value_proposition || '',
      target_audience: acc.target_audience || '',
      cta_text: acc.cta_text || '',
      cta_url: acc.cta_url || '',
      location: acc.location || '',
      phone: acc.phone || '',
      hashtags_text: (acc.mandatory_hashtags || []).join(', '),
      forbidden_text: (acc.forbidden_words || []).join(', '),
    });
    setShowForm(true);
  };

  const handleSelect = async (accountId: string) => {
    setMsg(null);
    try {
      const res = await apiSelectAccount(accountId);
      setActiveId(res.active_account.account_id);
      await loadAccounts();
      onAccountSwitched(res.active_account);
      setMsg({ type: 'success', text: `Aktywowano konto: ${res.active_account.display_name}. Teraz możesz autoryzować/sprawdzić token YT powyżej.` });
    } catch (e: any) {
      setMsg({ type: 'error', text: e?.response?.data?.detail || 'Błąd przełączania konta.' });
    }
  };

  const handleDelete = async (acc: AccountProfile) => {
    setMsg(null);
    try {
      await apiDeleteAccount(acc.account_id);
      await loadAccounts();
      setMsg({ type: 'success', text: `Usunięto konto: ${acc.display_name}` });
    } catch (e: any) {
      setMsg({ type: 'error', text: e?.response?.data?.detail || 'Nie można usunąć tego konta.' });
    }
  };

  const handleSaveForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.display_name.trim()) {
      setMsg({ type: 'error', text: 'Podaj nazwę kanału / klienta.' });
      return;
    }
    setSaving(true);
    setMsg(null);
    const parseList = (raw: string) =>
      raw
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    const parseCommaList = (raw: string) =>
      raw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

    try {
      const res = await apiUpsertAccount({
        account_id: form.account_id,
        display_name: form.display_name.trim(),
        handle: form.handle.trim(),
        content_mode: form.content_mode,
        language: form.language,
        peak_hours_cet: parseCommaList(form.peak_hours_text),
        brand_voice: form.brand_voice.trim(),
        value_proposition: form.value_proposition.trim(),
        target_audience: form.target_audience.trim(),
        cta_text: form.cta_text.trim(),
        cta_url: form.cta_url.trim(),
        location: form.location.trim(),
        phone: form.phone.trim(),
        mandatory_hashtags: parseList(form.hashtags_text),
        forbidden_words: parseCommaList(form.forbidden_text),
        set_active: true,
      });
      setShowForm(false);
      await loadAccounts();
      onAccountSwitched(res.account);
      setMsg({ type: 'success', text: `Zapisano i aktywowano profil: ${res.account.display_name}` });
    } catch (e: any) {
      setMsg({ type: 'error', text: e?.response?.data?.detail || 'Błąd zapisu konta.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-6 fk-cut bg-[#0E0F11] border border-[#272A2F] space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2.5 text-sm font-bold text-[#FFFFFF]">
            <Users className="w-4 h-4 text-[#C8FF3A]" />
            <span>Multi-Account &amp; Wytyczne Kontentu (Klienci / Sandbox YT)</span>
          </div>
          <p className="text-[11px] text-[#A0A7B1] mt-1">
            Przełączaj między kanałem gamingowym, kontem testowym (Sandbox) i klientami (salon, e-commerce). Generator metadanych i token YouTube dopasują się automatycznie.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadAccounts}
            disabled={loading || !tokenReady}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#050505] border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF] disabled:opacity-40"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Odśwież
          </button>
          <button
            type="button"
            onClick={showForm ? () => setShowForm(false) : startNewAccount}
            disabled={!tokenReady}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#C8FF3A] text-[#050505] text-xs font-extrabold hover:bg-[#d6ff66] disabled:opacity-40"
          >
            <Plus className="w-3.5 h-3.5" /> {showForm ? 'Zamknij formularz' : 'Dodaj Konto / Klienta'}
          </button>
        </div>
      </div>

      {!tokenReady && (
        <div className="p-3 bg-[#050505] border border-[#272A2F] text-xs text-[#A0A7B1]">
          Zaloguj się tokenem JWT powyżej, aby zarządzać kontami.
        </div>
      )}

      {msg && (
        <div className={`p-3 fk-cut-sm border text-xs flex items-start gap-2 ${msg.type === 'success' ? 'bg-[#2ECC71]/10 border-[#2ECC71]/30 text-[#55E88D]' : 'bg-[#FF5C5C]/10 border-[#FF5C5C]/30 text-[#FF5C5C]'}`}>
          {msg.type === 'success' ? <Check className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
          <span className="font-semibold">{msg.text}</span>
        </div>
      )}

      {/* Account List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {accounts.map((acc) => {
          const isActive = acc.account_id === activeId || acc.is_active;
          return (
            <div
              key={acc.account_id}
              className={`p-4 fk-cut-sm bg-[#050505] border space-y-2.5 ${
                isActive ? 'border-[#C8FF3A]' : 'border-[#272A2F]'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-extrabold text-[#FFFFFF] truncate">{acc.display_name}</span>
                    {isActive && (
                      <span className="px-1.5 py-0.5 text-[10px] font-extrabold bg-[#C8FF3A] text-[#050505]">
                        AKTYWNE
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-[#686E78] font-mono mt-0.5">
                    {acc.handle || acc.account_id} · {acc.content_mode} · {acc.language?.toUpperCase()}
                  </div>
                </div>
                <span
                  className={`flex items-center gap-1 text-[10px] font-bold flex-shrink-0 ${
                    acc.yt_token_exists ? 'text-[#55E88D]' : 'text-[#FFB347]'
                  }`}
                >
                  {acc.yt_token_exists ? <ShieldCheck className="w-3.5 h-3.5" /> : <ShieldOff className="w-3.5 h-3.5" />}
                  {acc.yt_token_exists ? 'Token YT OK' : 'Brak tokenu YT'}
                </span>
              </div>

              <div className="text-[11px] text-[#A0A7B1] space-y-1">
                {acc.value_proposition && <div className="line-clamp-2"><span className="text-[#686E78]">Cel/Nisza:</span> {acc.value_proposition}</div>}
                {acc.brand_voice && <div><span className="text-[#686E78]">Styl:</span> {acc.brand_voice}</div>}
                <div>
                  <span className="text-[#686E78]">Sloty CET:</span> {(acc.peak_hours_cet || []).join(' & ') || '15:00 & 21:30'}
                  {acc.location ? ` · 📍 ${acc.location}` : ''}
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1 flex-wrap">
                {!isActive && (
                  <button
                    type="button"
                    onClick={() => handleSelect(acc.account_id)}
                    className="px-2.5 py-1 bg-[#C8FF3A]/15 border border-[#C8FF3A]/50 text-[#C8FF3A] text-[11px] font-bold hover:bg-[#C8FF3A]/25"
                  >
                    Aktywuj
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => startEditAccount(acc)}
                  className="flex items-center gap-1 px-2.5 py-1 bg-[#0E0F11] border border-[#272A2F] text-[#A0A7B1] text-[11px] font-semibold hover:text-[#FFFFFF]"
                >
                  <Edit3 className="w-3 h-3" /> Wytyczne
                </button>
                {!acc.builtin && (
                  <button
                    type="button"
                    onClick={() => handleDelete(acc)}
                    className="flex items-center gap-1 px-2 py-1 bg-[#FF5C5C]/10 border border-[#FF5C5C]/30 text-[#FF5C5C] text-[11px] font-semibold hover:bg-[#FF5C5C]/20 ml-auto"
                  >
                    <Trash2 className="w-3 h-3" /> Usuń
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {showForm && (
        <AccountForm
          form={form}
          setForm={setForm}
          presets={presets}
          saving={saving}
          onApplyPresetToNew={applyPresetToNewForm}
          onSubmit={handleSaveForm}
          onCancel={() => setShowForm(false)}
        />
      )}
    </div>
  );
}
