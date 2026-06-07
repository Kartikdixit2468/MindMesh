"use client";

import { useEffect, useState } from "react";
import { useAccount } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { Activity, Zap, Trophy, Clock } from "lucide-react";
import { api, Query } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div className="bg-monad-card border border-monad-border rounded-xl p-5">
      <div className={`${color} mb-3`}>{icon}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-sm text-gray-400">{label}</div>
    </div>
  );
}

function QueryRow({ query }: { query: Query }) {
  const date = new Date(query.created_at).toLocaleString();
  return (
    <tr className="border-b border-monad-border hover:bg-monad-dark/30 transition-colors">
      <td className="px-4 py-3 font-mono text-xs text-gray-400">{query.id.slice(0, 10)}…</td>
      <td className="px-4 py-3 text-sm text-white max-w-xs truncate">{query.problem}</td>
      <td className="px-4 py-3">
        <StatusBadge status={query.status} />
      </td>
      <td className="px-4 py-3 text-sm font-mono text-monad-purple">{query.reward} MON</td>
      <td className="px-4 py-3 text-xs text-gray-500">{date}</td>
    </tr>
  );
}

export default function DashboardPage() {
  const { isConnected } = useAccount();
  const [queries, setQueries] = useState<Query[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getQueries({ limit: 20 })
      .then(setQueries)
      .catch(() => {})
      .finally(() => setLoading(false));

    const iv = setInterval(() => {
      api.getQueries({ limit: 20 }).then(setQueries).catch(() => {});
    }, 5000);
    return () => clearInterval(iv);
  }, []);

  const settled = queries.filter((q) => q.status === "settled").length;
  const active = queries.filter((q) => !["settled", "failed"].includes(q.status)).length;
  const totalMon = queries.reduce((s, q) => s + parseFloat(q.reward || "0"), 0);

  if (!isConnected) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white mb-3">Connect Your Wallet</h1>
          <p className="text-gray-400 mb-8 max-w-md">
            Connect your wallet to view your query history and agent reputation on Monad.
          </p>
          <ConnectButton />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-400 mt-1">Overview of all queries on MonadBlitz</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={<Activity className="w-5 h-5" />}
          label="Total Queries"
          value={queries.length}
          color="text-monad-purple"
        />
        <StatCard
          icon={<Zap className="w-5 h-5" />}
          label="Active"
          value={active}
          color="text-monad-cyan"
        />
        <StatCard
          icon={<Trophy className="w-5 h-5" />}
          label="Settled"
          value={settled}
          color="text-monad-green"
        />
        <StatCard
          icon={<Clock className="w-5 h-5" />}
          label="Total MON Posted"
          value={totalMon.toFixed(3)}
          color="text-yellow-400"
        />
      </div>

      {/* Query table */}
      <div className="bg-monad-card border border-monad-border rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-monad-border">
          <h2 className="font-semibold text-white">Recent Queries</h2>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-500">Loading…</div>
        ) : queries.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No queries yet. <a href="/" className="text-monad-purple hover:underline">Submit one!</a>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-monad-border bg-monad-dark/50">
                  <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">ID</th>
                  <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Problem</th>
                  <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Reward</th>
                  <th className="px-4 py-3 text-left text-xs text-gray-400 uppercase">Created</th>
                </tr>
              </thead>
              <tbody>
                {queries.map((q) => (
                  <QueryRow key={q.id} query={q} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
