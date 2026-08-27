'use client';
import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { getAgentSession } from '@/lib/api';
import ReactMarkdown from 'react-markdown';
import { CheckCircle, XCircle, Loader, Clock, ChevronDown, ChevronUp, ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function SessionDetailPage() {
  const { session_id } = useParams<{ session_id: string }>();
  const [session, setSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [stepsOpen, setStepsOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await getAgentSession(session_id);
      setSession(r);
      return r;
    } catch {} finally { setLoading(false); }
  }, [session_id]);

  useEffect(() => {
    load();
    const t = setInterval(async () => {
      const r = await load();
      if (r && !['RUNNING', 'INITIALIZING'].includes(r.status)) clearInterval(t);
    }, 3000);
    return () => clearInterval(t);
  }, [load]);

  if (loading) return <div className="flex items-center justify-center h-64"><Loader size={32} className="animate-spin text-brand-500" /></div>;
  if (!session) return <div className="text-gray-500">Session not found</div>;

  const isRunning = ['RUNNING', 'INITIALIZING'].includes(session.status);

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-4">
        <Link href="/agents" className="text-gray-500 hover:text-gray-300"><ArrowLeft size={20} /></Link>
        <div>
          <h1 className="text-xl font-bold text-white truncate">{session.input_query}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-sm text-gray-500 capitalize">{session.workflow?.replace(/_/g, ' ')}</span>
            <span className="badge-gray font-mono text-xs">{session.session_id}</span>
          </div>
        </div>
      </div>

      {/* Status */}
      <div className="card flex items-center gap-4">
        {isRunning ? <Loader size={20} className="animate-spin text-blue-400" /> :
         session.status === 'COMPLETED' ? <CheckCircle size={20} className="text-green-400" /> :
         <XCircle size={20} className="text-red-400" />}
        <div>
          <div className="font-medium text-white capitalize">{session.status}</div>
          {session.current_node && isRunning && (
            <div className="text-sm text-gray-500">Running: {session.current_node}</div>
          )}
        </div>
        {session.result?.confidence != null && (
          <div className="ml-auto text-right">
            <div className="text-xl font-bold text-white">{(session.result.confidence * 100).toFixed(0)}%</div>
            <div className="text-xs text-gray-500">confidence</div>
          </div>
        )}
        {session.total_duration_ms && (
          <div className="text-right">
            <div className="text-xl font-bold text-white">{(session.total_duration_ms / 1000).toFixed(1)}s</div>
            <div className="text-xs text-gray-500">duration</div>
          </div>
        )}
      </div>

      {/* Response */}
      {session.result?.response && (
        <div className="card">
          <h2 className="font-semibold text-white mb-4">Response</h2>
          <div className="prose prose-invert prose-sm max-w-none text-gray-300">
            <ReactMarkdown>{session.result.response}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Evaluation scores */}
      {session.evaluation && (
        <div className="card">
          <h2 className="font-semibold text-white mb-4">Evaluation Scores</h2>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {Object.entries(session.evaluation).map(([key, val]: [string, any]) => val != null && (
              <div key={key} className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-lg font-bold text-white">{(Number(val) * 100).toFixed(0)}%</div>
                <div className="text-xs text-gray-500 capitalize mt-1">{key.replace(/_/g, ' ')}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sources */}
      {session.result?.sources?.length > 0 && (
        <div className="card">
          <button onClick={() => setSourcesOpen(!sourcesOpen)}
            className="flex items-center justify-between w-full">
            <h2 className="font-semibold text-white">Sources ({session.result.sources.length})</h2>
            {sourcesOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {sourcesOpen && (
            <div className="mt-4 space-y-2">
              {session.result.sources.map((s: any, i: number) => (
                <div key={i} className="bg-gray-800 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-400 font-medium">{s.filename}</span>
                    <span className="text-xs text-yellow-500">{(s.relevance_score * 100).toFixed(1)}%</span>
                  </div>
                  <p className="text-xs text-gray-500">{s.content_preview}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Steps */}
      {session.steps?.length > 0 && (
        <div className="card">
          <button onClick={() => setStepsOpen(!stepsOpen)}
            className="flex items-center justify-between w-full">
            <h2 className="font-semibold text-white">Execution Steps ({session.steps.length})</h2>
            {stepsOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {stepsOpen && (
            <div className="mt-4 space-y-2">
              {session.steps.map((step: any) => (
                <div key={step.step_index} className="flex items-center gap-3 bg-gray-800 rounded-lg px-3 py-2">
                  <span className="text-xs font-mono text-gray-600 w-6">{step.step_index + 1}</span>
                  <span className="text-sm text-gray-300">{step.node}</span>
                  {step.tool_calls_count > 0 && <span className="badge-blue">{step.tool_calls_count} tools</span>}
                  {step.duration_ms && <span className="ml-auto text-xs text-gray-600">{step.duration_ms}ms</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
