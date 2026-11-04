import React, { useState } from 'react';
import { useCameras } from '../../context/CamerasContext';
import { api } from '../../services/api';
import type { Camera, CameraFeatures } from '../../types';

interface TestResult {
  status: 'ok' | 'failed';
  width?: number;
  height?: number;
  fps?: number;
  reason?: string;
}

export const CamerasManager: React.FC = () => {
  const { cameras, loading, refreshCameras } = useCameras();

  // Modals & form state
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null);
  const [deletingCamera, setDeletingCamera] = useState<Camera | null>(null);

  // Add form fields
  const [addName, setAddName] = useState<string>('');
  const [addRtsp, setAddRtsp] = useState<string>('');
  const [addFeatures, setAddFeatures] = useState<CameraFeatures>({ vehicles: true, id_check: false });

  // Edit form fields
  const [editName, setEditName] = useState<string>('');
  const [editRtsp, setEditRtsp] = useState<string>('');
  const [editEnabled, setEditEnabled] = useState<boolean>(true);
  const [editFeatures, setEditFeatures] = useState<CameraFeatures>({ vehicles: true, id_check: false });

  // Status & Feedback
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});
  const [testingCamId, setTestingCamId] = useState<string | null>(null);

  const resetAddForm = () => {
    setAddName('');
    setAddRtsp('');
    setAddFeatures({ vehicles: true, id_check: false });
    setShowAddModal(false);
  };

  const handleStartEdit = (cam: Camera) => {
    setEditingCamera(cam);
    setEditName(cam.name);
    setEditRtsp(''); // Leave empty to indicate no change to encrypted URL
    setEditEnabled(cam.enabled);
    setEditFeatures({ ...cam.features });
  };

  const handleCreateCamera = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addName.trim() || !addRtsp.trim()) {
      setMessage({ type: 'error', text: 'Camera Name and RTSP URL are required.' });
      return;
    }

    setActionLoading(true);
    setMessage(null);
    try {
      await api.createCamera({
        name: addName.trim(),
        rtsp_url: addRtsp.trim(),
        features: addFeatures,
      });
      await refreshCameras();
      setMessage({ type: 'success', text: `Camera '${addName}' registered successfully.` });
      resetAddForm();
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to create camera.' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateCamera = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCamera) return;
    if (!editName.trim()) {
      setMessage({ type: 'error', text: 'Camera Name cannot be empty.' });
      return;
    }

    setActionLoading(true);
    setMessage(null);
    try {
      const payload: { name: string; enabled: boolean; features: CameraFeatures; rtsp_url?: string } = {
        name: editName.trim(),
        enabled: editEnabled,
        features: editFeatures,
      };
      if (editRtsp.trim()) {
        payload.rtsp_url = editRtsp.trim();
      }

      await api.updateCamera(editingCamera.id, payload);
      await refreshCameras();
      setMessage({ type: 'success', text: `Camera '${editName}' updated successfully.` });
      setEditingCamera(null);
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to update camera.' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteCamera = async () => {
    if (!deletingCamera) return;
    setActionLoading(true);
    setMessage(null);
    try {
      await api.deleteCamera(deletingCamera.id);
      await refreshCameras();
      setMessage({ type: 'success', text: `Camera '${deletingCamera.name}' deleted.` });
      setDeletingCamera(null);
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to delete camera.' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleEnabled = async (cam: Camera) => {
    try {
      await api.updateCamera(cam.id, { enabled: !cam.enabled });
      await refreshCameras();
      setMessage({
        type: 'success',
        text: `Camera '${cam.name}' is now ${!cam.enabled ? 'Enabled' : 'Disabled'}.`,
      });
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.message || 'Failed to toggle camera state.' });
    }
  };

  const handleTestCamera = async (camId: string) => {
    setTestingCamId(camId);
    try {
      const res = await api.testCamera(camId);
      setTestResults((prev) => ({
        ...prev,
        [camId]: {
          status: res.status === 'ok' ? 'ok' : 'failed',
          width: res.width,
          height: res.height,
          fps: res.fps,
          reason: res.reason,
        },
      }));
      await refreshCameras();
    } catch (err: any) {
      setTestResults((prev) => ({
        ...prev,
        [camId]: {
          status: 'failed',
          reason: err?.message || 'Connection error',
        },
      }));
    } finally {
      setTestingCamId(null);
    }
  };

  const getStatusDot = (status: string, enabled: boolean) => {
    if (!enabled) return 'bg-slate-500';
    switch (status) {
      case 'online':
        return 'bg-emerald-400 ring-4 ring-emerald-500/20';
      case 'reconnecting':
        return 'bg-amber-400 animate-pulse';
      case 'offline':
      default:
        return 'bg-rose-500';
    }
  };

  return (
    <div className="space-y-6" data-testid="cameras-manager">
      {/* Top Banner & Action */}
      <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-white tracking-wide flex items-center gap-2">
            <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            Camera Stream Management
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Add RTSP video sources, configure feature pipelines, test stream reachability, or remove cameras.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs rounded-xl shadow-md shadow-amber-500/20 transition-all flex items-center space-x-2"
          data-testid="btn-add-camera"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>Add Camera</span>
        </button>
      </div>

      {/* Global alert messages */}
      {message && (
        <div
          className={`p-4 rounded-xl text-xs font-medium border flex items-center justify-between ${
            message.type === 'success'
              ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
              : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
          }`}
          data-testid="cameras-message"
        >
          <span>{message.text}</span>
          <button
            type="button"
            onClick={() => setMessage(null)}
            className="text-slate-400 hover:text-white font-bold ml-4"
          >
            &times;
          </button>
        </div>
      )}

      {/* Camera List */}
      {loading ? (
        <div className="p-12 text-center text-slate-500 text-xs">Loading cameras...</div>
      ) : cameras.length === 0 ? (
        <div className="p-12 bg-slate-900 border border-slate-800 rounded-2xl text-center space-y-3">
          <p className="text-slate-400 text-xs">No cameras configured yet.</p>
          <button
            type="button"
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-semibold rounded-xl hover:bg-amber-500/20"
          >
            Add Your First Camera
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {cameras.map((cam) => {
            const testResult = testResults[cam.id];
            const isTesting = testingCamId === cam.id;

            return (
              <div
                key={cam.id}
                className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-all space-y-4"
                data-testid={`camera-card-${cam.id}`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center space-x-3">
                    <span className={`w-3 h-3 rounded-full flex-shrink-0 ${getStatusDot(cam.status, cam.enabled)}`} />
                    <div>
                      <div className="flex items-center space-x-2">
                        <h3 className="text-sm font-bold text-white tracking-wide">{cam.name}</h3>
                        {!cam.enabled && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-400">
                            Disabled
                          </span>
                        )}
                        <span className="text-[10px] text-slate-500 font-mono">ID: {cam.id.slice(0, 10)}…</span>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                        <span>
                          Status:{' '}
                          <span
                            className={`font-semibold capitalize ${
                              cam.status === 'online'
                                ? 'text-emerald-400'
                                : cam.status === 'reconnecting'
                                ? 'text-amber-400'
                                : 'text-slate-400'
                            }`}
                          >
                            {cam.status}
                          </span>
                        </span>
                        <span>•</span>
                        <span>
                          Resolution:{' '}
                          {cam.width && cam.height
                            ? `${cam.width}×${cam.height} @ ${cam.fps ?? 0}fps`
                            : 'Unprobed / Offline'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions & Enabled Toggle */}
                  <div className="flex items-center flex-wrap gap-2">
                    {/* Enable / Disable switch */}
                    <button
                      type="button"
                      onClick={() => handleToggleEnabled(cam)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                        cam.enabled
                          ? 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
                          : 'bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-400 border-emerald-800/50'
                      }`}
                      data-testid={`toggle-camera-${cam.id}`}
                      title={cam.enabled ? 'Click to disable' : 'Click to enable'}
                    >
                      {cam.enabled ? 'Pause' : 'Enable'}
                    </button>

                    {/* Test Stream Button */}
                    <button
                      type="button"
                      onClick={() => handleTestCamera(cam.id)}
                      disabled={isTesting}
                      className="px-3 py-1.5 bg-blue-950/40 hover:bg-blue-900/50 border border-blue-800/50 text-blue-300 text-xs font-semibold rounded-lg transition-all flex items-center space-x-1 disabled:opacity-50"
                      data-testid={`test-camera-${cam.id}`}
                    >
                      {isTesting ? (
                        <>
                          <svg className="animate-spin w-3.5 h-3.5 text-blue-400" viewBox="0 0 24 24" fill="none">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                          </svg>
                          <span>Testing…</span>
                        </>
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                          </svg>
                          <span>Test Stream</span>
                        </>
                      )}
                    </button>

                    {/* Edit Button */}
                    <button
                      type="button"
                      onClick={() => handleStartEdit(cam)}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition-all flex items-center space-x-1"
                      data-testid={`edit-camera-${cam.id}`}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                      <span>Edit</span>
                    </button>

                    {/* Delete Button */}
                    <button
                      type="button"
                      onClick={() => setDeletingCamera(cam)}
                      className="px-3 py-1.5 bg-rose-950/40 hover:bg-rose-900/50 border border-rose-800/50 text-rose-300 text-xs font-semibold rounded-lg transition-all flex items-center space-x-1"
                      data-testid={`delete-camera-${cam.id}`}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      <span>Delete</span>
                    </button>
                  </div>
                </div>

                {/* Features & Test Feedback */}
                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800/80">
                  <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold mr-1">
                    Features:
                  </span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${
                      cam.features.vehicles
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        : 'bg-slate-800/50 text-slate-500 border-slate-700/50'
                    }`}
                  >
                    {cam.features.vehicles ? '✓ Vehicles / OCR' : '✕ Vehicles'}
                  </span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${
                      cam.features.id_check
                        ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                        : 'bg-slate-800/50 text-slate-500 border-slate-700/50'
                    }`}
                  >
                    {cam.features.id_check ? '✓ ID-Card Check' : '✕ ID-Card'}
                  </span>

                  {/* Inline test feedback */}
                  {testResult && (
                    <div className="ml-auto text-xs">
                      {testResult.status === 'ok' ? (
                        <span className="text-emerald-400 font-semibold bg-emerald-950/60 border border-emerald-800/50 px-2.5 py-0.5 rounded-full inline-flex items-center gap-1.5">
                          <span>✓ Live OK</span>
                          <span className="text-emerald-300 font-normal">
                            ({testResult.width}×{testResult.height} @ {testResult.fps}fps)
                          </span>
                        </span>
                      ) : (
                        <span className="text-rose-400 font-medium bg-rose-950/60 border border-rose-800/50 px-2.5 py-0.5 rounded-full inline-flex items-center gap-1.5">
                          <span>✗ Test Failed:</span>
                          <span className="text-rose-300">{testResult.reason || 'Cannot read stream'}</span>
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ADD CAMERA MODAL */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 animate-in fade-in duration-200">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-white tracking-wide flex items-center gap-2">
                <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Register New Camera Stream
              </h3>
              <button
                type="button"
                onClick={resetAddForm}
                className="text-slate-400 hover:text-white font-bold text-lg"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateCamera} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Camera Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={addName}
                  onChange={(e) => setAddName(e.target.value)}
                  placeholder="e.g. South Gate Inbound"
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-white text-xs focus:outline-none focus:border-amber-500"
                  required
                  data-testid="input-camera-name"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  RTSP Stream URL <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={addRtsp}
                  onChange={(e) => setAddRtsp(e.target.value)}
                  placeholder="rtsp://user:pass@192.168.1.100:554/live"
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-white text-xs font-mono focus:outline-none focus:border-amber-500"
                  required
                  data-testid="input-camera-rtsp"
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  Credentials are encrypted at rest using Fernet encryption in the local database.
                </p>
              </div>

              <div className="space-y-2 pt-2 border-t border-slate-800">
                <label className="block text-xs font-semibold text-slate-300">
                  Feature Pipelines
                </label>
                <label className="flex items-center space-x-2.5 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={addFeatures.vehicles}
                    onChange={(e) =>
                      setAddFeatures((prev) => ({ ...prev, vehicles: e.target.checked }))
                    }
                    className="rounded bg-slate-950 border-slate-700 text-amber-500 focus:ring-0"
                    data-testid="checkbox-add-vehicles"
                  />
                  <span>Enable Vehicles Detection &amp; License Plate OCR</span>
                </label>
                <label className="flex items-center space-x-2.5 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={addFeatures.id_check}
                    onChange={(e) =>
                      setAddFeatures((prev) => ({ ...prev, id_check: e.target.checked }))
                    }
                    className="rounded bg-slate-950 border-slate-700 text-amber-500 focus:ring-0"
                    data-testid="checkbox-add-id-check"
                  />
                  <span>Enable ID Card Check (Turnstiles / Pedestrian Checkpoints)</span>
                </label>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={resetAddForm}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-5 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold rounded-xl shadow-md shadow-amber-500/20 disabled:opacity-50"
                  data-testid="btn-save-new-camera"
                >
                  {actionLoading ? 'Saving…' : 'Register Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT CAMERA MODAL */}
      {editingCamera && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 animate-in fade-in duration-200">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-white tracking-wide">
                Edit Camera: {editingCamera.name}
              </h3>
              <button
                type="button"
                onClick={() => setEditingCamera(null)}
                className="text-slate-400 hover:text-white font-bold text-lg"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleUpdateCamera} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Camera Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-white text-xs focus:outline-none focus:border-amber-500"
                  required
                  data-testid="edit-camera-name"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  New RTSP URL (Optional)
                </label>
                <input
                  type="text"
                  value={editRtsp}
                  onChange={(e) => setEditRtsp(e.target.value)}
                  placeholder="Leave blank to keep existing encrypted URL"
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-white text-xs font-mono focus:outline-none focus:border-amber-500"
                  data-testid="edit-camera-rtsp"
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  Only fill this in if you are updating the camera stream network address or credentials.
                </p>
              </div>

              <div className="pt-2 border-t border-slate-800 space-y-3">
                <label className="flex items-center space-x-2.5 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editEnabled}
                    onChange={(e) => setEditEnabled(e.target.checked)}
                    className="rounded bg-slate-950 border-slate-700 text-amber-500 focus:ring-0"
                    data-testid="edit-camera-enabled"
                  />
                  <span className="font-semibold">Stream Pipeline Enabled</span>
                </label>

                <div className="space-y-2">
                  <span className="block text-xs font-semibold text-slate-300">Feature Pipelines</span>
                  <label className="flex items-center space-x-2.5 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editFeatures.vehicles}
                      onChange={(e) =>
                        setEditFeatures((prev) => ({ ...prev, vehicles: e.target.checked }))
                      }
                      className="rounded bg-slate-950 border-slate-700 text-amber-500 focus:ring-0"
                      data-testid="edit-camera-feature-vehicles"
                    />
                    <span>Enable Vehicles Detection &amp; License Plate OCR</span>
                  </label>
                  <label className="flex items-center space-x-2.5 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editFeatures.id_check}
                      onChange={(e) =>
                        setEditFeatures((prev) => ({ ...prev, id_check: e.target.checked }))
                      }
                      className="rounded bg-slate-950 border-slate-700 text-amber-500 focus:ring-0"
                      data-testid="edit-camera-feature-id-check"
                    />
                    <span>Enable ID Card Check</span>
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setEditingCamera(null)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-5 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold rounded-xl shadow-md shadow-amber-500/20 disabled:opacity-50"
                  data-testid="btn-save-edit-camera"
                >
                  {actionLoading ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* DELETE CAMERA CONFIRMATION MODAL */}
      {deletingCamera && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-rose-900/50 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 animate-in fade-in duration-200">
            <div className="w-12 h-12 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-400 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </div>

            <div className="text-center space-y-2">
              <h3 className="text-base font-bold text-white">Delete Camera '{deletingCamera.name}'?</h3>
              <p className="text-xs text-rose-300 leading-relaxed bg-rose-950/30 p-3 rounded-xl border border-rose-900/40">
                Warning: Deleting this camera will cascade-delete all defined zones, registered actions/rules, and alerts attached to it. This action cannot be undone.
              </p>
            </div>

            <div className="flex items-center justify-center space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setDeletingCamera(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteCamera}
                disabled={actionLoading}
                className="px-5 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-xl shadow-md shadow-rose-600/20 disabled:opacity-50"
                data-testid="confirm-delete-camera"
              >
                {actionLoading ? 'Deleting…' : 'Yes, Delete Camera'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

