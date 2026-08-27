'use client';
import { useState } from 'react';
import { getEntity } from '@/lib/api';
import toast from 'react-hot-toast';
import { Search, GitBranch, Loader } from 'lucide-react';

export default function KnowledgeGraphPage() {
  const [query, setQuery] = useState('');
  const [entity, setEntity] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try { setEntity(await getEntity(query)); }
    catch (e: any) { toast.error(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Knowledge Graph</h1>
        <p className="text-gray-500 mt-1">Explore entity relationships extracted from your documents</p>
      </div>

      <form onSubmit={handleSearch} className="flex gap-3">
        <input value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for an entity (e.g. payment-service, AuthError, kubernetes)..."
          className="input flex-1" />
        <button type="submit" disabled={loading || !query.trim()} className="btn-primary flex items-center gap-2">
          {loading ? <Loader size={16} className="animate-spin" /> : <Search size={16} />}
          Explore
        </button>
      </form>

      {entity && (
        <div className="space-y-6">
          {/* Entity card */}
          <div className="card">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-brand-600/20 rounded-xl flex items-center justify-center flex-shrink-0">
                <GitBranch size={22} className="text-brand-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">{entity.entity?.name}</h2>
                <span className="badge-blue capitalize mt-1">{entity.entity?.type?.replace(/_/g, ' ')}</span>
              </div>
            </div>
          </div>

          {/* Related entities */}
          {entity.related_entities?.length > 0 && (
            <div className="card">
              <h3 className="font-semibold text-white mb-4">Related Entities ({entity.related_entities.length})</h3>
              <div className="flex flex-wrap gap-2">
                {entity.related_entities.map((r: any, i: number) => (
                  <button key={i} onClick={() => { setQuery(r.name); }}
                    className="bg-gray-800 hover:bg-gray-700 rounded-lg px-3 py-2 text-sm transition-colors text-left">
                    <span className="text-gray-300">{r.name}</span>
                    {r.relation && <span className="text-xs text-gray-600 ml-2">via {r.relation}</span>}
                    {r.type && <span className="text-xs text-brand-500 ml-1 capitalize">{r.type?.replace(/_/g, ' ')}</span>}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Source documents */}
          {entity.source_documents?.length > 0 && (
            <div className="card">
              <h3 className="font-semibold text-white mb-3">Appears In ({entity.source_documents.length} documents)</h3>
              <div className="flex flex-wrap gap-2">
                {entity.source_documents.map((id: string) => (
                  <span key={id} className="badge-gray font-mono text-xs">{id.slice(0, 16)}…</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!entity && !loading && (
        <div className="card text-center py-16">
          <GitBranch size={48} className="mx-auto text-gray-700 mb-4" />
          <p className="text-gray-600">Search for an entity to explore its knowledge graph neighborhood</p>
          <p className="text-gray-700 text-sm mt-2">Try: service names, error types, technology names</p>
        </div>
      )}
    </div>
  );
}
