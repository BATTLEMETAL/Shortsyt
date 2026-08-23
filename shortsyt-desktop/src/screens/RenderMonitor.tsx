import React, { useEffect, useState, useRef } from 'react';
import { apiGetStatus, apiStopPipeline, PipelineStateResponse } from '../lib/api';
import StatusBadge, { PipelineStatusType } from '../components/StatusBadge';
import { Cpu, Square, Terminal, RefreshCw, Layers } from 'lucide-react';

export default function RenderMonitor() {
  const [pipelineState, setPipelineState] = useState<PipelineStateResponse>({
    status: 'idle',
    progress: 0,
    current_step: '',
    output_path: null,
    error: null,
    started_at: null,
    finished_at: null,
    logs: [],
  });
  const [isStopping, setIsStopping] = useState(false);
  const logsContainerRef = useRef<HTMLDivElement>(null);

  const fetchStatus = async () => {
    try {
      const st = await apiGetStatus();
      setPipelineState(st);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1500);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [pipelineState.logs]);

  const handleStop = async () => {
    setIsStopping(true);
    try {
      await apiStopPipeline();
      await fetchStatus();
    } finally {
      setIsStopping(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2438]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
            <Cpu className="w-6 h-6 text-[#C89B3C]" />
            <span>Render Monitor (Live)</span>
            <StatusBadge status={pipelineState.status as PipelineStatusType} />
          </h1>
          <p className="text-xs text-[#8B8FA8] mt-1 font-medium">
            Śledzenie procesu renderowania FFmpeg i analizy OCR w czasie rzeczywistym
          </p>
        </div>

        {pipelineState.status === 'running' && (
          <button
            onClick={handleStop}
            disabled={isStopping}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#E84040]/20 hover:bg-[#E84040]/30 border border-[#E84040]/40 text-xs font-bold text-[#FF6060] transition-colors"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            <span>{isStopping ? 'Zatrzymywanie...' : 'Stop Pipeline'}</span>
          </button>
        )}
      </div>

      {/* Progress Section */}
      <div className="p-6 rounded-2xl bg-[#121624] border border-[#1E2438] space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#C89B3C]" />
            <span className="text-xs font-bold uppercase tracking-wider text-[#8B8FA8]">
              Aktualny krok: {pipelineState.current_step || 'Brak aktywnego zadania'}
            </span>
          </div>
          <span className="text-xl font-black text-[#C89B3C]">{pipelineState.progress}%</span>
        </div>

        <div className="w-full bg-[#0A0E1A] h-3 rounded-full overflow-hidden border border-[#1E2438]">
          <div
            className="bg-gradient-to-r from-[#2A7FD4] via-[#C89B3C] to-[#2ECC71] h-full transition-all duration-500 rounded-full"
            style={{ width: `${Math.max(pipelineState.progress, 0)}%` }}
          />
        </div>
      </div>

      {/* Finished Result Quick Preview */}
      {pipelineState.status === 'done' && pipelineState.output_path && (
        <div className="p-5 rounded-2xl bg-[#121624] border border-[#2ECC71]/40 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-[#2ECC71]/20 border border-[#2ECC71]/40 flex items-center justify-center text-[#2ECC71]">
              <Layers className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#E4D6B5]">Render zakończony sukcesem!</h3>
              <p className="text-xs text-[#8B8FA8] mt-0.5 truncate max-w-md" title={pipelineState.output_path}>
                Plik: {pipelineState.output_path.split('\\').pop() || pipelineState.output_path}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (pipelineState.output_path && window.electronApp?.showItemInFolder) {
                  window.electronApp.showItemInFolder(pipelineState.output_path);
                }
              }}
              className="px-3.5 py-2 rounded-xl bg-[#1E2438] hover:bg-[#2A2D40] text-xs font-bold text-[#E4D6B5] transition-colors"
            >
              Pokaż w folderze
            </button>
            <button
              onClick={() => {
                if (pipelineState.output_path) {
                  const thumbPath = pipelineState.output_path.replace('.mp4', '_thumb.jpg');
                  navigator.clipboard.writeText(thumbPath);
                  alert('Skopiowano ścieżkę miniaturki do schowka!');
                }
              }}
              className="px-3.5 py-2 rounded-xl bg-[#C89B3C] hover:bg-[#E5C269] text-xs font-bold text-[#0A0E1A] transition-colors"
            >
              Kopiuj ścieżkę miniaturki
            </button>
          </div>
        </div>
      )}

      {/* Full Live Logs */}
      <div className="flex-1 min-h-[400px] flex flex-col rounded-2xl bg-[#070A12] border border-[#1E2438] overflow-hidden shadow-2xl">
        <div className="px-4 py-3 bg-[#121624] border-b border-[#1E2438] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#E4D6B5]">
            <Terminal className="w-4 h-4 text-[#C89B3C]" />
            <span>Pełny strumień logów</span>
          </div>
        </div>

        <div
          ref={logsContainerRef}
          className="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-1 bg-[#070A12] text-[#8B8FA8]"
        >
          {pipelineState.logs && pipelineState.logs.length > 0 ? (
            pipelineState.logs.map((log, index) => (
              <div key={index} className="flex items-start gap-2">
                <span className="text-[#50546A] select-none text-[10px]">{String(index + 1).padStart(3, '0')}</span>
                <span className="break-all whitespace-pre-wrap">{log}</span>
              </div>
            ))
          ) : (
            <div className="h-full flex items-center justify-center text-[#50546A] py-16">
              Brak logów aktywnych.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
