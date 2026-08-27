import type { Metadata } from 'next';
import './globals.css';
import { Toaster } from 'react-hot-toast';
import Sidebar from '@/components/Sidebar';

export const metadata: Metadata = {
  title: 'AEIMPS — Enterprise Intelligence Platform',
  description: 'Autonomous Enterprise Intelligence & Multimodal Processing System',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen flex">
        <Sidebar />
        <main className="flex-1 ml-64 p-8 overflow-auto">
          {children}
        </main>
        <Toaster position="top-right" toastOptions={{
          style: { background: '#1f2937', color: '#f3f4f6', border: '1px solid #374151' }
        }} />
      </body>
    </html>
  );
}
