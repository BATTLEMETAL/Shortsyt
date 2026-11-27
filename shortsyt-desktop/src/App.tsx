import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './screens/Dashboard';
import { apiHealthCheck, apiGetStatus } from './lib/api';
import { PipelineStatusType } from './components/StatusBadge';
import ErrorBoundary from './components/ErrorBoundary';

const ClipBrowser = lazy(() => import('./screens/ClipBrowser'));
const RenderMonitor = lazy(() => import('./screens/RenderMonitor'));
const Outputs = lazy(() => import('./screens/Outputs'));
const Analytics = lazy(() => import('./screens/Analytics'));
const FeedbackTuning = lazy(() => import('./screens/FeedbackTuning'));
const Settings = lazy(() => import('./screens/Settings'));
const Comments = lazy(() => import('./screens/Comments'));
const DarkAgent = lazy(() => import('./screens/DarkAgent'));
const NicheResearch = lazy(() => import('./screens/NicheResearch'));
const Compilations = lazy(() => import('./screens/Compilations'));
const CalendarScheduler = lazy(() =>
  import('./screens/CalendarScheduler').then((m) => ({ default: m.CalendarScheduler }))
);

export default function App() {
  const [backendConnected, setBackendConnected] = useState<boolean>(false);
  const [pipelineRunning, setPipelineRunning] = useState<boolean>(false);
  const inFlightRef = useRef<boolean>(false);

  // Background health check (adaptive polling + visibility pause + in-flight guard)
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const scheduleNext = (running: boolean) => {
      if (!active) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(check, running ? 2500 : 5000);
    };

    const check = async () => {
      if (!active) return;
      if (document.hidden) {
        scheduleNext(false);
        return;
      }
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      let isRunning = false;
      try {
        const h = await apiHealthCheck();
        if (!active) return;
        setBackendConnected(h.ok);
        if (h.ok) {
          try {
            const st = await apiGetStatus();
            if (!active) return;
            isRunning = st.status === 'running';
            setPipelineRunning(isRunning);
          } catch {
            // keep previous running flag on transient /status error
          }
        } else {
          setPipelineRunning(false);
        }
      } catch {
        if (!active) return;
        setBackendConnected(false);
        setPipelineRunning(false);
      } finally {
        inFlightRef.current = false;
        scheduleNext(isRunning);
      }
    };

    const onVisibilityChange = () => {
      if (!document.hidden && active) {
        if (timer) clearTimeout(timer);
        check();
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    check();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  const handleStatusChange = (status: PipelineStatusType, connected: boolean) => {
    setBackendConnected(connected);
    setPipelineRunning(status === 'running');
  };

  return (
    <HashRouter>
      <div className="flex h-screen w-screen overflow-hidden bg-[#050505] text-[#FFFFFF]">
        {/* Left Navigation Sidebar */}
        <Sidebar backendConnected={backendConnected} pipelineRunning={pipelineRunning} />

        {/* Main Content Area */}
        <main className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[#050505] p-4 pb-24 md:p-6">
          <ErrorBoundary>
            <Suspense
              fallback={
                <div className="flex-1 flex items-center justify-center text-xs text-[#A0A7B1]">
                  Ładowanie modułu...
                </div>
              }
            >
              <Routes>
                <Route path="/" element={<Dashboard onStatusChange={handleStatusChange} />} />
                <Route path="/clips" element={<ClipBrowser />} />
                <Route path="/calendar" element={<CalendarScheduler />} />
                <Route path="/render" element={<RenderMonitor />} />
                <Route path="/outputs" element={<Outputs />} />
                <Route path="/compilations" element={<Compilations />} />
                <Route path="/analytics" element={<Analytics />} />
                <Route path="/research" element={<NicheResearch />} />
                <Route path="/dark" element={<DarkAgent />} />
                <Route path="/tuning" element={<FeedbackTuning />} />
                <Route path="/comments" element={<Comments />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </HashRouter>
  );
}
