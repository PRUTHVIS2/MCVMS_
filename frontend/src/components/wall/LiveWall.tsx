import React, { useState } from 'react';
import { useCameras } from '../../context/CamerasContext';
import { CameraTile } from './CameraTile';

type GridLayout = 'auto' | '1x1' | '2x2' | '3x3';

export const LiveWall: React.FC = () => {
  const { cameras, loading, refreshCameras } = useCameras();
  const [layout, setLayout] = useState<GridLayout>('auto');
  const [focusedCameraId, setFocusedCameraId] = useState<string | null>(null);

  const onlineCount = cameras.filter((c) => c.status === 'online').length;
  const offlineCount = cameras.filter((c) => c.status === 'offline').length;

  const getGridClasses = () => {
    if (focusedCameraId) {
      return 'grid-cols-1';
    }

    switch (layout) {
      case '1x1':
        return 'grid-cols-1 max-w-4xl mx-auto';
      case '2x2':
        return 'grid-cols-1 md:grid-cols-2';
      case '3x3':
        return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3';
      case 'auto':
      default:
        if (cameras.length <= 1) return 'grid-cols-1 max-w-4xl mx-auto';
        if (cameras.length === 2) return 'grid-cols-1 md:grid-cols-2';
        if (cameras.length <= 4) return 'grid-cols-1 sm:grid-cols-2';
        return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4';
    }
  };

  const displayedCameras = focusedCameraId
    ? cameras.filter((c) => c.id === focusedCameraId)
    : cameras;

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Wall Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/90 border border-slate-800 p-3 rounded-xl shadow-md">
        {/* Left: Status Counts */}
        <div className="flex items-center space-x-3 text-xs">
          <div className="flex items-center space-x-1.5 font-medium text-slate-200">
            <span className="w-2 h-2 rounded-full bg-slate-400"></span>
            <span>{cameras.length} Cameras</span>
          </div>
          <span className="text-slate-600">|</span>
          <div className="flex items-center space-x-1.5 font-medium text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span>{onlineCount} Online</span>
          </div>
          {offlineCount > 0 && (
            <>
              <span className="text-slate-600">|</span>
              <div className="flex items-center space-x-1.5 font-medium text-red-400">
                <span className="w-2 h-2 rounded-full bg-red-500"></span>
                <span>{offlineCount} Offline</span>
              </div>
            </>
          )}
        </div>

        {/* Right: Layout Switcher + Controls */}
        <div className="flex items-center space-x-2">
          {focusedCameraId && (
            <button
              type="button"
              onClick={() => setFocusedCameraId(null)}
              className="px-2.5 py-1 text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30 rounded-lg hover:bg-amber-500/20 transition-colors flex items-center space-x-1"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              <span>Back to Wall</span>
            </button>
          )}

          {/* Grid Layout Buttons */}
          <div className="hidden sm:inline-flex bg-slate-950 p-0.5 rounded-lg border border-slate-800 text-xs">
            {(['auto', '1x1', '2x2', '3x3'] as GridLayout[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => {
                  setLayout(mode);
                  setFocusedCameraId(null);
                }}
                className={`px-2.5 py-1 rounded-md transition-colors uppercase font-mono text-[11px] ${
                  layout === mode && !focusedCameraId
                    ? 'bg-amber-500 text-slate-950 font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={refreshCameras}
            title="Refresh Cameras"
            className="p-1.5 bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg border border-slate-700 transition-colors"
            aria-label="Refresh Cameras"
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin text-amber-400' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {/* Grid Container */}
      {cameras.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center p-12 bg-slate-900/50 border border-slate-800/80 rounded-2xl text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-800 flex items-center justify-center text-slate-400 mb-3 border border-slate-700">
            <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-white">No Cameras Configured</h3>
          <p className="text-xs text-slate-400 max-w-sm mt-1">
            Add cameras in the Setup page or assign cameras to this account to begin monitoring.
          </p>
        </div>
      ) : (
        <div className={`grid gap-4 flex-1 ${getGridClasses()}`}>
          {displayedCameras.map((camera) => (
            <CameraTile
              key={camera.id}
              camera={camera}
              isFocused={focusedCameraId === camera.id}
              onToggleFocus={() => {
                setFocusedCameraId(focusedCameraId === camera.id ? null : camera.id);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
};

