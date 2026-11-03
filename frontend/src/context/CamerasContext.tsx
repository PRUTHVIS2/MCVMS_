import React, { createContext, useContext, useEffect, useState } from 'react';
import type { Camera } from '../types';
import { api } from '../services/api';
import { wsService } from '../services/websocket';
import { useAuth } from './AuthContext';

interface CamerasContextType {
  cameras: Camera[];
  loading: boolean;
  refreshCameras: () => Promise<void>;
  getCameraById: (id: string) => Camera | undefined;
}

const CamerasContext = createContext<CamerasContextType | undefined>(undefined);

export const CamerasProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshCameras = async () => {
    if (!user) {
      setCameras([]);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const data = await api.listCameras();
      setCameras(data);

      // Subscribe to all cameras over WebSocket
      if (data.length > 0) {
        wsService.subscribeCameras(data.map((c) => c.id));
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshCameras();
  }, [user]);

  useEffect(() => {
    // Listen for live camera status updates
    const unsubscribe = wsService.onCameraStatus((msg) => {
      setCameras((prev) =>
        prev.map((c) => (c.id === msg.camera_id ? { ...c, status: msg.status } : c))
      );
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const getCameraById = (id: string) => cameras.find((c) => c.id === id);

  return (
    <CamerasContext.Provider value={{ cameras, loading, refreshCameras, getCameraById }}>
      {children}
    </CamerasContext.Provider>
  );
};

export const useCameras = (): CamerasContextType => {
  const context = useContext(CamerasContext);
  if (!context) {
    throw new Error('useCameras must be used within a CamerasProvider');
  }
  return context;
};
