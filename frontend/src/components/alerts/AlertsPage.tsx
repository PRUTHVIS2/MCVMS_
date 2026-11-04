import React, { useEffect, useState } from 'react';
import type { Alert, AlertSeverity, AlertStatus } from '../../types';
import { api } from '../../services/api';
import { wsService } from '../../services/websocket';
import { formatLocalDateTime } from '../../utils/date';
import { useAuth } from '../../context/AuthContext';

export const AlertsPage: React.FC = () => {
  const { hasRole } = useAuth();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedStatus, setSelectedStatus] = useState<string>('open');
  const [selectedLevel, setSelectedLevel] = useState<string>('');

  // Dismiss modal state
  const [dismissingAlertId, setDismissingAlertId] = useState<string | null>(null);
  const [dismissReason, setDismissReason] = useState<string>('');
  const [actionLoading, setActionLoading] = useState(false);

  const fetchAlerts = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listAlerts(selectedStatus || 'open');
      const filtered = selectedLevel
        ? data.filter((a) => a.level === selectedLevel)
        : data;
      setAlerts(filtered);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load alerts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, [selectedStatus, selectedLevel]);

  // Real-time WebSocket subscriptions
  useEffect(() => {
    const unsubCreated = wsService.onAlertCreated((newAlert) => {
      if (!selectedLevel || newAlert.level === selectedLevel) {
        setAlerts((prev) => [newAlert, ...prev]);
      }
    });

    const unsubUpdated = wsService.onAlertUpdated((updatedAlert) => {
      setAlerts((prev) =>
        prev.map((a) => (a.id === updatedAlert.id ? { ...a, ...updatedAlert } : a))
      );
    });

    return () => {
      unsubCreated();
      unsubUpdated();
    };
  }, [selectedLevel]);

  const handleAck = async (alertId: string) => {
    try {
      await api.ackAlert(alertId);
      setAlerts((prev) =>
        prev.map((a) => (a.id === alertId ? { ...a, status: 'acknowledged' } : a))
      );
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to acknowledge alert');
    }
  };

  const handleDismiss = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dismissingAlertId || !dismissReason.trim()) return;
    setActionLoading(true);
    try {
      await api.dismissAlert(dismissingAlertId, dismissReason.trim());
      setAlerts((prev) =>
        prev.map((a) => (a.id === dismissingAlertId ? { ...a, status: 'dismissed' } : a))
      );
      setDismissingAlertId(null);
      setDismissReason('');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to dismiss alert');
    } finally {
      setActionLoading(false);
    }
  };

  const getSeverityBadgeClass = (level: AlertSeverity) => {
    switch (level) {
      case 'critical':
        return 'bg-red-500/20 text-red-400 border-red-500/40';
      case 'medium':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/40';
      case 'low':
      default:
        return 'bg-blue-500/20 text-blue-400 border-blue-500/40';
    }
  };

  const getStatusBadgeClass = (status: AlertStatus) => {
    switch (status) {
      case 'acknowledged':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      case 'dismissed':
        return 'bg-slate-800 text-slate-400 border-slate-700';
      case 'expired':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
      case 'open':
      default:
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold';
    }
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Top Filter Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-md">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Severity
            </label>
            <select
              value={selectedLevel}
              onChange={(e) => setSelectedLevel(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="">All Severities</option>
              <option value="critical">Critical (Red)</option>
              <option value="medium">Medium (Amber)</option>
              <option value="low">Low (Blue)</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Status
            </label>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="dismissed">Dismissed</option>
              <option value="expired">Expired</option>
            </select>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400 font-mono">
            {alerts.length} {alerts.length === 1 ? 'alert' : 'alerts'}
          </span>
          <button
            type="button"
            onClick={fetchAlerts}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            title="Refresh alerts"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {/* Alerts Table */}
      <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg flex flex-col">
        {loading && alerts.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-slate-400 text-xs">
            <span className="animate-spin inline-block w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full mr-2"></span>
            Loading alerts...
          </div>
        ) : error ? (
          <div className="p-6 text-center text-red-400 text-xs">{error}</div>
        ) : alerts.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-slate-500 text-center">
            <svg className="w-12 h-12 mb-3 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-sm font-medium text-slate-300">No alerts match the selected criteria</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300 divide-y divide-slate-800">
              <thead className="bg-slate-950/80 text-slate-400 uppercase font-semibold text-[10px] tracking-wider sticky top-0 z-10 select-none">
                <tr>
                  <th scope="col" className="px-4 py-3">Timestamp (IST)</th>
                  <th scope="col" className="px-4 py-3">Severity</th>
                  <th scope="col" className="px-4 py-3">Message</th>
                  <th scope="col" className="px-4 py-3">Camera & Zone</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {alerts.map((al) => (
                  <tr key={al.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3.5 whitespace-nowrap font-mono text-[11px] text-slate-200">
                      {formatLocalDateTime(al.created_at ?? al.opened_at)}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded uppercase font-bold tracking-wider border ${getSeverityBadgeClass(
                          al.level
                        )}`}
                      >
                        {al.level}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 font-medium text-white max-w-md">
                      {al.message}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap text-slate-300">
                      <span className="font-semibold text-slate-200">{al.camera_name || al.camera_id}</span>
                      {al.zone_name ? ` · ${al.zone_name}` : ''}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded uppercase font-medium border ${getStatusBadgeClass(
                          al.status
                        )}`}
                      >
                        {al.status}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-right whitespace-nowrap space-x-2">
                      {al.status === 'open' && (
                        <button
                          type="button"
                          onClick={() => handleAck(al.id)}
                          className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-amber-400 rounded border border-slate-700 text-[11px] font-medium transition-colors"
                        >
                          Acknowledge
                        </button>
                      )}
                      {al.status === 'open' && hasRole(['owner', 'admin']) && (
                        <button
                          type="button"
                          onClick={() => setDismissingAlertId(al.id)}
                          className="px-2.5 py-1 bg-red-950 hover:bg-red-900 text-red-300 rounded border border-red-800 text-[11px] font-medium transition-colors"
                        >
                          Dismiss
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Dismiss Modal */}
      {dismissingAlertId && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-base font-semibold text-white mb-2">Dismiss Alert</h3>
            <p className="text-xs text-slate-400 mb-4">
              Enter a reason for dismissing this alert. This will be audited.
            </p>
            <form onSubmit={handleDismiss} className="space-y-4">
              <input
                type="text"
                value={dismissReason}
                onChange={(e) => setDismissReason(e.target.value)}
                placeholder="e.g. Known camera maintenance / deliberate gate opening"
                required
                className="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
              <div className="flex justify-end space-x-2">
                <button
                  type="button"
                  onClick={() => setDismissingAlertId(null)}
                  className="px-3.5 py-1.5 text-xs text-slate-400 hover:text-white rounded-lg bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !dismissReason.trim()}
                  className="px-3.5 py-1.5 text-xs font-semibold text-white bg-red-600 hover:bg-red-500 rounded-lg disabled:opacity-50"
                >
                  Confirm Dismiss
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

