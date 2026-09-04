/**
 * Shortsyt Desktop — API Client
 * Komunikacja z FastAPI backend (lokalnie lub przez sieć)
 * Zapis JWT i URL w electron-store
 */
import axios, { AxiosInstance, AxiosError } from 'axios';

// Storage keys
const SERVER_URL_KEY = 'api_url';
const JWT_TOKEN_KEY = 'jwt_token';

export const DEFAULT_URL = 'http://localhost:8765';

// Electron Store wrapper with localStorage fallback for web dev
interface ElectronStoreBridge {
  get: (key: string, defaultValue?: any) => Promise<any>;
  set: (key: string, value: any) => Promise<boolean>;
  delete: (key: string) => Promise<boolean>;
  clear: () => Promise<boolean>;
}

declare global {
  interface Window {
    electronStore?: ElectronStoreBridge;
    electronApp?: {
      getVersion: () => Promise<string>;
      openExternal: (url: string) => Promise<void>;
      showItemInFolder: (fullPath: string) => Promise<void>;
      openPath: (fullPath: string) => Promise<void>;
      selectDirectory: () => Promise<string | null>;
    };
  }
}

async function getStoreValue(key: string, defaultValue: any = null): Promise<any> {
  if (window.electronStore) {
    try {
      const val = await window.electronStore.get(key, defaultValue);
      return val !== undefined && val !== null ? val : defaultValue;
    } catch {
      return defaultValue;
    }
  }
  const item = localStorage.getItem(key);
  return item !== null ? JSON.parse(item) : defaultValue;
}

async function setStoreValue(key: string, value: any): Promise<void> {
  if (window.electronStore) {
    await window.electronStore.set(key, value);
    return;
  }
  localStorage.setItem(key, JSON.stringify(value));
}

async function deleteStoreValue(key: string): Promise<void> {
  if (window.electronStore) {
    await window.electronStore.delete(key);
    return;
  }
  localStorage.removeItem(key);
}

// ── Storage helpers ──────────────────────────────────────────────────────────

export async function getServerUrl(): Promise<string> {
  const stored = await getStoreValue(SERVER_URL_KEY, DEFAULT_URL);
  return stored || DEFAULT_URL;
}

export async function setServerUrl(url: string): Promise<void> {
  const cleanUrl = url.trim().replace(/\/$/, '');
  await setStoreValue(SERVER_URL_KEY, cleanUrl);
}

export async function getJwtToken(): Promise<string | null> {
  return await getStoreValue(JWT_TOKEN_KEY, null);
}

export async function setJwtToken(token: string): Promise<void> {
  await setStoreValue(JWT_TOKEN_KEY, token);
}

export async function clearJwtToken(): Promise<void> {
  await deleteStoreValue(JWT_TOKEN_KEY);
}

// ── Axios instance factory ───────────────────────────────────────────────────

export async function createClient(): Promise<AxiosInstance> {
  const baseURL = await getServerUrl();
  let token = await getJwtToken();

  // If no token exists, attempt auto-login with default API password
  if (!token) {
    try {
      const res = await axios.post(`${baseURL}/auth/login`, { password: 'shortsyt2026' }, { timeout: 4000 });
      if (res.data?.access_token) {
        token = res.data.access_token;
        if (token) {
          await setJwtToken(token);
        }
      }
    } catch {
      // fallback without token if server unavailable or password changed
    }
  }

  return axios.create({
    baseURL,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

export function parseError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const ae = err as AxiosError<any>;
    return ae.response?.data?.detail || ae.message || 'Błąd połączenia z backendem';
  }
  return String(err);
}

// ── API calls ────────────────────────────────────────────────────────────────

export async function apiLogin(password: string): Promise<string> {
  const url = await getServerUrl();
  const res = await axios.post(`${url}/auth/login`, { password }, { timeout: 10000 });
  const token = res.data.access_token;
  await setJwtToken(token);
  return token;
}

export async function apiCheckAuth(): Promise<boolean> {
  try {
    const client = await createClient();
    await client.get('/auth/me');
    return true;
  } catch {
    return false;
  }
}

export interface PipelineStateResponse {
  status: 'idle' | 'running' | 'done' | 'error';
  progress: number;
  current_step: string;
  output_path: string | null;
  thumbnail_path?: string | null;
  title?: string | null;
  description?: string | null;
  pinned_comment?: string | null;
  champion_name?: string | null;
  action_type?: string | null;
  rank?: string | null;
  source_path?: string | null;
  clip_start?: number | null;
  clip_end?: number | null;
  combat_segments?: Array<[number, number]> | null;
  qa_status?: 'PASS' | 'WARN' | 'FAIL';
  qa_score?: number;
  qa_details?: string[];
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  logs: string[];
}

export async function apiGetStatus(): Promise<PipelineStateResponse> {
  const client = await createClient();
  const res = await client.get('/status');
  return res.data;
}

export async function apiStartPipeline(params: {
  source_path: string;
  clip_start: number;
  clip_end: number;
  action_type: string;
  champion_name: string;
  rank: string;
  peak_moment: number;
  hook_text: string;
  output_filename: string;
  use_speed_ramp: boolean;
  use_zoom_punch: boolean;
  use_smart_camera: boolean;
  expo_push_token?: string;
  combat_segments?: Array<[number, number]> | null;
}): Promise<void> {
  const client = await createClient();
  await client.post('/pipeline/start', params);
}

export async function apiStopPipeline(): Promise<void> {
  const client = await createClient();
  await client.post('/pipeline/stop');
}

export interface ClipItem {
  filename: string;
  path: string;
  size_mb: number;
  modified: number;
}

export interface AutoDetectResult {
  clip_start: number;
  clip_end: number;
  peak_moment: number;
  action_type: string;
  hook_text: string;
  total_duration: number;
  detected_peaks: Array<[number, string]>;
  confidence: string;
  combat_segments?: Array<[number, number]> | null;
  has_jump_cut?: boolean;
}

export async function apiListClips(folder?: string): Promise<ClipItem[]> {
  const client = await createClient();
  const url = folder ? `/clips?folder=${encodeURIComponent(folder)}` : '/clips';
  const res = await client.get(url);
  return res.data.clips || [];
}

export async function apiAutoDetectClip(params: {
  source_path: string;
  action_type?: string;
  champion_name?: string;
}): Promise<AutoDetectResult> {
  const client = await createClient();
  const res = await client.post('/clips/auto-detect', params);
  return res.data;
}

export interface OutputItem {
  filename: string;
  path: string;
  size_mb: number;
  modified: number;
}

export async function apiListOutputs(): Promise<OutputItem[]> {
  const client = await createClient();
  const res = await client.get('/outputs');
  return res.data.outputs || [];
}

export async function apiDeleteOutput(filename: string): Promise<void> {
  const client = await createClient();
  await client.delete(`/outputs/${encodeURIComponent(filename)}`);
}

export async function apiGetOutputUrl(filename: string): Promise<string> {
  const baseURL = await getServerUrl();
  const token = await getJwtToken();
  return `${baseURL}/outputs/${encodeURIComponent(filename)}?token=${token || ''}`;
}

export interface OutputMetadata {
  filename: string;
  title: string;
  description: string;
  tags: string[];
  champion_name: string;
  action_type: string;
  hook_text: string;
  clip_start: number;
  clip_end: number;
  peak_moment: number;
  use_speed_ramp: boolean;
  use_zoom_punch: boolean;
  use_smart_camera: boolean;
  source_path: string;
  rendered_at: string | null;
  frag_confidence: number | null;
}

export async function apiGetOutputMetadata(filename: string): Promise<OutputMetadata> {
  const client = await createClient();
  const res = await client.get(`/outputs/${encodeURIComponent(filename)}/metadata`);
  return res.data;
}

export async function apiSaveOutputMetadata(
  filename: string,
  data: Partial<OutputMetadata>
): Promise<{ status: string; needs_rerender: boolean }> {
  const client = await createClient();
  const res = await client.post(`/outputs/${encodeURIComponent(filename)}/metadata`, data);
  return res.data;
}


export interface ThumbnailItem {
  filename: string;
  path: string;
  size_kb: number;
  modified: number;
  associated_video: string;
}

export async function apiListThumbnails(): Promise<ThumbnailItem[]> {
  const client = await createClient();
  const res = await client.get('/thumbnails');
  return res.data.thumbnails || [];
}

export async function apiGetThumbnailUrl(filename: string): Promise<string> {
  const baseURL = await getServerUrl();
  const token = await getJwtToken();
  return `${baseURL}/thumbnails/${encodeURIComponent(filename)}?token=${token || ''}`;
}

export async function apiGetCameraPreviewUrl(filePath: string, timestamp: number = 0.0, cropX?: number): Promise<string> {
  const baseURL = await getServerUrl();
  const token = await getJwtToken();
  let url = `${baseURL}/camera-preview?file_path=${encodeURIComponent(filePath)}&timestamp=${timestamp}&token=${token || ''}`;
  if (cropX !== undefined) {
    url += `&crop_x=${cropX}`;
  }
  return url;
}

export interface YtTokenStatusResponse {
  has_token: boolean;
  is_valid: boolean;
  can_refresh: boolean;
  expires_at: string | null;
  days_remaining: number | null;
  message: string;
}

export async function apiGetYtTokenStatus(): Promise<YtTokenStatusResponse> {
  const client = await createClient();
  const res = await client.get('/youtube/token-status');
  return res.data;
}

export async function apiGetYtAuthUrl(): Promise<string> {
  const client = await createClient();
  const res = await client.get('/youtube/auth-url');
  return res.data.auth_url;
}

export async function apiExchangeYtCode(code: string): Promise<any> {
  const client = await createClient();
  const res = await client.post('/youtube/auth-code', { code });
  return res.data;
}

export interface PeakSlotInfo {
  publish_at: string;
  label: string;
  local_time: string;
  peak_slots: string[];
}

export async function apiGetNextPeakSlot(): Promise<PeakSlotInfo> {
  const client = await createClient();
  const res = await client.get('/youtube/next-peak-slot');
  return res.data;
}

export async function apiUploadToYt(
  filename: string,
  title: string,
  description: string,
  tags: string[],
  privacy: string = 'public',
  pinned_comment?: string,
  thumbnail_path?: string,
  publish_at?: string
): Promise<any> {
  // YouTube upload takes 1-5 minutes for a typical Short (~20MB).
  // Use a dedicated client with a 10-minute timeout to avoid premature failure.
  const baseURL = await getServerUrl();
  const token = await getJwtToken();
  const uploadClient = axios.create({
    baseURL,
    timeout: 600000, // 10 minutes – enough for any Short file size
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  const res = await uploadClient.post(`/youtube/upload/${encodeURIComponent(filename)}`, {
    filename,
    title,
    description,
    tags,
    privacy,
    pinned_comment,
    thumbnail_path,
    publish_at,
  });
  return res.data;
}

export async function apiGetAnalytics(range: string = '30d', refresh: boolean = false): Promise<any> {
  const client = await createClient();
  const res = await client.get(`/analytics?range=${range}${refresh ? '&refresh=true' : ''}`);
  return res.data;
}

export async function apiGetTuningConfig(): Promise<any> {
  const client = await createClient();
  const res = await client.get('/config/tuning');
  return res.data;
}

export async function apiSaveTuningConfig(config: any): Promise<any> {
  const client = await createClient();
  const res = await client.post('/config/tuning', config);
  return res.data;
}

export async function apiHealthCheck(url?: string): Promise<{ ok: boolean; status?: string; service?: string }> {
  try {
    const targetUrl = url ? url.trim().replace(/\/$/, '') : await getServerUrl();
    const res = await axios.get(`${targetUrl}/health`, { timeout: 4000 });
    return {
      ok: res.data?.status === 'ok',
      status: res.data?.status,
      service: res.data?.service,
    };
  } catch {
    return { ok: false };
  }
}

// ── Dark Psychology Agent API ─────────────────────────────────────────────────

export async function apiGetDarkStatus(): Promise<any> {
  const client = await createClient();
  const res = await client.get('/dark/status');
  return res.data;
}

export async function apiGetDarkAnalytics(): Promise<any> {
  const client = await createClient();
  const res = await client.get('/dark/analytics');
  return res.data;
}

export async function apiGetDarkCalibration(): Promise<any> {
  const client = await createClient();
  const res = await client.get('/dark/calibration');
  return res.data;
}

export async function apiGetDarkDirective(): Promise<any> {
  const client = await createClient();
  const res = await client.get('/dark/directive');
  return res.data;
}

export async function apiRunDarkAgent(params: { dry_run?: boolean; videos?: number }): Promise<any> {
  const client = await createClient();
  const res = await client.post('/dark/run', { dry_run: params.dry_run ?? false, videos: params.videos ?? 2 });
  return res.data;
}

export async function apiRecalibrateDark(): Promise<any> {
  const client = await createClient();
  const res = await client.post('/dark/recalibrate');
  return res.data;
}

// ── Calendar & Pipeline Slot Reservation API ─────────────────────────────────

export interface CalendarSlot {
  slot_id: string;
  date: string;
  time: string;
  datetime_local: string;
  datetime_utc: string;
  is_peak: boolean;
  is_past: boolean;
  status: 'free' | 'reserved' | 'rendering' | 'ready' | 'scheduled' | 'published' | 'past';
  title?: string;
  champion?: string;
  frag_type?: string;
  source_clip?: string;
  output_video?: string;
  thumbnail_url?: string;
  yt_video_id?: string;
  yt_url?: string;
  notes?: string;
  created_at?: string;
}

export interface FragAnalysis {
  video_path: string;
  duration: number;
  detected_frag_type: 'pentakill' | 'quadrakill' | 'triple' | 'double' | 'clutch' | 'outplay';
  confidence: number;
  kill_count: number;
  kills: Array<{ timestamp: number; label: string; tier: number }>;
  min_hp_percentage: number;
  is_clutch_1hp: boolean;
  badge_label: string;
  suggested_title_hook: string;
  suggested_badge_color: string;
}

export async function apiGetCalendarSlots(startDate?: string, days: number = 14): Promise<{ slots: CalendarSlot[]; days: number; total: number }> {
  const client = await createClient();
  const params: any = { days };
  if (startDate) params.start_date = startDate;
  const res = await client.get('/calendar/slots', { params });
  return res.data;
}

export async function apiReserveCalendarSlot(data: {
  slot_id: string;
  title?: string;
  champion?: string;
  frag_type?: string;
  source_clip?: string;
  output_video?: string;
  notes?: string;
}): Promise<any> {
  const client = await createClient();
  const res = await client.post('/calendar/reserve', data);
  return res.data;
}

export async function apiDeleteCalendarSlot(slotId: string): Promise<any> {
  const client = await createClient();
  const res = await client.delete(`/calendar/slot/${encodeURIComponent(slotId)}`);
  return res.data;
}

export async function apiPublishCalendarSlot(slotId: string): Promise<any> {
  const client = await createClient();
  const res = await client.post(`/calendar/slot/${encodeURIComponent(slotId)}/publish`);
  return res.data;
}

export async function apiAutoFillCalendar(maxSlots: number = 4): Promise<any> {
  const client = await createClient();
  const res = await client.post('/calendar/auto-fill', { max_slots: maxSlots });
  return res.data;
}

export async function apiAnalyzeFrag(clipPath: string): Promise<FragAnalysis> {
  const client = await createClient();
  const res = await client.post('/clips/analyze-frag', { clip_path: clipPath });
  return res.data;
}

// ── Hardware Benchmark & Auto-Tuning API ─────────────────────────────────────

export interface HardwareProfile {
  scanned_at: string;
  tier: 'high' | 'medium' | 'low';
  tier_label: string;
  tier_description: string;
  hardware: {
    cpu_name: string;
    cpu_cores: number;
    ram_total_gb: number;
    ram_available_gb: number;
    gpu_name: string;
    gpu_vendor: string;
    vram_gb: number;
    detected_encoder: string;
    os_version: string;
  };
  tuned_settings: {
    encoder: string;
    encoder_args: string[];
    render_fps: number;
    render_threads: number;
    ocr_sample_fps: number;
    max_ocr_workers: number;
    enable_heavy_filters: boolean;
  };
}

export async function apiGetHardwareInfo(): Promise<HardwareProfile> {
  const client = await createClient();
  const res = await client.get('/system/hardware-info');
  return res.data;
}

export async function apiRunBenchmarkScan(): Promise<{ status: string; profile: HardwareProfile }> {
  const client = await createClient();
  const res = await client.post('/system/benchmark-scan');
  return res.data;
}


