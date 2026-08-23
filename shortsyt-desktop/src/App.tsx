import React, { useState, useEffect } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './screens/Dashboard';
import ClipBrowser from './screens/ClipBrowser';
import RenderMonitor from './screens/RenderMonitor';
import Outputs from './screens/Outputs';
import Analytics from './screens/Analytics';
import FeedbackTuning from './screens/FeedbackTuning';
import Settings from './screens/Settings';
import { apiHealthCheck, apiGetStatus } from './lib/api';
import { PipelineStatusType } from './components/StatusBadge';

export default function App() {
  const [backendConnected, setBackendConnected] = useState<boolean>(false);
  const [pipelineRunning, setPipelineRunning] = useState<boolean>(false);

  // Background health check
  useEffect(() => {
    const check = async () => {
      try {
        const h = await apiHealthCheck();
        setBackendConnected(h.ok);
        if (h.ok) {
          try {
            const st = await apiGetStatus();
            setPipelineRunning(st.status === 'running');
          } catch {
            // ignore
          }
        } else {
          setPipelineRunning(false);
        }
      } catch {
        setBackendConnected(false);
        setPipelineRunning(false);
      }
    };

    check();
    const interval = setInterval(check, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleStatusChange = (status: PipelineStatusType, connected: boolean) => {
    setBackendConnected(connected);
    setPipelineRunning(status === 'running');
  };

  return (
    <HashRouter>
      <div className="flex h-screen w-screen overflow-hidden bg-[#0A0E1A] text-[#E4D6B5]">
        {/* Left Navigation Sidebar */}
        <Sidebar backendConnected={backendConnected} pipelineRunning={pipelineRunning} />

        {/* Main Content Area */}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#0A0E1A]">
          <Routes>
            <Route path="/" element={<Dashboard onStatusChange={handleStatusChange} />} />
            <Route path="/clips" element={<ClipBrowser />} />
            <Route path="/render" element={<RenderMonitor />} />
            <Route path="/outputs" element={<Outputs />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/tuning" element={<FeedbackTuning />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  );
}
