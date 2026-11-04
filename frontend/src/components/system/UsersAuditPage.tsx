import React, { useEffect, useState } from 'react';
import type { AuditLogEntry, Role, User } from '../../types';
import { api } from '../../services/api';
import { formatLocalDateTime } from '../../utils/date';
import { useAuth } from '../../context/AuthContext';

export const UsersAuditPage: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [activeTab, setActiveTab] = useState<'users' | 'audit'>('users');

  // Users state
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [isCreateUserModalOpen, setIsCreateUserModalOpen] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<Role>('incharge');
  const [createUserError, setCreateUserError] = useState<string | null>(null);

  // Audit state
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [actionFilter, setActionFilter] = useState('');

  const fetchUsers = async () => {
    setUsersLoading(true);
    try {
      const data = await api.listUsers();
      setUsers(data);
    } catch {
      // ignore
    } finally {
      setUsersLoading(false);
    }
  };

  const fetchAuditLogs = async () => {
    setAuditLoading(true);
    try {
      const data = await api.listAuditLogs({ action: actionFilter || undefined, limit: 100 });
      setAuditLogs(data);
    } catch {
      // ignore
    } finally {
      setAuditLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'users' && currentUser?.role === 'owner') {
      fetchUsers();
    } else if (activeTab === 'audit') {
      fetchAuditLogs();
    }
  }, [activeTab, actionFilter]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword) return;
    setCreateUserError(null);
    try {
      await api.createUser({
        username: newUsername.trim(),
        password: newPassword,
        role: newRole,
      });
      setIsCreateUserModalOpen(false);
      setNewUsername('');
      setNewPassword('');
      fetchUsers();
    } catch (err) {
      setCreateUserError(err instanceof Error ? err.message : 'Failed to create user');
    }
  };

  const getRoleBadge = (role: Role) => {
    switch (role) {
      case 'owner':
        return 'bg-purple-500/20 text-purple-300 border-purple-500/40';
      case 'admin':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
      case 'incharge':
      default:
        return 'bg-blue-500/20 text-blue-300 border-blue-500/40';
    }
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Header with Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-md">
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => setActiveTab('users')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'users'
                ? 'bg-amber-500 text-slate-950 shadow-md'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            User Management
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('audit')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'audit'
                ? 'bg-amber-500 text-slate-950 shadow-md'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            Audit Log Feed
          </button>
        </div>

        {activeTab === 'users' && currentUser?.role === 'owner' && (
          <button
            type="button"
            onClick={() => setIsCreateUserModalOpen(true)}
            className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-lg text-xs font-semibold flex items-center space-x-1.5 shadow-md transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Add New User</span>
          </button>
        )}

        {activeTab === 'audit' && (
          <div className="flex items-center space-x-2">
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="">All Actions</option>
              <option value="login_success">login_success</option>
              <option value="login_failed">login_failed</option>
              <option value="event_ack">event_ack</option>
              <option value="event_false_alarm">event_false_alarm</option>
              <option value="user_created">user_created</option>
            </select>
            <button
              type="button"
              onClick={fetchAuditLogs}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
              title="Refresh audit logs"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Tab Content */}
      <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg flex flex-col">
        {activeTab === 'users' ? (
          usersLoading && users.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-xs">
              Loading users...
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300 divide-y divide-slate-800">
                <thead className="bg-slate-950/80 text-slate-400 uppercase font-semibold text-[10px] tracking-wider">
                  <tr>
                    <th scope="col" className="px-5 py-3.5">Username</th>
                    <th scope="col" className="px-5 py-3.5">Role</th>
                    <th scope="col" className="px-5 py-3.5">Status</th>
                    <th scope="col" className="px-5 py-3.5">Created At (IST)</th>
                    <th scope="col" className="px-5 py-3.5">Assigned Cameras</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-5 py-3.5 font-medium text-white">
                        {u.username}
                        <span className="block text-[10px] font-mono text-slate-500">{u.id}</span>
                      </td>
                      <td className="px-5 py-3.5 whitespace-nowrap">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded uppercase font-bold tracking-wider border ${getRoleBadge(
                            u.role
                          )}`}
                        >
                          {u.role}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 whitespace-nowrap">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                            u.active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
                          }`}
                        >
                          {u.active ? 'Active' : 'Disabled'}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 whitespace-nowrap font-mono text-[11px] text-slate-300">
                        {formatLocalDateTime(u.created_at)}
                      </td>
                      <td className="px-5 py-3.5 text-slate-400 text-[11px]">
                        {u.cameras && u.cameras.length > 0 ? u.cameras.join(', ') : 'All cameras (unrestricted)'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          /* Audit Log Table */
          auditLoading && auditLogs.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-xs">
              Loading audit logs...
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300 divide-y divide-slate-800">
                <thead className="bg-slate-950/80 text-slate-400 uppercase font-semibold text-[10px] tracking-wider sticky top-0 z-10 select-none">
                  <tr>
                    <th scope="col" className="px-5 py-3.5">Timestamp (IST)</th>
                    <th scope="col" className="px-5 py-3.5">User</th>
                    <th scope="col" className="px-5 py-3.5">Action</th>
                    <th scope="col" className="px-5 py-3.5">Target</th>
                    <th scope="col" className="px-5 py-3.5">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                  {auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-5 py-3 whitespace-nowrap text-slate-200">
                        {formatLocalDateTime(log.ts)}
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap text-amber-400 font-sans font-medium">
                        {log.username || log.user_id || 'system'}
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-sans text-[10px] font-semibold border border-slate-700">
                          {log.action}
                        </span>
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap text-slate-300 truncate max-w-xs">
                        {log.target}
                      </td>
                      <td className="px-5 py-3 text-slate-400 max-w-md truncate text-[10px]">
                        {JSON.stringify(log.detail)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {/* Create User Modal */}
      {isCreateUserModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-base font-semibold text-white mb-2">Create New User</h3>
            {createUserError && (
              <div className="mb-3 p-2.5 bg-red-950 border border-red-800 rounded text-xs text-red-200">
                {createUserError}
              </div>
            )}
            <form onSubmit={handleCreateUser} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-400 font-semibold mb-1">Username</label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder="e.g. guard_gate1"
                  required
                  className="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white"
                />
              </div>
              <div>
                <label className="block text-slate-400 font-semibold mb-1">Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white"
                />
              </div>
              <div>
                <label className="block text-slate-400 font-semibold mb-1">Role</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as Role)}
                  className="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white"
                >
                  <option value="incharge">In-charge (Restricted Live View & Acks)</option>
                  <option value="admin">Admin (Full Operational Control)</option>
                  <option value="owner">Owner (Complete Administrative Control)</option>
                </select>
              </div>
              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateUserModalOpen(false)}
                  className="px-3.5 py-1.5 text-slate-400 hover:text-white rounded-lg bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-3.5 py-1.5 font-semibold text-slate-950 bg-amber-500 hover:bg-amber-400 rounded-lg"
                >
                  Create User
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
