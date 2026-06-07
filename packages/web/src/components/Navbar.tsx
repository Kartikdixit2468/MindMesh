"use client";

import Link from "next/link";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { Zap } from "lucide-react";

export function Navbar() {
  return (
    <nav className="fixed top-0 w-full z-50 bg-monad-dark/80 backdrop-blur-md border-b border-monad-border">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-bold text-xl">
          <Zap className="text-monad-purple w-6 h-6" />
          <span className="bg-gradient-to-r from-monad-purple to-monad-cyan bg-clip-text text-transparent">
            MonadBlitz
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-8 text-sm text-gray-400">
          <Link href="/explore" className="hover:text-white transition-colors">
            Explore
          </Link>
          <Link href="/dashboard" className="hover:text-white transition-colors">
            Dashboard
          </Link>
          <Link href="/leaderboard" className="hover:text-white transition-colors">
            Leaderboard
          </Link>
        </div>

        <ConnectButton chainStatus="icon" showBalance={false} />
      </div>
    </nav>
  );
}
