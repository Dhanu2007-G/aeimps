'use client';
import { useState, useEffect } from 'react';
import { runAgent, listAgentSessions, WorkflowType } from '@/lib/api';
import toast from 'react-hot-toast';
import Link from 'next/link';
import { Bot, Play, Clock, CheckCircle, XCircle, Loader, ChevronRight } from 'lucide-react';

const WORKFLOWS: { value: WorkflowType; label: string; desc: string }[] = [
  { value: 'incident_investigation', label: 'Incident Investigation', desc: 'Investigate production incidents with full context retrieval' },
  { value: 'question_answering', label: 'Question Answering', desc: 'Answer questions from your enterprise knowledge base' },
  { value: 'summarization', label: 'Summarization', desc: 'Summarize documents or topics' },
  { value: 'root_cause_analysis', label: 'Root Cause Analysis', desc: 'Deep causal analysis with graph traversal' },
  { value: 'remediation', label: 'Remediation', desc: 'Generate actionable fix recommendations' },
];

const STATUS_ICON: any = {
  RUNNING: <Loader size={14} className="text-blue-400 animate-spin" />,
  COMPLETED: <CheckCircle size={14} className="text-green-400" />,
  FAILED: <XCircle size={14} className="text-red-400" />,
  INITIALIZING: <Clock size={14} className="text-yellow-400" />,
};

export default function AgentsPage() {
  const [workflow, setWorkflow] = useState<WorkflowType>('question_answering');
  const [input, setInput] = useState('');
  const [running, setRunning] = useState(false);
  const [sessions, setSessions] = useState<any[]>([]);

  const loadSessions = async () => {
    try { const r = await listAgentSessions({ limit: 20 }); setSessions(r.sessions || []); } catch {}
  };

  useEffect(() => { loadSessions(); const t = setInterval(loadSessions, 5000); return () => clearInterval(t); }, []);

  const handleRun = async () => {
    if (!input.trim()) return;
    setRunning(true);
    try {
      const r = await runAgent(workflow, input);
      toast.success(`Session ${r.session_id} started`);
      setInput('');
      setTimeout(loadSessions, 500);
    } catch (e: any) { toast.error(e.message); }
    finally { setRunning(false); }
  };

  const selected = WORKFLOWS.find(w => w.value === workflow)!;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Agent Workflows</h1>
        <p className="text-gray-500 mt-1">Stateful, multi-step AI workflows over your knowledge base</p>
      </div>

      <div className="card space-y-5">
        <h2 className="font-semibold text-white">Run New Workflow</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {WORKFLOWS.map((w) => (
            <button key={w.value} onClick={() => setWorkflow(w.value)}
              className={`p-3 rounded-lg text-left text-xs transition-colors border ${
                workflow === w.value
                  ? 'border-brand-500 bg-brand-600/20 text-white'
                  : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
              }`}>
              <div className="font-medium">{w.label}</div>
              <div className="text-gray-500 mt-1 hidden sm:block">{w.desc}</div>
            </button>
          ))}
        </div>
        <textarea
          value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={`Describe your ${selected.label.toLowerCase()}...`}
          className="input resize-none h-32"
        />
        <div className="flex justify-end">
          <button onClick={handleRun} disabled={running || !input.trim()} className="btn-primary flex items-center gap-2">
            {running ? <Loader size={16} className="animate-spin" /> : <Play size={16} />}
            {running ? 'Starting...' : 'Run Workflow'}
          </button>
        </div>
      </div>

      <div className="card">
        <h2 className="font-semibold text-white mb-4">Recent Sessions</h2>
        {sessions.length === 0 ? (
          <div className="text-gray-600 text-sm py-6 text-center">No sessions yet</div>
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => (
              <Link key={s.session_id} href={`/agents/${s.session_id}`}
                className="flex items-center gap-4 bg-gray-800 hover:bg-gray-750 rounded-lg px-4 py-3 transition-colors group">
                <Bot size={16} className="text-gray-500 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-300 truncate">{s.input_query}</div>
                  <div className="text-xs text-gray-600 mt-0.5 capitalize">{s.workflow?.replace(/_/g, ' ')}</div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {STATUS_ICON[s.status] || null}
                  {s.confidence_score != null && (
                    <span className="text-xs text-gray-500">{(s.confidence_score * 100).toFixed(0)}%</span>
                  )}
                  <ChevronRight size={14} className="text-gray-600 group-hover:text-gray-400" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
