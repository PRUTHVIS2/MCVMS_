import React from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { CamerasProvider } from './context/CamerasContext';
import { AlertsProvider } from './context/AlertsContext';
import { LoginPage } from './components/auth/LoginPage';
import { AppShell } from './components/layout/AppShell';

const MainRouter: React.FC = () => {
  const { user, token, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-400">
        <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mb-4"></div>
        <p className="text-xs uppercase tracking-widest font-mono text-slate-500">Initializing MCVMS...</p>
      </div>
    );
  }

  if (!token || !user) {
    return <LoginPage />;
  }

  return (
    <CamerasProvider>
      <AlertsProvider>
        <AppShell />
      </AlertsProvider>
    </CamerasProvider>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <MainRouter />
    </AuthProvider>
  );
}
