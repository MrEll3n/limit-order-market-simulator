<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import useAuth from '@/composables/useAuth';
import { useWebSocket } from '@vueuse/core';

const { t } = useI18n();
const tDashboardPage = (key: string) => t(`dashboardPage.${key}`);

const { clearAuthAndRedirect, getAuthData, refreshAccessToken, logout } = useAuth();

// ── Types ──────────────────────────────────────────────────────────
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

// ── FIX protocol parser ────────────────────────────────────────────
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

// ── WebSocket ──────────────────────────────────────────────────────
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
const MAX_POINTS = 100;

const chartData = ref({
    labels: [] as string[],
    datasets: [
        {
            label: 'Best Bid',
            data: [] as (number | null)[],
            borderColor: '#22c55e',
            backgroundColor: 'rgba(34,197,94,0.08)',
            fill: false,
            tension: 0.2,
            pointRadius: 0,
            borderWidth: 2,
        },
        {
            label: 'Best Ask',
            data: [] as (number | null)[],
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239,68,68,0.08)',
            fill: false,
            tension: 0.2,
            pointRadius: 0,
            borderWidth: 2,
        },
    ],
});

const chartOptions = ref({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
        legend: {
            position: 'top' as const,
            labels: { usePointStyle: true, pointStyleWidth: 10, boxHeight: 6 },
        },
        tooltip: {
            mode: 'index' as const,
            intersect: false,
            callbacks: {
                title: (items: { label: string }[]) => items[0]?.label ?? '',
            },
        },
    },
    scales: {
        x: {
            ticks: {
                maxTicksLimit: 6,
                maxRotation: 0,
            },
        },
        y: { grid: { color: 'rgba(128,128,128,0.1)' } },
    },
    interaction: { mode: 'nearest' as const, axis: 'x' as const, intersect: false },
});

// Appends one point to the chart, keeping at most MAX_POINTS points
const appendChartPoint = (timestamp: string, bestBid: number | null, bestAsk: number | null) => {
    const labels = [...chartData.value.labels, timestamp].slice(-MAX_POINTS);
    const bids = [...chartData.value.datasets[0].data, bestBid].slice(-MAX_POINTS);
    const asks = [...chartData.value.datasets[1].data, bestAsk].slice(-MAX_POINTS);
    chartData.value = {
        labels,
        datasets: [
            { ...chartData.value.datasets[0], data: bids },
            { ...chartData.value.datasets[1], data: asks },
        ],
    };
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
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        appendChartPoint(time, bestBid, bestAsk);
    } catch {
        // malformed message — ignore
    }
});

// Initial history from REST API
const fetchChartHistory = async () => {
    try {
        const res = await fetch('/api/market/report?product=product1&history_len=60');
        if (!res.ok) return;
        const { history } = (await res.json()) as MarketReportResponse;

        const labels: string[] = [];
        const bids: (number | null)[] = [];
        const asks: (number | null)[] = [];

        const now = Date.now();
        const timeOpts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit' };

        history.forEach((snapshotStr, i) => {
            const snapshot = JSON.parse(snapshotStr) as OrderBookSnapshot;
            const msAgo = (history.length - 1 - i) * 2000;
            labels.push(new Date(now - msAgo).toLocaleTimeString([], timeOpts));
            bids.push(snapshot.Bids?.[0]?.Price ?? null);
            asks.push(snapshot.Asks?.[0]?.Price ?? null);
        });

        chartData.value = {
            labels,
            datasets: [
                { ...chartData.value.datasets[0], data: bids },
                { ...chartData.value.datasets[1], data: asks },
            ],
        };
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

    await fetchChartHistory();
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
                    <Chart type="line" :data="chartData" :options="chartOptions" class="h-74 w-full" />
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
