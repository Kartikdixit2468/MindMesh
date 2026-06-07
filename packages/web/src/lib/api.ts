const BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL || "http://localhost:8000";

export interface Query {
  id: string;
  problem: string;
  status: string;
  reward: string;
  current_round: number;
  response_count: number;
  winner_address?: string;
  created_at: string;
}

export interface Agent {
  address: string;
  name: string;
  tier: string;
  reputation_score: number;
  capabilities: string[];
  is_active: boolean;
  total_responses: number;
  win_rate: number;
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
    ...opts,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  getQueries: (params?: { status?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    return fetchAPI<Query[]>(`/api/queries${qs.toString() ? "?" + qs : ""}`);
  },

  getQuery: (id: string) => fetchAPI<Query>(`/api/queries/${id}`),

  createQuery: (problem: string, reward: string) =>
    fetchAPI<Query>("/api/queries", {
      method: "POST",
      body: JSON.stringify({ problem, reward }),
    }),

  getMemory: (queryId: string) =>
    fetchAPI<TaskMemory>(`/api/queries/${queryId}/memory`),

  getAgents: () => fetchAPI<Agent[]>("/api/agents/"),

  getLeaderboard: () => fetchAPI<Agent[]>("/api/agents/leaderboard"),
};
