'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, formatAPIError } from '@/lib/api';
import type { ProactiveDecision, ProactiveRun } from '@/lib/proactive-agent';

function displayTime(value: string | null): string {
  if (!value) return 'UNKNOWN TIME';
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString();
}

interface ProactiveTracePanelProps {
  onEvaluateNow?: () => Promise<boolean>;
}

export default function ProactiveTracePanel({ onEvaluateNow }: ProactiveTracePanelProps) {
  const [runs, setRuns] = useState<ProactiveDecision[]>([]);
  const [selected, setSelected] = useState<ProactiveRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRuns(await api.getProactiveRuns(20));
    } catch (loadError) {
      setError(formatAPIError(loadError, 'Could not load proactive trace.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const openRun = async (decisionId: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      setSelected(await api.getProactiveRun(decisionId));
    } catch (loadError) {
      setError(formatAPIError(loadError, 'Could not load trace details.'));
    } finally {
      setDetailLoading(false);
    }
  };

  const evaluateNow = async () => {
    if (!onEvaluateNow) return;
    setChecking(true);
    setError(null);
    try {
      await onEvaluateNow();
      await loadRuns();
    } catch (evaluateError) {
      setError(formatAPIError(evaluateError, 'Could not evaluate proactive policy.'));
    } finally {
      setChecking(false);
    }
  };

  return (
    <section className="space-y-3 border-[3px] border-black bg-amber-50 p-3 font-mono">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-black uppercase">Proactive Trace</h3>
          <p className="mt-1 text-[9px] text-gray-600">Structured decisions only—no prompts or private chat.</p>
        </div>
        <div className="flex gap-1">
          {onEvaluateNow ? (
            <button
              type="button"
              onClick={() => void evaluateNow()}
              disabled={checking || loading}
              className="border-2 border-black bg-cyan-300 px-2 py-1 text-[9px] font-black disabled:opacity-50"
            >
              {checking ? 'CHECKING' : 'CHECK NOW'}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void loadRuns()}
            disabled={loading || checking}
            className="border-2 border-black bg-white px-2 py-1 text-[9px] font-black disabled:opacity-50"
          >
            REFRESH
          </button>
        </div>
      </div>

      {error ? <p role="alert" className="border-2 border-red-600 bg-red-100 p-2 text-[9px] font-bold text-red-800">{error}</p> : null}
      {loading ? <p className="text-[9px] font-bold">LOADING RUNS...</p> : null}
      {!loading && runs.length === 0 ? (
        <p className="border-2 border-dashed border-gray-400 bg-white p-2 text-[9px] text-gray-600">No proactive decisions yet.</p>
      ) : null}

      <div className="max-h-52 space-y-2 overflow-y-auto">
        {runs.map(run => (
          <button
            key={run.decision_id}
            type="button"
            onClick={() => void openRun(run.decision_id)}
            className={`w-full border-2 border-black p-2 text-left ${selected?.decision_id === run.decision_id ? 'bg-cyan-200' : 'bg-white'}`}
          >
            <div className="flex items-center justify-between gap-2 text-[9px] font-black">
              <span>{run.action}</span>
              <span>{run.status}</span>
            </div>
            <div className="mt-1 text-[8px] text-gray-600">{displayTime(run.created_at)}</div>
            <div className="mt-1 text-[8px] font-bold text-amber-800">{run.reason_codes.join(' · ')}</div>
          </button>
        ))}
      </div>

      {detailLoading ? <p className="text-[9px] font-bold">LOADING TRACE...</p> : null}
      {selected && !detailLoading ? (
        <div className="space-y-2 border-t-2 border-dashed border-gray-500 pt-3">
          <div className="break-all text-[8px] text-gray-600">RUN {selected.decision_id}</div>
          <div className="flex flex-wrap gap-1">
            {selected.candidate_actions.map(action => (
              <span key={action} className="border border-black bg-white px-1 py-0.5 text-[8px] font-bold">{action}</span>
            ))}
          </div>
          {selected.trace.map(event => (
            <details key={`${event.sequence}-${event.stage}`} className="border-2 border-black bg-white p-2">
              <summary className="cursor-pointer text-[9px] font-black">
                {event.sequence}. {event.stage}
              </summary>
              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-[8px] text-gray-700">
                {JSON.stringify(event.details, null, 2)}
              </pre>
            </details>
          ))}
        </div>
      ) : null}
    </section>
  );
}
