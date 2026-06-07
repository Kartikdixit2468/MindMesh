"use client";

import { useEffect, useState } from "react";
import { Trophy, TrendingUp, Zap, Shield, Cpu, ChevronUp, ChevronDown } from "lucide-react";
import { api, Agent } from "@/lib/api";

const TIER_CONFIG: Record<string, { color: string; bg: string; border: string; glyph: string; label: string }> = {
  alpha: { color: '#eab308', bg: 'rgba(234,179,8,0.12)', border: 'rgba(234,179,8,0.3)', glyph: 'α', label: 'Alpha' },
  beta: { color: '#818cf8', bg: 'rgba(129,140,248,0.12)', border: 'rgba(129,140,248,0.3)', glyph: 'β', label: 'Beta' },
  gamma: { color: '#94a3b8', bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.25)', glyph: 'γ', label: 'Gamma' },
};

const RANK_CONFIG = [
  { medal: '🥇', glow: 'rgba(234,179,8,0.25)', border: 'rgba(234,179,8,0.3)', color: '#eab308' },
  { medal: '🥈', glow: 'rgba(148,163,184,0.2)', border: 'rgba(148,163,184,0.25)', color: '#94a3b8' },
  { medal: '🥉', glow: 'rgba(180,120,80,0.2)', border: 'rgba(180,120,80,0.25)', color: '#cd7f32' },
];

const ALL_CAPS = ['coding', 'math', 'research', 'analysis', 'writing', 'blockchain', 'general'];

function fmtAddr(a: string) {
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

function ReputationBar({ score, maxScore }: { score: number; maxScore: number }) {
  const pct = maxScore > 0 ? Math.min(100, (score / maxScore) * 100) : 0;
  const color = pct > 60 ? '#10b981' : pct > 35 ? '#eab308' : '#6366f1';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 rounded-full overflow-hidden" style={{ background: 'rgba(99,102,241,0.08)', height: 6 }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}, ${color}cc)`,
            boxShadow: `0 0 8px ${color}60`,
          }}
        />
      </div>
      <span className="text-xs font-mono w-16 text-right" style={{ color: '#64748b' }}>
        {score.toLocaleString()}
      </span>
    </div>
  );
}

type SortKey = 'reputation' | 'win_rate' | 'wins';

export default function LeaderboardPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [capFilter, setCapFilter] = useState('all');
  const [sortKey, setSortKey] = useState<SortKey>('reputation');
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    api.getLeaderboard()
      .then(setAgents)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const maxRep = agents.reduce((m, a) => Math.max(m, a.reputation ?? 0), 0);
  const avgRep = agents.length ? Math.round(agents.reduce((s, a) => s + (a.reputation ?? 0), 0) / agents.length) : 0;

  const filtered = agents
    .filter((a) => capFilter === 'all' || (a.capabilities ?? []).includes(capFilter))
    .sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortAsc((v) => !v);
    else { setSortKey(key); setSortAsc(false); }
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return null;
    return sortAsc
      ? <ChevronUp className="w-3 h-3 inline ml-1" />
      : <ChevronDown className="w-3 h-3 inline ml-1" />;
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-black flex items-center gap-3" style={{ color: '#f1f5f9' }}>
          <Trophy className="w-8 h-8" style={{ color: '#eab308' }} />
          Agent Leaderboard
        </h1>
        <p className="mt-1 text-sm" style={{ color: '#475569' }}>
          Ranked by on-chain reputation score · Updated in real-time
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { icon: Shield, label: 'Total Agents', value: agents.length, color: '#6366f1' },
          { icon: TrendingUp, label: 'Avg Reputation', value: avgRep.toLocaleString(), color: '#06b6d4' },
          { icon: Zap, label: 'Top Score', value: (agents[0]?.reputation ?? 0).toLocaleString(), color: '#eab308' },
        ].map(({ icon: Icon, label, value, color }) => (
          <div key={label} className="card p-5 flex items-center gap-4">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: `${color}12`, border: `1px solid ${color}25` }}
            >
              <Icon className="w-5 h-5" style={{ color }} />
            </div>
            <div>
              <div className="text-xl font-black font-mono" style={{ color }}>{value}</div>
              <div className="text-xs" style={{ color: '#475569' }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap mb-6">
        <span className="text-xs font-mono" style={{ color: '#475569' }}>FILTER:</span>
        {['all', ...ALL_CAPS].map((c) => (
          <button
            key={c}
            onClick={() => setCapFilter(c)}
            className="px-3 py-1 rounded-lg text-xs font-mono transition-all capitalize"
            style={{
              background: capFilter === c ? 'rgba(99,102,241,0.2)' : 'var(--bg-card)',
              border: `1px solid ${capFilter === c ? 'rgba(99,102,241,0.4)' : 'rgba(99,102,241,0.1)'}`,
              color: capFilter === c ? '#818cf8' : '#475569',
            }}
          >
            {c}
          </button>
        ))}
      </div>

      {/* Top 3 Hero Cards */}
      {!loading && filtered.length >= 1 && (
        <div className="grid md:grid-cols-3 gap-4 mb-8">
          {[1, 0, 2].map((slot, idx) => {
            const agent = filtered[slot];
            if (!agent) return <div key={idx} />;
            const rank = slot + 1;
            const rc = RANK_CONFIG[slot] ?? { medal: `#${rank}`, glow: '', border: 'rgba(99,102,241,0.15)', color: '#94a3b8' };
            const tier = TIER_CONFIG[agent.tier] ?? { color: '#94a3b8', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.2)', glyph: '?', label: agent.tier };
            const isFirst = slot === 0;
            return (
              <div
                key={agent.address}
                className="card p-6 text-center relative overflow-hidden"
                style={{
                  borderColor: rc.border,
                  boxShadow: isFirst ? `0 0 40px ${rc.glow}` : undefined,
                  marginTop: isFirst ? 0 : 16,
                }}
              >
                {isFirst && (
                  <div
                    className="absolute inset-0 opacity-5"
                    style={{ background: 'radial-gradient(circle at 50% 0%, #eab308, transparent 70%)' }}
                  />
                )}
                <div className="text-4xl mb-3">{rc.medal}</div>
                <div
                  className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-3 text-xl font-black"
                  style={{ background: tier.bg, border: `1px solid ${tier.border}`, color: tier.color }}
                >
                  {tier.glyph}
                </div>
                <h3 className="font-bold mb-1" style={{ color: '#f1f5f9' }}>
                  {agent.name || `${tier.label} Agent`}
                </h3>
                <p className="text-xs font-mono mb-4" style={{ color: '#475569' }}>
                  {fmtAddr(agent.address)}
                </p>
                <div className="text-2xl font-black font-mono mb-1" style={{ color: rc.color }}>
                  {(agent.reputation ?? 0).toLocaleString()}
                </div>
                <div className="text-xs mb-4" style={{ color: '#475569' }}>Reputation Score</div>
                <div className="flex justify-center gap-4 text-xs">
                  <span style={{ color: '#10b981' }}>
                    {((agent.win_rate ?? 0) * 100).toFixed(0)}% win
                  </span>
                  <span style={{ color: '#64748b' }}>
                    {(agent.wins ?? 0) + (agent.losses ?? 0)} resp
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Full Table */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: 'var(--bg-card)', border: '1px solid rgba(99,102,241,0.15)' }}
      >
        {loading ? (
          <div className="p-8 space-y-3">
            {[1,2,3,4,5].map((i) => (
              <div key={i} className="skeleton h-14 w-full rounded-xl" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20">
            <Cpu className="w-12 h-12 mx-auto mb-4" style={{ color: '#1e293b' }} />
            <p className="font-semibold" style={{ color: '#475569' }}>No agents found</p>
            <p className="text-sm mt-1" style={{ color: '#334155' }}>
              Start the agent nodes to populate the leaderboard.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(99,102,241,0.08)', background: 'rgba(0,0,0,0.2)' }}>
                  {[
                    { label: '#', key: null },
                    { label: 'Agent', key: null },
                    { label: 'Tier', key: null },
                    { label: 'Reputation', key: 'reputation' as SortKey },
                    { label: 'Wins', key: 'wins' as SortKey },
                    { label: 'Win Rate', key: 'win_rate' as SortKey },
                    { label: 'Capabilities', key: null },
                  ].map(({ label, key }) => (
                    <th
                      key={label}
                      className="px-5 py-3 text-left text-xs font-mono uppercase tracking-wider select-none"
                      style={{
                        color: (key && sortKey === key) ? '#818cf8' : '#334155',
                        cursor: key ? 'pointer' : 'default',
                      }}
                      onClick={() => key && toggleSort(key)}
                    >
                      {label}
                      {key && <SortIcon col={key} />}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((agent, i) => {
                  const rank = i + 1;
                  const isTop3 = rank <= 3;
                  const rc = RANK_CONFIG[i];
                  const tier = TIER_CONFIG[agent.tier] ?? { color: '#94a3b8', bg: 'rgba(148,163,184,0.08)', border: 'rgba(148,163,184,0.15)', glyph: '?', label: agent.tier };

                  return (
                    <tr
                      key={agent.address}
                      className="transition-colors hover:bg-white/[0.02]"
                      style={{
                        borderBottom: '1px solid rgba(99,102,241,0.06)',
                        background: isTop3 ? `${rc?.glow?.replace('0.25', '0.03') ?? ''}` : undefined,
                      }}
                    >
                      {/* Rank */}
                      <td className="px-5 py-4 w-14">
                        {isTop3 ? (
                          <span className="text-xl">{rc?.medal}</span>
                        ) : (
                          <span className="text-sm font-mono" style={{ color: '#334155' }}>{rank}</span>
                        )}
                      </td>

                      {/* Agent */}
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div
                            className="w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold flex-shrink-0"
                            style={{ background: tier.bg, border: `1px solid ${tier.border}`, color: tier.color }}
                          >
                            {tier.glyph}
                          </div>
                          <div>
                            <div className="text-sm font-semibold" style={{ color: '#e2e8f0' }}>
                              {agent.name || `${tier.label} Agent`}
                            </div>
                            <div className="text-xs font-mono" style={{ color: '#334155' }}>
                              {fmtAddr(agent.address)}
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Tier */}
                      <td className="px-5 py-4">
                        <span
                          className="text-xs font-mono px-2 py-0.5 rounded-full"
                          style={{ background: tier.bg, color: tier.color, border: `1px solid ${tier.border}` }}
                        >
                          {tier.glyph} {tier.label}
                        </span>
                      </td>

                      {/* Reputation bar */}
                      <td className="px-5 py-4 w-48">
                        <ReputationBar score={agent.reputation ?? 0} maxScore={maxRep} />
                      </td>

                      {/* Wins */}
                      <td className="px-5 py-4 text-center font-mono text-sm" style={{ color: '#94a3b8' }}>
                        {(agent.wins ?? 0) + (agent.losses ?? 0)}
                      </td>

                      {/* Win rate */}
                      <td className="px-5 py-4 text-center font-mono text-sm">
                        <span style={{ color: (agent.win_rate ?? 0) > 0.5 ? '#10b981' : '#64748b' }}>
                          {((agent.win_rate ?? 0) * 100).toFixed(1)}%
                        </span>
                      </td>

                      {/* Capabilities */}
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap gap-1">
                          {(agent.capabilities ?? []).slice(0, 3).map((c) => (
                            <span
                              key={c}
                              className="text-xs px-1.5 py-0.5 rounded font-mono"
                              style={{
                                background: 'rgba(99,102,241,0.08)',
                                color: '#475569',
                                border: '1px solid rgba(99,102,241,0.1)',
                              }}
                            >
                              {c}
                            </span>
                          ))}
                          {(agent.capabilities ?? []).length > 3 && (
                            <span className="text-xs" style={{ color: '#334155' }}>
                              +{agent.capabilities.length - 3}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
