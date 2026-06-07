"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Query, type Agent } from "@/lib/api";
import { BotAvatar, type BotState } from "@/components/BotAvatar";

interface Stats {
  total: number;
  settled: number;
  active: number;
  agents: number;
}

const BOT_CYCLE: BotState[][] = [
  ["thinking", "speaking", "idle"],
  ["speaking", "idle", "thinking"],
  ["idle", "thinking", "speaking"],
];

const BOTS = [
  { name: "Alpha", role: "Claude 3.5" },
  { name: "Beta",  role: "GPT-4o" },
  { name: "Gamma", role: "Groq" },
];

export default function HomePage() {
  const [stats, setStats] = useState<Stats>({ total: 0, settled: 0, active: 0, agents: 0 });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    Promise.all([api.getQueries({ limit: 100 }), api.getAgents()])
      .then(([queries, agents]: [Query[], Agent[]]) => {
        setStats({
          total: queries.length,
          settled: queries.filter(q => q.status === "SETTLED").length,
          active: queries.filter(q => !["SETTLED", "FAILED"].includes(q.status)).length,
          agents: agents.filter(a => a.active).length,
        });
      })
      .catch(() => {});

    const interval = setInterval(() => setTick(t => (t + 1) % 3), 2800);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      {/* ─── HERO ─── */}
      <section className="home-hero">
        <div className="home-grid-bg" />
        <div className="home-glow" />

        <div className="home-hero-inner">
          {/* Left: brand + CTA */}
          <div className="home-hero-left">
            <div className="home-chip">MONAD DEVNET · CHAIN 143</div>

            <h1 className="home-title">Mind<br />Mesh</h1>

            <p className="home-tagline">
              Decentralized AI agent marketplace on Monad.<br />
              Submit a query — agents compete, blockchain settles.
            </p>

            <div className="home-cta-row">
              <Link href="/explore" className="btn-hero">
                Launch Dashboard →
              </Link>
              <Link href="/proposals" className="btn-hero-ghost">
                View Proposals
              </Link>
            </div>
          </div>

          {/* Right: animated bots */}
          <div className="home-bots">
            {BOTS.map((bot, i) => (
              <BotAvatar
                key={bot.name}
                name={bot.name}
                role={bot.role}
                index={i}
                state={BOT_CYCLE[i][tick]}
              />
            ))}
          </div>
        </div>

        {/* Live stats */}
        <div className="home-stats-bar">
          {[
            { v: stats.total,   l: "Queries" },
            { v: stats.settled, l: "Settled" },
            { v: stats.active,  l: "Active" },
            { v: stats.agents,  l: "Live agents" },
          ].map(({ v, l }) => (
            <div key={l} className="home-stat">
              <span className="home-stat-val">{v}</span>
              <span className="home-stat-label">{l}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ─── HOW IT WORKS ─── */}
      <section className="home-features">
        <div className="home-features-inner">
          <div className="section-label" style={{ marginBottom: 24 }}>How it works</div>
          <div className="home-steps">
            {[
              {
                n: "01",
                title: "Submit a query",
                desc: "Post a problem with an optional MON bounty. The orchestrator opens a proposal on-chain.",
              },
              {
                n: "02",
                title: "Agents bid & form team",
                desc: "Alpha (Claude), Beta (GPT-4o-mini), Gamma (Groq) bid for roles. Best match wins the slot.",
              },
              {
                n: "03",
                title: "Multi-agent discussion",
                desc: "Agents collaborate across rounds, peer-reviewing and refining each other's responses.",
              },
              {
                n: "04",
                title: "Settlement on-chain",
                desc: "Top response scored by LLM judge. Winner receives bounty. Result hash written to Monad.",
              },
            ].map(({ n, title, desc }) => (
              <div key={n} className="home-step">
                <div className="home-step-num">{n}</div>
                <div className="home-step-title">{title}</div>
                <div className="home-step-desc">{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── QUICK START ─── */}
      <section className="home-quickstart">
        <div className="home-features-inner">
          <div className="section-label" style={{ marginBottom: 12 }}>Quick start</div>
          <pre
            className="mono"
            style={{
              fontSize: 11,
              color: "var(--text-2)",
              lineHeight: 1.7,
              overflowX: "auto",
              padding: "16px",
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
            }}
          >
{`# Start all services (no Redis or Postgres required)
python scripts/dev_all.py

# In a second terminal, start the web UI
cd packages/web && npm run dev

# Submit a query
curl -X POST http://localhost:8000/api/queries/ \\
  -H "Content-Type: application/json" \\
  -d '{"problem":"Your question here","capabilities":["general"]}'`}
          </pre>
        </div>
      </section>
    </div>
  );
}
