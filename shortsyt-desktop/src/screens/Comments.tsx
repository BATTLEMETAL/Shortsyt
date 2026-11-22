import React, { useCallback, useEffect, useState } from 'react';
import { MessageSquare, RefreshCw, Send, AlertCircle, Check } from 'lucide-react';
import { apiGetCommentSuggestions, apiReplyToComment, CommentReplySuggestion } from '../lib/api';

export default function Comments() {
  const [items, setItems] = useState<CommentReplySuggestion[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [sent, setSent] = useState<Record<string, boolean>>({});
  const [sending, setSending] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiGetCommentSuggestions(5);
      if (data.error) setError(data.error);
      setItems(data.items || []);
      const initial: Record<string, string> = {};
      (data.items || []).forEach((it) => { initial[it.parent_comment_id] = it.suggested_replies[0] || ''; });
      setDrafts(initial);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Nie udało się pobrać komentarzy.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const send = async (it: CommentReplySuggestion) => {
    const text = (drafts[it.parent_comment_id] || '').trim();
    if (!text) return;
    setSending(it.parent_comment_id);
    try {
      await apiReplyToComment(it.parent_comment_id, text);
      setSent((s) => ({ ...s, [it.parent_comment_id]: true }));
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Błąd wysyłki odpowiedzi.');
    } finally {
      setSending('');
    }
  };

  return (
    <div className="max-w-4xl space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5 text-lg font-bold text-[#FFFFFF]">
          <MessageSquare className="w-5 h-5 text-[#C8FF3A]" />
          <span>Komentarze — Sugestie Odpowiedzi</span>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1 px-3 py-1.5 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#A0A7B1] hover:text-[#FFFFFF] disabled:opacity-40"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Odśwież
        </button>
      </div>
      <p className="text-xs text-[#A0A7B1]">
        Odpowiedź wysyłasz sam jednym kliknięciem — nic nie jest publikowane automatycznie. Możesz edytować treść przed wysyłką.
      </p>

      {error && (
        <div className="p-3 bg-[#FF5C5C]/10 border border-[#FF5C5C]/30 text-xs text-[#FF5C5C] flex items-start gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" /> <span>{error}</span>
        </div>
      )}

      {!loading && items.length === 0 && !error && (
        <div className="p-4 bg-[#0E0F11] border border-[#272A2F] text-xs text-[#A0A7B1]">
          Brak nieodpowiedzianych komentarzy na ostatnich filmach.
        </div>
      )}

      {items.map((it) => (
        <div key={it.parent_comment_id} className="p-4 bg-[#0E0F11] border border-[#272A2F] space-y-3">
          <div className="text-[11px] text-[#686E78] truncate">{it.video_title}</div>
          <div className="text-sm text-[#FFFFFF]">
            <span className="font-bold text-[#C8FF3A]">{it.author}:</span> {it.comment_text}
          </div>
          <div className="flex gap-2 flex-wrap">
            {it.suggested_replies.map((r, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setDrafts((d) => ({ ...d, [it.parent_comment_id]: r }))}
                className="px-2.5 py-1 text-[11px] bg-[#050505] border border-[#272A2F] text-[#A0A7B1] hover:text-[#FFFFFF] text-left"
              >
                {r}
              </button>
            ))}
          </div>
          <textarea
            value={drafts[it.parent_comment_id] || ''}
            onChange={(e) => setDrafts((d) => ({ ...d, [it.parent_comment_id]: e.target.value }))}
            rows={2}
            className="w-full px-3 py-2 bg-[#050505] border border-[#272A2F] text-xs text-[#FFFFFF]"
          />
          <div className="flex justify-end">
            {sent[it.parent_comment_id] ? (
              <span className="flex items-center gap-1 text-xs font-bold text-[#55E88D]"><Check className="w-3.5 h-3.5" /> Wysłano</span>
            ) : (
              <button
                type="button"
                onClick={() => send(it)}
                disabled={sending === it.parent_comment_id}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[#C8FF3A] text-[#050505] text-xs font-extrabold disabled:opacity-50"
              >
                <Send className="w-3.5 h-3.5" /> {sending === it.parent_comment_id ? 'Wysyłanie...' : 'Wyślij odpowiedź'}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
