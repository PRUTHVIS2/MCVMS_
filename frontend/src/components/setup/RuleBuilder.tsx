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

const SEVERITIES: { id: AlertSeverity; label: string; activeClass: string }[] = [
  { id: 'low', label: 'Low', activeClass: 'border-blue-500 bg-blue-500/20 text-blue-400' },
  { id: 'medium', label: 'Medium', activeClass: 'border-amber-500 bg-amber-500/20 text-amber-400' },
  { id: 'critical', label: 'Critical', activeClass: 'border-red-500 bg-red-500/20 text-red-400' },
];

function isoToDisplay(iso?: string | null): string {
  if (!iso) return '';
  const m = iso.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return `${m[3]}/${m[2]}/${m[1]}`;
  return iso;
}

function displayToIso(dmy?: string | null): string | null {
  if (!dmy || !dmy.trim()) return null;
  const m = dmy.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) {
    const day = m[1].padStart(2, '0');
    const month = m[2].padStart(2, '0');
    const year = m[3];
    return `${year}-${month}-${day}`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(dmy.trim())) {
    return dmy.trim();
  }
  return dmy.trim();
}

export const RuleBuilder: React.FC<RuleBuilderProps> = ({
  zoneName,
  zoneShape,
  initialSpec,
  templatesData,
  calendarExemptions = [],
  onSpecChange,
}) => {
  const [spec, setSpec] = useState<RegisteredActionSpec>(initialSpec || DEFAULT_SPEC);
  const [alwaysArmed, setAlwaysArmed] = useState<boolean>(!spec.schedule);
  const [lastSchedule, setLastSchedule] = useState(
    spec.schedule || {
      days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
      from: '09:00',
      to: '17:00',
      timezone: 'Asia/Kolkata',
    }
  );
  const [selectedPresetKey, setSelectedPresetKey] = useState<string>('heavy_vehicle');

  const updateSpec = (updater: (prev: RegisteredActionSpec) => RegisteredActionSpec) => {
    setSpec((prev) => {
      const next = updater(prev);
      onSpecChange(next);
      return next;
    });
  };

  const applyPreset = (presetKey: string) => {
    setSelectedPresetKey(presetKey);

    if (templatesData?.presets && templatesData.presets[presetKey]) {
      const p = templatesData.presets[presetKey];
      const hasSched = !!p.schedule;
      setAlwaysArmed(!hasSched);
      if (p.schedule) setLastSchedule(p.schedule);
      updateSpec(() => ({ ...p }));
      return;
    }

    if (presetKey === 'heavy_vehicle') {
      const sched = {
        days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
        from: '09:00',
        to: '17:00',
        timezone: 'Asia/Kolkata',
      };
      setAlwaysArmed(false);
      setLastSchedule(sched);
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
        schedule: sched,
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
      const sched = {
        days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
        from: '00:00',
        to: '23:59',
        timezone: 'Asia/Kolkata',
      };
      setAlwaysArmed(false);
      setLastSchedule(sched);
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
        schedule: sched,
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
      setAlwaysArmed(true);
      updateSpec(() => ({
        name: 'Vehicle stays too long',
        subject: { kind: 'vehicle', min_box_px: 80 },
        trigger: { template: 'dwell', dwell_seconds: 120 },
        confirm: { n_of_m: [3, 4], min_confidence: 0.5 },
        schedule: null,
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
      setAlwaysArmed(true);
      updateSpec(() => ({
        name: 'Vehicle count above threshold',
        subject: { kind: 'vehicle', min_box_px: 80 },
        trigger: { template: 'count_threshold', count_threshold: 5 },
        confirm: { n_of_m: [3, 4], min_confidence: 0.6 },
        schedule: null,
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
      setAlwaysArmed(true);
      updateSpec(() => ({
        name: 'Vehicle crosses line',
        subject: { kind: 'vehicle', min_box_px: 80 },
        trigger: { template: 'line_crossing' },
        confirm: { n_of_m: [2, 3], min_confidence: 0.6 },
        schedule: null,
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
      setAlwaysArmed(true);
      updateSpec(() => ({
        name: 'Person without visible ID card',
        subject: {
          kind: 'person',
          where: [{ attr: 'id_state', op: 'eq', value: 'not_wearing' }],
          min_box_px: 150,
        },
        trigger: { template: 'presence', min_seconds: 1 },
        confirm: { n_of_m: [4, 5], min_confidence: 0.6 },
        schedule: null,
        response: {
          severity: 'low',
          pre_roll_s: 15,
          hold_s: 20,
          max_clip_min: 15,
          cooldown_s: 60,
          alert_ttl_min: 120,
          escalation: [
            { if_count_in_window: { n: 5, window_min: 10 }, severity: 'medium' },
          ],
        },
      }));
    }
  };

  const handleAlwaysArmedToggle = (checked: boolean) => {
    setAlwaysArmed(checked);
    if (checked) {
      if (spec.schedule) {
        setLastSchedule(spec.schedule);
      }
      updateSpec((p) => ({ ...p, schedule: null }));
    } else {
      const restored = lastSchedule || {
        days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
        from: '09:00',
        to: '17:00',
        timezone: 'Asia/Kolkata',
      };
      updateSpec((p) => ({ ...p, schedule: restored }));
    }
  };

  const toggleDay = (dayId: string) => {
    updateSpec((prev) => {
      const currentDays = prev.schedule?.days || [];
      const nextDays = currentDays.includes(dayId)
        ? currentDays.filter((d) => d !== dayId)
        : [...currentDays, dayId];
      const sched = {
        ...prev.schedule,
        days: nextDays,
        from: prev.schedule?.from || '09:00',
        to: prev.schedule?.to || '17:00',
        timezone: 'Asia/Kolkata',
      };
      setLastSchedule(sched);
      return {
        ...prev,
        schedule: sched,
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
    <div className="space-y-4" data-testid="rule-builder">
      {/* Top Bar: Start from preset */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex-1">
          <label htmlFor="select-preset" className="text-xs font-medium text-slate-300 block mb-1">
            Start from
          </label>
          <select
            id="select-preset"
            data-testid="select-preset"
            value={selectedPresetKey}
            onChange={(e) => {
              if (e.target.value) {
                applyPreset(e.target.value);
              }
            }}
            className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
          >
            <option value="">Custom rule</option>
            <option value="heavy_vehicle">Heavy vehicle in zone</option>
            <option value="vehicle_dwell" disabled={zoneShape === 'line'}>
              Vehicle stays too long
            </option>
            <option value="vehicle_count" disabled={zoneShape === 'line'}>
              Vehicle count above threshold
            </option>
            <option value="line_crossing" disabled={zoneShape === 'polygon'}>
              Vehicle crosses line
            </option>
            <option value="unregistered_vehicle" disabled>
              Unregistered vehicle in zone (Available after Step 12-13)
            </option>
            <option value="person_no_id" disabled>
              Person without visible ID card (Available after Step 17-18)
            </option>
          </select>
        </div>
      </div>

      {/* Rule Name & Severity */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-slate-300 block mb-1">Rule name</label>
            <input
              type="text"
              value={spec.name}
              onChange={(e) => updateSpec((p) => ({ ...p, name: e.target.value }))}
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
              data-testid="input-rule-name"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-slate-300 block mb-1">Severity</label>
            <div className="flex space-x-2">
              {SEVERITIES.map((sev) => {
                const isSelected = spec.response.severity === sev.id;
                return (
                  <button
                    key={sev.id}
                    type="button"
                    onClick={() =>
                      updateSpec((p) => ({
                        ...p,
                        response: { ...p.response, severity: sev.id },
                      }))
                    }
                    className={`flex-1 py-1.5 px-3 rounded text-xs font-semibold border transition-all ${
                      isSelected
                        ? sev.activeClass
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                    }`}
                    data-testid={`severity-btn-${sev.id}`}
                  >
                    {sev.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Rule Sentence with Inline Controls */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-3">
        <label className="text-xs font-medium text-slate-300 block">Rule sentence</label>
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-200">
          <span className="text-slate-400">Alert when</span>
          <select
            aria-label="Applies to"
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
            className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
          >
            <option value="vehicle">a vehicle</option>
            <option value="person">a person</option>
          </select>

          <select
            aria-label="Alert when"
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
            className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
          >
            <option value="presence" disabled={zoneShape === 'line'}>
              is inside the zone
            </option>
            <option value="dwell" disabled={zoneShape === 'line'}>
              dwells in the zone
            </option>
            <option value="count_threshold" disabled={zoneShape === 'line'}>
              count exceeds threshold
            </option>
            <option value="line_crossing" disabled={zoneShape === 'polygon'}>
              crosses the line
            </option>
          </select>

          {spec.trigger.template === 'dwell' ? (
            <>
              <span className="text-slate-400">longer than</span>
              <input
                aria-label="Dwell duration (seconds)"
                type="number"
                min={1}
                value={spec.trigger.dwell_seconds ?? 60}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  updateSpec((p) => ({
                    ...p,
                    trigger: { ...p.trigger, dwell_seconds: val },
                  }));
                }}
                className="w-16 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 text-center"
              />
              <span className="text-slate-400">seconds</span>
            </>
          ) : spec.trigger.template === 'count_threshold' ? (
            <>
              <span className="text-slate-400">of</span>
              <input
                aria-label="Threshold count"
                type="number"
                min={1}
                value={spec.trigger.count_threshold ?? 5}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  updateSpec((p) => ({
                    ...p,
                    trigger: { ...p.trigger, count_threshold: val },
                  }));
                }}
                className="w-16 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 text-center"
              />
              <span className="text-slate-400">for at least</span>
              <input
                aria-label="for at least N seconds"
                type="number"
                min={0}
                value={spec.trigger.min_seconds ?? 2}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  updateSpec((p) => ({
                    ...p,
                    trigger: { ...p.trigger, min_seconds: val },
                  }));
                }}
                className="w-16 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 text-center"
              />
              <span className="text-slate-400">seconds</span>
            </>
          ) : spec.trigger.template === 'presence' ? (
            <>
              <span className="text-slate-400">for at least</span>
              <input
                aria-label="for at least N seconds"
                type="number"
                min={0}
                value={spec.trigger.min_seconds ?? 2}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  updateSpec((p) => ({
                    ...p,
                    trigger: { ...p.trigger, min_seconds: val },
                  }));
                }}
                className="w-16 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 text-center"
              />
              <span className="text-slate-400">seconds</span>
            </>
          ) : null}
        </div>

        {/* Filter condition (e.g. heavy vehicles) if applicable */}
        {spec.subject.kind === 'vehicle' && (
          <div className="pt-2 border-t border-slate-800 flex items-center gap-2 text-xs text-slate-300">
            <span className="text-slate-400">Filter:</span>
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={spec.subject.where?.some(
                  (w) => w.attr === 'heavy' && (w.value === true || w.value === 'true')
                )}
                onChange={(e) => {
                  const isHeavy = e.target.checked;
                  updateSpec((p) => ({
                    ...p,
                    subject: {
                      ...p.subject,
                      where: isHeavy ? [{ attr: 'heavy', op: 'eq', value: true }] : [],
                    },
                  }));
                }}
                className="rounded text-amber-500 focus:ring-amber-500 bg-slate-950 border-slate-700"
              />
              <span>Heavy vehicles only (truck, bus)</span>
            </label>
          </div>
        )}

        {/* Live plain-text summary sentence below inline controls */}
        <div className="pt-2.5 border-t border-slate-800">
          <span className="text-[11px] font-medium text-slate-400 block mb-0.5">Summary</span>
          <p className="text-xs text-slate-200 font-mono" data-testid="live-sentence-summary">
            {liveSentence}
          </p>
        </div>
      </div>

      {/* Schedule */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-slate-300">Schedule</span>
            <label className="inline-flex items-center gap-1.5 cursor-pointer text-xs text-slate-200">
              <input
                type="checkbox"
                checked={alwaysArmed}
                onChange={(e) => handleAlwaysArmedToggle(e.target.checked)}
                className="rounded text-amber-500 focus:ring-amber-500 bg-slate-950 border-slate-700"
                data-testid="toggle-always-armed"
              />
              <span>Always armed</span>
            </label>
          </div>
          <span className="text-[11px] text-slate-400" data-testid="schedule-clock-help">
            Live cameras evaluate schedules using the server's wall clock (Asia/Kolkata).
          </span>
        </div>

        {!alwaysArmed && (
          <div className="space-y-3 pt-1">
            <div>
              <label className="text-[11px] text-slate-400 block mb-1.5">Active days</label>
              <div className="flex flex-wrap gap-1.5">
                {DAYS_OF_WEEK.map((d) => {
                  const active = (spec.schedule?.days || []).includes(d.id);
                  return (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => toggleDay(d.id)}
                      className={`px-2.5 py-1 rounded text-xs font-semibold border transition-all ${
                        active
                          ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-sm'
                          : 'bg-slate-950 text-slate-400 border-slate-800 hover:border-slate-700'
                      }`}
                      data-testid={`day-${d.id}`}
                    >
                      {d.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">From time (24h)</label>
                <input
                  type="text"
                  placeholder="HH:MM"
                  maxLength={5}
                  value={spec.schedule?.from || '09:00'}
                  onChange={(e) =>
                    updateSpec((p) => ({
                      ...p,
                      schedule: { ...p.schedule, from: e.target.value },
                    }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
                  data-testid="input-from-time"
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">To time (24h)</label>
                <input
                  type="text"
                  placeholder="HH:MM"
                  maxLength={5}
                  value={spec.schedule?.to || '17:00'}
                  onChange={(e) =>
                    updateSpec((p) => ({
                      ...p,
                      schedule: { ...p.schedule, to: e.target.value },
                    }))
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
                  data-testid="input-to-time"
                />
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 pt-1 border-t border-slate-800">
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Active from (optional)</label>
            <input
              type="text"
              placeholder="dd/mm/yyyy"
              maxLength={10}
              value={isoToDisplay(spec.valid?.from_date)}
              onChange={(e) => {
                const iso = displayToIso(e.target.value);
                updateSpec((p) => ({
                  ...p,
                  valid: { ...p.valid, from_date: iso },
                }));
              }}
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Active until (optional)</label>
            <input
              type="text"
              placeholder="dd/mm/yyyy"
              maxLength={10}
              value={isoToDisplay(spec.valid?.until_date)}
              onChange={(e) => {
                const iso = displayToIso(e.target.value);
                updateSpec((p) => ({
                  ...p,
                  valid: { ...p.valid, until_date: iso },
                }));
              }}
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>
      </div>

      {/* Escalation & Limits */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-slate-300">Escalation &amp; cooldown</label>
          <button
            type="button"
            onClick={addEscalationRow}
            className="text-xs text-amber-400 hover:text-amber-300 font-semibold"
          >
            + Add escalation
          </button>
        </div>

        {(spec.response.escalation || []).map((row, idx) => (
          <div key={idx} className="flex items-center space-x-2 bg-slate-950 p-2 rounded border border-slate-800">
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
              className="w-14 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 text-center"
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
              className="w-14 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 text-center"
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
              className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
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

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Cooldown (seconds)</label>
            <input
              type="number"
              value={spec.response.cooldown_s ?? 300}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  response: { ...p.response, cooldown_s: Number(e.target.value) },
                }))
              }
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Alert expiry (minutes)</label>
            <input
              type="number"
              value={spec.response.alert_ttl_min ?? 240}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  response: { ...p.response, alert_ttl_min: Number(e.target.value) },
                }))
              }
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Pre-roll clip (seconds)</label>
            <input
              type="number"
              value={spec.response.pre_roll_s ?? 15}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  response: { ...p.response, pre_roll_s: Number(e.target.value) },
                }))
              }
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Hold clip (seconds)</label>
            <input
              type="number"
              value={spec.response.hold_s ?? 20}
              onChange={(e) =>
                updateSpec((p) => ({
                  ...p,
                  response: { ...p.response, hold_s: Number(e.target.value) },
                }))
              }
              className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200"
            />
          </div>
        </div>
      </div>

      {/* Calendar Exemptions */}
      {calendarExemptions.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-2">
          <label className="text-xs font-medium text-slate-300 block">
            Calendar exemptions (ignore on these dates)
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {calendarExemptions.map((cal) => {
              const isChecked = (spec.exemptions?.calendar_ids || []).includes(cal.id);
              return (
                <label
                  key={cal.id}
                  className="flex items-center space-x-2 text-xs text-slate-300 bg-slate-950 p-2 rounded border border-slate-800 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleCalendarExemption(cal.id)}
                    className="rounded text-amber-500 focus:ring-amber-500 bg-slate-900 border-slate-700"
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
