import '@/styles/globals.css';
import '@rainbowme/rainbowkit/styles.css';
import type { AppProps } from 'next/app';
import { getDefaultConfig, RainbowKitProvider, darkTheme } from '@rainbowme/rainbowkit';
import { WagmiProvider } from 'wagmi';
import { mainnet, polygon, arbitrum, base } from 'wagmi/chains';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const config = getDefaultConfig({
  appName: 'Arbitrage Arena VIP',
  projectId: 'YOUR_WALLETCONNECT_PROJECT_ID', // Acquire free at cloud.walletconnect.com
  chains: [mainnet, polygon, arbitrum, base],
  ssr: true,
});

const queryClient = new QueryClient();

export default function App({ Component, pageProps }: AppProps) {
  return (
    <WagmiProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider theme={darkTheme()}>
          <Component {...pageProps} />
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
