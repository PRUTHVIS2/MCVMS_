import React, { useEffect, useState } from 'react';
import { useCameras } from '../../context/CamerasContext';
import { api } from '../../services/api';
import type { CalendarExemption } from '../../types';

export const CalendarExemptionsEditor: React.FC = () => {
  const { cameras } = useCameras();
  const [exemptions, setExemptions] = useState<CalendarExemption[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Form state
  const [label, setLabel] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [scope, setScope] = useState<'all' | 'camera' | 'action'>('all');
  const [targetCameraId, setTargetCameraId] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const loadExemptions = async () => {
    try {
      setLoading(true);
      const list = await api.listCalendarExemptions();
      setExemptions(list);
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to load calendar exemptions' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadExemptions();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!label.trim() || !dateFrom || !dateTo) {
      setMessage({ type: 'error', text: 'Label, Date From, and Date To are required.' });
      return;
    }

    setIsSubmitting(true);
    setMessage(null);
    try {
      const created = await api.createCalendarExemption({
        label: label.trim(),
        date_from: dateFrom,
        date_to: dateTo,
        scope,
        camera_id: scope === 'camera' ? targetCameraId || null : null,
      });

      setExemptions((prev) => [...prev, created]);
      setLabel('');
      setDateFrom('');
      setDateTo('');
      setScope('all');
      setMessage({ type: 'success', text: `Calendar exemption '${created.label}' created successfully.` });
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to create calendar exemption' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string, labelText: string) => {
    if (!window.confirm(`Delete calendar exemption '${labelText}'?`)) return;
    try {
      await api.deleteCalendarExemption(id);
      setExemptions((prev) => prev.filter((ex) => ex.id !== id));
      setMessage({ type: 'success', text: `Exemption '${labelText}' deleted.` });
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to delete exemption' });
    }
  };

  return (
    <div className="space-y-6" data-testid="calendar-exemptions-editor">
      {/* Header */}
      <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Calendar Exemptions Editor</h3>
        <p className="text-xs text-slate-400 mt-0.5">
          Define special-case calendar dates (holidays, exams, festivals) where rules are automatically disarmed or exempted
        </p>
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

      {/* Add New Exemption Form */}
      <form onSubmit={handleCreate} className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-4">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">Add New Calendar Exemption</h4>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div className="sm:col-span-2">
            <label className="text-[11px] text-slate-400 block mb-1">Exemption Label / Reason</label>
            <input
              type="text"
              placeholder="e.g. Annual College Sports Day"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-amber-500"
              data-testid="input-exemption-label"
              required
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Date From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-amber-500"
              data-testid="input-date-from"
              required
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Date To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-amber-500"
              data-testid="input-date-to"
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Scope</label>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as any)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-amber-500"
            >
              <option value="all">All Rules (Global)</option>
              <option value="camera">Specific Camera</option>
            </select>
          </div>

          {scope === 'camera' && (
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Target Camera</label>
              <select
                value={targetCameraId}
                onChange={(e) => setTargetCameraId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-amber-500"
              >
                <option value="">Select camera...</option>
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold rounded-lg shadow-sm transition-all"
              data-testid="btn-add-exemption"
            >
              {isSubmitting ? 'Adding...' : '+ Add Exemption'}
            </button>
          </div>
        </div>
      </form>

      {/* Table of Exemptions */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-500 font-mono">Loading exemptions...</div>
        ) : exemptions.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No calendar exemptions registered yet. Rules will execute on their regular daily schedules.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="px-4 py-3">Exemption Label</th>
                  <th className="px-4 py-3">Dates (Inclusive)</th>
                  <th className="px-4 py-3">Scope</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {exemptions.map((ex) => (
                  <tr key={ex.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 font-semibold text-slate-200">{ex.label}</td>
                    <td className="px-4 py-3 font-mono text-slate-300">
                      {ex.date_from} → {ex.date_to}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-amber-400">
                        {ex.scope}
                      </span>
                      {ex.camera_id && <span className="text-slate-400 ml-1.5">({ex.camera_id})</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleDelete(ex.id, ex.label)}
                        className="p-1 rounded text-slate-400 hover:text-red-400 hover:bg-slate-800 transition-colors"
                        title="Delete exemption"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

