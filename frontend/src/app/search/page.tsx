'use client';
import { useState } from 'react';
import { search } from '@/lib/api';
import toast from 'react-hot-toast';
import { Search, Loader, FileText, Star, ChevronDown, ChevronUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const MODES = ['hybrid', 'dense', 'sparse', 'keyword', 'graph'];

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('hybrid');
  const [topK, setTopK] = useState(8);
  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const r = await search(query, mode, topK);
      setResults(r);
    } catch (e: any) { toast.error(e.message); }
    finally { setLoading(false); }
  };

  const toggleExpand = (i: number) => {
    const s = new Set(expanded);
    s.has(i) ? s.delete(i) : s.add(i);
    setExpanded(s);
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Knowledge Search</h1>
        <p className="text-gray-500 mt-1">Hybrid retrieval across your enterprise knowledge base</p>
      </div>

      <form onSubmit={handleSearch} className="card space-y-4">
        <textarea
          value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask anything about your enterprise documents..."
          className="input resize-none h-24 text-base"
          onKeyDown={(e) => { if (e.key === 'Enter' && e.metaKey) handleSearch(e as any); }}
        />
        <div className="flex items-center gap-4">
          <div className="flex gap-1">
            {MODES.map((m) => (
              <button key={m} type="button" onClick={() => setMode(m)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  mode === m ? 'bg-brand-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}>{m}</button>
            ))}
          </div>
          <select value={topK} onChange={(e) => setTopK(Number(e.target.value))}
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-gray-300">
            {[4, 8, 12, 20].map((n) => <option key={n} value={n}>Top {n}</option>)}
          </select>
          <button type="submit" disabled={loading || !query.trim()} className="btn-primary flex items-center gap-2 ml-auto">
            {loading ? <Loader size={16} className="animate-spin" /> : <Search size={16} />}
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
      </form>

      {results && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-500">
              {results.total_results} results · {results.query_metadata?.retrieval_latency_ms}ms
              {results.query_metadata?.reranker_applied && <span className="ml-2 badge-blue">reranked</span>}
            </div>
          </div>

          {results.results?.map((r: any, i: number) => (
            <div key={r.chunk_id} className="card hover:border-gray-700 transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-mono text-brand-400">#{r.rank}</span>
                    <FileText size={14} className="text-gray-600" />
                    <span className="text-sm font-medium text-gray-300 truncate">{r.source?.original_name || r.source?.filename}</span>
                    {r.source?.page_number && <span className="text-xs text-gray-600">p.{r.source.page_number}</span>}
                    <span className="badge-gray capitalize">{r.chunk_type}</span>
                  </div>
                  <div className={`text-sm text-gray-400 leading-relaxed ${expanded.has(i) ? '' : 'line-clamp-3'}`}>
                    <ReactMarkdown>{r.content}</ReactMarkdown>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 flex-shrink-0">
                  <div className="flex items-center gap-1 text-yellow-500">
                    <Star size={12} />
                    <span className="text-xs">{(r.score * 100).toFixed(1)}</span>
                  </div>
                  <button onClick={() => toggleExpand(i)} className="text-gray-600 hover:text-gray-400">
                    {expanded.has(i) ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
