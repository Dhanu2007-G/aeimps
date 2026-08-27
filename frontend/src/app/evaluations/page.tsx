'use client';
import { useEffect, useState } from 'react';
import { getEvalSummary } from '@/lib/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const MetricBar = ({ label, value }: { label: string; value: number | null }) => {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? '#4ade80' : pct >= 60 ? '#facc15' : '#f87171';
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-gray-400 capitalize">{label.replace(/_/g, ' ')}</span>
        <span className="text-white font-medium">{pct}%</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
};

export default function EvaluationsPage() {
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getEvalSummary().then(setSummary).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500 mt-16 text-center">Loading evaluation data...</div>;

  const distData = summary?.score_distribution
    ? Object.entries(summary.score_distribution).map(([range, count]) => ({ range, count }))
    : [];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Evaluation Dashboard</h1>
        <p className="text-gray-500 mt-1">Automated quality metrics for all agent responses</p>
      </div>

      {!summary || summary.total_evaluations === 0 ? (
        <div className="card text-center py-12 text-gray-600">
          No evaluations yet — run an agent workflow and evaluations will appear automatically.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4">
            <div className="card">
              <div className="text-3xl font-bold text-white">{summary.total_evaluations}</div>
              <div className="text-sm text-gray-500 mt-1">Total evaluations</div>
            </div>
            <div className="card">
              <div className="text-3xl font-bold text-white">
                {summary.average_scores?.overall_score != null
                  ? `${(summary.average_scores.overall_score * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="text-sm text-gray-500 mt-1">Average overall score</div>
            </div>
          </div>

          {summary.average_scores && (
            <div className="card space-y-4">
              <h2 className="font-semibold text-white">Average Metric Scores</h2>
              {Object.entries(summary.average_scores).map(([k, v]: [string, any]) => (
                <MetricBar key={k} label={k} value={v} />
              ))}
            </div>
          )}

          {distData.length > 0 && (
            <div className="card">
              <h2 className="font-semibold text-white mb-4">Score Distribution</h2>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={distData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="range" stroke="#6b7280" fontSize={12} />
                  <YAxis stroke="#6b7280" fontSize={12} />
                  <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
                  <Bar dataKey="count" fill="#4f6ef7" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {summary.worst_performing?.length > 0 && (
            <div className="card">
              <h2 className="font-semibold text-white mb-4">Lowest Scoring Sessions</h2>
              <div className="space-y-2">
                {summary.worst_performing.map((s: any) => (
                  <div key={s.session_id} className="flex items-center gap-4 bg-gray-800 rounded-lg px-4 py-3">
                    <span className="text-sm font-bold text-red-400">{(s.score * 100).toFixed(0)}%</span>
                    <span className="text-sm text-gray-400 truncate flex-1">{s.query}</span>
                    <span className="text-xs font-mono text-gray-600">{String(s.session_id).slice(0, 12)}…</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
