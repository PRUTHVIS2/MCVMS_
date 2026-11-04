import React, { useEffect, useState } from 'react';
import type { EventItem, EventSeverity, EventStatus } from '../../types';
import { api } from '../../services/api';
import { wsService } from '../../services/websocket';
import { useCameras } from '../../context/CamerasContext';
import { formatLocalDateTime } from '../../utils/date';
import { EventDetailDrawer } from './EventDetailDrawer';

export const EventsPage: React.FC = () => {
  const { cameras } = useCameras();
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedCameraId, setSelectedCameraId] = useState<string>('');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');

  // Selected event for detail drawer
  const [activeEvent, setActiveEvent] = useState<EventItem | null>(null);

  const fetchEvents = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listEvents({
        camera_id: selectedCameraId || undefined,
        severity: selectedSeverity || undefined,
        status: selectedStatus || undefined,
        limit: 100,
      });
      setEvents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load events');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, [selectedCameraId, selectedSeverity, selectedStatus]);

  // Listen for real-time WebSocket events
  useEffect(() => {
    const unsubEventCreated = wsService.onEventCreated((newEvent) => {
      setEvents((prev) => [newEvent, ...prev]);
    });

    const unsubEventUpdated = wsService.onEventUpdated((updatedEvent) => {
      setEvents((prev) =>
        prev.map((e) => (e.id === updatedEvent.id ? { ...e, ...updatedEvent } : e))
      );
      if (activeEvent && activeEvent.id === updatedEvent.id) {
        setActiveEvent((prev) => (prev ? { ...prev, ...updatedEvent } : null));
      }
    });

    return () => {
      unsubEventCreated();
      unsubEventUpdated();
    };
  }, [activeEvent]);

  const getSeverityBadgeClass = (severity: EventSeverity) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-500/20 text-red-400 border-red-500/40';
      case 'medium':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/40';
      case 'low':
      default:
        return 'bg-blue-500/20 text-blue-400 border-blue-500/40';
    }
  };

  const getStatusBadgeClass = (status: EventStatus) => {
    switch (status) {
      case 'acknowledged':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      case 'false_alarm':
        return 'bg-slate-800 text-slate-400 border-slate-700 line-through';
      case 'resolved':
        return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30';
      case 'open':
      default:
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold';
    }
  };

  const handleEventUpdated = (updated: EventItem) => {
    setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
    setActiveEvent(updated);
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Top Filter Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-md">
        <div className="flex flex-wrap items-center gap-3">
          {/* Camera Filter */}
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Camera
            </label>
            <select
              value={selectedCameraId}
              onChange={(e) => setSelectedCameraId(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="">All Cameras</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          {/* Severity Filter */}
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Severity
            </label>
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="">All Severities</option>
              <option value="low">Low (Blue)</option>
              <option value="medium">Medium (Amber)</option>
              <option value="critical">Critical (Red)</option>
            </select>
          </div>

          {/* Status Filter */}
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Status
            </label>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="">All Statuses</option>
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="false_alarm">False Alarm</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400 font-mono">
            {events.length} {events.length === 1 ? 'event' : 'events'}
          </span>
          <button
            type="button"
            onClick={fetchEvents}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            title="Refresh events list"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {/* Events Table Container */}
      <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg flex flex-col">
        {loading && events.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-slate-400 text-xs">
            <span className="animate-spin inline-block w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full mr-2"></span>
            Loading recorded events...
          </div>
        ) : error ? (
          <div className="p-6 text-center text-red-400 text-xs">
            {error}
          </div>
        ) : events.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-slate-500 text-center">
            <svg className="w-12 h-12 mb-3 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <p className="text-sm font-medium text-slate-300">No events found</p>
            <p className="text-xs text-slate-500 mt-1">
              Events triggered by rule conditions will appear here in real-time.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300 divide-y divide-slate-800">
              <thead className="bg-slate-950/80 text-slate-400 uppercase font-semibold text-[10px] tracking-wider sticky top-0 z-10 select-none">
                <tr>
                  <th scope="col" className="px-4 py-3">Timestamp (IST)</th>
                  <th scope="col" className="px-4 py-3">Severity</th>
                  <th scope="col" className="px-4 py-3">Rule / Kind</th>
                  <th scope="col" className="px-4 py-3">Camera & Zone</th>
                  <th scope="col" className="px-4 py-3">Subject</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {events.map((ev) => {
                  const subjectSummary = ev.subject
                    ? Object.entries(ev.subject)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(', ')
                    : '—';

                  return (
                    <tr
                      key={ev.id}
                      data-testid={`event-row-${ev.id}`}
                      onClick={() => setActiveEvent(ev)}
                      className={`hover:bg-slate-800/50 cursor-pointer transition-colors ${
                        activeEvent?.id === ev.id ? 'bg-slate-800/80 ring-1 ring-amber-500/40' : ''
                      }`}
                    >
                      <td className="px-4 py-3.5 whitespace-nowrap font-mono text-[11px] text-slate-200">
                        {formatLocalDateTime(ev.started_at)}
                      </td>
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded uppercase font-bold tracking-wider border ${getSeverityBadgeClass(
                            ev.severity
                          )}`}
                        >
                          {ev.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 whitespace-nowrap font-medium text-white">
                        {ev.kind.replace(/_/g, ' ')}
                      </td>
                      <td className="px-4 py-3.5 whitespace-nowrap text-slate-300">
                        <span className="font-semibold text-slate-200">{ev.camera_name || ev.camera_id}</span>
                        {ev.zone_name ? ` · ${ev.zone_name}` : ''}
                      </td>
                      <td className="px-4 py-3.5 max-w-xs truncate text-amber-400 font-mono text-[11px]">
                        {subjectSummary}
                      </td>
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded uppercase font-medium border ${getStatusBadgeClass(
                            ev.status
                          )}`}
                        >
                          {ev.status}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-right whitespace-nowrap">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveEvent(ev);
                          }}
                          className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-amber-400 rounded border border-slate-700 text-[11px] font-medium transition-colors"
                        >
                          View Clip & Details
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Drawer Component */}
      <EventDetailDrawer
        event={activeEvent}
        onClose={() => setActiveEvent(null)}
        onEventUpdated={handleEventUpdated}
      />
    </div>
  );
};

