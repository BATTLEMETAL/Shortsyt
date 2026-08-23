import React, { useEffect, useState } from 'react';
import { apiListOutputs, OutputItem, apiGetOutputUrl, apiListThumbnails, ThumbnailItem, apiGetThumbnailUrl } from '../lib/api';
import { Video, RefreshCw, Upload, Play, Film, FolderOpen, Image as ImageIcon, Copy, Check } from 'lucide-react';

export default function Outputs() {
  const [outputs, setOutputs] = useState<OutputItem[]>([]);
  const [thumbnails, setThumbnails] = useState<ThumbnailItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedVideoUrl, setSelectedVideoUrl] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const fetchOutputs = async () => {
    setLoading(true);
    try {
      const [outData, thumbData] = await Promise.all([
        apiListOutputs(),
        apiListThumbnails(),
      ]);
      setOutputs(outData);
      setThumbnails(thumbData);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOutputs();
  }, []);

  const handlePlay = async (filename: string) => {
    const url = await apiGetOutputUrl(filename);
    setSelectedVideoUrl(url);
  };

  const findMatchingThumb = (videoFilename: string) => {
    const base = videoFilename.replace('.mp4', '').toLowerCase();
    return thumbnails.find(t => t.filename.toLowerCase().includes(base) || t.associated_video.toLowerCase() === videoFilename.toLowerCase());
  };

  const handleOpenFolder = (fullPath: string) => {
    if (window.electronApp?.showItemInFolder) {
      window.electronApp.showItemInFolder(fullPath);
    }
  };

  const handleOpenImage = (fullPath: string) => {
    if (window.electronApp?.openPath) {
      window.electronApp.openPath(fullPath);
    }
  };

  const handleCopyPath = (pathStr: string) => {
    navigator.clipboard.writeText(pathStr);
    setCopiedPath(pathStr);
    setTimeout(() => setCopiedPath(null), 2000);
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-[#0A0E1A] p-6 lg:p-8 space-y-6 text-[#E4D6B5]">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2438]">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-[#E4D6B5] flex items-center gap-2.5">
            <Video className="w-6 h-6 text-[#C89B3C]" />
            <span>Biblioteka Gotowych Shortów & Miniaturki</span>
          </h1>
          <p className="text-xs text-[#8B8FA8] mt-1 font-medium">
            Wyrenderowane wideo 9:16 i wygenerowane miniaturki YouTube Shorts
          </p>
        </div>

        <button
          onClick={fetchOutputs}
          disabled={loading}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#121624] hover:bg-[#1A1E30] border border-[#1E2438] text-xs font-semibold text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#C89B3C]' : ''}`} />
          <span>Odśwież listę</span>
        </button>
      </div>

      {/* Video preview modal if open */}
      {selectedVideoUrl && (
        <div className="p-4 rounded-2xl bg-[#121624] border border-[#C89B3C]/40 flex flex-col items-center">
          <div className="w-full flex justify-between items-center mb-3">
            <span className="text-xs font-bold text-[#E4D6B5]">Odtwarzacz Short (9:16)</span>
            <button
              onClick={() => setSelectedVideoUrl(null)}
              className="text-xs text-[#8B8FA8] hover:text-[#E4D6B5] px-2 py-1 bg-[#1E2438] rounded-md"
            >
              Zamknij podgląd
            </button>
          </div>
          <video
            src={selectedVideoUrl}
            controls
            autoPlay
            className="h-[480px] rounded-xl border border-[#1E2438] shadow-2xl bg-black"
          />
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center text-[#8B8FA8] py-16">
          <RefreshCw className="w-8 h-8 animate-spin text-[#C89B3C] mb-2" />
          <p className="text-xs">Ładowanie biblioteki...</p>
        </div>
      ) : outputs.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {outputs.map((out) => {
            const thumb = findMatchingThumb(out.filename);
            return (
              <div
                key={out.filename}
                className="p-4 rounded-xl bg-[#121624] border border-[#1E2438] hover:border-[#C89B3C]/40 transition-all flex flex-col justify-between space-y-4"
              >
                <div className="flex gap-3">
                  {/* 9:16 Thumbnail box */}
                  <div className="w-20 h-32 rounded-lg bg-[#070A12] border border-[#1E2438] overflow-hidden flex-shrink-0 relative group">
                    {thumb ? (
                      <>
                        <img
                          src={`http://localhost:8765/thumbnails/${encodeURIComponent(thumb.filename)}`}
                          alt="Thumbnail 9:16"
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform cursor-pointer"
                          onClick={() => handleOpenImage(thumb.path)}
                          title="Kliknij, aby otworzyć miniaturkę w pełnym rozmiarze"
                        />
                        <button
                          onClick={() => handleOpenImage(thumb.path)}
                          className="absolute bottom-1 right-1 p-1 rounded bg-black/70 hover:bg-[#C89B3C] text-white hover:text-black transition-colors"
                          title="Otwórz plik miniaturki"
                        >
                          <ImageIcon className="w-3 h-3" />
                        </button>
                      </>
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center text-[#50546A] p-1 text-center">
                        <ImageIcon className="w-4 h-4 mb-1 opacity-50" />
                        <span className="text-[9px] leading-tight">Brak miniaturki</span>
                      </div>
                    )}
                  </div>

                  <div className="flex-1 min-w-0 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-bold text-[#E4D6B5] truncate" title={out.filename}>
                        <Film className="w-3.5 h-3.5 text-[#2ECC71] flex-shrink-0" />
                        <span className="truncate">{out.filename}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-[11px] text-[#8B8FA8]">
                        <span>{out.size_mb} MB</span>
                        <span>•</span>
                        <span>{new Date(out.modified * 1000).toLocaleDateString()}</span>
                      </div>
                    </div>

                    {thumb && (
                      <div className="flex items-center gap-1.5 pt-2">
                        <button
                          onClick={() => handleCopyPath(thumb.path)}
                          className="flex items-center gap-1 px-2 py-1 rounded bg-[#1A1E30] hover:bg-[#252A40] text-[10px] text-[#C89B3C] font-semibold transition-colors"
                          title="Kopiuj pełną ścieżkę miniaturki do szybkiego wgrania na YT Studio"
                        >
                          {copiedPath === thumb.path ? <Check className="w-3 h-3 text-[#2ECC71]" /> : <Copy className="w-3 h-3" />}
                          <span>{copiedPath === thumb.path ? 'Skopiowano!' : 'Kopiuj ścieżkę'}</span>
                        </button>
                        <button
                          onClick={() => handleOpenFolder(thumb.path)}
                          className="p-1 rounded bg-[#1A1E30] hover:bg-[#252A40] text-[#8B8FA8] hover:text-[#E4D6B5] transition-colors"
                          title="Pokaż w folderze Windows"
                        >
                          <FolderOpen className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="pt-3 border-t border-white/5 flex items-center justify-between gap-2">
                  <button
                    onClick={() => handlePlay(out.filename)}
                    className="text-xs bg-[#1E2438] hover:bg-[#2A2D40] text-[#E4D6B5] font-semibold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Wideo</span>
                  </button>

                  <button className="text-xs bg-[#C89B3C] hover:bg-[#E5C269] text-[#0A0E1A] font-bold px-3.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 shadow-md shadow-[#C89B3C]/10">
                    <Upload className="w-3.5 h-3.5" />
                    <span>YouTube</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-[#50546A] py-16">
          <Video className="w-10 h-10 mb-2 opacity-40" />
          <p className="text-sm font-semibold">Brak wyrenderowanych filmów</p>
          <p className="text-xs mt-1 opacity-70">Uruchom pipeline renderowania, aby stworzyć pierwsze Shorts.</p>
        </div>
      )}
    </div>
  );
}
