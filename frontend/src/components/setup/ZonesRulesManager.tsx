import React, { useEffect, useState } from 'react';
import { useCameras } from '../../context/CamerasContext';
import { api } from '../../services/api';
import type { ActionItem, Zone } from '../../types';
import { formatScheduleDays } from '../../utils/sentenceGenerator';

export const ZonesRulesManager: React.FC = () => {
  const { cameras } = useCameras();
  const [selectedCameraId, setSelectedCameraId] = useState<string>('');
  const [zones, setZones] = useState<Zone[]>([]);
  const [actionsMap, setActionsMap] = useState<Record<string, ActionItem[]>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (cameras.length > 0 && !selectedCameraId) {
      setSelectedCameraId(cameras[0].id);
    }
  }, [cameras, selectedCameraId]);

  const loadZonesAndActions = async (camId: string) => {
    if (!camId) return;
    setLoading(true);
    try {
      const zList = await api.listZones(camId);
      setZones(zList);

      const aMap: Record<string, ActionItem[]> = {};
      for (const z of zList) {
        if (z.kind === 'special') {
          try {
            const acts = await api.listActions(z.id);
            aMap[z.id] = acts;
          } catch {
            aMap[z.id] = [];
          }
        }
      }
      setActionsMap(aMap);
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to load zones and actions' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCameraId) {
      loadZonesAndActions(selectedCameraId);
    }
  }, [selectedCameraId]);

  const toggleActionEnabled = async (action: ActionItem) => {
    try {
      const updated = await api.updateAction(action.id, { enabled: !action.enabled });
      setActionsMap((prev) => ({
        ...prev,
        [action.zone_id]: (prev[action.zone_id] || []).map((a) => (a.id === action.id ? updated : a)),
      }));
      setMessage({
        type: 'success',
        text: `Rule '${action.name}' is now ${updated.enabled ? 'Active (Armed)' : 'Paused'}.`,
      });
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to toggle rule state' });
    }
  };

  const deleteAction = async (actionId: string, zoneId: string) => {
    if (!window.confirm('Are you sure you want to delete this registered action?')) return;
    try {
      await api.deleteAction(actionId);
      setActionsMap((prev) => ({
        ...prev,
        [zoneId]: (prev[zoneId] || []).filter((a) => a.id !== actionId),
      }));
      setMessage({ type: 'success', text: 'Action successfully deleted.' });
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to delete action' });
    }
  };

  const deleteZone = async (zone: Zone) => {
    const attachedActions = actionsMap[zone.id] || [];
    if (
      attachedActions.length > 0 &&
      !window.confirm(
        `Zone '${zone.name}' has ${attachedActions.length} attached registered rule(s). Deleting the zone will also delete all attached rules. Proceed?`
      )
    ) {
      return;
    } else if (
      attachedActions.length === 0 &&
      !window.confirm(`Are you sure you want to delete zone '${zone.name}'?`)
    ) {
      return;
    }

    try {
      await api.deleteZone(zone.id);
      setZones((prev) => prev.filter((z) => z.id !== zone.id));
      setMessage({ type: 'success', text: `Zone '${zone.name}' successfully deleted.` });
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to delete zone' });
    }
  };

  return (
    <div className="space-y-6" data-testid="zones-rules-manager">
      {/* Header and Camera Picker */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-4 rounded-xl">
        <div>
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Zones &amp; Rules Manager</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Audit, pause/resume, edit, or remove configured zones and registered actions
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400 shrink-0">Camera:</span>
          <select
            value={selectedCameraId}
            onChange={(e) => setSelectedCameraId(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
          >
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.id})
              </option>
            ))}
          </select>
        </div>
      </div>

      {message && (
        <div
          className={`p-3 rounded-xl border text-xs flex items-center justify-between ${
            message.type === 'error'
              ? 'bg-red-950/50 border-red-800/80 text-red-300'
              : 'bg-emerald-950/50 border-emerald-800/80 text-emerald-300'
          }`}
        >
          <span>{message.text}</span>
          <button type="button" onClick={() => setMessage(null)} className="text-xs opacity-75 hover:opacity-100">
            &times;
          </button>
        </div>
      )}

      {loading ? (
        <div className="p-12 text-center text-xs text-slate-500 font-mono">
          Loading configured zones and rules...
        </div>
      ) : zones.length === 0 ? (
        <div className="p-12 text-center bg-slate-900/40 border border-slate-800 rounded-2xl">
          <p className="text-xs text-slate-400">No zones configured for this camera yet.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {zones.map((zone) => {
            const actions = actionsMap[zone.id] || [];
            return (
              <div
                key={zone.id}
                className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-4"
                data-testid={`zone-card-${zone.id}`}
              >
                {/* Zone Header */}
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center space-x-2.5">
                      <span className="text-sm font-bold text-white">{zone.name}</span>
                      <span
                        className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border ${
                          zone.kind === 'special'
                            ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                            : 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                        }`}
                      >
                        {zone.kind} Zone
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono px-2 py-0.5 rounded bg-slate-950 border border-slate-800">
                        {zone.shape} ({zone.points.length} pts)
                      </span>
                      {zone.is_read_area && (
                        <span className="text-[10px] bg-purple-950 text-purple-300 border border-purple-800 px-1.5 py-0.5 rounded">
                          Plate Read Area
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-slate-400 font-mono mt-1 block">ID: {zone.id}</span>
                  </div>

                  <button
                    type="button"
                    onClick={() => deleteZone(zone)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-slate-800 transition-colors"
                    title="Delete zone"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>

                {/* Attached Actions / Rules */}
                <div className="pt-2 border-t border-slate-800/80">
                  {zone.kind === 'normal' ? (
                    <p className="text-[11px] text-slate-400 italic">
                      Normal zones record traffic metrics and vehicle sightings only. No rules or alerts can be attached.
                    </p>
                  ) : actions.length === 0 ? (
                    <p className="text-[11px] text-slate-400 italic">
                      Special zone active with 0 registered actions configured.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block mb-1">
                        Attached Registered Actions ({actions.length})
                      </span>

                      {actions.map((act) => {
                        const schedDays = formatScheduleDays(act.spec.schedule?.days);
                        return (
                          <div
                            key={act.id}
                            className="bg-slate-950 border border-slate-800 rounded-lg p-3 flex items-center justify-between"
                          >
                            <div className="space-y-1">
                              <div className="flex items-center space-x-2">
                                <span className="text-xs font-semibold text-slate-100">{act.name}</span>
                                <span
                                  className={`text-[9px] uppercase font-bold px-1.5 py-0.2 rounded border ${
                                    act.severity === 'critical'
                                      ? 'bg-red-950 text-red-300 border-red-800/60'
                                      : act.severity === 'medium'
                                      ? 'bg-amber-950 text-amber-300 border-amber-800/60'
                                      : 'bg-blue-950 text-blue-300 border-blue-800/60'
                                  }`}
                                >
                                  {act.severity}
                                </span>
                                <span className="text-[10px] text-slate-400 font-mono">
                                  Template: {act.spec.trigger.template}
                                </span>
                              </div>

                              <div className="flex items-center space-x-3 text-[11px] text-slate-400">
                                <span>
                                  Schedule: {schedDays || 'Daily'} ({act.spec.schedule?.from || '00:00'}-
                                  {act.spec.schedule?.to || '23:59'})
                                </span>
                                <span>&bull;</span>
                                <span>Cooldown: {act.spec.response.cooldown_s ?? 300}s</span>
                              </div>
                            </div>

                            <div className="flex items-center space-x-2">
                              {/* Enable / Pause toggle */}
                              <button
                                type="button"
                                onClick={() => toggleActionEnabled(act)}
                                className={`px-2.5 py-1 rounded text-xs font-semibold border transition-all ${
                                  act.enabled
                                    ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60 hover:bg-emerald-900/60'
                                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
                                }`}
                              >
                                {act.enabled ? 'Active' : 'Paused'}
                              </button>

                              <button
                                type="button"
                                onClick={() => deleteAction(act.id, zone.id)}
                                className="p-1 rounded text-slate-400 hover:text-red-400 hover:bg-slate-900"
                                title="Delete action"
                              >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

