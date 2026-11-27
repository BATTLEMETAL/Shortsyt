import { OutputMetadata } from '../../lib/api';

export const CHAMPIONS = [
  'Katarina', 'Ahri', 'Zed', 'Yasuo', 'Jinx', 'Thresh', 'Lee Sin', 'Vayne',
  'Samira', 'Akali', 'Yone', 'Riven', 'Kassadin', 'Evelynn', 'Master Yi', 'Darius',
];

export const ACTION_TYPES = [
  { id: 'pentakill', label: 'PENTAKILL 🔥' },
  { id: 'quadrakill', label: 'QUADRAKILL ⚡' },
  { id: 'triple', label: 'TRIPLE KILL 🎯' },
  { id: 'double', label: 'DOUBLE KILL ⚔️' },
  { id: 'solo_bolo', label: 'SOLO BOLO 👑' },
  { id: 'outplay', label: 'OUTPLAY 🧠' },
  { id: 'clutch', label: 'CLUTCH 1% HP 💀' },
];

// Which fields require re-render when changed
export const RENDER_FIELDS: (keyof OutputMetadata)[] = [
  'champion_name', 'action_type', 'hook_text', 'clip_start', 'clip_end',
  'peak_moment', 'use_speed_ramp', 'use_zoom_punch', 'use_smart_camera',
];

export interface ThumbLightboxData {
  url: string;
  path?: string | null;
  filename: string;
  videoFilename: string;
}

export function basenameOf(p?: string | null): string | null {
  if (!p) return null;
  const parts = p.split(/[\\/]/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : null;
}

export function buildLocalTiktokCopy(rawTitle: string, champion?: string, _actionType?: string): string {
  const clean = (rawTitle || '').replace(/#\S+/g, '').replace(/\s{2,}/g, ' ').trim();
  const champTag = (champion || 'katarina').replace(/['\s]/g, '').toLowerCase();
  return `${clean}\n#outplayed #pcgaming #leagueoflegends #lolhighlights #${champTag}`.trim();
}

export function buildLocalIgCopy(rawTitle: string, champion?: string): string {
  const clean = (rawTitle || '').replace(/#\S+/g, '').replace(/\s{2,}/g, ' ').trim();
  const champTag = (champion || 'katarina').replace(/['\s]/g, '').toLowerCase();
  return `${clean}\n#leagueoflegends #${champTag} #${champTag}mains #loloutplay #reels`.trim();
}

export function buildLocalFbCopy(rawTitle: string, champion?: string): string {
  const clean = (rawTitle || '').replace(/#\S+/g, '').replace(/\s{2,}/g, ' ').trim();
  const champTag = (champion || 'katarina').replace(/['\s]/g, '').toLowerCase();
  return `${clean} — clean play! #LeagueOfLegends #${champTag} #LoL`.trim();
}
