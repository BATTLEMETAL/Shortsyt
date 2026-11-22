/**
 * Shortsyt Desktop — API Client
 * Komunikacja z FastAPI backend (lokalnie lub przez sieć)
 * Zapis JWT i URL w electron-store
 */
import axios, { AxiosInstance, AxiosError } from 'axios';

// Storage keys
const SERVER_URL_KEY = 'api_url';
const JWT_TOKEN_KEY = 'jwt_token';

function getDefaultServerUrl(): string {
  if (
    typeof window !== 'undefined' &&
    !(window as any).electronStore &&
    window.location?.protocol?.startsWith('http') &&
    window.location.port !== '5173'
  ) {
    return window.location.origin;
  }
  return 'http://localhost:8765';
}

export const DEFAULT_URL = getDefaultServerUrl();

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

async function getStoreValue<T = any>(key: string, defaultValue: T = null as any): Promise<T> {
  if (window.electronStore) {
    try {
      const val = await window.electronStore.get(key, defaultValue);
      return val !== undefined && val !== null ? (val as T) : defaultValue;
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
  if (
    typeof window !== 'undefined' &&
    !(window as any).electronStore &&
    window.location?.protocol?.startsWith('http') &&
    window.location.port !== '5173'
  ) {
    return window.location.origin;
  }
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
  await deleteStoreValue('api_password');
}

// ── Axios instance factory ───────────────────────────────────────────────────

export async function createClient(): Promise<AxiosInstance> {
  const baseURL = await getServerUrl();
  let token = await getJwtToken();

  // If no token exists, attempt auto-login with stored or default API password
  if (!token) {
    try {
      const storedPwd = await getStoreValue<string>('api_password');
      const password = storedPwd || 'shortsyt2026';
      const res = await axios.post(`${baseURL}/auth/login`, { password }, { timeout: 4000 });
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

  const instance = axios.create({
    baseURL,
    timeout: 60000,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  instance.interceptors.response.use(
    (response) => response,
    async (error) => {
      const originalRequest = error.config;
      if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
        originalRequest._retry = true;
        try {
          const storedPwd = await getStoreValue<string>('api_password');
          const password = storedPwd || 'shortsyt2026';
          const res = await axios.post(`${baseURL}/auth/login`, { password }, { timeout: 4000 });
          if (res.data?.access_token) {
            const newToken = res.data.access_token;
            await setJwtToken(newToken);
            originalRequest.headers = originalRequest.headers || {};
            originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
            return axios(originalRequest);
          }
        } catch {
          await clearJwtToken();
        }
      }
      return Promise.reject(error);
    }
  );

  return instance;
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
  await setStoreValue('api_password', password);
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
  title_variant_b?: string | null;
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
  queue_length?: number;
  queue?: Array<{ output_filename?: string; champion_name?: string; action_type?: string }>;
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
  game_type?: string;
}): Promise<void> {
  const client = await createClient();
  await client.post('/pipeline/start', params);
}


export async function apiStopPipeline(): Promise<void> {
  const client = await createClient();
  await client.post('/pipeline/stop');
}

export interface ClipItem {
  already_published?: boolean;
  published_url?: string;
  duplicate_reason?: string;
  pre_score?: number | null;
  pre_action?: string | null;
  pre_recommendation?: string | null;
  match_folder?: string;
  match_date?: string;
  clip_base_key?: string;
  champion?: string;
  is_favorite?: boolean;
  event_tier?: string;
  event_tier_rank?: number | null;
  event_source?: string;
  best_event_time_s?: number | null;
  total_kills_in_clip?: number | null;
  match_kda?: string;
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
  hashtags?: string[];
  pinned_comment?: string;
  rank?: string;
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

export async function apiGetBackendBaseUrl(): Promise<string> {
  return await getServerUrl();
}

export interface ThumbnailActionResponse {
  status: string;
  thumbnail_filename: string;
  thumbnail_path: string;
  size_kb: number;
}

export async function apiUploadOutputThumbnail(videoFilename: string, file: File): Promise<ThumbnailActionResponse> {
  const client = await createClient();
  const form = new FormData();
  form.append('file', file);
  const res = await client.post(
    `/outputs/${encodeURIComponent(videoFilename)}/thumbnail`,
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    },
  );
  return res.data;
}

export async function apiRegenerateOutputThumbnail(videoFilename: string): Promise<ThumbnailActionResponse> {
  const client = await createClient();
  const res = await client.post(
    `/outputs/${encodeURIComponent(videoFilename)}/thumbnail/regenerate`,
    {},
    { timeout: 60000 },
  );
  return res.data;
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

export async function apiFlushPendingComments(): Promise<{ sent: any[]; still_pending: any[] }> {
  const client = await createClient();
  const res = await client.post('/youtube/flush-comments');
  return res.data;
}

export async function apiPostComment(videoId: string, text: string): Promise<{ video_id: string; comment_id: string | null; ok: boolean }> {
  const client = await createClient();
  const res = await client.post(`/youtube/video/${encodeURIComponent(videoId)}/comment`, { text });
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
  views?: number;
  likes?: number;
  comments?: number;
  duration_s?: number;
  engagement_rate?: number;
  performance_score?: string;
  performance_ratio?: number;
  performance_tier?: 'viral_hit' | 'above_avg' | 'average' | 'below_avg';
  performance_label?: string;
  performance_diff?: string;
  social_queue?: SlotSocialQueueEntry[];
}

export interface SlotSocialQueueEntry {
  id: string;
  platform: 'tiktok' | 'instagram' | 'facebook' | string;
  status: 'pending' | 'published' | 'failed' | string;
  publish_at: string;
  caption?: string;
  hashtags?: string[];
  url?: string;
  publish_id?: string;
  error?: string;
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

export async function apiGetCalendarSlots(startDate?: string, days: number = 14, forceRefresh: boolean = false): Promise<{ slots: CalendarSlot[]; days: number; total: number; social_queue_summary?: { total: number; pending: number; published: number; failed: number } }> {
  const client = await createClient();
  const params: any = { days };
  if (startDate) params.start_date = startDate;
  if (forceRefresh) params.force_refresh = true;
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
  const res = await client.post('/calendar/auto-fill', { max_slots: maxSlots }, { timeout: 120000 });
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

// ── Autonomous Learning Engine API ──────────────────────────────────────────

export interface LearningDirective {
  timestamp: string;
  total_videos_analyzed: number;
  channel_avg_views: number;
  channel_avg_engagement_rate?: number;
  top_action_type: string;
  action_weights: Record<string, number>;
  action_stats: Record<string, { count: number; avg_views: number; performance_ratio: number; weight: number }>;
  duration_analysis?: {
    best_bucket: string;
    viral_avg_duration_s: number;
    viral_count: number;
  };
  top_title_structure?: string;
  winning_keywords: string[];
  avoid_keywords: string[];
  top_viral_titles?: string[];
  recommended_pacing: string;
  evaluator_config?: {
    base_kill_weights: Record<string, number>;
    demoted_formats: string[];
    demoted_penalty_points: number;
    s_tier_min: number;
    a_tier_min: number;
    b_tier_min: number;
  };
  retention_analysis?: {
    channel_avg_swiped_away_pct: number;
    channel_avg_hook_retention_pct: number;
    channel_avg_view_pct: number;
    total_curves_analyzed: number;
    insights?: string[];
  };
  insights: string[];
}

export async function apiGetLearningStatus(): Promise<{ ok: boolean; directive: LearningDirective }> {
  const client = await createClient();
  const res = await client.get('/learning/status');
  return res.data;
}

export async function apiRecalibrateLearning(): Promise<{ ok: boolean; result: any }> {
  const client = await createClient();
  const res = await client.post('/learning/recalibrate');
  return res.data;
}

export async function apiRecordCorrection(
  param_name: string,
  old_value: string,
  new_value: string,
  source = 'ui_manual',
  reason = ''
): Promise<{ ok: boolean }> {
  try {
    const client = await createClient();
    const res = await client.post('/learning/correction', { param_name, old_value, new_value, source, reason });
    return res.data;
  } catch {
    // Fire-and-forget — nie przerywaj UX jeśli endpoint niedostępny
    return { ok: false };
  }
}

// ── YouTube Analytics API (Retention Curve & Swiped Away) ─────────────────────

export interface DropOffPoint {
  time_s: number;
  elapsed_pct: number;
  drop_pct: number;
  watch_pct_after: number;
  reason: string;
}

export interface SampledCurvePoint {
  percentile: number;
  time_s: number;
  retention_pct: number;
  relative_performance: number;
}

export interface VideoRetentionPoint {
  elapsed_ratio: number;
  time_s: number;
  watch_ratio: number;
  watch_pct: number;
  relative_performance: number;
}

export interface VideoRetentionData {
  video_id: string;
  status: string;
  has_curve: boolean;
  message?: string;
  duration_s?: number;
  swiped_away_pct?: number;
  hook_retention_pct?: number;
  completion_rate_pct?: number;
  avg_view_pct?: number;
  avg_view_duration_s?: number;
  top_drop_offs?: DropOffPoint[];
  sampled_curve?: SampledCurvePoint[];
  curve_points_count?: number;
  raw_curve?: VideoRetentionPoint[];
  diagnosis?: string;
  overview?: {
    views?: number;
    avg_view_pct?: number;
    avg_view_duration_s?: number;
    est_minutes_watched?: number;
    likes?: number;
    subscribers_gained?: number;
  };
}

export interface ChannelRetentionOverview {
  status: string;
  total_curves_analyzed: number;
  channel_avg_swiped_away_pct: number;
  channel_avg_hook_retention_pct: number;
  channel_avg_view_pct: number;
  videos: Array<{
    video_id: string;
    title: string;
    action_type: string;
    duration_s: number;
    views: number;
    swiped_away_pct: number;
    hook_retention_pct: number;
    avg_view_pct: number;
    diagnosis: string;
    top_drop_offs: DropOffPoint[];
  }>;
  insights: string[];
}

export async function apiGetVideoRetention(
  videoId: string,
  durationS: number = 13.0,
  forceRefresh: boolean = false
): Promise<{ ok: boolean; data: VideoRetentionData }> {
  const client = await createClient();
  const res = await client.get(`/analytics/video/${encodeURIComponent(videoId)}`, {
    params: { duration_s: durationS, force_refresh: forceRefresh }
  });
  return res.data;
}

export async function apiGetChannelRetention(): Promise<{ ok: boolean; data: ChannelRetentionOverview }> {
  const client = await createClient();
  const res = await client.get('/analytics/channel/retention');
  return res.data;
}

// ── Social & Multi-Platform Publishing (TikTok & YouTube) ────────────────────

export interface TikTokStatus {
  connected: boolean;
  valid: boolean;
  open_id?: string;
  scope?: string;
  expires_in_hours?: number;
  refresh_expires_in_days?: number;
  message: string;
}

export interface InstagramStatus {
  connected: boolean;
  valid: boolean;
  username?: string;
  instagram_account_id?: string;
  page_id?: string;
  message: string;
}

export interface SocialOverview {
  youtube: any;
  tiktok: TikTokStatus;
  instagram: InstagramStatus;
}

export async function apiGetSocialOverview(): Promise<SocialOverview> {
  const client = await createClient();
  const res = await client.get('/social/status');
  return res.data;
}

export async function apiGetTikTokStatus(): Promise<TikTokStatus> {
  const client = await createClient();
  const res = await client.get('/social/tiktok/token-status');
  return res.data;
}

export async function apiGetTikTokAuthUrl(): Promise<string> {
  const client = await createClient();
  const res = await client.get('/social/tiktok/auth-url');
  return res.data.auth_url;
}

export async function apiExchangeTikTokCode(code: string): Promise<any> {
  const client = await createClient();
  const res = await client.post('/social/tiktok/auth-code', { code });
  return res.data;
}

export async function apiGetInstagramStatus(): Promise<InstagramStatus> {
  const client = await createClient();
  const res = await client.get('/social/instagram/token-status');
  return res.data;
}

export interface FacebookStatus {
  connected: boolean;
  valid: boolean;
  can_publish: boolean;
  page_id?: string;
  page_name?: string;
  fan_count?: number;
  message?: string;
  error?: string;
}

export async function apiGetFacebookStatus(): Promise<FacebookStatus> {
  const client = await createClient();
  const res = await client.get('/social/facebook/token-status');
  return res.data;
}

export async function apiSetupMetaToken(userToken: string): Promise<{ success: boolean; username?: string; page_id?: string; message: string }> {
  const client = await createClient();
  const res = await client.post('/social/meta/setup-token', { user_token: userToken });
  return res.data;
}

export interface InstagramUploadRequest {
  caption: string;
  share_to_feed?: boolean;
}

export async function apiUploadToInstagram(
  filename: string,
  req: InstagramUploadRequest
): Promise<any> {
  const client = await createClient();
  const res = await client.post('/social/instagram/upload/' + encodeURIComponent(filename), req);
  return res.data;
}

export interface MultiPublishRequest {
  title: string;
  description?: string;
  tags?: string[];
  hashtags?: string[];
  platforms?: string[];
  privacy_yt?: string;
  privacy_tiktok?: string;
  share_to_ig_feed?: boolean;
  thumbnail_path?: string;
  publish_at?: string;
  pinned_comment?: string;
  champion_name?: string;
  action_type?: string;
  rank?: string;
  tiktok_caption?: string;
}

export interface SocialQueueItem {
  id: string;
  platform: string;
  video_path: string;
  caption: string;
  publish_at: string;
  thumbnail_path?: string | null;
  peak_moment?: number | null;
  status: 'pending' | 'published' | 'failed' | string;
  created_at?: string;
  published_at?: string;
  error?: string;
  extra?: Record<string, any>;
  result?: Record<string, any>;
}

export async function apiGetSocialQueue(): Promise<{ items: SocialQueueItem[]; summary: { total: number; pending: number; published: number; failed: number } }> {
  const client = await createClient();
  const res = await client.get('/social/queue');
  return res.data;
}

export async function apiFlushSocialQueue(): Promise<{ ok: boolean; flushed_posts: number; flushed_comments: number }> {
  const client = await createClient();
  const res = await client.post('/social/queue/flush', {}, { timeout: 180000 });
  return res.data;
}

export async function apiPreviewSocialCopy(params: { title: string; champion_name?: string; action_type?: string }): Promise<{ tiktok_copy_text: string; copies: Record<string, any> }> {
  const client = await createClient();
  const res = await client.post('/social/preview-copy', params);
  return res.data;
}

export async function apiPublishMulti(
  filename: string,
  req: MultiPublishRequest
): Promise<{ filename: string; results: Record<string, any> }> {
  const baseURL = await getServerUrl();
  const token = await getJwtToken();
  const uploadClient = axios.create({
    baseURL,
    timeout: 600000,
    headers: {
      Authorization: 'Bearer ' + token,
      'Content-Type': 'application/json'
    }
  });
  const res = await uploadClient.post('/social/publish/' + encodeURIComponent(filename), req);
  return res.data;
}

export async function apiGetSocialAnalytics(
  platform: 'all' | 'youtube' | 'instagram' | 'facebook' | 'tiktok' = 'all',
  refresh: boolean = false
): Promise<any> {
  const client = await createClient();
  const query = "/social/analytics?platform=" + encodeURIComponent(platform) + (refresh ? "&refresh=true" : "");
  const res = await client.get(query);
  return res.data;
}

// ── Multi-Account & Content Guidelines ──────────────────────────────────────

export interface AccountProfile {
  account_id: string;
  display_name: string;
  handle: string;
  content_mode: 'GAMING_HIGHLIGHTS' | 'PRODUCT_ECOMMERCE_AD' | 'BEAUTY_SALON_SERVICE' | 'EXPERT_BRAND_SHORT' | string;
  game_type: string;
  language: string;
  yt_token_file?: string;
  peak_hours_cet: string[];
  target_duration_range?: number[];
  camera_mode?: string;
  brand_voice: string;
  value_proposition: string;
  cta_text: string;
  cta_url: string;
  location: string;
  phone: string;
  mandatory_hashtags: string[];
  forbidden_words: string[];
  target_audience: string;
  yt_category_id?: string;
  builtin?: boolean;
  is_active?: boolean;
  yt_token_exists?: boolean;
  yt_token_path?: string;
}

export interface ContentModePreset {
  label: string;
  game_type: string;
  language: string;
  peak_hours_cet: string[];
  target_duration_range: number[];
  camera_mode: string;
  brand_voice: string;
  value_proposition: string;
  cta_text: string;
  cta_url: string;
  mandatory_hashtags: string[];
  forbidden_words: string[];
  yt_category_id: string;
}

export interface AccountsRegistryResponse {
  active_account_id: string;
  accounts: AccountProfile[];
  presets: Record<string, ContentModePreset>;
}

export interface AccountUpsertPayload {
  account_id?: string;
  display_name: string;
  handle?: string;
  content_mode: string;
  language?: string;
  peak_hours_cet?: string[];
  brand_voice?: string;
  value_proposition?: string;
  cta_text?: string;
  cta_url?: string;
  location?: string;
  phone?: string;
  mandatory_hashtags?: string[];
  forbidden_words?: string[];
  target_audience?: string;
  set_active?: boolean;
}

export async function apiListAccounts(): Promise<AccountsRegistryResponse> {
  const client = await createClient();
  const res = await client.get<AccountsRegistryResponse>('/accounts');
  return res.data;
}

export async function apiUpsertAccount(payload: AccountUpsertPayload): Promise<{ ok: boolean; account: AccountProfile }> {
  const client = await createClient();
  const res = await client.post<{ ok: boolean; account: AccountProfile }>('/accounts', payload);
  return res.data;
}

export async function apiSelectAccount(accountId: string): Promise<{ ok: boolean; active_account: AccountProfile }> {
  const client = await createClient();
  const res = await client.post<{ ok: boolean; active_account: AccountProfile }>(`/accounts/select/${encodeURIComponent(accountId)}`);
  return res.data;
}

export async function apiDeleteAccount(accountId: string): Promise<{ ok: boolean; deleted: string }> {
  const client = await createClient();
  const res = await client.delete<{ ok: boolean; deleted: string }>(`/accounts/${encodeURIComponent(accountId)}`);
  return res.data;
}

// ── Remote Mobile Access (LAN + Cloudflare Quick Tunnel) ────────────────────

export interface RemoteAccessStatus {
  ok?: boolean;
  port: number;
  lan_ips: string[];
  lan_urls: string[];
  primary_lan_url: string;
  tunnel_active: boolean;
  tunnel_url: string | null;
  tunnel_started_at: string | null;
  tunnel_error: string | null;
  cloudflared_available: boolean;
}

export async function apiGetRemoteAccess(): Promise<RemoteAccessStatus> {
  const client = await createClient();
  const res = await client.get<RemoteAccessStatus>('/system/remote-access');
  return res.data;
}

export async function apiStartRemoteTunnel(): Promise<RemoteAccessStatus> {
  const client = await createClient();
  const res = await client.post<RemoteAccessStatus>('/system/remote-access/tunnel/start', {}, { timeout: 60000 });
  return res.data;
}

export async function apiStopRemoteTunnel(): Promise<RemoteAccessStatus> {
  const client = await createClient();
  const res = await client.post<RemoteAccessStatus>('/system/remote-access/tunnel/stop');
  return res.data;
}



// ── Sugestie odpowiedzi na komentarze widzów (Synapsa + 1-klik) ─────────────

export interface CommentReplySuggestion {
  video_id: string;
  video_title: string;
  parent_comment_id: string;
  author: string;
  comment_text: string;
  published_at?: string;
  suggested_replies: string[];
}

export interface CommentSuggestionsResponse {
  items: CommentReplySuggestion[];
  count?: number;
  error?: string;
}

export async function apiGetCommentSuggestions(maxVideos: number = 5): Promise<CommentSuggestionsResponse> {
  const client = await createClient();
  const res = await client.get<CommentSuggestionsResponse>(`/youtube/comments/suggestions?max_videos=${maxVideos}`, { timeout: 90000 });
  return res.data;
}

export async function apiReplyToComment(parentId: string, text: string): Promise<{ ok: boolean; comment_id?: string }> {
  const client = await createClient();
  const res = await client.post<{ ok: boolean; comment_id?: string }>('/youtube/comments/reply', { parent_id: parentId, text });
  return res.data;
}

// ── Tryb Nocny („Opcja Nocna”: Skan -> Top 5 -> Rekomendacja Synapsy) ──────

export interface OvernightStartRequest {
  folder?: string;
  top_n?: number;
  skip_published?: boolean;
  champion_name?: string;
  rank?: string;
  use_local_ai?: boolean;
  tier_filter?: 'auto' | 'all' | 'any_kill' | 'double_plus' | 'triple_plus' | 'quadra_plus';
  only_channel_champion?: boolean;
}

export interface OvernightStatusResponse {
  status: 'idle' | 'scanning' | 'rendering' | 'evaluating' | 'done' | 'error' | 'stopped';
  batch_id: string | null;
  phase: string;
  progress: number;
  total_clips: number;
  scanned_clips: number;
  skipped_published: number;
  qualified_count: number;
  rejected_count: number;
  selected_count: number;
  rendered_count: number;
  current_clip: string;
  recommended_filename: string | null;
  summary_pl: string;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  logs: string[];
}

export interface OvernightShortItem {
  overnight_rank: number;
  candidate_rank: number;
  source_filename: string;
  source_path: string;
  output_filename: string;
  output_path: string | null;
  thumbnail_path?: string | null;
  thumbnail_filename?: string | null;
  champion_name: string;
  action_type: string;
  kill_count?: number;
  kill_span_s?: number;
  objective_secured?: boolean;
  is_clutch_1hp?: boolean;
  min_hp_percentage?: number;
  is_favorite?: boolean;
  event_tier?: string;
  event_source?: string;
  best_event_time_s?: number | null;
  total_kills_in_clip?: number | null;
  match_folder?: string;
  match_date?: string;
  clip_base_key?: string;
  match_kda?: string;
  title: string;
  hook_text?: string;
  hype_score: number;
  watchability_score?: number;
  qa_score: number;
  final_score: number;
  verdict: 'PICK_WINNER' | 'STRONG_ALT' | 'NEEDS_TWEAK' | 'SKIP' | 'RENDER_ERROR';
  synapsa_comment_pl: string;
  defects?: string[];
  has_critical_defect?: boolean;
  fallback_mediocre?: boolean;
  render_ok: boolean;
  error?: string | null;
}

export interface OvernightBatchManifest {
  batch_id: string;
  status: string;
  auto_publish: boolean;
  champion_name: string;
  tier_filter?: string;
  only_channel_champion?: boolean;
  rank: string;
  folder: string;
  started_at: string;
  finished_at: string;
  scan_stats: {
    total_clips_found: number;
    skipped_published: number;
    scanned_unpublished: number;
    qualified_count: number;
    rejected_count: number;
    rejection_breakdown: Record<string, number>;
  };
  recommended_filename: string | null;
  recommended_verdict: string | null;
  recommendation_source: string;
  guard_override: boolean;
  summary_pl: string;
  items: OvernightShortItem[];
}

export interface OvernightMatchSummary {
  match_folder: string;
  match_date: string;
  champion: string;
  clips_count: number;
  multikills_count: number;
  highest_tier: string;
  match_kda: string;
}

export interface OvernightCatalogResponse {
  total_clips: number;
  unpublished_clips: number;
  favorites_count: number;
  multikill_clips: number;
  tier_counts: Record<string, number>;
  by_champion: Record<string, { total: number; multikill: number; favorites: number }>;
  matches_count: number;
  matches: OvernightMatchSummary[];
  requested_champion?: string;
  skip_published?: boolean;
  all_champions_summary?: OvernightCatalogResponse;
}

export async function apiStartOvernight(params: OvernightStartRequest): Promise<{
  status: string;
  top_n: number;
  tier_filter?: string;
  only_channel_champion?: boolean;
  auto_publish: boolean;
}> {
  const client = await createClient();
  const res = await client.post('/overnight/start', params);
  return res.data;
}

export async function apiGetOvernightStatus(): Promise<OvernightStatusResponse> {
  const client = await createClient();
  const res = await client.get<OvernightStatusResponse>('/overnight/status');
  return res.data;
}

export async function apiStopOvernight(): Promise<{ status: string }> {
  const client = await createClient();
  const res = await client.post<{ status: string }>('/overnight/stop');
  return res.data;
}

export async function apiGetLatestOvernight(): Promise<{ batch: OvernightBatchManifest | null }> {
  const client = await createClient();
  const res = await client.get<{ batch: OvernightBatchManifest | null }>('/overnight/latest');
  return res.data;
}

export async function apiGetOvernightCatalog(params?: {
  folder?: string;
  champion_name?: string;
  skip_published?: boolean;
}): Promise<OvernightCatalogResponse> {
  const client = await createClient();
  const res = await client.get<OvernightCatalogResponse>('/overnight/catalog', { params });
  return res.data;
}
