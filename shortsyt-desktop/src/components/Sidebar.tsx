import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Film,
  Cpu,
  Video,
  BarChart3,
  Settings,
  Flame,
  Radio,
  SlidersHorizontal,
  Brain,
  Calendar,
} from 'lucide-react';

interface SidebarProps {
  backendConnected: boolean;
  pipelineRunning?: boolean;
}

export default function Sidebar({ backendConnected, pipelineRunning = false }: SidebarProps) {
  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/clips', label: 'Studio Klipów', icon: Film, badge: 'Drop' },
    { to: '/calendar', label: 'Kalendarz & Sloty', icon: Calendar, badge: 'Peak ⚡' },
    { to: '/render', label: 'Render Monitor', icon: Cpu, activeGlow: pipelineRunning },
    { to: '/outputs', label: 'Biblioteka Shorts', icon: Video },
    { to: '/analytics', label: 'Analityka Kanału', icon: BarChart3 },
    { to: '/dark', label: 'Strategia & Wnioski', icon: Brain, badge: 'Dwannellenga' },
    { to: '/tuning', label: 'Styl & Feedback', icon: SlidersHorizontal },
    { to: '/settings', label: 'Ustawienia', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-[#070A12] border-r border-[#1E2438] flex flex-col justify-between select-none h-screen flex-shrink-0">
      {/* Top Header & Branding */}
      <div>
        <div className="p-5 border-b border-[#1E2438]/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-[#C89B3C] to-[#7A6026] flex items-center justify-center shadow-lg shadow-[#C89B3C]/10 border border-[#E5C269]/30">
              <Flame className="w-5 h-5 text-[#0A0E1A] fill-[#0A0E1A]" />
            </div>
            <div>
              <div className="text-sm font-black tracking-wider text-[#E4D6B5] flex items-center gap-1.5">
                SHORTSYT <span className="text-[10px] px-1.5 py-0.2 bg-[#C89B3C]/20 text-[#C89B3C] border border-[#C89B3C]/40 rounded">DESKTOP</span>
              </div>
              <div className="text-[11px] text-[#8B8FA8] font-medium tracking-tight">LoL Automation v25</div>
            </div>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="p-3 space-y-1.5 mt-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all group ${
                    isActive
                      ? 'bg-[#1A1E30] text-[#C89B3C] border border-[#C89B3C]/30 shadow-md shadow-black/30'
                      : 'text-[#8B8FA8] hover:text-[#E4D6B5] hover:bg-[#121624]'
                  }`
                }
              >
                <div className="flex items-center gap-3">
                  <Icon className="w-4 h-4 transition-colors group-hover:text-[#C89B3C]" />
                  <span>{item.label}</span>
                </div>

                {item.activeGlow && (
                  <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#4FA3F7] opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-[#2A7FD4]"></span>
                  </span>
                )}

                {item.badge && !item.activeGlow && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1E2338] text-[#8B8FA8] font-semibold border border-white/5">
                    {item.badge}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Footer Backend Status Info */}
      <div className="p-4 border-t border-[#1E2438] bg-[#0A0E1A]/40 m-2 rounded-xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio className={`w-3.5 h-3.5 ${backendConnected ? 'text-[#2ECC71] animate-pulse' : 'text-[#E84040]'}`} />
            <span className="text-xs font-semibold text-[#8B8FA8]">Backend API</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                backendConnected ? 'bg-[#2ECC71] shadow-sm shadow-[#2ECC71]' : 'bg-[#E84040]'
              }`}
            />
            <span
              className={`text-xs font-bold ${
                backendConnected ? 'text-[#55E88D]' : 'text-[#FF6060]'
              }`}
            >
              {backendConnected ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
        </div>
        <div className="text-[11px] text-[#50546A] mt-1.5 truncate">
          Port: 8765 (FastAPI)
        </div>
      </div>
    </aside>
  );
}
