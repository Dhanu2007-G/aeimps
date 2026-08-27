import axios from 'axios';

const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';
const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: `${BASE}/api/v1`,
  headers: { 'X-API-Key': API_KEY },
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const msg = err.response?.data?.error?.message || err.message;
    return Promise.reject(new Error(msg));
  }
);

// ─── Ingest ───────────────────────────────────────────────
export const ingestDocument = async (file: File, tags?: string[], priority = 5) => {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('tags', tags?.join(',') || '');
  fd.append('priority', String(priority));
  fd.append('metadata', '{}');
  const { data } = await api.post('/ingest/document', fd);
  return data;
};

export const getJobStatus = async (jobId: string) => {
  const { data } = await api.get(`/ingest/job/${jobId}`);
  return data;
};

export const listJobs = async (params?: { status?: string; limit?: number }) => {
  const { data } = await api.get('/ingest/jobs', { params });
  return data;
};

export const getDocument = async (docId: string) => {
  const { data } = await api.get(`/ingest/document/${docId}`);
  return data;
};

export const deleteDocument = async (docId: string) => {
  const { data } = await api.delete(`/ingest/document/${docId}`);
  return data;
};

// ─── Retrieve ─────────────────────────────────────────────
export const search = async (query: string, mode = 'hybrid', topK = 8, filters?: object) => {
  const { data } = await api.post('/retrieve/search', { query, mode, top_k: topK, filters: filters || {} });
  return data;
};

export const getEntity = async (name: string) => {
  const { data } = await api.get(`/retrieve/entity/${encodeURIComponent(name)}`);
  return data;
};

// ─── Agent ────────────────────────────────────────────────
export type WorkflowType = 'incident_investigation' | 'question_answering' | 'summarization' | 'root_cause_analysis' | 'remediation';

export const runAgent = async (workflow: WorkflowType, input: string, context?: object) => {
  const { data } = await api.post('/agent/run', {
    workflow, input,
    context: context || {},
    config: { max_iterations: 8, include_evaluation: true },
  });
  return data;
};

export const getAgentSession = async (sessionId: string) => {
  const { data } = await api.get(`/agent/session/${sessionId}`);
  return data;
};

export const listAgentSessions = async (params?: { workflow?: string; status?: string; limit?: number }) => {
  const { data } = await api.get('/agent/sessions', { params });
  return data;
};

export const continueSession = async (sessionId: string, input: string) => {
  const { data } = await api.post(`/agent/session/${sessionId}/continue`, { input });
  return data;
};

// ─── Evaluate ─────────────────────────────────────────────
export const getEvalSummary = async (params?: { workflow?: string }) => {
  const { data } = await api.get('/evaluate/summary', { params });
  return data;
};

// ─── Admin ────────────────────────────────────────────────
export const getHealth = async () => {
  const { data } = await api.get('/admin/health');
  return data;
};

export const getMetrics = async () => {
  const { data } = await api.get('/admin/metrics/summary');
  return data;
};

export const getWorkerStatus = async () => {
  const { data } = await api.get('/admin/workers');
  return data;
};
