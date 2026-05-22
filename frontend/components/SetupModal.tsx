'use client';

import { motion } from 'motion/react';
import { useState } from 'react';

interface SetupModalProps {
  onComplete: (name: string) => void;
}

export default function SetupModal({ onComplete }: SetupModalProps) {
  const [name, setName] = useState('Pomo');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      onComplete(name.trim());
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={{ scale: 0.9, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        className="w-full max-w-sm bg-white border-[4px] border-black shadow-[12px_12px_0_#000] p-6 sm:p-8 relative overflow-hidden"
      >
        <div className="text-center mb-8 relative">
          <div className="w-24 h-24 mx-auto bg-black border-[4px] border-black flex items-center justify-center mb-6 shadow-[inset_0_0_10px_rgba(255,255,255,0.2),_4px_4px_0_#00cbd7]">
            {/* Grid overlay */}
            <div className="absolute inset-0 bg-[linear-gradient(rgba(34,211,238,0.2)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.2)_1px,transparent_1px)] bg-[size:4px_4px] pointer-events-none opacity-50" />
            <div className="flex gap-2 relative z-10">
                <div className="w-4 h-8 bg-cyan-400 animate-pulse" />
                <div className="w-4 h-8 bg-cyan-400 animate-pulse delay-75" />
            </div>
          </div>
          <h2 className="text-2xl font-bold text-black font-space uppercase tracking-wider mb-2">Initialize Pet</h2>
          <p className="text-gray-600 text-xs font-mono font-bold">BOOT SEQUENCE... ENTER DESIGNATION FOR VIRTUAL COMPANION.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-xs font-mono font-bold uppercase text-black mb-2">
              DESIGNATION
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-white border-[4px] border-black px-4 py-3 text-black font-mono font-bold text-lg outline-none focus:bg-cyan-50 shadow-[4px_4px_0_#000] transition-colors text-center uppercase"
              placeholder="NAME..."
              autoFocus
            />
          </div>
          
          <button
            type="submit"
            disabled={!name.trim()}
            className="w-full bg-cyan-400 hover:bg-cyan-300 text-black font-bold font-mono uppercase text-lg py-3 border-[4px] border-black shadow-[4px_4px_0_#000] active:shadow-none active:translate-y-[4px] active:translate-x-[4px] disabled:opacity-50 disabled:active:shadow-[4px_4px_0_#000] disabled:active:translate-y-0 disabled:active:translate-x-0 transition-all"
          >
            START
          </button>
        </form>
      </motion.div>
    </div>
  );
}
