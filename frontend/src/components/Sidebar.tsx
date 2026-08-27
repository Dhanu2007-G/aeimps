'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Brain, Upload, Search, Bot, GitBranch, BarChart3, Activity } from 'lucide-react';

const links = [
  { href: '/', label: 'Dashboard', icon: Activity },
  { href: '/ingest', label: 'Ingest', icon: Upload },
  { href: '/search', label: 'Search', icon: Search },
  { href: '/agents', label: 'Agents', icon: Bot },
  { href: '/knowledge-graph', label: 'Knowledge Graph', icon: GitBranch },
  { href: '/evaluations', label: 'Evaluations', icon: BarChart3 },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="fixed inset-y-0 left-0 w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-brand-600 rounded-lg flex items-center justify-center">
            <Brain size={20} />
          </div>
          <div>
            <div className="font-bold text-white text-sm">AEIMPS</div>
            <div className="text-xs text-gray-500">Enterprise Intelligence</div>
          </div>
        </div>
      </div>
      <nav className="flex-1 p-4 space-y-1">
        {links.map(({ href, label, icon: Icon }) => {
          const active = path === href || (href !== '/' && path.startsWith(href));
          return (
            <Link key={href} href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active ? 'bg-brand-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}>
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-gray-800 text-xs text-gray-600">v1.0.0 MVP</div>
    </aside>
  );
}
