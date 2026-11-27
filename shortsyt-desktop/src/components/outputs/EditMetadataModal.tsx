import React, { useEffect, useState } from 'react';
import {
  Edit3, X, AlertTriangle, Upload, Info, Sliders, RefreshCw,
  CheckCircle2, Zap, Loader, RotateCcw, Save,
} from 'lucide-react';
import {
  apiGetOutputMetadata, apiSaveOutputMetadata, apiStartPipeline,
  apiRecordCorrection, OutputMetadata,
} from '../../lib/api';
import { CHAMPIONS, ACTION_TYPES, RENDER_FIELDS } from './socialCopyHelpers';

interface EditMetadataModalProps {
  filename: string | null;
  onClose: () => void;
  onRerenderStarted: () => void;
}

export default function EditMetadataModal({
  filename,
  onClose,
  onRerenderStarted,
}: EditMetadataModalProps) {
  const [editMeta, setEditMeta] = useState<OutputMetadata | null>(null);
  const [editOriginal, setEditOriginal] = useState<OutputMetadata | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editSaved, setEditSaved] = useState(false);
  const [editRerendering, setEditRerendering] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editSection, setEditSection] = useState<'meta' | 'stats' | 'render'>('meta');

  useEffect(() => {
    if (!filename) return;
    let active = true;
    setEditLoading(true);
    setEditError(null);
    setEditSaved(false);
    setEditSection('meta');
    apiGetOutputMetadata(filename)
      .then((meta) => {
        if (!active) return;
        setEditMeta(meta);
        setEditOriginal(JSON.parse(JSON.stringify(meta)));
      })
      .catch((e: any) => {
        if (active) setEditError(String(e));
      })
      .finally(() => {
        if (active) setEditLoading(false);
      });
    return () => { active = false; };
  }, [filename]);

  if (!filename) return null;

  const hasRenderChanges = () => {
    if (!editMeta || !editOriginal) return false;
    return RENDER_FIELDS.some((k) => JSON.stringify(editMeta[k]) !== JSON.stringify(editOriginal[k]));
  };

  const handleSaveMeta = async () => {
    if (!filename || !editMeta) return;
    setEditSaving(true);
    setEditError(null);
    try {
      await apiSaveOutputMetadata(filename, {
        title: editMeta.title,
        description: editMeta.description,
        tags: editMeta.tags,
      });
      if (editOriginal?.title !== editMeta.title) {
        apiRecordCorrection('title', editOriginal?.title ?? '', editMeta.title, 'ui_edit_panel');
      }
      if (editOriginal?.description !== editMeta.description) {
        apiRecordCorrection('description', editOriginal?.description ?? '', editMeta.description, 'ui_edit_panel');
      }
      setEditOriginal((prev) => (prev ? { ...prev, title: editMeta.title, description: editMeta.description, tags: editMeta.tags } : prev));
      setEditSaved(true);
      setTimeout(() => setEditSaved(false), 3000);
    } catch (e: any) {
      setEditError(String(e));
    } finally {
      setEditSaving(false);
    }
  };

  const handleRerender = async () => {
    if (!filename || !editMeta) return;
    setEditRerendering(true);
    setEditError(null);
    try {
      await apiSaveOutputMetadata(filename, editMeta);
      const outFile = `short_${Date.now()}_rerender.mp4`;
      await apiStartPipeline({
        source_path: editMeta.source_path,
        clip_start: editMeta.clip_start,
        clip_end: editMeta.clip_end,
        action_type: editMeta.action_type,
        champion_name: editMeta.champion_name,
        rank: 'Master',
        peak_moment: editMeta.peak_moment,
        hook_text: editMeta.hook_text,
        output_filename: outFile,
        use_speed_ramp: editMeta.use_speed_ramp,
        use_zoom_punch: editMeta.use_zoom_punch,
        use_smart_camera: editMeta.use_smart_camera,
      });
      onRerenderStarted();
    } catch (e: any) {
      setEditError(String(e));
    } finally {
      setEditRerendering(false);
    }
  };

  const sectionTab = (id: 'meta' | 'stats' | 'render', label: string, icon: React.ReactNode) => (
    <button
      onClick={() => setEditSection(id)}
      className={`flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg transition-colors ${editSection === id ? 'bg-[#C8FF3A]/15 text-[#C8FF3A] border border-[#C8FF3A]/40' : 'text-[#A0A7B1] hover:text-[#FFFFFF]'}`}
    >
      {icon}{label}
    </button>
  );

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-[#0E0F11] border border-[#C8FF3A]/40 fk-cut p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto space-y-5 text-[#FFFFFF]">
        <div className="flex items-start justify-between pb-3 border-b border-[#272A2F]">
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-[#C8FF3A] flex items-center gap-1.5">
              <Edit3 className="w-4 h-4" />Edytor Shorta
            </div>
            <div className="text-sm font-bold text-[#FFFFFF] mt-1 truncate max-w-md">{filename}</div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg bg-[#272A2F] hover:bg-[#272A2F] text-[#A0A7B1] hover:text-white transition-colors"><X className="w-4 h-4" /></button>
        </div>

        {/* Re-render warning banner */}
        {hasRenderChanges() && (
          <div className="p-3 fk-cut-sm bg-[#C8FF3A]/10 border border-[#C8FF3A]/30 text-[#C8FF3A] text-xs flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <div><b>Zmieniono parametry renderowania</b> — aby zapisać te zmiany, aplikacja wyrenderuje klip ponownie. Kliknij <b>"Zapisz i Re-Renderuj"</b>.</div>
          </div>
        )}

        {editError && <div className="p-3 fk-cut-sm bg-red-500/10 border border-red-500/30 text-red-400 text-xs">{editError}</div>}

        {/* Section tabs */}
        <div className="flex items-center gap-1 p-1 bg-[#050505] fk-cut-sm border border-[#272A2F]">
          {sectionTab('meta', 'Metadane YouTube', <Upload className="w-3 h-3" />)}
          {sectionTab('stats', 'Statystyki AI', <Info className="w-3 h-3" />)}
          {sectionTab('render', 'Parametry Renderu', <Sliders className="w-3 h-3" />)}
        </div>

        {editLoading ? (
          <div className="py-12 flex flex-col items-center justify-center text-[#A0A7B1]">
            <RefreshCw className="w-6 h-6 animate-spin text-[#C8FF3A] mb-2" /><span className="text-xs">Ładowanie metadanych...</span>
          </div>
        ) : editMeta && (
          <>
            {/* SECTION: META */}
            {editSection === 'meta' && (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[#C8FF3A]">Tytuł YouTube Shorts</label>
                  <input
                    value={editMeta.title}
                    onChange={(e) => setEditMeta((m) => (m ? { ...m, title: e.target.value } : m))}
                    className="w-full bg-[#050505] border border-[#272A2F] focus:border-[#C8FF3A] fk-cut-sm px-3 py-2.5 text-sm text-[#FFFFFF] outline-none"
                    placeholder="Tytuł Shorta..."
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[#C8FF3A]">Opis</label>
                  <textarea
                    value={editMeta.description}
                    onChange={(e) => setEditMeta((m) => (m ? { ...m, description: e.target.value } : m))}
                    rows={5}
                    className="w-full bg-[#050505] border border-[#272A2F] focus:border-[#C8FF3A] fk-cut-sm px-3 py-2 text-xs text-[#FFFFFF] outline-none resize-none"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[#C8FF3A]">Hashtagi (oddzielone przecinkami)</label>
                  <input
                    value={(editMeta.tags || []).join(', ')}
                    onChange={(e) => setEditMeta((m) => (m ? { ...m, tags: e.target.value.split(',').map((t) => t.trim()).filter(Boolean) } : m))}
                    className="w-full bg-[#050505] border border-[#272A2F] focus:border-[#C8FF3A] fk-cut-sm px-3 py-2 text-xs text-[#FFFFFF] outline-none"
                    placeholder="league of legends, shorts, lol, outplay..."
                  />
                </div>
                <p className="text-[11px] text-[#686E78]">ℹ️ Zmiany metadanych nie wymagają ponownego renderowania — zostaną natychmiast zapisane i użyte przy uploadzie na YouTube.</p>
              </div>
            )}

            {/* SECTION: STATS */}
            {editSection === 'stats' && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: 'Wykryty Typ Fraga', val: editMeta.action_type?.toUpperCase() || '—' },
                    { label: 'Confidence AI', val: editMeta.frag_confidence ? `${Math.round(editMeta.frag_confidence * 100)}%` : '—' },
                    { label: 'Start Klipu', val: editMeta.clip_start != null ? `${editMeta.clip_start}s` : '—' },
                    { label: 'Koniec Klipu', val: editMeta.clip_end != null ? `${editMeta.clip_end}s` : '—' },
                    { label: 'Długość', val: (editMeta.clip_end != null && editMeta.clip_start != null) ? `${(editMeta.clip_end - editMeta.clip_start).toFixed(1)}s` : '—' },
                    { label: 'Peak Moment', val: editMeta.peak_moment != null ? `${editMeta.peak_moment}s` : '—' },
                    { label: 'Bohater', val: editMeta.champion_name || '—' },
                    { label: 'Wyrenderowano', val: editMeta.rendered_at ? new Date(editMeta.rendered_at).toLocaleString('pl-PL') : '—' },
                  ].map(({ label, val }) => (
                    <div key={label} className="p-3 fk-cut-sm bg-[#050505] border border-[#272A2F]">
                      <div className="text-[10px] text-[#A0A7B1] uppercase tracking-wider mb-1">{label}</div>
                      <div className="text-sm font-bold text-[#C8FF3A]">{val}</div>
                    </div>
                  ))}
                </div>
                <div className="p-3 fk-cut-sm bg-[#050505] border border-[#272A2F]">
                  <div className="text-[10px] text-[#A0A7B1] uppercase tracking-wider mb-1">Źródłowy Plik</div>
                  <div className="text-xs font-mono text-[#FFFFFF] break-all">{editMeta.source_path || '—'}</div>
                </div>
                <div className="flex items-center gap-3 text-xs text-[#A0A7B1]">
                  <span className="flex items-center gap-1">{editMeta.use_smart_camera ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <X className="w-3.5 h-3.5 text-red-400" />}Smart Camera</span>
                  <span className="flex items-center gap-1">{editMeta.use_speed_ramp ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <X className="w-3.5 h-3.5 text-red-400" />}Speed Ramp</span>
                  <span className="flex items-center gap-1">{editMeta.use_zoom_punch ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <X className="w-3.5 h-3.5 text-red-400" />}Zoom Punch</span>
                </div>
              </div>
            )}

            {/* SECTION: RENDER PARAMS */}
            {editSection === 'render' && (
              <div className="space-y-4">
                <div className="p-3 fk-cut-sm bg-[#C8FF3A]/10 border border-[#C8FF3A]/30 text-[#C8FF3A] text-xs flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  Zmiana poniższych parametrów WYMAGA ponownego wyrenderowania klipu (przycisk "Zapisz i Re-Renderuj").
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Bohater:</label>
                    <select
                      value={editMeta.champion_name}
                      onChange={(e) => setEditMeta((m) => (m ? { ...m, champion_name: e.target.value } : m))}
                      className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]"
                    >
                      {CHAMPIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Typ Akcji:</label>
                    <select
                      value={editMeta.action_type}
                      onChange={(e) => setEditMeta((m) => (m ? { ...m, action_type: e.target.value } : m))}
                      className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#C8FF3A] focus:outline-none focus:border-[#C8FF3A]"
                    >
                      {ACTION_TYPES.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
                    </select>
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-xs font-bold text-[#A0A7B1] block mb-1.5">Hook Text (napis na początku):</label>
                    <input
                      value={editMeta.hook_text}
                      onChange={(e) => setEditMeta((m) => (m ? { ...m, hook_text: e.target.value } : m))}
                      className="w-full px-3 py-2 fk-cut-sm bg-[#050505] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  {[{ l: 'Start (s)', k: 'clip_start' }, { l: 'Koniec (s)', k: 'clip_end' }, { l: 'Peak (s)', k: 'peak_moment' }].map(({ l, k }) => (
                    <div key={k}>
                      <label className="text-[11px] font-bold text-[#A0A7B1] block mb-1">{l}</label>
                      <div className="flex gap-1 mb-1">
                        {[-1, 1].map((d) => (
                          <button
                            key={d}
                            type="button"
                            onClick={() => setEditMeta((m) => (m ? { ...m, [k]: Math.max(0, +((m[k as keyof OutputMetadata] as number) + d).toFixed(1)) } : m))}
                            className="px-1.5 py-0.5 bg-[#0E0F11] hover:bg-[#272A2F] text-[#A0A7B1] rounded border border-[#272A2F] text-[10px]"
                          >
                            {d > 0 ? '+1s' : '-1s'}
                          </button>
                        ))}
                      </div>
                      <input
                        type="number"
                        step="0.5"
                        value={editMeta[k as keyof OutputMetadata] as number}
                        onChange={(e) => setEditMeta((m) => (m ? { ...m, [k]: parseFloat(e.target.value) || 0 } : m))}
                        className="w-full px-3 py-1.5 rounded-lg bg-[#0E0F11] border border-[#272A2F] text-xs font-mono text-[#FFFFFF] focus:outline-none focus:border-[#C8FF3A]"
                      />
                    </div>
                  ))}
                </div>
                <div className="p-4 fk-cut-sm bg-[#050505] border border-[#272A2F] space-y-2.5">
                  <div className="text-xs font-bold text-[#A0A7B1] uppercase tracking-wider mb-2">Moduły Efektów:</div>
                  {[
                    { l: 'Smart Camera (Śledzenie HP)', k: 'use_smart_camera' },
                    { l: 'Slow-Mo Ramp 0.45x + Minterpolate', k: 'use_speed_ramp' },
                    { l: 'Zoom-Punch 1.20x + Bass Boost', k: 'use_zoom_punch' },
                  ].map(({ l, k }) => (
                    <label key={k} className="flex items-center justify-between cursor-pointer text-xs font-semibold">
                      <span className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-[#C8FF3A]" />{l}</span>
                      <input
                        type="checkbox"
                        checked={editMeta[k as keyof OutputMetadata] as boolean}
                        onChange={(e) => setEditMeta((m) => (m ? { ...m, [k]: e.target.checked } : m))}
                        className="rounded border-[#272A2F] bg-[#0E0F11] text-[#C8FF3A]"
                      />
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center justify-between gap-3 pt-3 border-t border-[#272A2F]">
              <button type="button" onClick={onClose} className="px-4 py-2 fk-cut-sm bg-[#272A2F] hover:bg-[#272A2F] text-xs font-bold text-[#A0A7B1] hover:text-[#FFFFFF] transition-colors">Anuluj</button>
              <div className="flex items-center gap-2">
                {editSaved && <span className="text-xs text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" />Zapisano!</span>}
                {hasRenderChanges() ? (
                  <button
                    type="button"
                    disabled={editRerendering}
                    onClick={handleRerender}
                    className="px-5 py-2.5 fk-cut-sm fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] text-xs font-black transition-colors flex items-center gap-2 disabled:opacity-50"
                  >
                    {editRerendering ? <Loader className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                    {editRerendering ? 'Re-renderuję...' : 'Zapisz i Re-Renderuj'}
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={editSaving}
                    onClick={handleSaveMeta}
                    className="px-5 py-2.5 fk-cut-sm bg-[#C8FF3A] hover:bg-[#C8FF3A] text-[#050505] text-xs font-black transition-colors flex items-center gap-2 disabled:opacity-50"
                  >
                    {editSaving ? <Loader className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    {editSaving ? 'Zapisuję...' : 'Zapisz Metadane'}
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
