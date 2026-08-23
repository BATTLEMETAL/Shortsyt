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

export async function apiListClips(): Promise<ClipItem[]> {
  const client = await createClient();
  const res = await client.get('/clips');
  return res.data.clips || [];
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

export async function apiGetOutputUrl(filename: string): Promise<string> {
  const baseURL = await getServerUrl();
  const token = await getJwtToken();
  return `${baseURL}/outputs/${encodeURIComponent(filename)}?token=${token || ''}`;
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

export async function apiUploadToYt(
  filename: string,
  title: string,
  description: string,
  tags: string[],
  privacy: string
): Promise<any> {
  const client = await createClient();
  const res = await client.post(`/youtube/upload/${encodeURIComponent(filename)}`, {
    filename,
    title,
    description,
    tags,
    privacy,
  });
  return res.data;
}

export async function apiGetAnalytics(range: string = '30d'): Promise<any> {
  const client = await createClient();
  const res = await client.get(`/analytics?range=${range}`);
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
