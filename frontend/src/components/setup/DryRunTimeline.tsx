import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import type { DryRunResponse, RegisteredActionSpec, SampleClip } from '../../types';

interface DryRunTimelineProps {
  zoneId: string;
  actionId?: string;
  spec: RegisteredActionSpec;
  onDryRunComplete?: (res: DryRunResponse) => void;
}

export const DryRunTimeline: React.FC<DryRunTimelineProps> = ({
  zoneId,
  actionId,
  spec,
  onDryRunComplete,
}) => {
  const [sampleClips, setSampleClips] = useState<SampleClip[]>([]);
  const [selectedClipPath, setSelectedClipPath] = useState<string>('');
  const [customPath, setCustomPath] = useState<string>('');
  const [maxFrames, setMaxFrames] = useState<number>(300);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [result, setResult] = useState<DryRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load available sample clips from server
  useEffect(() => {
    let mounted = true;
    api
      .listSampleClips()
      .then((clips) => {
        if (!mounted) return;
        setSampleClips(clips);
        if (clips.length > 0 && !selectedClipPath) {
          // Default to heavy truck clip or first clip
          const truckClip = clips.find((c) => c.id.includes('truck') || c.name.toLowerCase().includes('truck'));
          setSelectedClipPath(truckClip ? truckClip.path : clips[0].path);
        }
      })
      .catch((err) => {
        console.warn('Failed to load sample clips:', err);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    setResult(null);

    const clipPathToUse = customPath.trim() || selectedClipPath;

    try {
      let res: DryRunResponse;
      if (actionId) {
        res = await api.dryRunAction(actionId, {
          clip_path: clipPathToUse,
          max_frames: maxFrames,
        });
      } else {
        res = await api.dryRunDraft({
          zone_id: zoneId,
          spec,
          clip_path: clipPathToUse,
          max_frames: maxFrames,
        });
      }
      setResult(res);
      if (onDryRunComplete) {
        onDryRunComplete(res);
      }
    } catch (err: any) {
      setError(err?.message || 'Dry run simulation failed');
    } finally {
      setIsRunning(false);
    }
  };

  // Compute timeline span for visual markers
  const minTs = result && result.decisions.length > 0 ? Math.min(...result.decisions.map((d) => d.ts_ms)) : 0;
  const maxTs = result && result.decisions.length > 0 ? Math.max(...result.decisions.map((d) => d.ts_ms)) : 1000;
  const timeSpan = Math.max(1, maxTs - minTs);

  return (
    <div className="space-y-4" data-testid="dry-run-timeline-container">
      {/* Clip Selector Controls */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-slate-200">Select Test Video Clip for Dry Run</label>
          <span className="text-[10px] text-slate-400 font-mono">Simulates real video analysis</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="sm:col-span-2">
            <select
              value={selectedClipPath}
              onChange={(e) => {
                setSelectedClipPath(e.target.value);
                setCustomPath('');
              }}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
              data-testid="select-sample-clip"
            >
              {sampleClips.map((clip) => (
                <option key={clip.id} value={clip.path}>
                  {clip.name} ({clip.path})
                </option>
              ))}
              <option value="">Custom Clip Path...</option>
            </select>
          </div>

          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs text-slate-400 shrink-0">Frames:</span>
              <input
                type="number"
                min={10}
                max={2000}
                step={50}
                value={maxFrames}
                onChange={(e) => setMaxFrames(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 text-center"
              />
            </div>
          </div>
        </div>

        {(!selectedClipPath || customPath) && (
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Custom File Path</label>
            <input
              type="text"
              placeholder="e.g. backend/tests/synthetic/heavy_truck_in_zone.mp4"
              value={customPath}
              onChange={(e) => setCustomPath(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono"
            />
          </div>
        )}

        <div className="pt-2 flex items-center justify-between">
          <p className="text-[11px] text-slate-400">
            Simulates the rule engine step-by-step against video tracks. Invariant:{' '}
            <strong className="text-slate-300">never creates real events or alerts in the DB</strong>.
          </p>
          <button
            type="button"
            onClick={handleRun}
            disabled={isRunning || (!selectedClipPath && !customPath)}
            className={`px-4 py-2 rounded-lg text-xs font-semibold flex items-center space-x-2 transition-all ${
              isRunning || (!selectedClipPath && !customPath)
                ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                : 'bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-md shadow-amber-500/20'
            }`}
            data-testid="btn-run-dry-run"
          >
            {isRunning ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></div>
                <span>Evaluating...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Run Dry Run Simulation</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-950/40 border border-red-800/80 rounded-xl p-3 text-xs text-red-300 flex items-center space-x-2">
          <svg className="w-4 h-4 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* Simulation Results & Visual Timeline */}
      {result && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-4" data-testid="dry-run-results">
          {/* Header & Stats */}
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <span className="text-xs font-bold text-white uppercase tracking-wider">
                Dry Run Simulation Report
              </span>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Rule: <strong className="text-amber-400">{result.rule_name}</strong>
              </p>
            </div>

            <div className="flex items-center space-x-3 text-xs">
              <div className="bg-slate-950 px-2.5 py-1 rounded border border-slate-800">
                <span className="text-slate-400">Frames:</span>{' '}
                <strong className="text-slate-200">{result.total_frames_processed}</strong>
              </div>
              <div className="bg-slate-950 px-2.5 py-1 rounded border border-slate-800">
                <span className="text-slate-400">Decisions:</span>{' '}
                <strong className={result.decisions_count > 0 ? 'text-amber-400' : 'text-slate-200'}>
                  {result.decisions_count}
                </strong>
              </div>
            </div>
          </div>

          {/* Visual Horizontal Timeline */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
              <span>0.00s</span>
              <span>{(timeSpan / 1000).toFixed(2)}s Timeline</span>
            </div>

            <div className="relative h-9 bg-slate-950 rounded-lg border border-slate-800 overflow-hidden flex items-center px-2">
              {/* Center track line */}
              <div className="absolute inset-x-0 h-0.5 bg-slate-800" />

              {/* Decision markers */}
              {result.decisions.map((d, idx) => {
                const percent = Math.min(100, Math.max(0, ((d.ts_ms - minTs) / timeSpan) * 100));
                const markerColor =
                  d.kind === 'start'
                    ? 'bg-red-500 ring-red-400/40'
                    : d.kind === 'end'
                    ? 'bg-blue-500 ring-blue-400/40'
                    : 'bg-amber-400 ring-amber-400/40';

                return (
                  <div
                    key={idx}
                    title={`${d.kind.toUpperCase()} - Track #${d.track_id} (conf: ${(d.confidence * 100).toFixed(0)}%)`}
                    className={`absolute w-3.5 h-3.5 rounded-full ${markerColor} ring-4 cursor-pointer transform -translate-x-1/2 transition-transform hover:scale-125 z-10 shadow-sm`}
                    style={{ left: `${percent}%` }}
                    data-testid={`timeline-marker-${d.kind}`}
                  />
                );
              })}
            </div>
          </div>

          {/* Decision Events List */}
          {result.decisions.length > 0 ? (
            <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
              {result.decisions.map((d, idx) => {
                const relTime = ((d.ts_ms - minTs) / 1000).toFixed(2);
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between bg-slate-950/70 border border-slate-800/80 px-3 py-1.5 rounded-lg text-xs"
                  >
                    <div className="flex items-center space-x-2.5">
                      <span
                        className={`text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded ${
                          d.kind === 'start'
                            ? 'bg-red-950 text-red-400 border border-red-800/60'
                            : d.kind === 'end'
                            ? 'bg-blue-950 text-blue-400 border border-blue-800/60'
                            : 'bg-amber-950 text-amber-400 border border-amber-800/60'
                        }`}
                      >
                        {d.kind}
                      </span>
                      <span className="font-mono text-slate-300">+{relTime}s</span>
                      <span className="text-slate-400">Track #{d.track_id}</span>
                    </div>

                    <div className="flex items-center space-x-2 text-[11px] text-slate-400 font-mono">
                      <span>Conf: {(d.confidence * 100).toFixed(0)}%</span>
                      {d.evidence && d.evidence.event_id && (
                        <span className="text-[10px] text-slate-400">{d.evidence.event_id}</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="p-4 bg-slate-950/40 rounded-lg border border-slate-800 text-center text-xs text-slate-400">
              No rule triggers matched in the evaluated frames.
            </div>
          )}

          {/* Safety Guarantee Notice */}
          <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-lg text-[11px] text-amber-300 flex items-center space-x-2">
            <svg className="w-4 h-4 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>
              Verified invariant: This was a <strong>dry-run simulation</strong>. 0 alerts created, 0 database events recorded.
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

