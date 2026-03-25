<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import useAuth from '@/composables/useAuth';
import { useWebSocket } from '@vueuse/core';
import Plotly from 'plotly.js-dist';
import { type ChartZoom } from '@/types'
import { SelectButton } from 'primevue';

const { t } = useI18n();
const tDashboardPage = (key: string) => t(`dashboardPage.${key}`);

const { clearAuthAndRedirect, getAuthData, refreshAccessToken, logout } = useAuth();

// Chart
const selectedProduct = ref<string>();
const chartZoomSelect = ref<ChartZoom>('MINUTE');

const chartZoomSelectOpts = ref([
    { name: 'Minute', value: 'MINUTE' },
    { name: 'Hour', value: 'HOUR' },
    { name: 'All', value: 'ALL' }
]);

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
let lastBid: number | null = null;
let lastAsk: number | null = null;
const rawHistory = ref<OrderBookSnapshot[]>([]);

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

    const filtered = snapshots.filter(s => {
        const ts = s.Timestamp > 0 ? s.Timestamp / 1_000_000 : now;
        return ts >= cutoff;
    });

    const timeOpts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit' };
    const labels = filtered.map(s => new Date(s.Timestamp > 0 ? s.Timestamp / 1_000_000 : now).toLocaleTimeString([], timeOpts));
    const bids = filtered.map(s => s.Bids?.[0]?.Price ?? null);
    const asks = filtered.map(s => s.Asks?.[0]?.Price ?? null);

    initPlot(labels, bids, asks);
};

watch(chartZoomSelect, () => plotFromHistory(rawHistory.value));

const initPlot = (labels: string[], bids: (number | null)[], asks: (number | null)[]) => {
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
    ];
    Plotly.newPlot(plotDiv.value, traces, plotLayout, plotConfig);
    plotInitialized = true;
};

const appendChartPoint = (timestamp: string, bestBid: number | null, bestAsk: number | null) => {
    if (!plotDiv.value || !plotInitialized) return;
    if (bestBid !== null) lastBid = bestBid;
    if (bestAsk !== null) lastAsk = bestAsk;
    if (lastBid === null || lastAsk === null) return;
    Plotly.extendTraces(
        plotDiv.value,
        { x: [[timestamp], [timestamp]], y: [[lastBid], [lastAsk]] },
        [0, 1],
        MAX_POINTS,
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

        let orderBook = JSON.parse(fields['58']) as OrderBookSnapshot | string;
        if (typeof orderBook === 'string') orderBook = JSON.parse(orderBook) as OrderBookSnapshot;

        const bestBid: number | null = orderBook.Bids?.[0]?.Price ?? null;
        const bestAsk: number | null = orderBook.Asks?.[0]?.Price ?? null;
        const time = orderBook.Timestamp > 0
            ? new Date(orderBook.Timestamp / 1_000_000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
            : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        appendChartPoint(time, bestBid, bestAsk);
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

        const timeOpts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit' };

        history.forEach((snapshotStr) => {
            const snapshot = JSON.parse(snapshotStr) as OrderBookSnapshot;
            const ts = snapshot.Timestamp > 0 ? snapshot.Timestamp / 1_000_000 : Date.now();
            labels.push(new Date(ts).toLocaleTimeString([], timeOpts));
            bids.push(snapshot.Bids?.[0]?.Price ?? null);
            asks.push(snapshot.Asks?.[0]?.Price ?? null);
        });

        rawHistory.value = history.map(s => JSON.parse(s) as OrderBookSnapshot);
        initPlot(labels, bids, asks);
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

    await fetchChartHistory(selectedProduct.value ?? 'product1');
    wsOpen();
});
</script>

<template>
    <div class="h-screen flex flex-col overflow-hidden gap-3 pb-3">
        <TopBar />
        <!-- Main View -->
        <div class="flex-1 flex flex-row overflow-hidden gap-3 mx-3">
            <div class="w-3/12 flex flex-col overflow-y-auto">
                <Fieldset legend="Active Orders" class="h-9/12 grow"> </Fieldset>
                <Fieldset legend="Trading Details" class="h-3/12 grow"></Fieldset>
            </div>

            <div class="w-6/12 flex flex-col overflow-y-auto">
                <Fieldset legend="Price Chart" class="">
                    <div ref="plotDiv" class="h-74 w-full" />
                    <div class="flex flex-row justify-left gap-4">
                        <SelectButton v-model="chartZoomSelect" :options="chartZoomSelectOpts" option-label="name" option-value="value" :allow-empty="false" />
                    </div>
                </Fieldset>
                <Fieldset legend="Order Book" class="grow"></Fieldset>
                <Fieldset legend="Order History" class="grow"></Fieldset>
            </div>

            <div class="w-3/12 flex flex-col overflow-y-auto">
                <Fieldset legend="Trading Panel" class="h-9/12 grow"> </Fieldset>
                <Fieldset legend="Trading Details" class="h-3/12 grow"></Fieldset>
            </div>
        </div>
    </div>
</template>
