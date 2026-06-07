"use client";

import { useEffect, useState, useRef } from "react";
import { RefreshCw, Search, Zap, ChevronDown, ChevronUp } from "lucide-react";
import { api, Query, TaskMemory } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";
const POLL_INTERVAL = 4000;

function formatAddr(addr: string) {
  return addr ? `${addr.slice(0, 8)}…${addr.slice(-6)}` : "";
}

function MemoryPanel({ queryId }: { queryId: string }) {
  const [memory, setMemory] = useState<TaskMemory | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getMemory(queryId)
      .then(setMemory)
      .catch(() => setMemory(null))
      .finally(() => setLoading(false));
  }, [queryId]);

  if (loading) return <div className="text-gray-500 text-sm p-4">Loading memory…</div>;
  if (!memory) return <div className="text-gray-500 text-sm p-4">No memory available</div>;

  const events = memory.content?.events ?? [];
  const rounds: Record<number, typeof events> = {};
  for (const ev of events) {
    const r = ev.round ?? 0;
    (rounds[r] = rounds[r] || []).push(ev);
  }

  return (
    <div className="p-4 space-y-3">
      <div className="text-xs text-gray-500 font-mono">
        Hash: {memory.current_hash?.slice(0, 20)}…
      </div>
      {Object.entries(rounds)
        .sort(([a], [b]) => Number(a) - Number(b))
        .map(([round, evs]) => (
          <div key={round} className="border border-monad-border rounded-lg overflow-hidden">
            <div className="bg-monad-dark/60 px-3 py-1.5 text-sm font-semibold text-cyan-400">
              Round {round}
            </div>
            <div className="divide-y divide-monad-border">
              {evs.map((ev, i) => (
                <div key={i} className="px-3 py-2 text-xs font-mono">
                  <span className="text-yellow-400">{ev.type}</span>
                  {ev.agent_address && (
                    <span className="text-gray-400 ml-2">agent={formatAddr(ev.agent_address)}</span>
                  )}
                  {ev.score !== undefined && (
                    <span
                      className={`ml-2 font-bold ${
                        ev.score >= 0.75 ? "text-green-400" : ev.score >= 0.6 ? "text-yellow-400" : "text-red-400"
                      }`}
                    >
                      score={ev.score.toFixed(3)}
                    </span>
                  )}
                  {ev.winner_address && (
                    <span className="text-green-400 ml-2">★ winner={formatAddr(ev.winner_address)}</span>
                  )}
                  {ev.reason && (
                    <span className="text-orange-400 ml-2">[{String(ev.reason).slice(0, 60)}]</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
    </div>
  );
}

function QueryCard({ query }: { query: Query }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-monad-card border border-monad-border rounded-xl overflow-hidden hover:border-monad-purple/30 transition-colors">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left p-4 flex items-start gap-4"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <StatusBadge status={query.status} />
            <span className="text-xs text-gray-500 font-mono">#{query.id.slice(0, 8)}</span>
            <span className="text-xs text-gray-500">Round {query.current_round}</span>
            <span className="text-xs text-monad-purple ml-auto">{query.reward} MON</span>
          </div>
          <p className="text-sm text-white line-clamp-2">{query.problem}</p>
          {query.winner_address && (
            <p className="text-xs text-green-400 mt-1 font-mono">
              ★ Winner: {formatAddr(query.winner_address)}
            </p>
          )}
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-gray-400 shrink-0 mt-1" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400 shrink-0 mt-1" />
        )}
      </button>
      {expanded && (
        <div className="border-t border-monad-border bg-monad-dark/40">
          <MemoryPanel queryId={query.id} />
        </div>
      )}
    </div>
  );
}

export default function ExplorePage() {
  const [queries, setQueries] = useState<Query[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<string[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  function fetchQueries() {
    api.getQueries({ limit: 50 })
      .then(setQueries)
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    fetchQueries();
    const iv = setInterval(fetchQueries, POLL_INTERVAL);
    return () => clearInterval(iv);
  }, []);

  // Live log feed via WebSocket
  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          const text = msg.message || msg.data || JSON.stringify(msg);
          setLogs((prev) => [text, ...prev].slice(0, 100));
        } catch {}
      };
      ws.onclose = () => setTimeout(connect, 3000);
    }
    connect();
    return () => wsRef.current?.close();
  }, []);

  const filtered = queries.filter(
    (q) =>
      !filter ||
      q.problem.toLowerCase().includes(filter.toLowerCase()) ||
      q.status.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Explore Queries</h1>
          <p className="text-gray-400 mt-1">Live and historical AI agent task results</p>
        </div>
        <button
          onClick={fetchQueries}
          className="flex items-center gap-2 bg-monad-card border border-monad-border hover:border-monad-purple/40 px-4 py-2 rounded-lg text-sm transition-colors"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Query list */}
        <div className="lg:col-span-2 space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by status, problem…"
              className="w-full bg-monad-card border border-monad-border rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-monad-purple/60 transition-colors"
            />
          </div>

          {loading ? (
            <div className="text-center py-20 text-gray-500">Loading queries…</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-20 text-gray-500">
              No queries yet. Submit one from the{" "}
              <a href="/" className="text-monad-purple hover:underline">home page</a>!
            </div>
          ) : (
            filtered.map((q) => <QueryCard key={q.id} query={q} />)
          )}
        </div>

        {/* Live log sidebar */}
        <div className="bg-monad-card border border-monad-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-monad-border flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-sm font-semibold text-white">Live Logs</span>
          </div>
          <div className="p-3 space-y-1 h-[60vh] overflow-y-auto">
            {logs.length === 0 ? (
              <p className="text-gray-500 text-xs">Connecting to orchestrator…</p>
            ) : (
              logs.map((log, i) => (
                <p key={i} className="text-xs font-mono text-gray-400 break-all">
                  {log.slice(0, 120)}
                </p>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
