import React, { useEffect, useState } from 'react';
import type { SystemHealth } from '../../types';
import { api } from '../../services/api';
import { formatLocalDateTime } from '../../utils/date';

export const SystemPage: React.FC = () => {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [configSummary, setConfigSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSystemData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthData, summaryData] = await Promise.all([
        api.getSystemHealth(),
        api.getSystemConfigSummary().catch(() => null),
      ]);
      setHealth(healthData);
      setConfigSummary(summaryData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load system health');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSystemData();
    const interval = setInterval(fetchSystemData, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full space-y-6 overflow-y-auto pr-1">
      {/* Header */}
      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-md">
        <div>
          <h2 className="text-base font-semibold text-white tracking-wide">System Health & Metrics</h2>
          <p className="text-xs text-slate-400">
            Real-time infrastructure health, storage utilization, and model constraints.
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {health && (
            <span className="text-xs font-mono text-slate-400">
              Updated: {formatLocalDateTime(health.timestamp)}
            </span>
          )}
          <button
            type="button"
            onClick={fetchSystemData}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            title="Refresh system health"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {loading && !health ? (
        <div className="p-12 text-center text-slate-400 text-xs">
          <span className="animate-spin inline-block w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full mr-2"></span>
          Querying system health and metrics...
        </div>
      ) : error ? (
        <div className="p-6 bg-red-950/80 border border-red-800 rounded-xl text-xs text-red-200">
          {error}
        </div>
      ) : health ? (
        <>
          {/* Top Stat Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Storage / Disk */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md flex flex-col justify-between">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Storage & Data Disk
                </span>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider border ${
                    health.disk.status === 'critical'
                      ? 'bg-red-500/20 text-red-400 border-red-500/40'
                      : health.disk.status === 'warning'
                      ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  }`}
                >
                  {health.disk.status}
                </span>
              </div>
              <div>
                <div className="flex items-baseline justify-between mb-1.5">
                  <span className="text-2xl font-bold text-white font-mono">{health.disk.free_gb} GB</span>
                  <span className="text-xs text-slate-400">free of {health.disk.total_gb} GB</span>
                </div>
                <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      health.disk.status === 'critical'
                        ? 'bg-red-500'
                        : health.disk.status === 'warning'
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                    }`}
                    style={{ width: `${Math.min(100, health.disk.percent_used)}%` }}
                  ></div>
                </div>
                <p className="text-[11px] text-slate-500 mt-2 font-mono">
                  {health.disk.percent_used}% utilized ({health.disk.used_gb} GB used)
                </p>
              </div>
            </div>

            {/* GPU / Inference Engine */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md flex flex-col justify-between">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Inference Device
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/30">
                  {health.gpu?.device ? health.gpu.device.toUpperCase() : (health.gpu?.available ? 'CUDA' : 'CPU')}
                </span>
              </div>
              <div>
                <p className="text-base font-semibold text-white truncate" title={health.gpu.name}>
                  {health.gpu.name}
                </p>
                <div className="flex items-center space-x-2 mt-2">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-500"></span>
                  <span className="text-xs text-slate-300">
                    CUDA Acceleration: {health.gpu.available ? 'Active' : 'Disabled'}
                  </span>
                </div>
                {health.gpu.memory_total_mb > 0 && (
                  <p className="text-[11px] text-slate-400 font-mono mt-1">
                    VRAM: {health.gpu.memory_used_mb} MB / {health.gpu.memory_total_mb} MB
                  </p>
                )}
              </div>
            </div>

            {/* Pipeline & Queues */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md flex flex-col justify-between">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Pipeline Health
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider bg-blue-500/10 text-blue-400 border border-blue-500/30">
                  Supervised
                </span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Cameras Configured:</span>
                  <span className="font-semibold text-white font-mono">{health.cameras.length}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Online Cameras:</span>
                  <span className="font-semibold text-emerald-400 font-mono">
                    {health.cameras.filter((c) => c.status === 'online').length}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-400">Decode Errors:</span>
                  <span className="font-mono text-slate-300">
                    {health.decode_errors ? Object.values(health.decode_errors).reduce((a, b) => a + b, 0) : 0} total
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Camera Status Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
            <div className="px-5 py-3.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <h3 className="text-xs font-semibold text-white uppercase tracking-wider">
                Connected Cameras & Stream Telemetry
              </h3>
              <span className="text-[11px] text-slate-400">
                {health.cameras.length} channels
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300 divide-y divide-slate-800">
                <thead className="bg-slate-950/60 text-slate-400 uppercase font-semibold text-[10px] tracking-wider">
                  <tr>
                    <th scope="col" className="px-5 py-3">Camera Name</th>
                    <th scope="col" className="px-5 py-3">Status</th>
                    <th scope="col" className="px-5 py-3">Resolution</th>
                    <th scope="col" className="px-5 py-3">FPS</th>
                    <th scope="col" className="px-5 py-3">Features</th>
                    <th scope="col" className="px-5 py-3">Decode Issues</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {health.cameras.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-5 py-3.5 font-medium text-white">
                        {c.name}
                        <span className="block text-[10px] font-mono text-slate-500">{c.id}</span>
                      </td>
                      <td className="px-5 py-3.5 whitespace-nowrap">
                        <span className="inline-flex items-center space-x-1.5">
                          <span
                            className={`w-2 h-2 rounded-full ${
                              c.status === 'online' ? 'bg-emerald-500' : 'bg-red-500'
                            }`}
                          ></span>
                          <span
                            className={`font-semibold uppercase text-[11px] ${
                              c.status === 'online' ? 'text-emerald-400' : 'text-red-400'
                            }`}
                          >
                            {c.status}
                          </span>
                        </span>
                      </td>
                      <td className="px-5 py-3.5 font-mono text-[11px] text-slate-300">
                        {c.width && c.height ? `${c.width}x${c.height}` : '—'}
                      </td>
                      <td className="px-5 py-3.5 font-mono text-[11px] text-slate-300">
                        {c.fps ? `${Math.round(c.fps)} fps` : '—'}
                      </td>
                      <td className="px-5 py-3.5 space-x-1">
                        {c.features?.vehicles && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-amber-500/10 text-amber-400 rounded border border-amber-500/20">
                            Vehicles
                          </span>
                        )}
                        {c.features?.id_check && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/10 text-blue-400 rounded border border-blue-500/20">
                            ID Check
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 font-mono text-[11px] text-slate-400">
                        {(health.decode_errors && health.decode_errors[c.id]) || 0} errors
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Configuration Summary Card */}
          {configSummary && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-md">
              <h3 className="text-xs font-semibold text-white uppercase tracking-wider mb-3">
                Configuration Summary
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4 text-xs">
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-slate-500 text-[10px] uppercase font-semibold block">Timezone</span>
                  <span className="text-amber-400 font-mono font-bold mt-1 block">
                    {configSummary.app?.timezone || 'Asia/Kolkata'}
                  </span>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-slate-500 text-[10px] uppercase font-semibold block">Active Model</span>
                  <span className="text-amber-400 font-mono font-bold mt-1 block">
                    {configSummary.model?.weights || 'yolo11n.pt'}
                  </span>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-slate-500 text-[10px] uppercase font-semibold block">Heavy Vehicles</span>
                  <span className="text-white font-mono font-medium mt-1 block">
                    {configSummary.heavy_categories?.join(', ')}
                  </span>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-slate-500 text-[10px] uppercase font-semibold block">Clip Retry Limit</span>
                  <span className="text-white font-mono font-medium mt-1 block">
                    {configSummary.clips?.retry_limit || 5} attempts
                  </span>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-slate-500 text-[10px] uppercase font-semibold block">GOP Variance Tolerance</span>
                  <span className="text-white font-mono font-medium mt-1 block">
                    {configSummary.clips?.segment_gap_tolerance_ms || 2500} ms
                  </span>
                </div>
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
};
