import React, { useRef, useState } from 'react';
import type { EventItem, EventSeverity } from '../../types';
import { api } from '../../services/api';
import { formatLocalDateTime } from '../../utils/date';

interface EventDetailDrawerProps {
  event: EventItem | null;
  onClose: () => void;
  onEventUpdated: (updated: EventItem) => void;
}

export const EventDetailDrawer: React.FC<EventDetailDrawerProps> = ({
  event,
  onClose,
  onEventUpdated,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [falseAlarmReason, setFalseAlarmReason] = useState('');
  const [isFalseAlarmDialogOpen, setIsFalseAlarmDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!event) return null;

  const getSeverityBadge = (level: EventSeverity) => {
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

  const handleAcknowledge = async () => {
    setActionLoading(true);
    setActionError(null);
    try {
      const updated = await api.ackEvent(event.id);
      onEventUpdated(updated);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to acknowledge event');
    } finally {
      setActionLoading(false);
    }
  };

  const handleMarkFalseAlarm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!falseAlarmReason.trim()) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const updated = await api.markFalseAlarm(event.id, falseAlarmReason.trim());
      setIsFalseAlarmDialogOpen(false);
      setFalseAlarmReason('');
      onEventUpdated(updated);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to mark false alarm');
    } finally {
      setActionLoading(false);
    }
  };

  const jumpToTrigger = () => {
    if (videoRef.current) {
      videoRef.current.currentTime = 15.0; // 15s pre-roll trigger anchor
      videoRef.current.play().catch(() => {});
    }
  };

  return (
    <div
      data-testid="event-detail-drawer"
      className="fixed inset-y-0 right-0 w-full max-w-2xl bg-slate-900 border-l border-slate-800 shadow-2xl z-50 flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-slate-950 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <span
            className={`text-xs px-2.5 py-1 rounded-md uppercase font-bold tracking-wider border ${getSeverityBadge(
              event.severity
            )}`}
          >
            {event.severity}
          </span>
          <div>
            <h2 className="text-base font-semibold text-white tracking-wide">
              {event.kind.replace(/_/g, ' ').toUpperCase()}
            </h2>
            <p className="text-xs text-slate-400">
              {formatLocalDateTime(event.started_at)}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close detail drawer"
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Body content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {actionError && (
          <div className="p-3 bg-red-950/80 border border-red-800 rounded-lg text-xs text-red-200">
            {actionError}
          </div>
        )}

        {/* Video Player */}
        <div className="bg-black rounded-xl overflow-hidden border border-slate-800 shadow-inner">
          <div className="relative aspect-video flex items-center justify-center">
            {event.clip_id ? (
              <video
                ref={videoRef}
                data-testid="event-clip-player"
                controls
                playsInline
                preload="metadata"
                src={api.getEventClipUrl(event.id)}
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="text-center p-6 text-slate-500 text-sm">
                No recorded video clip available for this event.
              </div>
            )}
          </div>

          {/* Timeline & Pre-roll control bar */}
          {event.clip_id && (
            <div className="px-4 py-2.5 bg-slate-950/90 border-t border-slate-800 flex items-center justify-between text-xs text-slate-300">
              <div className="flex items-center space-x-2">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse"></span>
                <span className="font-medium text-amber-400">Trigger Point: 15s (15s pre-roll + 20s hold)</span>
              </div>
              <button
                type="button"
                onClick={jumpToTrigger}
                className="px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded font-medium transition-colors"
              >
                Jump to Trigger (15s)
              </button>
            </div>
          )}
        </div>

        {/* Keyframe Thumbnails */}
        {event.clip_id && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2.5">
              Key Frames
            </h3>
            <div className="grid grid-cols-3 gap-3">
              {(['first', 'anchor', 'last'] as const).map((label) => (
                <div
                  key={label}
                  className="bg-slate-950 border border-slate-800 rounded-lg overflow-hidden group hover:border-slate-700 transition-colors"
                >
                  <div className="relative aspect-video bg-slate-900 flex items-center justify-center">
                    <img
                      src={api.getEventKeyframeUrl(event.id, label)}
                      alt={`${label} keyframe`}
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                      }}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="px-2 py-1 bg-slate-900/90 border-t border-slate-800 text-[10px] uppercase font-mono text-center text-slate-400">
                    {label === 'anchor' ? 'Trigger (Anchor)' : `${label} frame`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Event Metadata & Subject Attributes */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2.5">
              Location & Details
            </h4>
            <dl className="space-y-1.5 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800/50">
                <dt className="text-slate-400">Camera:</dt>
                <dd className="text-slate-200 font-medium">{event.camera_name || event.camera_id}</dd>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/50">
                <dt className="text-slate-400">Zone:</dt>
                <dd className="text-slate-200 font-medium">{event.zone_name || event.zone_id || 'Global'}</dd>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/50">
                <dt className="text-slate-400">Confidence:</dt>
                <dd className="text-slate-200 font-mono">
                  {event.confidence ? `${Math.round(event.confidence * 100)}%` : 'N/A'}
                </dd>
              </div>
              <div className="flex justify-between py-1">
                <dt className="text-slate-400">Status:</dt>
                <dd className="font-semibold text-slate-200 uppercase text-[11px]">{event.status}</dd>
              </div>
            </dl>
          </div>

          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2.5">
              Subject Attributes
            </h4>
            {event.subject && Object.keys(event.subject).length > 0 ? (
              <dl className="space-y-1.5 text-xs">
                {Object.entries(event.subject).map(([k, v]) => (
                  <div key={k} className="flex justify-between py-1 border-b border-slate-800/50 last:border-0">
                    <dt className="text-slate-400 capitalize">{k.replace(/_/g, ' ')}:</dt>
                    <dd className="text-amber-400 font-mono font-medium">
                      {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-xs text-slate-500 italic py-2">No subject attributes recorded</p>
            )}
          </div>
        </div>
      </div>

      {/* Footer Actions */}
      <div className="px-6 py-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
        <div className="text-xs text-slate-400 font-mono">
          ID: {event.id}
        </div>
        <div className="flex items-center space-x-3">
          {event.status === 'open' && (
            <>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => setIsFalseAlarmDialogOpen(true)}
                className="px-4 py-2 bg-red-950 hover:bg-red-900 text-red-300 hover:text-white rounded-lg border border-red-800/80 text-xs font-semibold transition-colors disabled:opacity-50"
              >
                Mark False Alarm
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={handleAcknowledge}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-lg text-xs font-semibold shadow-md hover:shadow-amber-500/20 transition-all disabled:opacity-50"
              >
                {actionLoading ? 'Saving...' : 'Acknowledge'}
              </button>
            </>
          )}
          {event.status !== 'open' && (
            <span className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 text-slate-400 font-medium capitalize">
              {event.status.replace(/_/g, ' ')}
            </span>
          )}
        </div>
      </div>

      {/* False Alarm Modal Dialog */}
      {isFalseAlarmDialogOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-base font-semibold text-white mb-2">Mark as False Alarm</h3>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Please provide a clear reason for marking this event as a false alarm. This feedback will be audited and used to tune future detection accuracy.
            </p>
            <form onSubmit={handleMarkFalseAlarm} className="space-y-4">
              <textarea
                value={falseAlarmReason}
                onChange={(e) => setFalseAlarmReason(e.target.value)}
                placeholder="e.g. Shadows or camera reflection caused erroneous vehicle detection"
                rows={3}
                required
                className="w-full p-3 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
              <div className="flex justify-end space-x-2">
                <button
                  type="button"
                  onClick={() => setIsFalseAlarmDialogOpen(false)}
                  className="px-3.5 py-1.5 text-xs text-slate-400 hover:text-white rounded-lg bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !falseAlarmReason.trim()}
                  className="px-3.5 py-1.5 text-xs font-semibold text-white bg-red-600 hover:bg-red-500 rounded-lg disabled:opacity-50"
                >
                  Confirm False Alarm
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

