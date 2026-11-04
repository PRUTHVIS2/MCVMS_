import React, { useState } from 'react';
import type { AlertSeverity, CalendarExemption, RegisteredActionSpec, RulePresetsResponse } from '../../types';
import { generateRuleSentence } from '../../utils/sentenceGenerator';

interface RuleBuilderProps {
  zoneName: string;
  zoneShape: 'polygon' | 'line';
  initialSpec?: RegisteredActionSpec;
  templatesData?: RulePresetsResponse | null;
  calendarExemptions?: CalendarExemption[];
  onSpecChange: (spec: RegisteredActionSpec) => void;
}

const DEFAULT_SPEC: RegisteredActionSpec = {
  name: 'No heavy vehicles during restricted hours',
  subject: {
    kind: 'vehicle',
    where: [{ attr: 'heavy', op: 'eq', value: true }],
    min_box_px: 80,
  },
  trigger: {
    template: 'presence',
    min_seconds: 2,
  },
  confirm: {
    n_of_m: [4, 5],
    min_confidence: 0.6,
  },
  schedule: {
    days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
    from: '09:00',
    to: '17:00',
    timezone: 'Asia/Kolkata',
  },
  valid: {
    from_date: '2026-10-01',
    until_date: null,
  },
  exemptions: {
    calendar_ids: [],
    note: '',
  },
  response: {
    severity: 'critical',
    pre_roll_s: 15,
    hold_s: 20,
    max_clip_min: 15,
    cooldown_s: 300,
    alert_ttl_min: 240,
    escalation: [],
  },
};

const DAYS_OF_WEEK = [
  { id: 'mon', label: 'Mon' },
  { id: 'tue', label: 'Tue' },
  { id: 'wed', label: 'Wed' },
  { id: 'thu', label: 'Thu' },
  { id: 'fri', label: 'Fri' },
  { id: 'sat', label: 'Sat' },
  { id: 'sun', label: 'Sun' },
];

export const RuleBuilder: React.FC<RuleBuilderProps> = ({
  zoneName,
  zoneShape,
  initialSpec,
  templatesData,
  calendarExemptions = [],
  onSpecChange,
}) => {
  const [spec, setSpec] = useState<RegisteredActionSpec>(initialSpec || DEFAULT_SPEC);

  const updateSpec = (updater: (prev: RegisteredActionSpec) => RegisteredActionSpec) => {
    setSpec((prev) => {
      const next = updater(prev);
      onSpecChange(next);
      return next;
    });
  };

  // Apply one of the 6 standard presets from docs/08 s4
  const applyPreset = (presetKey: string) => {
    if (templatesData?.presets && templatesData.presets[presetKey]) {
      const p = templatesData.presets[presetKey];
      updateSpec(() => ({ ...p }));
      return;
    }

    // Built-in presets fallback
    if (presetKey === 'heavy_vehicle') {
      updateSpec(() => ({
        name: 'No heavy vehicles during college hours',
        subject: {
          kind: 'vehicle',
          where: [{ attr: 'heavy', op: 'eq', value: true }],
          min_box_px: 80,
        },
        trigger: {
          template: 'presence',
          min_seconds: 2,
        },
        confirm: { n_of_m: [4, 5], min_confidence: 0.6 },
        schedule: {
          days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
          from: '09:00',
          to: '17:00',
          timezone: 'Asia/Kolkata',
        },
        valid: { from_date: '2026-10-01', until_date: null },
        exemptions: { calendar_ids: [], note: '' },
        response: {
          severity: 'critical',
          pre_roll_s: 15,
          hold_s: 20,
          max_clip_min: 15,
          cooldown_s: 300,
          alert_ttl_min: 240,
          escalation: [],
        },
      }));
    } else if (presetKey === 'unregistered_vehicle') {
      updateSpec(() => ({
        name: 'Unregistered vehicle in zone',
        subject: {
          kind: 'vehicle',
          where: [{ attr: 'registry_status', op: 'eq', value: 'unregistered' }],
          min_box_px: 80,
        },
        trigger: {
          template: 'dwell',
          dwell_seconds: 60,
        },
        confirm: { n_of_m: [3, 4], min_confidence: 0.6 },
        schedule: {
          days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
          from: '00:00',
          to: '23:59',
          timezone: 'Asia/Kolkata',
        },
        response: {
          severity: 'medium',
          pre_roll_s: 15,
          hold_s: 20,
          max_clip_min: 15,
          cooldown_s: 300,
          alert_ttl_min: 240,
          escalation: [],
        },
      }));
    } else if (presetKey === 'vehicle_dwell') {
      updateSpec(() => ({
        name: 'Vehicle stays too long',
        subject: { kind: 'vehicle', min_box_px: 80 },
        trigger: { template: 'dwell', dwell_seconds: 120 },
        confirm: { n_of_m: [3, 4], min_confidence: 0.5 },
        response: {
          severity: 'low',
          pre_roll_s: 15,
          hold_s: 20,
          max_clip_min: 15,
          cooldown_s: 300,
          alert_ttl_min: 180,
          escalation: [],
        },
      }));
    } else if (presetKey === 'vehicle_count') {
      updateSpec(() => ({
        name: 'Vehicle count above threshold',
        subject: { kind: 'vehicle', min_box_px: 80 },
        trigger: { template: 'count_threshold', count_threshold: 5 },
        confirm: { n_of_m: [3, 4], min_confidence: 0.6 },
        response: {
          severity: 'medium',
          pre_roll_s: 15,
          hold_s: 20,
          max_clip_min: 15,
          cooldown_s: 300,
          alert_ttl_min: 180,
          escalation: [],
        },
      }));
    } else if (presetKey === 'line_crossing') {
      updateSpec(() => ({
        name: 'Vehicle crosses line',
        subject: { kind: 'vehicle', min_box_px: 80 },
        trigger: { template: 'line_crossing' },
        confirm: { n_of_m: [2, 3], min_confidence: 0.6 },
        response: {
          severity: 'critical',
          pre_roll_s: 15,
          hold_s: 20,
          max_clip_min: 15,
          cooldown_s: 180,
          alert_ttl_min: 120,
          escalation: [],
        },
      }));
    } else if (presetKey === 'person_no_id') {
      updateSpec(() => ({
        name: 'Person without visible ID card',
        subject: {
          kind: 'person',
          where: [{ attr: 'id_state', op: 'eq', value: 'not_wearing' }],
          min_box_px: 100,
        },
        trigger: { template: 'presence', min_seconds: 1 },
        confirm: { n_of_m: [4, 5], min_confidence: 0.7 },
        response: {
          severity: 'critical',
          pre_roll_s: 15,
          hold_s: 20,
          max_clip_min: 15,
          cooldown_s: 180,
          alert_ttl_min: 240,
          escalation: [],
        },
      }));
    }
  };

  const toggleDay = (dayId: string) => {
    updateSpec((prev) => {
      const currentDays = prev.schedule?.days || [];
      const nextDays = currentDays.includes(dayId)
        ? currentDays.filter((d) => d !== dayId)
        : [...currentDays, dayId];
      return {
        ...prev,
        schedule: {
          ...prev.schedule,
          days: nextDays,
          from: prev.schedule?.from || '09:00',
          to: prev.schedule?.to || '17:00',
          timezone: 'Asia/Kolkata',
        },
      };
    });
  };

  const addEscalationRow = () => {
    updateSpec((prev) => ({
      ...prev,
      response: {
        ...prev.response,
        escalation: [
          ...(prev.response.escalation || []),
          {
            if_count_in_window: { n: 5, window_min: 10 },
            severity: 'critical',
          },
        ],
      },
    }));
  };

  const removeEscalationRow = (idx: number) => {
    updateSpec((prev) => ({
      ...prev,
      response: {
        ...prev.response,
        escalation: (prev.response.escalation || []).filter((_, i) => i !== idx),
      },
    }));
  };

  const toggleCalendarExemption = (calId: string) => {
    updateSpec((prev) => {
      const currentEx = prev.exemptions?.calendar_ids || [];
      const nextEx = currentEx.includes(calId) ? currentEx.filter((id) => id !== calId) : [...currentEx, calId];
      return {
        ...prev,
        exemptions: {
          ...prev.exemptions,
          calendar_ids: nextEx,
        },
      };
    });
  };

  const liveSentence = generateRuleSentence(spec, zoneName || 'Current Zone');

  return (
    <div className="space-y-6" data-testid="rule-builder">
      {/* Live Plain-Language Sentence Summary Banner */}
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 shadow-sm flex items-start space-x-3">
        <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0 mt-0.5">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div>
          <span className="text-[10px] uppercase font-bold tracking-wider text-amber-400 block mb-1">
            Live Rule Sentence (Plain English)
          </span>
          <p className="text-sm font-medium text-slate-100 leading-snug" data-testid="live-sentence-summary">
            {liveSentence}
          </p>
        </div>
      </div>

      {/* Presets Quick Picker */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-slate-300 block">Choose a Quick Preset</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <button
            type="button"
            onClick={() => applyPreset('heavy_vehicle')}
            className="p-2.5 rounded-lg text-left bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 transition-all text-xs text-slate-200 flex flex-col justify-between"
            data-testid="preset-heavy-vehicle"
          >
            <span className="font-semibold text-amber-400 flex items-center">
              <span className="mr-1.5">🚛</span> Heavy vehicle in zone
            </span>
            <span className="text-[10px] text-slate-400 mt-1">Truck/bus, Mon-Sat 09-17, Critical</span>
          </button>

          <button
            type="button"
            onClick={() => applyPreset('unregistered_vehicle')}
            className="p-2.5 rounded-lg text-left bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 transition-all text-xs text-slate-200 flex flex-col justify-between"
          >
            <span className="font-semibold text-blue-400 flex items-center">
              <span className="mr-1.5">🚗</span> Unregistered vehicle
            </span>
            <span className="text-[10px] text-slate-400 mt-1">Registry unknown, Dwell 60s, Medium</span>
          </button>

          <button
            type="button"
            onClick={() => applyPreset('vehicle_dwell')}
            className="p-2.5 rounded-lg text-left bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 transition-all text-xs text-slate-200 flex flex-col justify-between"
          >
            <span className="font-semibold text-emerald-400 flex items-center">
              <span className="mr-1.5">⏱️</span> Vehicle stays too long
            </span>
            <span className="text-[10px] text-slate-400 mt-1">Dwell 120s, Low</span>
          </button>

          <button
            type="button"
            onClick={() => applyPreset('vehicle_count')}
            className="p-2.5 rounded-lg text-left bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 transition-all text-xs text-slate-200 flex flex-col justify-between"
          >
            <span className="font-semibold text-purple-400 flex items-center">
              <span className="mr-1.5">🔢</span> Vehicle count above N
            </span>
            <span className="text-[10px] text-slate-400 mt-1">Occupancy threshold &gt; 5, Medium</span>
          </button>

          <button
            type="button"
            onClick={() => applyPreset('line_crossing')}
            className="p-2.5 rounded-lg text-left bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 transition-all text-xs text-slate-200 flex flex-col justify-between"
          >
            <span className="font-semibold text-rose-400 flex items-center">
              <span className="mr-1.5">⚡</span> Vehicle crosses line
            </span>
            <span className="text-[10px] text-slate-400 mt-1">Line crossing orientation, Critical</span>
          </button>

          <button
            type="button"
            onClick={() => applyPreset('person_no_id')}
            className="p-2.5 rounded-lg text-left bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 transition-all text-xs text-slate-200 flex flex-col justify-between"
          >
            <span className="font-semibold text-red-400 flex items-center">
              <span className="mr-1.5">🪪</span> Person without visible ID
            </span>
            <span className="text-[10px] text-slate-400 mt-1">ID card missing, Presence 1s, Critical</span>
          </button>
        </div>
      </div>

      {/* Basic Rule Details */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-semibold text-slate-300 block mb-1.5">Rule Name</label>
          <input
            type="text"
            value={spec.name}
            onChange={(e) => updateSpec((p) => ({ ...p, name: e.target.value }))}
            className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-amber-500"
            data-testid="input-rule-name"
          />
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-300 block mb-1.5">Severity</label>
          <div className="flex space-x-2">
            {(['low', 'medium', 'critical'] as AlertSeverity[]).map((sev) => {
              const isSelected = spec.response.severity === sev;
              const color =
                sev === 'critical'
                  ? 'border-red-500 bg-red-950/40 text-red-300'
                  : sev === 'medium'
                  ? 'border-amber-500 bg-amber-950/40 text-amber-300'
                  : 'border-blue-500 bg-blue-950/40 text-blue-300';
              return (
                <button
                  key={sev}
                  type="button"
                  onClick={() =>
                    updateSpec((p) => ({
                      ...p,
                      response: { ...p.response, severity: sev },
                    }))
                  }
                  className={`flex-1 py-2 px-3 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all ${
                    isSelected ? color : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
                  }`}
                  data-testid={`severity-btn-${sev}`}
                >
                  {sev}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Subject & Conditions */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center justify-between">
          <span>1. What to Look For (Subject & Conditions)</span>
          <span className="text-[10px] text-slate-400 lowercase font-normal">pure logic evaluation</span>
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Subject Kind</label>
            <select
              value={spec.subject.kind}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  subject: {
                    ...p.subject,
                    kind: e.target.value as 'vehicle' | 'person',
                    where: [],
                  },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="vehicle">Vehicle</option>
              <option value="person">Person</option>
            </select>
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Trigger Template</label>
            <select
              value={spec.trigger.template}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  trigger: {
                    ...p.trigger,
                    template: e.target.value as any,
                  },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="presence" disabled={zoneShape === 'line'}>
                Presence (Inside Polygon)
              </option>
              <option value="dwell" disabled={zoneShape === 'line'}>
                Dwell (Inside Polygon)
              </option>
              <option value="count_threshold" disabled={zoneShape === 'line'}>
                Count Threshold
              </option>
              <option value="line_crossing" disabled={zoneShape === 'polygon'}>
                Line Crossing
              </option>
            </select>
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">
              {spec.trigger.template === 'dwell'
                ? 'Dwell Seconds'
                : spec.trigger.template === 'count_threshold'
                ? 'Vehicle Count'
                : 'Min Seconds (Sustained)'}
            </label>
            <input
              type="number"
              min={0}
              value={
                spec.trigger.template === 'dwell'
                  ? spec.trigger.dwell_seconds ?? 60
                  : spec.trigger.template === 'count_threshold'
                  ? spec.trigger.count_threshold ?? 5
                  : spec.trigger.min_seconds ?? 2
              }
              onChange={(e) => {
                const val = Number(e.target.value);
                updateSpec((p) => ({
                  ...p,
                  trigger: {
                    ...p.trigger,
                    ...(spec.trigger.template === 'dwell'
                      ? { dwell_seconds: val }
                      : spec.trigger.template === 'count_threshold'
                      ? { count_threshold: val }
                      : { min_seconds: val }),
                  },
                }));
              }}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>
      </div>

      {/* Armed Schedule */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center justify-between">
          <span>2. Armed Schedule</span>
          <span className="text-[10px] text-amber-400 font-mono">Asia/Kolkata (+05:30)</span>
        </h4>

        <div>
          <label className="text-[11px] text-slate-400 block mb-1.5">Active Days</label>
          <div className="flex flex-wrap gap-1.5">
            {DAYS_OF_WEEK.map((d) => {
              const active = (spec.schedule?.days || []).includes(d.id);
              return (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => toggleDay(d.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                    active
                      ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-sm'
                      : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                  }`}
                  data-testid={`day-${d.id}`}
                >
                  {d.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">From Time</label>
            <input
              type="time"
              value={spec.schedule?.from || '09:00'}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  schedule: { ...p.schedule, from: e.target.value },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
              data-testid="input-from-time"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">To Time</label>
            <input
              type="time"
              value={spec.schedule?.to || '17:00'}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  schedule: { ...p.schedule, to: e.target.value },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
              data-testid="input-to-time"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Active From Date</label>
            <input
              type="date"
              value={spec.valid?.from_date || ''}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  valid: { ...p.valid, from_date: e.target.value || null },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Active Until Date</label>
            <input
              type="date"
              value={spec.valid?.until_date || ''}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  valid: { ...p.valid, until_date: e.target.value || null },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>
      </div>

      {/* Escalation Rows & Special Cases */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            3. Escalation Rows &amp; Cooldown
          </h4>
          <button
            type="button"
            onClick={addEscalationRow}
            className="text-xs text-amber-400 hover:text-amber-300 font-semibold"
          >
            + Add Escalation
          </button>
        </div>

        {(spec.response.escalation || []).map((row, idx) => (
          <div key={idx} className="flex items-center space-x-2 bg-slate-900 p-2.5 rounded-lg border border-slate-800">
            <span className="text-xs text-slate-400">If</span>
            <input
              type="number"
              min={1}
              value={row.if_count_in_window.n}
              onChange={(e) => {
                const val = Number(e.target.value);
                updateSpec((p) => {
                  const esc = [...(p.response.escalation || [])];
                  esc[idx].if_count_in_window.n = val;
                  return { ...p, response: { ...p.response, escalation: esc } };
                });
              }}
              className="w-16 bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 text-center"
            />
            <span className="text-xs text-slate-400">events in</span>
            <input
              type="number"
              min={1}
              value={row.if_count_in_window.window_min}
              onChange={(e) => {
                const val = Number(e.target.value);
                updateSpec((p) => {
                  const esc = [...(p.response.escalation || [])];
                  esc[idx].if_count_in_window.window_min = val;
                  return { ...p, response: { ...p.response, escalation: esc } };
                });
              }}
              className="w-16 bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 text-center"
            />
            <span className="text-xs text-slate-400">minutes, escalate to</span>
            <select
              value={row.severity}
              onChange={(e) => {
                const val = e.target.value as AlertSeverity;
                updateSpec((p) => {
                  const esc = [...(p.response.escalation || [])];
                  esc[idx].severity = val;
                  return { ...p, response: { ...p.response, escalation: esc } };
                });
              }}
              className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="critical">Critical</option>
            </select>
            <button
              type="button"
              onClick={() => removeEscalationRow(idx)}
              className="text-red-400 hover:text-red-300 p-1"
              title="Remove row"
            >
              &times;
            </button>
          </div>
        ))}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Cooldown (sec)</label>
            <input
              type="number"
              value={spec.response.cooldown_s ?? 300}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  response: { ...p.response, cooldown_s: Number(e.target.value) },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Alert Expiry (min)</label>
            <input
              type="number"
              value={spec.response.alert_ttl_min ?? 240}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  response: { ...p.response, alert_ttl_min: Number(e.target.value) },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Pre-roll Clip (sec)</label>
            <input
              type="number"
              value={spec.response.pre_roll_s ?? 15}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  response: { ...p.response, pre_roll_s: Number(e.target.value) },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Hold Clip (sec)</label>
            <input
              type="number"
              value={spec.response.hold_s ?? 20}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  response: { ...p.response, hold_s: Number(e.target.value) },
                }))
              }
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200"
            />
          </div>
        </div>
      </div>

      {/* Calendar Exemptions Selection */}
      {calendarExemptions.length > 0 && (
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-2">
          <label className="text-xs font-bold uppercase tracking-wider text-slate-300 block">
            Calendar Exemptions (Ignore on these dates)
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {calendarExemptions.map((cal) => {
              const isChecked = (spec.exemptions?.calendar_ids || []).includes(cal.id);
              return (
                <label
                  key={cal.id}
                  className="flex items-center space-x-2 text-xs text-slate-300 bg-slate-900 p-2 rounded-lg border border-slate-800 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleCalendarExemption(cal.id)}
                    className="rounded text-amber-500 focus:ring-amber-500 bg-slate-950 border-slate-700"
                  />
                  <span>
                    <strong>{cal.label}</strong> ({cal.date_from} to {cal.date_to})
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

