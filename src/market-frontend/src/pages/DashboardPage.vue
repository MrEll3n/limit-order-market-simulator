<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import useAuth from '@/composables/useAuth';
import { useWebSocket } from '@vueuse/core';
import Plotly from 'plotly.js-dist';
import { type ChartZoom } from '@/types'
import { SelectButton } from 'primevue';
import { Select } from 'primevue'
import { useMarketStore } from '@/stores';
import { storeToRefs } from 'pinia';

const { t } = useI18n();
const tDashboardPage = (key: string) => t(`dashboardPage.${key}`);

const { clearAuthAndRedirect, getAuthData, refreshAccessToken, logout } = useAuth();

// Market store
const marketStore = useMarketStore();
const { products, selectedProduct } = storeToRefs(marketStore);

// Chart
const chartZoomSelect = ref<ChartZoom>('ALL');

const chartZoomSelectOpts = computed(() => [
    { name: tDashboardPage('chart.zoom.minute'), value: 'MINUTE' },
    { name: tDashboardPage('chart.zoom.hour'), value: 'HOUR' },
    { name: tDashboardPage('chart.zoom.all'), value: 'ALL' },
]);

const chartProductOpts = [
]


// Types
type OrderBookEntry = {
    ID: string;
    User: string;
    Quantity: number;
    Price: number;
};

type OrderBookSnapshot = {
    Bids: OrderBookEntry[];
    Asks: OrderBookEntry[];
    Timestamp: number;
};

type WsEnvelope = {
    message: string;
};

type MarketReportResponse = {
    product: string;
    history: string[]; // each item is a JSON-serialised OrderBookSnapshot
};


// FIX protocol parser
// Messages are FIX 4.4 encoded: fields separated by \x01, format tag=value
const decoder = new TextDecoder();

const parseFIX = (raw: string): Record<string, string> => {
    const fields: Record<string, string> = {};
    for (const field of raw.split('\x01')) {
        const eq = field.indexOf('=');
        if (eq === -1) continue;
        fields[field.slice(0, eq)] = field.slice(eq + 1);
    }
    return fields;
};

// WebSocket
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${wsProtocol}//${window.location.host}/websocket`;

const { data: wsData, open: wsOpen } = useWebSocket(wsUrl, {
    immediate: false,
    autoReconnect: { retries: 10, delay: 2000 },
    onConnected: (ws) => {
        ws.binaryType = 'arraybuffer';
    },
});

// ── Price chart ────────────────────────────────────────────────────
const MAX_POINTS = 1000;
const plotDiv = ref<HTMLDivElement | null>(null);
let plotInitialized = false;
const rawHistory = ref<OrderBookSnapshot[]>([]);

// Mid price & imbalance
const midPrice = ref<number | null>(null);
const imbalanceIndex = ref<number | null>(null);

const calculateImbalance = (bids: OrderBookEntry[], asks: OrderBookEntry[], alpha = 0.5, levels = 3): number | null => {
    if (!bids.length || !asks.length) return null;

    // Agregace množství podle ceny (stejně jako groupby v Pythonu)
    const aggregate = (entries: OrderBookEntry[]) => {
        const map = new Map<number, number>();
        for (const e of entries) map.set(e.Price, (map.get(e.Price) ?? 0) + e.Quantity);
        return [...map.values()];
    };

    const bidQtys = aggregate(bids).slice(0, levels);
    const askQtys = aggregate(asks).slice(0, levels);

    let vBid = 0, vAsk = 0;
    for (let i = 0; i < Math.max(bidQtys.length, askQtys.length); i++) {
        const w = Math.exp(-alpha * i);
        if (i < bidQtys.length) vBid += bidQtys[i] * w;
        if (i < askQtys.length) vAsk += askQtys[i] * w;
    }
    if (vBid + vAsk === 0) return null;
    return (vBid - vAsk) / (vBid + vAsk);
};

const updatePriceMetrics = (snapshot: OrderBookSnapshot) => {
    const bestBid = snapshot.Bids?.[0]?.Price ?? null;
    const bestAsk = snapshot.Asks?.[0]?.Price ?? null;
    midPrice.value = bestBid !== null && bestAsk !== null ? (bestBid + bestAsk) / 2 : null;
    imbalanceIndex.value = calculateImbalance(snapshot.Bids ?? [], snapshot.Asks ?? []);
};

const plotLayout: Partial<Plotly.Layout> = {
    margin: { t: 10, r: 10, b: 40, l: 50 },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: '#9ca3af' },
    xaxis: {
        showgrid: false,
        tickfont: { size: 11 },
        nticks: 6,
    },
    yaxis: {
        gridcolor: 'rgba(128,128,128,0.15)',
        tickfont: { size: 11 },
        zerolinecolor: 'rgba(128,128,128,0.2)',
    },
    legend: { orientation: 'h', y: 1.12, x: 0 },
    hovermode: 'x unified',
};

const plotConfig: Partial<Plotly.Config> = {
    responsive: true,
    displayModeBar: false,
};

const plotFromHistory = (snapshots: OrderBookSnapshot[]) => {
    const now = Date.now();
    const cutoff = chartZoomSelect.value === 'MINUTE' ? now - 60_000
        : chartZoomSelect.value === 'HOUR' ? now - 3_600_000
        : 0;

    const sorted = [...snapshots].sort((a, b) => a.Timestamp - b.Timestamp);
    const filtered = sorted.filter(s => {
        const ts = s.Timestamp > 0 ? s.Timestamp / 1_000_000 : now;
        return ts >= cutoff;
    });

    const timeOpts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit' };
    const labels = filtered.map(s => new Date(s.Timestamp > 0 ? s.Timestamp / 1_000_000 : now).toLocaleTimeString([], timeOpts));
    const bids = filtered.map(s => s.Bids?.[0]?.Price ?? null);
    const asks = filtered.map(s => s.Asks?.[0]?.Price ?? null);
    const mids = filtered.map(s => {
        const b = s.Bids?.[0]?.Price ?? null;
        const a = s.Asks?.[0]?.Price ?? null;
        return b !== null && a !== null ? (b + a) / 2 : null;
    });

    initPlot(labels, bids, asks, mids);
};

watch(chartZoomSelect, () => plotFromHistory(rawHistory.value));
watch(selectedProduct, async (product) => {
    if (!product) return;
    midPrice.value = null;
    imbalanceIndex.value = null;
    rawHistory.value = [];
    plotInitialized = false;
    await fetchChartHistory(product);
    try {
        const res = await fetch(`/api/market/orderbook?product=${product}`);
        if (res.ok) {
            const data = await res.json() as { orderBook: OrderBookSnapshot };
            updatePriceMetrics(data.orderBook);
        }
    } catch { /* ignore */ }
});

const initPlot = (labels: string[], bids: (number | null)[], asks: (number | null)[], mids: (number | null)[] = []) => {
    if (!plotDiv.value) return;
    const traces: Plotly.Data[] = [
        {
            name: 'Best Bid',
            x: labels,
            y: bids,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#22c55e', width: 2, shape: 'spline', smoothing: 0.3 },
            connectgaps: false,
        },
        {
            name: 'Best Ask',
            x: labels,
            y: asks,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#ef4444', width: 2, shape: 'spline', smoothing: 0.3 },
            connectgaps: false,
        },
        {
            name: 'Mid Price',
            x: labels,
            y: mids,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#facc15', width: 1.5, dash: 'dot', shape: 'spline', smoothing: 0.3 },
            connectgaps: false,
        },
    ];
    Plotly.newPlot(plotDiv.value, traces, plotLayout, plotConfig);
    plotInitialized = true;
};

const appendChartPoint = (timestamp: string, bestBid: number | null, bestAsk: number | null, mid: number | null) => {
    if (!plotDiv.value || !plotInitialized) return;
    const rollover = chartZoomSelect.value === 'ALL' ? undefined : MAX_POINTS;
    Plotly.extendTraces(
        plotDiv.value,
        { x: [[timestamp], [timestamp], [timestamp]], y: [[bestBid], [bestAsk], [mid]] },
        [0, 1, 2],
        rollover,
    );
};

// Process incoming WebSocket message
// Server wraps the FIX message in a JSON envelope: { "message": "<raw FIX string>" }
watch(wsData, (raw) => {
    if (!raw) return;
    try {
        const text = raw instanceof ArrayBuffer ? decoder.decode(raw) : String(raw);
        const envelope = JSON.parse(text) as WsEnvelope;
        const fixText: string = envelope?.message ?? text;
        const fields = parseFIX(fixText);

        // tag 35 = MsgType, "W" = MarketDataSnapshot
        if (fields['35'] !== 'W') return;

        // tag 55 = Symbol (product name) — ignore snapshots for other products
        const product = fields['55'];
        if (product && product !== (selectedProduct.value ?? 'product1')) return;

        let orderBook = JSON.parse(fields['58']) as OrderBookSnapshot | string;
        if (typeof orderBook === 'string') orderBook = JSON.parse(orderBook) as OrderBookSnapshot;

        rawHistory.value.push(orderBook);

        const now = Date.now();
        const ts = orderBook.Timestamp > 0 ? orderBook.Timestamp / 1_000_000 : now;
        const cutoff = chartZoomSelect.value === 'MINUTE' ? now - 60_000
            : chartZoomSelect.value === 'HOUR' ? now - 3_600_000
            : 0;
        if (ts < cutoff) return;

        updatePriceMetrics(orderBook);
        const bestBid: number | null = orderBook.Bids?.[0]?.Price ?? null;
        const bestAsk: number | null = orderBook.Asks?.[0]?.Price ?? null;
        const time = new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        appendChartPoint(time, bestBid, bestAsk, midPrice.value);
    } catch {
        // malformed message — ignore
    }
});

// Initial history from REST API
const fetchChartHistory = async (product: string, historyLength: number = -1) => {
    try {
        const res = await fetch(`/api/market/report?product=${product}&history_len=${historyLength}`);
        if (!res.ok) return;
        const { history } = (await res.json()) as MarketReportResponse;

        const labels: string[] = [];
        const bids: (number | null)[] = [];
        const asks: (number | null)[] = [];
        const mids: (number | null)[] = [];

        const timeOpts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit' };

        history.forEach((snapshotStr) => {
            const snapshot = JSON.parse(snapshotStr) as OrderBookSnapshot;
            const ts = snapshot.Timestamp > 0 ? snapshot.Timestamp / 1_000_000 : Date.now();
            const b = snapshot.Bids?.[0]?.Price ?? null;
            const a = snapshot.Asks?.[0]?.Price ?? null;
            labels.push(new Date(ts).toLocaleTimeString([], timeOpts));
            bids.push(b);
            asks.push(a);
            mids.push(b !== null && a !== null ? (b + a) / 2 : null);
        });

        rawHistory.value = history.map(s => JSON.parse(s) as OrderBookSnapshot);
        initPlot(labels, bids, asks, mids);
    } catch {
        // server not ready yet
    }
};

onMounted(async () => {
    const authData = getAuthData();
    if (!authData?.accessToken) {
        clearAuthAndRedirect();
        return;
    }

    try {
        const res = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${authData.accessToken}` },
        });

        if (!res.ok) {
            const refreshed = await refreshAccessToken();
            if (!refreshed) {
                clearAuthAndRedirect();
                return;
            }
        }
    } catch {
        clearAuthAndRedirect();
        return;
    }

    await marketStore.fetchProducts();
    await fetchChartHistory(selectedProduct.value);
    wsOpen();
});
</script>

<template>
    <div class="h-screen flex flex-col overflow-hidden gap-3 pb-3">
        <TopBar />
        <!-- Main View -->
        <div class="flex-1 flex flex-row overflow-hidden gap-3 mx-3">
            <div class="w-3/12 flex flex-col overflow-y-auto">
                <Fieldset :legend="tDashboardPage('panels.activeOrders')" class="h-9/12 grow"> </Fieldset>
                <Fieldset :legend="tDashboardPage('panels.tradingDetails')" class="h-3/12 grow">
                    <div class="flex flex-col gap-1 text-sm">
                        <div class="flex justify-between">
                            <span class="text-gray-400">{{ tDashboardPage('metrics.midPrice') }}</span>
                            <span class="text-yellow-400 font-mono">{{ midPrice !== null ? midPrice.toFixed(2) : '—' }}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-400">{{ tDashboardPage('metrics.imbalance') }}</span>
                            <span
                                class="font-mono"
                                :class="imbalanceIndex === null ? 'text-gray-400' : imbalanceIndex > 0 ? 'text-green-400' : 'text-red-400'"
                            >
                                {{ imbalanceIndex !== null ? imbalanceIndex.toFixed(3) : '—' }}
                            </span>
                        </div>
                    </div>
                </Fieldset>
            </div>

            <div class="w-6/12 flex flex-col overflow-y-auto">
                <Fieldset :legend="tDashboardPage('panels.priceChart')" class="">
                    <div ref="plotDiv" class="h-74 w-full" />
                    <div class="flex flex-row justify-between">
                        <SelectButton v-model="chartZoomSelect" :options="chartZoomSelectOpts" option-label="name" option-value="value" :allow-empty="false" />
                        <Select v-model="selectedProduct" :options="products" :placeholder="tDashboardPage('chart.selectProduct')" class="w-full md:w-56" />
                    </div>
                </Fieldset>
                <Fieldset :legend="tDashboardPage('panels.orderBook')" class="grow"></Fieldset>
                <Fieldset :legend="tDashboardPage('panels.orderHistory')" class="grow"></Fieldset>
            </div>

            <div class="w-3/12 flex flex-col overflow-y-auto">
                <Fieldset :legend="tDashboardPage('panels.tradingPanel')" class="h-9/12 grow"> </Fieldset>
                <Fieldset :legend="tDashboardPage('panels.tradingDetails')" class="h-3/12 grow"></Fieldset>
            </div>
        </div>
    </div>
</template>
