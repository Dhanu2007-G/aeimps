'use client';
import { useCallback, useState, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { ingestDocument, listJobs } from '@/lib/api';
import toast from 'react-hot-toast';
import { Upload, File, CheckCircle, XCircle, Clock, Loader } from 'lucide-react';

const STATUS_ICON: any = {
  QUEUED: <Clock size={14} className="text-yellow-400" />,
  RUNNING: <Loader size={14} className="text-blue-400 animate-spin" />,
  COMPLETED: <CheckCircle size={14} className="text-green-400" />,
  FAILED: <XCircle size={14} className="text-red-400" />,
};

export default function IngestPage() {
  const [uploading, setUploading] = useState(false);
  const [jobs, setJobs] = useState<any[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);

  const loadJobs = async () => {
    try { const r = await listJobs({ limit: 30 }); setJobs(r.jobs || []); }
    catch {} finally { setLoadingJobs(false); }
  };

  useEffect(() => { loadJobs(); const t = setInterval(loadJobs, 5000); return () => clearInterval(t); }, []);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setUploading(true);
    let ok = 0, fail = 0;
    for (const file of acceptedFiles) {
      try {
        await ingestDocument(file);
        ok++;
      } catch (e: any) { fail++; toast.error(`${file.name}: ${e.message}`); }
    }
    if (ok > 0) toast.success(`${ok} file${ok > 1 ? 's' : ''} queued for processing`);
    setUploading(false);
    setTimeout(loadJobs, 1000);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, multiple: true,
    accept: {
      'application/pdf': ['.pdf'],
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'],
      'text/*': ['.txt', '.md', '.csv', '.log'],
      'application/octet-stream': ['.py', '.js', '.ts', '.go', '.java', '.yaml', '.yml', '.json'],
    },
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Document Ingestion</h1>
        <p className="text-gray-500 mt-1">Upload PDFs, images, logs, code, CSV, and text files</p>
      </div>

      {/* Drop zone */}
      <div {...getRootProps()} className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
        isDragActive ? 'border-brand-500 bg-brand-600/10' : 'border-gray-700 hover:border-gray-600'
      } ${uploading ? 'opacity-50 pointer-events-none' : ''}`}>
        <input {...getInputProps()} />
        <Upload size={40} className="mx-auto mb-4 text-gray-600" />
        {isDragActive ? (
          <p className="text-brand-400 font-medium">Drop files here...</p>
        ) : (
          <>
            <p className="text-gray-300 font-medium">Drag & drop files or click to browse</p>
            <p className="text-gray-600 text-sm mt-2">PDF · Images · Markdown · CSV · Logs · Code files · Max 100MB each</p>
          </>
        )}
        {uploading && <p className="text-brand-400 mt-4 text-sm animate-pulse">Uploading...</p>}
      </div>

      {/* Jobs list */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">Processing Jobs</h2>
        {loadingJobs ? (
          <div className="text-gray-500 text-sm">Loading...</div>
        ) : jobs.length === 0 ? (
          <div className="text-gray-600 text-sm py-8 text-center">No jobs yet — upload a document to start</div>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => (
              <div key={job.job_id} className="flex items-center justify-between bg-gray-800 rounded-lg px-4 py-3">
                <div className="flex items-center gap-3 min-w-0">
                  <File size={16} className="text-gray-500 flex-shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm text-gray-300 truncate font-mono">{job.job_id.slice(0, 16)}…</div>
                    <div className="text-xs text-gray-600">{job.job_type}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {STATUS_ICON[job.status] || <span className="text-gray-500 text-xs">{job.status}</span>}
                  <span className="text-xs text-gray-500">{job.status}</span>
                  {job.duration_ms && <span className="text-xs text-gray-600">{job.duration_ms}ms</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
