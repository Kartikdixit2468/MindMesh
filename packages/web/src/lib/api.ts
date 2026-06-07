const BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ||
  "http://localhost:8000";

export interface Query {
  id: string;
  problem: string;
  status: string;
  reward: string;
  current_round: number;
  response_count?: number;
  winner_address?: string;
  created_at: string;
  capabilities?: string[];
}

export interface Agent {
  address: string;
  name: string;
  tier: string;
  reputation: number;
  capabilities: string[];
  active: boolean;
  wins: number;
  losses: number;
  win_rate: number;
  stake?: string;
  metadata_uri?: string;
}

export interface TaskMemory {
  query_id: string;
  content: {
    events: Array<{
      type: string;
      round: number;
      agent_address?: string;
      score?: number;
      winner_address?: string;
      reason?: string;
      [key: string]: unknown;
    }>;
  };
  current_hash: string;
}

async function fetchAPI<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getQueries: (params?: { status?: string; limit?: number; capability?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.capability) qs.set("capability", params.capability);
    return fetchAPI<Query[]>(`/api/queries${qs.toString() ? "?" + qs : ""}`);
  },

  getQuery: (id: string) => fetchAPI<Query>(`/api/queries/${id}`),

  createQuery: (problem: string, reward: string, capabilities?: string[]) =>
    fetchAPI<Query>("/api/queries", {
      method: "POST",
      body: JSON.stringify({ problem, reward, capabilities }),
    }),

  getMemory: (queryId: string) =>
    fetchAPI<TaskMemory>(`/api/queries/${queryId}/memory`),

  getAgents: () => fetchAPI<Agent[]>("/api/agents/"),

  getLeaderboard: () => fetchAPI<Agent[]>("/api/agents/leaderboard"),

  getAgent: (address: string) => fetchAPI<Agent>(`/api/agents/${address}`),
};
