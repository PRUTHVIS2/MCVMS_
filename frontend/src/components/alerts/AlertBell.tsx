import React, { useState, useRef, useEffect } from 'react';
import { useAlerts } from '../../context/AlertsContext';
import type { AlertSeverity } from '../../types';
import { formatLocalTime } from '../../utils/date';

export const AlertBell: React.FC = () => {
  const { alerts, unackCount, highestSeverity, soundEnabled, toggleSound, ackAlert } = useAlerts();
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close panel on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const getSeverityBadgeClass = (level: AlertSeverity) => {
    switch (level) {
      case 'critical':
        return 'bg-red-500 text-white border-red-400';
      case 'medium':
        return 'bg-amber-500 text-slate-950 font-bold border-amber-400';
      case 'low':
      default:
        return 'bg-blue-500 text-white border-blue-400';
    }
  };

  const getBellBadgeClass = (severity: AlertSeverity | null) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-600 text-white animate-pulse shadow-red-500/50 shadow-md';
      case 'medium':
        return 'bg-amber-500 text-slate-950 font-bold shadow-amber-500/50 shadow-md';
      case 'low':
        return 'bg-blue-600 text-white';
      default:
        return 'bg-slate-700 text-slate-300';
    }
  };



  return (
    <div className="relative" ref={panelRef}>
      {/* Sound Toggle + Bell Button Group */}
      <div className="flex items-center space-x-1.5">
        <button
          type="button"
          onClick={toggleSound}
          title={soundEnabled ? 'Alert Chime: Enabled' : 'Alert Chime: Muted'}
          className={`p-2 rounded-lg transition-colors ${
            soundEnabled
              ? 'text-amber-400 hover:text-amber-300 bg-amber-500/10'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
          aria-label="Toggle alert sound"
        >
          {soundEnabled ? (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
            </svg>
          )}
        </button>

        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          aria-label="Alerts"
          className="relative p-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
            />
          </svg>

          {unackCount > 0 && (
            <span
              data-testid="alert-bell-badge"
              className={`absolute -top-1 -right-1 min-w-[20px] h-5 px-1.5 flex items-center justify-center text-xs rounded-full font-semibold ${getBellBadgeClass(
                highestSeverity
              )}`}
            >
              {unackCount > 99 ? '99+' : unackCount}
            </span>
          )}
        </button>
      </div>

      {/* Dropdown Panel */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-96 bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl z-50 overflow-hidden">
          <div className="p-3.5 bg-slate-800/80 border-b border-slate-700/80 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="font-semibold text-white text-sm">System Alerts</span>
              {unackCount > 0 && (
                <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${getBellBadgeClass(highestSeverity)}`}>
                  {unackCount} Open
                </span>
              )}
            </div>
            <span className="text-xs text-slate-400">Real-time Feed</span>
          </div>

          <div className="max-h-96 overflow-y-auto divide-y divide-slate-800">
            {alerts.length === 0 ? (
              <div className="p-6 text-center text-slate-400 text-xs">
                <svg className="w-8 h-8 mx-auto mb-2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                No active unacknowledged alerts.
              </div>
            ) : (
              alerts.map((alert) => (
                <div key={alert.id} className="p-3.5 hover:bg-slate-800/40 transition-colors">
                  <div className="flex items-center justify-between mb-1.5">
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-md uppercase font-bold tracking-wider border ${getSeverityBadgeClass(
                        alert.level
                      )}`}
                    >
                      {alert.level}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {formatLocalTime(alert.created_at ?? alert.opened_at)}
                    </span>
                  </div>

                  <p className="text-sm font-medium text-slate-200 mb-1 leading-snug">{alert.message}</p>

                  <div className="flex items-center justify-between mt-2 pt-1.5 border-t border-slate-800/60 text-xs">
                    <span className="text-slate-400 text-[11px]">
                      {alert.camera_name || alert.camera_id} {alert.zone_name ? `· ${alert.zone_name}` : ''}
                    </span>
                    <button
                      type="button"
                      onClick={() => ackAlert(alert.id)}
                      className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-amber-400 hover:text-amber-300 rounded border border-slate-700 text-[11px] font-medium transition-colors"
                    >
                      Acknowledge
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
