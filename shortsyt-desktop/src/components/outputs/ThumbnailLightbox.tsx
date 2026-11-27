import React from 'react';
import {
  Image as ImageIcon, X, Upload, Loader, RotateCcw, FolderOpen,
} from 'lucide-react';
import { ThumbLightboxData } from './socialCopyHelpers';

interface ThumbnailLightboxProps {
  thumbLightbox: ThumbLightboxData | null;
  thumbBusyFor: string | null;
  onClose: () => void;
  onTriggerUpload: (videoFilename: string) => void;
  onRegenerate: (videoFilename: string) => void;
  onOpenImage: (path: string) => void;
  onOpenFolder: (path: string) => void;
}

export default function ThumbnailLightbox({
  thumbLightbox,
  thumbBusyFor,
  onClose,
  onTriggerUpload,
  onRegenerate,
  onOpenImage,
  onOpenFolder,
}: ThumbnailLightboxProps) {
  if (!thumbLightbox) return null;
  const busy = thumbBusyFor === thumbLightbox.videoFilename;

  return (
    <div className="fixed inset-0 bg-black/85 z-[60] flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[#0E0F11] border border-[#C8FF3A]/50 fk-cut p-5 w-full max-w-md space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-bold text-[#C8FF3A] truncate flex items-center gap-1.5">
            <ImageIcon className="w-4 h-4 flex-shrink-0" />Podgląd Miniaturki (9:16)
          </span>
          <button onClick={onClose} className="text-[#A0A7B1] hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <div className="text-[10px] font-mono text-[#A0A7B1] truncate">{thumbLightbox.filename}</div>
        <div className="flex justify-center bg-[#050505] rounded-lg border border-[#272A2F] p-2">
          <img src={thumbLightbox.url} alt="Podgląd miniaturki 9:16" className="max-h-[60vh] aspect-[9/16] object-cover rounded" />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onTriggerUpload(thumbLightbox.videoFilename)}
            className="py-2 px-3 fk-cut-sm bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            <Upload className="w-3.5 h-3.5 text-[#C8FF3A]" />Zmień plik
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onRegenerate(thumbLightbox.videoFilename)}
            className="py-2 px-3 fk-cut-sm bg-[#17191C] hover:bg-[#272A2F] border border-[#272A2F] text-xs font-bold text-[#FFFFFF] flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            {busy ? <Loader className="w-3.5 h-3.5 animate-spin text-[#C8FF3A]" /> : <RotateCcw className="w-3.5 h-3.5 text-[#C8FF3A]" />}
            Wygeneruj nową
          </button>
        </div>
        {thumbLightbox.path && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => onOpenImage(thumbLightbox.path!)}
              className="flex-1 py-1.5 px-2.5 rounded-lg bg-[#272A2F] hover:bg-[#32363D] text-[11px] font-semibold text-white flex items-center justify-center gap-1.5"
            >
              <ImageIcon className="w-3.5 h-3.5" />Otwórz w systemie
            </button>
            <button
              type="button"
              onClick={() => onOpenFolder(thumbLightbox.path!)}
              className="flex-1 py-1.5 px-2.5 rounded-lg bg-[#272A2F] hover:bg-[#32363D] text-[11px] font-semibold text-white flex items-center justify-center gap-1.5"
            >
              <FolderOpen className="w-3.5 h-3.5" />Pokaż w folderze
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
