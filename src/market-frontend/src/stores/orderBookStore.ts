import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import type { OrderBookEntry, OrderBookSnapshot } from '@/types';

export const useOrderBookStore = defineStore('orderBook', () => {
    const loading = ref(true);
    const error = ref(false);

    const bids = ref<OrderBookEntry[]>([]);
    const asks = ref<OrderBookEntry[]>([]);
    const timestamp = ref<number>(0);

    const bestBid = computed(() => bids.value[0]?.Price ?? null);
    const bestAsk = computed(() => asks.value[0]?.Price ?? null);
    const midPrice = computed(() =>
        bestBid.value !== null && bestAsk.value !== null
            ? (bestBid.value + bestAsk.value) / 2
            : null
    );
    const spread = computed(() =>
        bestBid.value !== null && bestAsk.value !== null
            ? bestAsk.value - bestBid.value
            : null
    );

    const imbalance = computed((): number | null => {
        if (!bids.value.length || !asks.value.length) return null;
        const alpha = 0.5;
        const levels = 3;
        const aggregate = (entries: OrderBookEntry[]) => {
            const map = new Map<number, number>();
            for (const e of entries) map.set(e.Price, (map.get(e.Price) ?? 0) + e.Quantity);
            return [...map.values()];
        };
        const bidQtys = aggregate(bids.value).slice(0, levels);
        const askQtys = aggregate(asks.value).slice(0, levels);
        let vBid = 0, vAsk = 0;
        for (let i = 0; i < Math.max(bidQtys.length, askQtys.length); i++) {
            const w = Math.exp(-alpha * i);
            if (i < bidQtys.length) vBid += bidQtys[i] * w;
            if (i < askQtys.length) vAsk += askQtys[i] * w;
        }
        if (vBid + vAsk === 0) return null;
        return (vBid - vAsk) / (vBid + vAsk);
    });

    function applySnapshot(snapshot: OrderBookSnapshot) {
        bids.value = snapshot.Bids ?? [];
        asks.value = snapshot.Asks ?? [];
        timestamp.value = snapshot.Timestamp;
    }

    async function fetchSnapshot(product: string) {
        loading.value = true;
        try {
            const authData = localStorage.getItem('auth-data');
            const token = authData ? (JSON.parse(authData) as { accessToken?: string }).accessToken : null;
            const res = await fetch(`/api/market/orderbook?product=${product}`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (!res.ok) return;
            const data = await res.json() as { orderBook: OrderBookSnapshot | string };
            const snapshot = typeof data.orderBook === 'string'
                ? JSON.parse(data.orderBook) as OrderBookSnapshot
                : data.orderBook;
            applySnapshot(snapshot);
        } catch {
            error.value = true;
        } finally {
            loading.value = false;
        }
    }

    function clear() {
        bids.value = [];
        asks.value = [];
        timestamp.value = 0;
    }

    return { bids, asks, timestamp, bestBid, bestAsk, midPrice, spread, imbalance, loading, applySnapshot, fetchSnapshot, clear };
});
