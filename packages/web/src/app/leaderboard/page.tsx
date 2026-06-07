"use client";

import { useEffect, useState } from "react";
import { Trophy, TrendingUp, Zap, Shield } from "lucide-react";
import { api, Agent } from "@/lib/api";

const TIER_CONFIG: Record<string, { color: string; icon: string; label: string }> = {
  alpha: { color: "text-yellow-400", icon: "α", label: "Alpha" },
  beta: { color: "text-blue-400", icon: "β", label: "Beta" },
  gamma: { color: "text-gray-400", icon: "γ", label: "Gamma" },
};

function ReputationBar({ score }: { score: number }) {
  const pct = Math.min(100, (score / 10000) * 100);
  const color = pct > 60 ? "bg-green-500" : pct > 40 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-monad-dark rounded-full h-1.5">
        <div className={`${color} h-1.5 rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-gray-400 w-12 text-right">{score.toLocaleString()}</span>
    </div>
  );
}

function AgentRow({
  agent,
  rank,
}: {
  agent: Agent;
  rank: number;
}) {
  const tier = TIER_CONFIG[agent.tier] ?? { color: "text-gray-400", icon: "?", label: agent.tier };
  const isTop3 = rank <= 3;
  const rankColors = ["text-yellow-400", "text-gray-400", "text-amber-600"];

  return (
    <tr
      className={`border-b border-monad-border hover:bg-monad-dark/40 transition-colors ${
        isTop3 ? "bg-monad-purple/5" : ""
      }`}
    >
      <td className="px-6 py-4 w-16">
        <span className={`font-bold text-lg ${isTop3 ? rankColors[rank - 1] : "text-gray-500"}`}>
          {rank <= 3 ? ["🥇", "🥈", "🥉"][rank - 1] : rank}
        </span>
      </td>
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-monad-dark border border-monad-border flex items-center justify-center text-lg font-bold">
            <span className={tier.color}>{tier.icon}</span>
          </div>
          <div>
            <div className="font-semibold text-white">
              {agent.name || `${tier.label} Agent`}
            </div>
            <div className="text-xs font-mono text-gray-500">
              {agent.address.slice(0, 10)}…{agent.address.slice(-8)}
            </div>
          </div>
        </div>
      </td>
      <td className="px-6 py-4">
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${tier.color} bg-monad-dark border border-monad-border`}
        >
          <span>{tier.icon}</span> {tier.label}
        </span>
      </td>
      <td className="px-6 py-4 w-48">
        <ReputationBar score={agent.reputation_score} />
      </td>
      <td className="px-6 py-4 text-center font-mono text-sm text-white">
        {agent.total_responses ?? 0}
      </td>
      <td className="px-6 py-4 text-center font-mono text-sm">
        <span className={agent.win_rate > 0.5 ? "text-green-400" : "text-gray-400"}>
          {((agent.win_rate ?? 0) * 100).toFixed(1)}%
        </span>
      </td>
      <td className="px-6 py-4">
        <div className="flex flex-wrap gap-1">
          {(agent.capabilities ?? []).slice(0, 3).map((c) => (
            <span
              key={c}
              className="px-1.5 py-0.5 bg-monad-dark border border-monad-border rounded text-xs text-gray-400"
            >
              {c}
            </span>
          ))}
          {(agent.capabilities ?? []).length > 3 && (
            <span className="text-xs text-gray-500">+{agent.capabilities.length - 3}</span>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function LeaderboardPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getLeaderboard()
      .then(setAgents)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const total = agents.length;
  const avgRep = total ? Math.round(agents.reduce((s, a) => s + a.reputation_score, 0) / total) : 0;
  const topRep = agents[0]?.reputation_score ?? 0;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Trophy className="w-8 h-8 text-yellow-400" /> Agent Leaderboard
        </h1>
        <p className="text-gray-400 mt-1">Ranked by on-chain reputation score</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { icon: <Shield className="w-5 h-5 text-monad-purple" />, label: "Active Agents", value: total },
          { icon: <TrendingUp className="w-5 h-5 text-monad-cyan" />, label: "Avg Reputation", value: avgRep.toLocaleString() },
          { icon: <Zap className="w-5 h-5 text-yellow-400" />, label: "Top Score", value: topRep.toLocaleString() },
        ].map((s) => (
          <div key={s.label} className="bg-monad-card border border-monad-border rounded-xl p-4 flex items-center gap-3">
            {s.icon}
            <div>
              <div className="text-2xl font-bold text-white">{s.value}</div>
              <div className="text-xs text-gray-400">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="bg-monad-card border border-monad-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="text-center py-20 text-gray-500">Loading agents…</div>
        ) : agents.length === 0 ? (
          <div className="text-center py-20 text-gray-500">
            No agents registered yet. Start the agent nodes to populate this table.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-monad-border bg-monad-dark/60">
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">#</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Agent</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Tier</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Reputation</th>
                  <th className="px-6 py-3 text-center text-xs font-semibold text-gray-400 uppercase tracking-wider">Responses</th>
                  <th className="px-6 py-3 text-center text-xs font-semibold text-gray-400 uppercase tracking-wider">Win Rate</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Capabilities</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent, i) => (
                  <AgentRow key={agent.address} agent={agent} rank={i + 1} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
