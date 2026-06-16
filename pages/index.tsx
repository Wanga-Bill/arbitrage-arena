import { ConnectButton } from '@rainbowme/rainbowkit';
import { useAccount, useWriteContract, useReadContract } from 'wagmi';
import { parseUnits } from 'viem';

const CONTRACT_ADDRESS = "0xYourDeployedContractAddressHere";
const CONTRACT_ABI = [
  {
    "anonymous": false,
    "inputs": [
      {
        "indexed": true,
        "internalType": "address",
        "name": "user",
        "type": "address"
      },
      {
        "indexed": false,
        "internalType": "uint256",
        "name": "expirationTime",
        "type": "uint256"
      },
      {
        "indexed": false,
        "internalType": "uint256",
        "name": "amountPaid",
        "type": "uint256"
      }
    ],
    "name": "SubscriptionPurchased",
    "type": "event"
  },
  {
    "inputs": [
      {
        "internalType": "address",
        "name": "_user",
        "type": "address"
      }
    ],
    "name": "isMemberValid",
    "outputs": [
      {
        "internalType": "bool",
        "name": "",
        "type": "bool"
      }
    ],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [
      {
        "internalType": "bool",
        "name": "isMonthly",
        "type": "bool"
      }
    ],
    "name": "purchasePass",
    "outputs": [],
    "stateMutability": "external",
    "type": "function"
  }
] as const;

export default function Home() {
  const { address, isConnected } = useAccount();
  const { writeContract, isPending } = useWriteContract();

  // On-chain check to display active membership status in the UI
  const { data: isValidMember } = useReadContract({
    address: CONTRACT_ADDRESS,
    abi: CONTRACT_ABI,
    functionName: 'isMemberValid',
    args: [address || '0x0000000000000000000000000000000000000000'],
  });

  const handleSubscribe = async (isMonthly: boolean) => {
    writeContract({
      address: CONTRACT_ADDRESS,
      abi: CONTRACT_ABI,
      functionName: 'purchasePass',
      args: [isMonthly],
    });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col items-center justify-center p-6">
      <header className="absolute top-6 right-6">
        <ConnectButton />
      </header>

      <main className="max-w-md w-full text-center space-y-8 bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-xl">
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
          ARBITRAGE ARENA VIP
        </h1>
        <p className="text-slate-400 text-sm">
          Connect your Web3 wallet to unlock our live algorithmic sports mismatch anomaly stream directly.
        </p>

        {isConnected && (
          <div className={`p-3 rounded-lg text-xs font-semibold ${isValidMember ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
            Status: {isValidMember ? "⚡ Active VIP Alpha Access" : "🔒 Access Restricted"}
          </div>
        )}

        <div className="space-y-4">
          <button 
            disabled={!isConnected || isPending}
            onClick={() => handleSubscribe(false)}
            className="w-full bg-slate-800 hover:bg-slate-700 disabled:opacity-50 font-bold p-4 rounded-xl transition border border-slate-700 flex justify-between"
          >
            <span>7-Day Tournament Pass</span>
            <span className="text-cyan-400">$10 USDC</span>
          </button>

          <button 
            disabled={!isConnected || isPending}
            onClick={() => handleSubscribe(true)}
            className="w-full bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-600 hover:to-cyan-600 disabled:opacity-50 text-slate-950 font-extrabold p-4 rounded-xl transition flex justify-between shadow-lg"
          >
            <span>30-Day Whale Access</span>
            <span>$30 USDC</span>
          </button>
        </div>
      </main>
    </div>
  );
}
