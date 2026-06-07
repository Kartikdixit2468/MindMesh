import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { defineChain } from "viem";

export const monadTestnet = defineChain({
  id: 10143,
  name: "Monad Testnet",
  nativeCurrency: { name: "Monad", symbol: "MON", decimals: 18 },
  rpcUrls: {
    default: { http: ["https://testnet-rpc.monad.xyz"] },
  },
  blockExplorers: {
    default: { name: "Monad Explorer", url: "https://testnet.monadexplorer.com" },
  },
  testnet: true,
});

export const wagmiConfig = getDefaultConfig({
  appName: "MonadBlitz",
  projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || "monadblitz-demo",
  chains: [monadTestnet],
  ssr: true,
});
