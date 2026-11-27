import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Film,
  Cpu,
  Video,
  BarChart3,
  Settings,
  Radio,
  SlidersHorizontal,
  Brain,
  Calendar,
  Users,
  MessageSquare,
  Compass,
  Clapperboard,
} from 'lucide-react';
import { apiListAccounts, AccountProfile } from '../lib/api';

interface SidebarProps {
  backendConnected: boolean;
  pipelineRunning?: boolean;
}

const WORDMARK_PATH =
  'M39.133 -32H43.133V-12.444L53.2 -24H58.333L47.733 -12L59.578 0H54.044L43.133 -11.556V0H39.111L39.133 -32ZM91.428 -0.111Q89.778 -0.844 88.689 -2.061Q87.6 -3.278 86.978 -4.772Q86.356 -6.267 86.1 -7.817Q85.844 -9.367 85.844 -10.733V-24H89.844V-11.978Q89.844 -10.289 90.15 -8.706Q90.456 -7.122 91.2 -5.861Q91.944 -4.6 93.2 -3.867Q94.456 -3.133 96.356 -3.133Q97.844 -3.133 99.061 -3.639Q100.278 -4.144 101.144 -5.161Q102.011 -6.178 102.483 -7.728Q102.956 -9.278 102.956 -11.356V-24H106.933V0H103.4V-3.099Q102.321 -1.64 100.767 -0.722Q98.489 0.622 95.4 0.622Q93.078 0.622 91.428 -0.111ZM66.156 -0.967Q63.611 -2.6 62.278 -5.461Q60.944 -8.322 60.911 -12Q60.944 -15.744 62.311 -18.6Q63.678 -21.456 66.233 -23.061Q68.789 -24.667 72.4 -24.667Q76.189 -24.667 78.933 -22.8Q81.678 -20.933 82.622 -17.689L78.711 -16.511Q77.944 -18.6 76.244 -19.756Q74.544 -20.911 72.356 -20.911Q69.889 -20.911 68.289 -19.767Q66.689 -18.622 65.911 -16.611Q65.133 -14.6 65.111 -12Q65.144 -7.989 66.961 -5.539Q68.778 -3.089 72.356 -3.089Q74.7 -3.089 76.256 -4.167Q77.811 -5.244 78.622 -7.289L82.622 -6.244Q81.367 -2.889 78.722 -1.111Q76.078 0.667 72.356 0.667Q68.7 0.667 66.156 -0.967ZM4.067 -20.733H0V-24H4.067V-25.311Q4.067 -26.233 4.15 -27.206Q4.233 -28.178 4.55 -29.1Q4.867 -30.022 5.578 -30.8Q6.4 -31.7 7.378 -32.094Q8.356 -32.489 9.367 -32.578Q10.378 -32.667 11.289 -32.667H14.333V-29.378H11.511Q9.756 -29.378 8.889 -28.517Q8.022 -27.656 8.022 -25.933V-24H14.333V-20.733H8.022V0H4.067V-20.733ZM121.678 -3.261Q123.422 -3.022 125.889 -3.4V0Q123.744 0.433 121.672 0.356Q119.6 0.278 117.972 -0.489Q116.344 -1.256 115.511 -2.889Q114.8 -4.3 114.744 -5.756Q114.689 -7.211 114.689 -9.067V-20.733H108.711L118.644 -30.667V-24H125.889V-20.733H118.644V-9.244Q118.644 -7.767 118.678 -6.728Q118.711 -5.689 119.133 -4.933Q119.933 -3.5 121.678 -3.261ZM17.444 -32.667H21.4V0H17.444V-32.667ZM28.289 -24H32.244V0H28.289V-24ZM28.289 -32.333H32.244V-28.244H28.289V-32.333Z';

export default function Sidebar({ backendConnected, pipelineRunning = false }: SidebarProps) {
  const [activeAccount, setActiveAccount] = useState<AccountProfile | null>(null);

  useEffect(() => {
    let mounted = true;
    const loadActive = async () => {
      try {
        const res = await apiListAccounts();
        if (!mounted) return;
        const found = res.accounts.find((a) => a.account_id === res.active_account_id) || res.accounts[0] || null;
        setActiveAccount(found);
      } catch (err) {
        console.warn('[Sidebar] Błąd wczytywania aktywnego konta:', err);
      }
    };
    loadActive();
    const onAccountChanged = () => { loadActive(); };
    window.addEventListener('account-changed', onAccountChanged);
    return () => {
      mounted = false;
      window.removeEventListener('account-changed', onAccountChanged);
    };
  }, [backendConnected]);

  const navItems = [
    { to: '/', label: 'Dashboard', shortLabel: 'Home', icon: LayoutDashboard },
    { to: '/clips', label: 'Studio Klipów', shortLabel: 'Klipy', icon: Film, badge: 'Drop' },
    { to: '/calendar', label: 'Kalendarz & Sloty', shortLabel: 'Sloty', icon: Calendar, badge: 'Peak ⚡' },
    { to: '/render', label: 'Render Monitor', shortLabel: 'Render', icon: Cpu, activeGlow: pipelineRunning },
    { to: '/outputs', label: 'Biblioteka Shorts', shortLabel: 'Shorts', icon: Video },
    { to: '/compilations', label: 'Kompilacje 16:9', shortLabel: 'Filmy', icon: Clapperboard, badge: '16:9' },
    { to: '/analytics', label: 'Analityka Kanału', shortLabel: 'Wyniki', icon: BarChart3 },
    { to: '/research', label: 'Research & Klienci', shortLabel: 'Klienci', icon: Compass, badge: 'DFY' },
    { to: '/dark', label: 'Strategia & Wnioski', shortLabel: 'Engine', icon: Brain, badge: 'Engine' },
    { to: '/tuning', label: 'Styl & Feedback', shortLabel: 'Styl', icon: SlidersHorizontal },
    { to: '/comments', label: 'Komentarze', shortLabel: 'Komentarze', icon: MessageSquare },
    { to: '/settings', label: 'Ustawienia', shortLabel: 'Opcje', icon: Settings },
  ];

  return (
    <>
    <aside className="hidden md:flex w-64 bg-[#0E0F11] border-r border-[#272A2F] flex-col justify-between select-none h-screen flex-shrink-0">
      {/* Top Header & Flikcut Branding */}
      <div>
        <div className="p-5 border-b border-[#272A2F]">
          <svg
            viewBox="0 0 192 60"
            className="h-7 w-auto text-[#FFFFFF] block overflow-visible"
            role="img"
            aria-label="Flikcut"
          >
            <g fill="#C8FF3A" transform="translate(0 6) scale(5.3333)">
              <path d="M0 0H3V1H1V3H0ZM6 0H9V3H8V1H6ZM9 9H6V8H8V6H9ZM0 9V6H1V8H3V9Z" />
              <path d="M5.5 2H7L3.5 7H2Z" />
            </g>
            <path fill="currentColor" transform="translate(64 48)" d={WORDMARK_PATH} />
          </svg>
          <div className="mt-2.5 flex items-center gap-2">
            <span className="fk-slash h-3 w-1.5" />
            <span className="text-[11px] font-extrabold tracking-[0.14em] uppercase text-[#A0A7B1]">
              DESKTOP STUDIO · 9:16
            </span>
          </div>
          {activeAccount && (
            <NavLink
              to="/settings"
              className="mt-3 flex items-center justify-between gap-2 px-2.5 py-2 bg-[#14171A] border border-[#272A2F] hover:border-[#C8FF3A]/50 transition-colors"
              title="Zmień aktywne konto lub wytyczne kontentu w Ustawieniach"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Users className="w-3.5 h-3.5 text-[#C8FF3A] flex-shrink-0" />
                <div className="min-w-0">
                  <div className="text-[11px] font-bold text-[#FFFFFF] truncate">
                    {activeAccount.display_name}
                  </div>
                  <div className="text-[10px] text-[#686E78] font-mono truncate">
                    {activeAccount.content_mode}
                  </div>
                </div>
              </div>
              <span className="text-[10px] font-bold text-[#C8FF3A] flex-shrink-0">AKTYWNE</span>
            </NavLink>
          )}
        </div>

        {/* Navigation Links */}
        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `fk-cut-sm flex items-center justify-between px-3.5 py-2.5 text-sm transition-all group border-l-2 ${
                    isActive
                      ? 'bg-[#17191C] text-[#FFFFFF] border-[#C8FF3A] font-bold'
                      : 'border-transparent text-[#A0A7B1] hover:text-[#FFFFFF] hover:bg-[#17191C]/70 font-semibold'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <div className="flex items-center gap-3">
                      <Icon
                        className={`w-4 h-4 transition-colors ${
                          isActive ? 'text-[#C8FF3A]' : 'group-hover:text-[#C8FF3A]'
                        }`}
                      />
                      <span>{item.label}</span>
                    </div>

                    {item.activeGlow && (
                      <span className="flex h-2 w-2 relative">
                        <span className="animate-ping absolute inline-flex h-full w-full bg-[#C8FF3A] opacity-75"></span>
                        <span className="relative inline-flex h-2 w-2 bg-[#C8FF3A]"></span>
                      </span>
                    )}

                    {item.badge && !item.activeGlow && (
                      <span className="fk-tag text-[10px] px-2 py-0.5 bg-[#272A2F] text-[#FFFFFF] font-extrabold tracking-wide">
                        {item.badge}
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Footer Backend Status Info */}
      <div className="p-3.5 border border-[#272A2F] bg-[#050505] m-3 fk-cut-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio
              className={`w-3.5 h-3.5 ${
                backendConnected ? 'text-[#C8FF3A] animate-pulse' : 'text-[#FF5C5C]'
              }`}
            />
            <span className="text-xs font-bold text-[#A0A7B1]">Backend API</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`inline-block w-2 h-2 ${
                backendConnected ? 'bg-[#C8FF3A]' : 'bg-[#FF5C5C]'
              }`}
            />
            <span
              className={`text-xs font-extrabold tabular-nums ${
                backendConnected ? 'text-[#C8FF3A]' : 'text-[#FF5C5C]'
              }`}
            >
              {backendConnected ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
        </div>
        <div className="text-[11px] text-[#686E78] font-medium mt-1.5 truncate tabular-nums">
          Port: 8765 · FastAPI Engine
        </div>
      </div>
    </aside>

    {/* Mobile Bottom Navigation Bar */}
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-[#0E0F11]/95 backdrop-blur border-t border-[#272A2F] flex items-center overflow-x-auto gap-1 px-2 py-1.5 select-none">
      {navItems.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center min-w-[56px] px-2 py-1 text-[10px] font-bold transition-colors flex-shrink-0 ${
                isActive
                  ? 'text-[#C8FF3A] bg-[#17191C] border-t-2 border-[#C8FF3A]'
                  : 'text-[#A0A7B1] hover:text-[#FFFFFF]'
              }`
            }
          >
            <Icon className="w-4 h-4 mb-0.5" />
            <span className="truncate">{item.shortLabel}</span>
          </NavLink>
        );
      })}
    </nav>
    </>
  );
}
