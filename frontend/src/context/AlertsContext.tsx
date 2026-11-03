import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { Alert, AlertSeverity } from '../types';
import { api } from '../services/api';
import { wsService } from '../services/websocket';

interface AlertsContextType {
  alerts: Alert[];
  unackCount: number;
  highestSeverity: AlertSeverity | null;
  soundEnabled: boolean;
  toggleSound: () => void;
  ackAlert: (id: string, reason?: string) => Promise<void>;
  refreshAlerts: () => Promise<void>;
}

const AlertsContext = createContext<AlertsContextType | undefined>(undefined);

// Synthesize pleasant attention chime using Web Audio API
function playAlertChime(severity: AlertSeverity) {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;

    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    // Critical: higher urgent double-beep; Medium: medium chime; Low: subtle ping
    const freq = severity === 'critical' ? 880 : severity === 'medium' ? 660 : 440;
    osc.frequency.setValueAtTime(freq, ctx.currentTime);
    osc.type = severity === 'critical' ? 'sawtooth' : 'sine';

    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);

    osc.start();
    osc.stop(ctx.currentTime + 0.35);
  } catch {
    // Audio context may be restricted by autoplay policy
  }
}

export const AlertsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [soundEnabled, setSoundEnabled] = useState<boolean>(() => {
    return localStorage.getItem('mcvms_alert_sound') === 'true';
  });

  const refreshAlerts = async () => {
    try {
      const data = await api.listAlerts('open');
      setAlerts(data);
    } catch {
      // ignore in offline/unauthorized state
    }
  };

  useEffect(() => {
    refreshAlerts();

    const unsubscribe = wsService.onAlert((msg) => {
      if (msg.type === 'alert.created') {
        setAlerts((prev) => [msg.data, ...prev.filter((a) => a.id !== msg.data.id)]);
        if (soundEnabled) {
          playAlertChime(msg.data.level);
        }
      } else if (msg.type === 'alert.updated') {
        setAlerts((prev) => {
          if (msg.data.status !== 'open') {
            return prev.filter((a) => a.id !== msg.data.id);
          }
          return prev.map((a) => (a.id === msg.data.id ? msg.data : a));
        });
      }
    });

    return () => {
      unsubscribe();
    };
  }, [soundEnabled]);

  const toggleSound = () => {
    setSoundEnabled((prev) => {
      const next = !prev;
      localStorage.setItem('mcvms_alert_sound', String(next));
      return next;
    });
  };

  const ackAlert = async (id: string, reason?: string) => {
    await api.ackAlert(id, reason);
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  };

  const unackAlerts = useMemo(() => {
    return alerts.filter((a) => a.status === 'open');
  }, [alerts]);

  const unackCount = unackAlerts.length;

  const highestSeverity = useMemo<AlertSeverity | null>(() => {
    if (unackAlerts.some((a) => a.level === 'critical')) return 'critical';
    if (unackAlerts.some((a) => a.level === 'medium')) return 'medium';
    if (unackAlerts.some((a) => a.level === 'low')) return 'low';
    return null;
  }, [unackAlerts]);

  return (
    <AlertsContext.Provider
      value={{
        alerts,
        unackCount,
        highestSeverity,
        soundEnabled,
        toggleSound,
        ackAlert,
        refreshAlerts,
      }}
    >
      {children}
    </AlertsContext.Provider>
  );
};

export const useAlerts = (): AlertsContextType => {
  const context = useContext(AlertsContext);
  if (!context) {
    throw new Error('useAlerts must be used within an AlertsProvider');
  }
  return context;
};
