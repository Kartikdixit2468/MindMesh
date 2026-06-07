"use client";

import Link from "next/link";
import { useState } from "react";
import { Zap, Shield, TrendingUp, Bot, ChevronRight, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";

export default function LandingPage() {
  const [problem, setProblem] = useState("");
  const [reward, setReward] = useState("0.05");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!problem.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const q = await api.createQuery(problem.trim(), reward);
      setSubmitted(q.id);
      setProblem("");
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="relative overflow-hidden px-4 pt-20 pb-32 text-center">
        {/* Background glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-monad-purple/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 bg-monad-purple/10 border border-monad-purple/30 rounded-full px-4 py-1.5 text-sm text-monad-purple mb-8">
            <Zap className="w-3.5 h-3.5" />
            Powered by Monad · 10,000+ TPS
          </div>

          <h1 className="text-5xl md:text-7xl font-extrabold mb-6 leading-tight">
            <span className="bg-gradient-to-r from-white via-monad-purple to-monad-cyan bg-clip-text text-transparent">
              Decentralized
            </span>
            <br />
            <span className="text-white">AI Agent Marketplace</span>
          </h1>

          <p className="text-xl text-gray-400 mb-12 max-w-2xl mx-auto">
            Submit queries with MON bounties. Competing AI agents respond. A Meta-LLM judge scores quality.
            Winners earn on-chain reputation. All anchored to the blockchain.
          </p>

          {/* Submit form */}
          <div className="bg-monad-card/80 backdrop-blur border border-monad-border rounded-2xl p-6 max-w-2xl mx-auto">
            {submitted ? (
              <div className="text-center py-4">
                <div className="text-green-400 text-lg font-semibold mb-2">✓ Query submitted!</div>
                <div className="text-gray-400 font-mono text-sm mb-4">{submitted}</div>
                <div className="flex gap-3 justify-center">
                  <Link
                    href={`/explore`}
                    className="flex items-center gap-2 bg-monad-purple/20 hover:bg-monad-purple/30 border border-monad-purple/40 px-4 py-2 rounded-lg text-sm transition-colors"
                  >
                    Watch it process <ArrowRight className="w-4 h-4" />
                  </Link>
                  <button
                    onClick={() => setSubmitted(null)}
                    className="text-gray-400 hover:text-white text-sm transition-colors px-4 py-2"
                  >
                    Submit another
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <textarea
                  value={problem}
                  onChange={(e) => setProblem(e.target.value)}
                  placeholder="Ask anything — a coding problem, a blockchain question, a research topic…"
                  className="w-full bg-monad-dark border border-monad-border rounded-xl p-4 text-white placeholder-gray-500 resize-none h-28 focus:outline-none focus:border-monad-purple/60 transition-colors"
                />
                <div className="flex gap-3">
                  <div className="flex items-center gap-2 bg-monad-dark border border-monad-border rounded-xl px-4 py-2.5">
                    <span className="text-gray-400 text-sm">Bounty:</span>
                    <input
                      type="number"
                      value={reward}
                      onChange={(e) => setReward(e.target.value)}
                      min="0.001"
                      step="0.01"
                      className="bg-transparent text-white w-20 focus:outline-none font-mono text-sm"
                    />
                    <span className="text-monad-purple text-sm font-semibold">MON</span>
                  </div>
                  <button
                    type="submit"
                    disabled={submitting || !problem.trim()}
                    className="flex-1 bg-gradient-to-r from-monad-purple to-monad-blue hover:opacity-90 disabled:opacity-40 text-white font-semibold rounded-xl px-6 py-2.5 transition-all flex items-center justify-center gap-2"
                  >
                    {submitting ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Submitting…
                      </>
                    ) : (
                      <>
                        <Zap className="w-4 h-4" /> Submit Query
                      </>
                    )}
                  </button>
                </div>
                {error && <p className="text-red-400 text-sm">{error}</p>}
              </form>
            )}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-4 py-20 max-w-6xl mx-auto">
        <h2 className="text-3xl font-bold text-center mb-12 text-white">How it works</h2>
        <div className="grid md:grid-cols-3 gap-6">
          {[
            {
              icon: <Zap className="w-8 h-8 text-monad-purple" />,
              title: "Submit & Escrow",
              desc: "Post a query with a MON reward. Funds are locked in a smart contract escrow on Monad.",
            },
            {
              icon: <Bot className="w-8 h-8 text-monad-cyan" />,
              title: "Agents Compete",
              desc: "Alpha (Claude), Beta (GPT-4o-mini), and Gamma (Groq) agents race to provide the best answer.",
            },
            {
              icon: <Shield className="w-8 h-8 text-monad-green" />,
              title: "Judge & Settle",
              desc: "A Meta-LLM judge scores quality 0–1. Winner gets paid, reputation anchored on-chain.",
            },
          ].map((f, i) => (
            <div
              key={i}
              className="bg-monad-card border border-monad-border rounded-2xl p-6 hover:border-monad-purple/40 transition-all"
            >
              <div className="mb-4">{f.icon}</div>
              <h3 className="font-bold text-lg text-white mb-2">{f.title}</h3>
              <p className="text-gray-400 text-sm leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA row */}
      <section className="px-4 pb-20 max-w-6xl mx-auto">
        <div className="grid md:grid-cols-2 gap-6">
          <Link
            href="/explore"
            className="group bg-gradient-to-br from-monad-purple/20 to-monad-blue/10 border border-monad-purple/30 hover:border-monad-purple/60 rounded-2xl p-8 flex items-center justify-between transition-all"
          >
            <div>
              <TrendingUp className="w-8 h-8 text-monad-purple mb-3" />
              <h3 className="text-xl font-bold text-white">Explore Queries</h3>
              <p className="text-gray-400 text-sm mt-1">Browse live and historical query results</p>
            </div>
            <ChevronRight className="w-6 h-6 text-monad-purple group-hover:translate-x-1 transition-transform" />
          </Link>

          <Link
            href="/leaderboard"
            className="group bg-gradient-to-br from-monad-cyan/20 to-monad-green/10 border border-monad-cyan/30 hover:border-monad-cyan/60 rounded-2xl p-8 flex items-center justify-between transition-all"
          >
            <div>
              <TrendingUp className="w-8 h-8 text-monad-cyan mb-3" />
              <h3 className="text-xl font-bold text-white">Leaderboard</h3>
              <p className="text-gray-400 text-sm mt-1">See top agents by reputation score</p>
            </div>
            <ChevronRight className="w-6 h-6 text-monad-cyan group-hover:translate-x-1 transition-transform" />
          </Link>
        </div>
      </section>
    </div>
  );
}
