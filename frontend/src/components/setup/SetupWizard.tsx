import React, { useEffect, useState } from 'react';
import { useCameras } from '../../context/CamerasContext';
import { api } from '../../services/api';
import type {
  CalendarExemption,
  Direction,
  RegisteredActionSpec,
  RulePresetsResponse,
  Zone,
  ZoneKind,
  ZoneShape,
} from '../../types';
import { flipDirection, validateZonePoints } from '../../utils/geometry';
import { DryRunTimeline } from './DryRunTimeline';
import { RuleBuilder } from './RuleBuilder';
import { ZoneCanvas } from './ZoneCanvas';

interface SetupWizardProps {
  onCompleted?: () => void;
}

type WizardStep = 1 | 2 | 3 | 4;

export const SetupWizard: React.FC<SetupWizardProps> = ({ onCompleted }) => {
  const { cameras, refreshCameras } = useCameras();

  // Wizard state
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);
  const [selectedCameraId, setSelectedCameraId] = useState<string>('');

  // Step 1: Camera Features
  const [featureVehicles, setFeatureVehicles] = useState<boolean>(true);
  const [featureIdCheck, setFeatureIdCheck] = useState<boolean>(false);
  const [savingFeatures, setSavingFeatures] = useState<boolean>(false);

  // Step 2: Zone geometry & kind
  const [zoneName, setZoneName] = useState<string>('Main Gate Entrance');
  const [zoneKind, setZoneKind] = useState<ZoneKind>('special');
  const [zoneShape, setZoneShape] = useState<ZoneShape>('polygon');
  const [zoneDirection, setZoneDirection] = useState<Direction>('in');
  const [isReadArea, setIsReadArea] = useState<boolean>(false);
  const [points, setPoints] = useState<[number, number][]>([
    [0.15, 0.2],
    [0.85, 0.2],
    [0.85, 0.8],
    [0.15, 0.8],
  ]);
  const [existingZones, setExistingZones] = useState<Zone[]>([]);
  const [savedZone, setSavedZone] = useState<Zone | null>(null);

  // Step 3: Rule Builder
  const [templatesData, setTemplatesData] = useState<RulePresetsResponse | null>(null);
  const [calendarExemptions, setCalendarExemptions] = useState<CalendarExemption[]>([]);
  const [spec, setSpec] = useState<RegisteredActionSpec>({
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
    response: {
      severity: 'critical',
      pre_roll_s: 15,
      hold_s: 20,
      max_clip_min: 15,
      cooldown_s: 300,
      alert_ttl_min: 240,
      escalation: [],
    },
  });

  // Step 4: Dry Run & Arm
  const [isSavingRule, setIsSavingRule] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Select first camera if available
  useEffect(() => {
    if (cameras.length > 0 && !selectedCameraId) {
      setSelectedCameraId(cameras[0].id);
      setFeatureVehicles(cameras[0].features?.vehicles ?? true);
      setFeatureIdCheck(cameras[0].features?.id_check ?? false);
    }
  }, [cameras, selectedCameraId]);

  // Load existing zones for selected camera
  useEffect(() => {
    if (selectedCameraId) {
      api
        .listZones(selectedCameraId)
        .then(setExistingZones)
        .catch((err) => console.warn('Failed to load existing zones:', err));
    }
  }, [selectedCameraId]);

  // Load templates and calendar exemptions
  useEffect(() => {
    api
      .getRuleTemplates()
      .then(setTemplatesData)
      .catch((err) => console.warn('Failed to load rule templates:', err));
    api
      .listCalendarExemptions()
      .then(setCalendarExemptions)
      .catch((err) => console.warn('Failed to load calendar exemptions:', err));
  }, []);

  const handleCameraChange = (camId: string) => {
    setSelectedCameraId(camId);
    const cam = cameras.find((c) => c.id === camId);
    if (cam) {
      setFeatureVehicles(cam.features?.vehicles ?? true);
      setFeatureIdCheck(cam.features?.id_check ?? false);
    }
    setSavedZone(null);
  };

  const handleSaveCameraFeatures = async () => {
    if (!selectedCameraId) return;
    setSavingFeatures(true);
    setStatusMessage(null);
    try {
      await api.updateCamera(selectedCameraId, {
        features: {
          vehicles: featureVehicles,
          id_check: featureIdCheck,
        },
      });
      await refreshCameras();
      setCurrentStep(2);
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err?.message || 'Failed to update camera features' });
    } finally {
      setSavingFeatures(false);
    }
  };

  const handleSaveZone = async () => {
    const val = validateZonePoints(zoneShape, points);
    if (!val.valid) {
      setStatusMessage({ type: 'error', text: val.error || 'Invalid zone geometry' });
      return;
    }

    setStatusMessage(null);
    try {
      const created = await api.createZone(selectedCameraId, {
        name: zoneName.trim() || 'New Zone',
        kind: zoneKind,
        shape: zoneShape,
        points,
        direction: zoneShape === 'line' ? zoneDirection : null,
        is_read_area: zoneKind === 'normal' && isReadArea,
        enabled: true,
      });
      setSavedZone(created);
      setExistingZones((prev) => [...prev, created]);

      if (zoneKind === 'normal') {
        setStatusMessage({
          type: 'success',
          text: `Normal zone '${created.name}' created successfully. Normal zones only record sightings and cannot take rules.`,
        });
      } else {
        // Move to Rule Builder for special zone
        setCurrentStep(3);
      }
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err?.message || 'Failed to save zone' });
    }
  };

  const handleSaveRule = async (arm: boolean) => {
    if (!savedZone) {
      setStatusMessage({ type: 'error', text: 'Zone must be saved before arming rule' });
      return;
    }

    setIsSavingRule(true);
    setStatusMessage(null);
    try {
      const actionPayload = {
        ...spec,
      };
      const createdAction = await api.createAction(savedZone.id, actionPayload);
      if (!arm) {
        await api.updateAction(createdAction.id, { enabled: false });
      }

      setStatusMessage({
        type: 'success',
        text: `Rule '${createdAction.name}' successfully ${arm ? 'saved & armed (Active)' : 'saved (Paused)'}!`,
      });

      if (onCompleted) {
        setTimeout(onCompleted, 1500);
      }
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err?.message || 'Failed to save rule' });
    } finally {
      setIsSavingRule(false);
    }
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 space-y-6" data-testid="setup-wizard">
      {/* Wizard Step Progression Bar */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-5">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <div>
            <h2 className="text-base font-bold text-white tracking-wide">Camera &amp; Zone Setup Wizard</h2>
            <p className="text-xs text-slate-400">
              Configure camera placement, draw normal/special zones, registered actions, and dry-run simulation
            </p>
          </div>
        </div>

        {/* Step Numbers */}
        <div className="flex items-center space-x-2">
          {[
            { num: 1, label: 'Features' },
            { num: 2, label: 'Draw Zone' },
            { num: 3, label: 'Rule Builder' },
            { num: 4, label: 'Dry Run & Arm' },
          ].map((s) => {
            const isActive = currentStep === s.num;
            const isCompleted = currentStep > s.num;
            return (
              <button
                key={s.num}
                type="button"
                onClick={() => {
                  if (s.num <= 2 || savedZone) setCurrentStep(s.num as WizardStep);
                }}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  isActive
                    ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                    : isCompleted
                    ? 'bg-slate-800 text-emerald-400 border border-emerald-500/30'
                    : 'bg-slate-950 text-slate-500 border border-slate-800'
                }`}
              >
                <span>{isCompleted ? '✓' : s.num}.</span>
                <span>{s.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Status Messages */}
      {statusMessage && (
        <div
          className={`p-3.5 rounded-xl border text-xs flex items-center justify-between ${
            statusMessage.type === 'error'
              ? 'bg-red-950/50 border-red-800/80 text-red-300'
              : 'bg-emerald-950/50 border-emerald-800/80 text-emerald-300'
          }`}
          data-testid="status-message"
        >
          <span>{statusMessage.text}</span>
          <button
            type="button"
            onClick={() => setStatusMessage(null)}
            className="text-xs opacity-70 hover:opacity-100"
          >
            &times;
          </button>
        </div>
      )}

      {/* STEP 1: Camera & Feature Switches */}
      {currentStep === 1 && (
        <div className="space-y-6" data-testid="wizard-step-1">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Left: Camera Picker & Switches */}
            <div className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-200 block mb-1.5">Select Target Camera</label>
                <select
                  value={selectedCameraId}
                  onChange={(e) => handleCameraChange(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
                  data-testid="select-camera"
                >
                  {cameras.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.id}) — {c.status}
                    </option>
                  ))}
                </select>
              </div>

              {/* Feature Switches per docs/08 s4 */}
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Feature Switches for this Camera
                </h3>

                {/* Switch 1: Vehicle Detection */}
                <div className="flex items-start justify-between">
                  <div className="pr-4">
                    <span className="text-xs font-semibold text-slate-200 block">1. Vehicle Detection</span>
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
                      Detects cars, trucks, buses, bikes. Enables plate extraction, category identification, and vehicle rules.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={featureVehicles}
                    onChange={(e) => setFeatureVehicles(e.target.checked)}
                    className="w-5 h-5 rounded text-amber-500 focus:ring-amber-500 bg-slate-900 border-slate-700 cursor-pointer"
                    data-testid="switch-vehicles"
                  />
                </div>

                <div className="h-[1px] bg-slate-800" />

                {/* Switch 2: ID-Card Check */}
                <div className="flex items-start justify-between">
                  <div className="pr-4">
                    <span className="text-xs font-semibold text-slate-200 block">2. ID-Card Physical Check</span>
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
                      Alerts when a person is confidently not wearing a visible ID card. Requires clear torso line-of-sight.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={featureIdCheck}
                    onChange={(e) => setFeatureIdCheck(e.target.checked)}
                    className="w-5 h-5 rounded text-amber-500 focus:ring-amber-500 bg-slate-900 border-slate-700 cursor-pointer"
                    data-testid="switch-id-check"
                  />
                </div>
              </div>
            </div>

            {/* Right: Camera Placement Tips & Constraints */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-5 space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center space-x-2">
                <span>Camera Placement &amp; Accuracy Constraints</span>
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Plates and ID cards depend on camera position and resolution more than on code. Ensure the camera satisfies:
              </p>
              <ul className="text-xs text-slate-400 space-y-2 list-disc list-inside">
                <li>
                  <strong className="text-slate-200">Vehicle &amp; Plate Angle:</strong> Max 20-30° horizontal angle.
                  Plates must be at least 120-150px wide for reliable OCR.
                </li>
                <li>
                  <strong className="text-slate-200">ID-Card Check Placement:</strong> Mount camera at chest height
                  (1.4-1.8m) at turnstiles/entrances with subjects walking forward.
                </li>
                <li>
                  <strong className="text-slate-200">Unknown is a Valid State:</strong> When attributes are unclear or
                  occluded, the system holds state as <em>unknown</em> rather than guessing.
                </li>
              </ul>
            </div>
          </div>

          <div className="flex justify-end pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={handleSaveCameraFeatures}
              disabled={savingFeatures || !selectedCameraId}
              className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold rounded-xl shadow-md shadow-amber-500/20 transition-all flex items-center space-x-2"
              data-testid="btn-next-step-1"
            >
              <span>Continue to Draw Zones →</span>
            </button>
          </div>
        </div>
      )}

      {/* STEP 2: Draw Zones on Snapshot */}
      {currentStep === 2 && (
        <div className="space-y-6" data-testid="wizard-step-2">
          {/* Controls Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 bg-slate-950 border border-slate-800 rounded-xl p-4">
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">Zone Name</label>
              <input
                type="text"
                value={zoneName}
                onChange={(e) => setZoneName(e.target.value)}
                placeholder="e.g. Loading Bay"
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-amber-500"
                data-testid="input-zone-name"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">Zone Kind</label>
              <select
                value={zoneKind}
                onChange={(e) => setZoneKind(e.target.value as ZoneKind)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-amber-500"
                data-testid="select-zone-kind"
              >
                <option value="special">Special (Can have registered actions &amp; alerts)</option>
                <option value="normal">Normal (Just record who passes)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">Shape Tool</label>
              <div className="flex space-x-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setZoneShape('polygon');
                    if (points.length < 3) {
                      setPoints([
                        [0.2, 0.2],
                        [0.8, 0.2],
                        [0.8, 0.8],
                        [0.2, 0.8],
                      ]);
                    }
                  }}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                    zoneShape === 'polygon'
                      ? 'bg-amber-500 text-slate-950 border-amber-400'
                      : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                  }`}
                  data-testid="btn-shape-polygon"
                >
                  Polygon
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setZoneShape('line');
                    setPoints([
                      [0.2, 0.5],
                      [0.8, 0.5],
                    ]);
                  }}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                    zoneShape === 'line'
                      ? 'bg-amber-500 text-slate-950 border-amber-400'
                      : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                  }`}
                  data-testid="btn-shape-line"
                >
                  Line
                </button>
              </div>
            </div>

            {/* Shape-specific actions */}
            <div className="flex items-end space-x-2">
              {zoneShape === 'line' ? (
                <button
                  type="button"
                  onClick={() => setZoneDirection(flipDirection(zoneDirection))}
                  className="w-full py-1.5 px-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-xs text-slate-200 border border-slate-800 font-semibold flex items-center justify-center space-x-1"
                  data-testid="btn-flip-direction"
                >
                  <span>Flip:</span>
                  <strong className="text-amber-400 uppercase">{zoneDirection}</strong>
                </button>
              ) : zoneKind === 'normal' ? (
                <label className="flex items-center space-x-2 text-xs text-slate-300 py-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isReadArea}
                    onChange={(e) => setIsReadArea(e.target.checked)}
                    className="rounded text-blue-500 focus:ring-blue-500 bg-slate-900 border-slate-700"
                  />
                  <span>Use as plate read area</span>
                </label>
              ) : (
                <div className="text-[11px] text-slate-400 py-1.5">Click canvas to place points</div>
              )}

              <button
                type="button"
                onClick={() => {
                  if (points.length > 1) {
                    setPoints(points.slice(0, -1));
                  }
                }}
                className="py-1.5 px-3 rounded-lg bg-slate-900 hover:bg-slate-800 text-xs text-slate-300 border border-slate-800"
                title="Undo last point"
                data-testid="btn-undo-point"
              >
                Undo
              </button>
              <button
                type="button"
                onClick={() => setPoints([])}
                className="py-1.5 px-3 rounded-lg bg-slate-900 hover:bg-slate-800 text-xs text-slate-300 border border-slate-800"
                title="Clear all points"
                data-testid="btn-clear-points"
              >
                Clear
              </button>
            </div>
          </div>

          {/* Interactive Canvas */}
          <ZoneCanvas
            snapshotUrl={selectedCameraId ? api.getSnapshotUrl(selectedCameraId) : undefined}
            shape={zoneShape}
            kind={zoneKind}
            direction={zoneDirection}
            existingZones={existingZones}
            points={points}
            onPointsChange={setPoints}
            frameWidth={cameras.find((c) => c.id === selectedCameraId)?.width}
            frameHeight={cameras.find((c) => c.id === selectedCameraId)?.height}
          />

          {/* Enforcement Notice: Normal vs Special Gating */}
          {zoneKind === 'normal' ? (
            <div className="p-4 bg-blue-950/30 border border-blue-900/60 rounded-xl flex items-start space-x-3 text-xs text-blue-200">
              <svg className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <strong className="font-semibold block mb-0.5">Normal Zone Rule Gating (Enforced)</strong>
                <p className="text-blue-300/80 leading-relaxed">
                  Normal zones only record sightings and traffic metrics. They cannot hold registered actions or trigger
                  alerts. Selecting a Normal zone hides the Rule Builder and completes the zone setup immediately upon saving.
                </p>
              </div>
            </div>
          ) : (
            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-center space-x-2.5 text-xs text-amber-300">
              <svg className="w-4 h-4 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>
                Special zone selected: will proceed to registered actions (rule builder) after saving geometry.
              </span>
            </div>
          )}

          {/* Footer Navigation */}
          <div className="flex items-center justify-between pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setCurrentStep(1)}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg"
            >
              ← Back to Features
            </button>

            <button
              type="button"
              onClick={handleSaveZone}
              className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold rounded-xl shadow-md shadow-amber-500/20 transition-all"
              data-testid="btn-save-zone"
            >
              {zoneKind === 'normal' ? 'Save Normal Zone & Finish' : 'Save Special Zone & Build Rule →'}
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: Registered Action & Rule Builder (Special zones only) */}
      {currentStep === 3 && (
        <div className="space-y-6" data-testid="wizard-step-3">
          {savedZone && savedZone.kind === 'normal' ? (
            <div className="p-6 bg-slate-950 border border-slate-800 rounded-2xl text-center space-y-3">
              <div className="w-12 h-12 rounded-xl bg-blue-900/30 text-blue-400 flex items-center justify-center mx-auto">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h3 className="text-sm font-bold text-white">Rule Builder is Disabled for Normal Zones</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                As per specification docs/04 and docs/08, normal zones cannot hold registered actions or trigger alerts.
              </p>
              <button
                type="button"
                onClick={() => setCurrentStep(2)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg"
              >
                Return to Zone Geometry
              </button>
            </div>
          ) : (
            <>
              <RuleBuilder
                zoneName={savedZone?.name || zoneName}
                zoneShape={savedZone?.shape || zoneShape}
                initialSpec={spec}
                templatesData={templatesData}
                calendarExemptions={calendarExemptions}
                onSpecChange={setSpec}
              />

              <div className="flex items-center justify-between pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setCurrentStep(2)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg"
                >
                  ← Back to Zone Drawing
                </button>

                <button
                  type="button"
                  onClick={() => setCurrentStep(4)}
                  className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold rounded-xl shadow-md shadow-amber-500/20 transition-all"
                  data-testid="btn-next-step-3"
                >
                  Proceed to Dry Run &amp; Arm →
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* STEP 4: Dry Run & Arm */}
      {currentStep === 4 && (
        <div className="space-y-6" data-testid="wizard-step-4">
          <DryRunTimeline
            zoneId={savedZone?.id || 'draft_zone'}
            spec={spec}
            onDryRunComplete={() => {
              setStatusMessage({
                type: 'success',
                text: 'Dry run completed successfully with timeline markers.',
              });
            }}
          />

          {/* Action Arm Buttons */}
          <div className="flex items-center justify-between pt-4 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setCurrentStep(3)}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg"
            >
              ← Edit Rule Conditions
            </button>

            <div className="flex items-center space-x-3">
              <button
                type="button"
                onClick={() => handleSaveRule(false)}
                disabled={isSavingRule}
                className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition-all"
                data-testid="btn-save-paused"
              >
                Save as Paused (Inactive)
              </button>

              <button
                type="button"
                onClick={() => handleSaveRule(true)}
                disabled={isSavingRule}
                className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl shadow-md shadow-emerald-600/25 transition-all flex items-center space-x-2"
                data-testid="btn-save-and-arm"
              >
                {isSavingRule ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>Arming...</span>
                  </>
                ) : (
                  <>
                    <span>⚡ Save and Arm Rule (Active)</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
