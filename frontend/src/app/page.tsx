'use client';
import { useEffect, useState } from 'react';
import { getHealth, getMetrics, getWorkerStatus } from '@/lib/api';
import { FileText, Cpu, Bot, Zap, CheckCircle, AlertCircle, Clock } from 'lucide-react';

function StatCard({ title, value, sub, icon: Icon, color = 'blue' }: any) {
  const colors: any = { blue: 'text-blue-400 bg-blue-900/30', green: 'text-green-400 bg-green-900/30', purple: 'text-purple-400 bg-purple-900/30', orange: 'text-orange-400 bg-orange-900/30' };
  return (
    <div className="card flex items-start gap-4">
      <div className={`p-3 rounded-lg ${colors[color]}`}><Icon size={22} className={colors[color].split(' ')[0]} /></div>
      <div>
        <div className="text-2xl font-bold text-white">{value ?? '—'}</div>
        <div className="text-sm font-medium text-gray-300">{title}</div>
        {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'healthy') return <span className="badge-green">● healthy</span>;
  if (status === 'degraded') return <span className="badge-yellow">● degraded</span>;
  return <span className="badge-red">● unhealthy</span>;
}

export default function DashboardPage() {
  const [health, setHealth] = useState<any>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [workers, setWorkers] = useState<any>(null);

  useEffect(() => {
    const load = async () => {
      try { setHealth(await getHealth()); } catch {}
      try { setMetrics(await getMetrics()); } catch {}
      try { setWorkers(await getWorkerStatus()); } catch {}
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-500 mt-1">System health and operational metrics</p>
      </div>

      {/* System status */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-white">System Status</h2>
          {health && <StatusBadge status={health.status} />}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {health?.services && Object.entries(health.services).map(([name, svc]: [string, any]) => (
            <div key={name} className="bg-gray-800 rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-1">{name}</div>
              <StatusBadge status={svc.status} />
              {svc.latency_ms != null && <div className="text-xs text-gray-600 mt-1">{svc.latency_ms}ms</div>}
            </div>
          ))}
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Documents" value={metrics?.documents_total?.toLocaleString()} sub="total ingested" icon={FileText} color="blue" />
        <StatCard title="Vectors" value={metrics?.vectors_total?.toLocaleString()} sub="in Qdrant" icon={Cpu} color="purple" />
        <StatCard title="Agent Runs Today" value={metrics?.agents_run_today} sub="workflows executed" icon={Bot} color="orange" />
        <StatCard title="Avg Retrieval" value={metrics?.avg_retrieval_ms ? `${Math.round(metrics.avg_retrieval_ms)}ms` : null} sub="last 24h P50" icon={Zap} color="green" />
      </div>

      {/* Workers */}
      {workers?.workers?.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-white mb-4">Workers</h2>
          <div className="space-y-2">
            {workers.workers.map((w: any) => (
              <div key={w.name} className="flex items-center justify-between bg-gray-800 rounded-lg px-4 py-3">
                <div className="flex items-center gap-3">
                  {w.status === 'alive' ? <CheckCircle size={16} className="text-green-400" /> :
                   w.status === 'stale' ? <Clock size={16} className="text-yellow-400" /> :
                   <AlertCircle size={16} className="text-red-400" />}
                  <span className="text-sm text-gray-300">{w.name}</span>
                </div>
                <span className="text-xs text-gray-500">
                  {w.seconds_since_heartbeat ? `${Math.round(w.seconds_since_heartbeat)}s ago` : 'never'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
