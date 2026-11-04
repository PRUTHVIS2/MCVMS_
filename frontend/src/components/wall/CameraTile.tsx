import React, { useEffect, useRef, useState } from 'react';
import type { Camera, Track, TracksMessage, Zone } from '../../types';
import { api } from '../../services/api';
import { wsService } from '../../services/websocket';
import { drawTrack, drawZone } from '../../utils/overlay';

interface CameraTileProps {
  camera: Camera;
  isFocused?: boolean;
  onToggleFocus?: () => void;
}

const TRACK_TIMEOUT_MS = 1000;

export const CameraTile: React.FC<CameraTileProps> = ({ camera, isFocused = false, onToggleFocus }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [zones, setZones] = useState<Zone[]>([]);
  const [streamError, setStreamError] = useState<boolean>(false);
  const [activeTracks, setActiveTracks] = useState<Track[]>([]);
  const [frameSize, setFrameSize] = useState<[number, number]>([
    camera.width || 1920,
    camera.height || 1080,
  ]);

  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const tracksTimeoutRef = useRef<number | null>(null);

  // 1. Load zones for this camera
  useEffect(() => {
    let isMounted = true;
    api
      .listZones(camera.id)
      .then((data) => {
        if (isMounted) setZones(data);
      })
      .catch(() => {
        // zone loading failure is non-fatal
      });

    return () => {
      isMounted = false;
    };
  }, [camera.id]);

  // 2. Setup video stream (WebRTC WHEP with HLS fallback)
  useEffect(() => {
    if (camera.status !== 'online') {
      setActiveTracks([]);
      return;
    }

    let isCancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    const videoEl = videoRef.current;

    const setupStream = async () => {
      if (isCancelled) return;
      try {
        const info = await api.getStreamInfo(camera.id);
        if (isCancelled) return;

        // Attempt WebRTC WHEP connection
        if (window.RTCPeerConnection && info.webrtc_url) {
          try {
            const pc = new RTCPeerConnection({
              iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
            });
            peerConnectionRef.current = pc;

            pc.addTransceiver('video', { direction: 'recvonly' });

            pc.onconnectionstatechange = () => {
              if (
                pc.connectionState === 'disconnected' ||
                pc.connectionState === 'failed' ||
                pc.connectionState === 'closed'
              ) {
                if (!isCancelled) {
                  setStreamError(true);
                  setActiveTracks([]);
                  if (camera.status === 'online' && !retryTimer) {
                    retryTimer = setTimeout(() => {
                      retryTimer = null;
                      setupStream();
                    }, 3000);
                  }
                }
              }
            };

            pc.ontrack = (event) => {
              if (videoEl && event.streams[0]) {
                videoEl.srcObject = event.streams[0];
                setStreamError(false);
                videoEl.onerror = () => {
                  if (!isCancelled) {
                    setStreamError(true);
                    setActiveTracks([]);
                  }
                };
                videoEl.play().catch(() => {});
              }
            };

            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);

            const res = await fetch(info.webrtc_url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/sdp' },
              body: offer.sdp,
            });

            if (res.ok) {
              const answerSdp = await res.text();
              if (!isCancelled && pc.signalingState !== 'closed') {
                await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
                setStreamError(false);
                return;
              }
            }
          } catch {
            // WHEP negotiation failed, fall back to HLS
          }
        }

        // HLS fallback
        if (videoEl && info.hls_url) {
          videoEl.srcObject = null;
          videoEl.src = info.hls_url;
          videoEl.play().catch(() => {});
        }
      } catch {
        if (!isCancelled) {
          setStreamError(true);
          setActiveTracks([]);
          if (camera.status === 'online' && !retryTimer) {
            retryTimer = setTimeout(() => {
              retryTimer = null;
              setupStream();
            }, 3000);
          }
        }
      }
    };

    setupStream();

    return () => {
      isCancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (peerConnectionRef.current) {
        peerConnectionRef.current.close();
        peerConnectionRef.current = null;
      }
      if (videoEl) {
        videoEl.srcObject = null;
        videoEl.src = '';
      }
    };
  }, [camera.id, camera.status]);

  // 3. Listen to live tracks messages over WebSocket
  useEffect(() => {
    const unsubscribe = wsService.onTracks((msg: TracksMessage) => {
      if (msg.camera_id === camera.id) {
        if (camera.status !== 'online' || streamError) {
          setActiveTracks([]);
          return;
        }

        setActiveTracks(msg.tracks);
        if (msg.frame_size && msg.frame_size[0] > 0 && msg.frame_size[1] > 0) {
          setFrameSize(msg.frame_size);
        }

        // Auto-clear tracks if no frame arrives within TRACK_TIMEOUT_MS
        if (tracksTimeoutRef.current) {
          window.clearTimeout(tracksTimeoutRef.current);
        }
        tracksTimeoutRef.current = window.setTimeout(() => {
          setActiveTracks([]);
        }, TRACK_TIMEOUT_MS);
      }
    });

    return () => {
      unsubscribe();
      if (tracksTimeoutRef.current) {
        window.clearTimeout(tracksTimeoutRef.current);
      }
    };
  }, [camera.id, camera.status, streamError]);

  // 4. Render overlay on canvas whenever zones, tracks, status, or dimensions change
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Match canvas buffer size to client display size
    const rect = canvas.getBoundingClientRect();
    if (canvas.width !== rect.width || canvas.height !== rect.height) {
      canvas.width = rect.width;
      canvas.height = rect.height;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // If stream is unavailable or camera is offline, keep canvas cleared
    if (camera.status !== 'online' || streamError) {
      return;
    }

    const canvasDimensions = { width: canvas.width, height: canvas.height };

    // 1. Draw zones (special dashed amber, normal dotted grey)
    for (const zone of zones) {
      if (zone.enabled) {
        drawZone(ctx, zone, canvasDimensions);
      }
    }

    // 2. Draw tracks
    for (const track of activeTracks) {
      drawTrack(ctx, track, frameSize, canvasDimensions);
    }
  }, [zones, activeTracks, frameSize, camera.status, streamError]);

  // Status dot style helper
  const getStatusDot = () => {
    if (streamError) {
      return (
        <span className="flex items-center space-x-1.5" title="Stream Error / Reconnecting">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500 animate-pulse"></span>
          <span className="text-[11px] text-amber-400 font-medium">CONNECTING</span>
        </span>
      );
    }

    switch (camera.status) {
      case 'online':
        return (
          <span className="flex items-center space-x-1.5" title="Camera Online">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="text-[11px] text-emerald-400 font-medium">LIVE</span>
          </span>
        );
      case 'reconnecting':
        return (
          <span className="flex items-center space-x-1.5" title="Camera Reconnecting">
            <span className="h-2.5 w-2.5 rounded-full bg-amber-500 animate-pulse"></span>
            <span className="text-[11px] text-amber-400 font-medium">CONNECTING</span>
          </span>
        );
      case 'offline':
      default:
        return (
          <span className="flex items-center space-x-1.5" title="Camera Offline">
            <span className="h-2.5 w-2.5 rounded-full bg-red-500"></span>
            <span className="text-[11px] text-red-400 font-medium">OFFLINE</span>
          </span>
        );
    }
  };

  return (
    <div
      ref={containerRef}
      className={`flex flex-col bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg transition-all ${
        isFocused ? 'ring-2 ring-amber-500 shadow-2xl' : 'hover:border-slate-700'
      }`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-slate-950/80 border-b border-slate-800/80 text-xs select-none">
        <div className="flex items-center space-x-2.5">
          {getStatusDot()}
          <span className="font-semibold text-white tracking-wide truncate max-w-[150px] sm:max-w-xs">
            {camera.name}
          </span>
        </div>

        <div className="flex items-center space-x-2">
          {camera.width && camera.height && (
            <span className="hidden sm:inline text-[10px] px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded border border-slate-700 font-mono">
              {camera.width}x{camera.height} {camera.fps ? `@ ${Math.round(camera.fps)}fps` : ''}
            </span>
          )}

          {onToggleFocus && (
            <button
              type="button"
              onClick={onToggleFocus}
              title={isFocused ? 'Exit focus' : 'Focus camera'}
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              aria-label={isFocused ? 'Exit focus' : 'Focus camera'}
            >
              {isFocused ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                </svg>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Video & Overlay Viewport */}
      <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
        {/* Offline / Error placeholder */}
        {camera.status === 'offline' || streamError ? (
          <div className="flex flex-col items-center justify-center text-slate-500 p-6 text-center select-none">
            <div className="w-12 h-12 rounded-full bg-slate-800/80 border border-slate-700 flex items-center justify-center mb-2.5 text-slate-400">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
            </div>
            <p className="text-sm font-medium text-slate-300">Stream Unavailable</p>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">
              {camera.status === 'offline'
                ? 'Camera is currently marked offline.'
                : 'Waiting for video stream signal from MediaMTX...'}
            </p>
          </div>
        ) : (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-contain"
          />
        )}

        {/* Real-time Canvas Overlay */}
        <canvas
          ref={canvasRef}
          data-testid="camera-overlay-canvas"
          className="absolute inset-0 w-full h-full pointer-events-none"
        />

        {/* Feature badges footer */}
        <div className="absolute bottom-2 left-2 flex items-center space-x-1.5 pointer-events-none">
          {camera.features.vehicles && (
            <span className="text-[10px] px-1.5 py-0.5 bg-slate-900/80 backdrop-blur-sm text-amber-400 rounded border border-amber-500/30 font-medium">
              Vehicles
            </span>
          )}
          {camera.features.id_check && (
            <span className="text-[10px] px-1.5 py-0.5 bg-slate-900/80 backdrop-blur-sm text-blue-400 rounded border border-blue-500/30 font-medium">
              ID Check
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
