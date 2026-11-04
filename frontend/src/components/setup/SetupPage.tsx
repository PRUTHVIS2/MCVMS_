import React, { useState } from 'react';
import { CalendarExemptionsEditor } from './CalendarExemptionsEditor';
import { CamerasManager } from './CamerasManager';
import { SetupWizard } from './SetupWizard';
import { ZonesRulesManager } from './ZonesRulesManager';

type SetupTab = 'wizard' | 'cameras' | 'manager' | 'calendar';

export const SetupPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SetupTab>('wizard');

  return (
    <div className="space-y-6 max-w-7xl mx-auto" data-testid="setup-page">
      {/* Top Header & Tab Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white tracking-wide">
            Setup &amp; Rules Administration
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Configure camera intelligence, zone boundaries, rule engines, dry-run simulations, and calendar exemptions
          </p>
        </div>

        {/* Tab Pills */}
        <div className="flex items-center space-x-1.5 bg-slate-900 border border-slate-800 p-1 rounded-xl">
          <button
            type="button"
            onClick={() => setActiveTab('wizard')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'wizard'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
            data-testid="tab-wizard"
          >
            Setup Wizard
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('cameras')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'cameras'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
            data-testid="tab-cameras"
          >
            Cameras
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('manager')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'manager'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
            data-testid="tab-manager"
          >
            Zones &amp; Rules
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('calendar')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'calendar'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
            data-testid="tab-calendar"
          >
            Calendar Exemptions
          </button>
        </div>
      </div>

      {/* Tab Contents */}
      {activeTab === 'wizard' && <SetupWizard onCompleted={() => setActiveTab('manager')} />}
      {activeTab === 'cameras' && <CamerasManager />}
      {activeTab === 'manager' && <ZonesRulesManager />}
      {activeTab === 'calendar' && <CalendarExemptionsEditor />}
    </div>
  );
};

