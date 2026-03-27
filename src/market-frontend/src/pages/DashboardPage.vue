<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import useAuth from '@/composables/useAuth';
import useToastHandler from '@/composables/useToastHandler';
import { useWebSocket } from '@vueuse/core';
import Plotly from 'plotly.js-dist';
import { useLocaleStore, useMarketStore, useAccountStore, useOrderBookStore } from '@/stores';
import type { OrderBookSnapshot } from '@/types';
import { storeToRefs } from 'pinia';
import { usePageReady } from '@/composables/usePageReady';
import { orderHistogramOptions, obMidPricePlugin, getObHistogramOptions, plotLayout, plotConfig } from '@/config/chartConfig';



// Locale
const { t } = useI18n();
const tDashboardPage = (key: string) => t(`dashboardPage.${key}`);

// Auth
const { clearAuthAndRedirect, getAuthData, refreshAccessToken } = useAuth();

// Stores
const marketStore = useMarketStore();
const { products, selectedProduct } = storeToRefs(marketStore);

const accountStore = useAccountStore();
const { orders, balance } = storeToRefs(accountStore);
const { showSuccess, showError } = useToastHandler();

const orderBookStore = useOrderBookStore();
const { midPrice, imbalance: imbalanceIndex, bids: obBids, asks: obAsks } = storeToRefs(orderBookStore);

const userOrders = computed(() =>
    Object.values(orders.value).sort((a, b) => b.timestamp - a.timestamp)
);

const localeStore = useLocaleStore();
const { locale } = storeToRefs(localeStore);
watch(locale, () => plotFromHistory(rawHistory.value));



// Types
type WsEnvelope = {
    message: string;
};

type MarketReportResponse = {
    product: string;
    history: string[];
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

// Orders histogram
const orderHistogramData = computed(() => {
    const aggregate = (entries: typeof obBids.value) => {
        const map = new Map<number, number>();
        for (const e of entries) map.set(e.Price, (map.get(e.Price) ?? 0) + e.Quantity);
        return map;
    };
    const bidMap = aggregate(obBids.value);
    const askMap = aggregate(obAsks.value);
    const prices = [...new Set([...bidMap.keys(), ...askMap.keys()])].sort((a, b) => a - b);
    return {
        labels: prices.map(String),
        datasets: [
            { label: 'Buy', data: prices.map(p => bidMap.get(p) ?? 0), backgroundColor: 'rgba(34,197,94,0.6)' },
            { label: 'Sell', data: prices.map(p => askMap.get(p) ?? 0), backgroundColor: 'rgba(239,68,68,0.6)' },
        ],
    };
});


// Order book chart
const obHistogramData = computed(() => {
    const bidMap = new Map<number, number>();
    for (const e of obBids.value) bidMap.set(e.Price, (bidMap.get(e.Price) ?? 0) + e.Quantity);
    const askMap = new Map<number, number>();
    for (const e of obAsks.value) askMap.set(e.Price, (askMap.get(e.Price) ?? 0) + e.Quantity);
    const prices = [...new Set([...bidMap.keys(), ...askMap.keys()])].sort((a, b) => a - b);
    return {
        labels: prices.map(p => p.toFixed(2)),
        datasets: [
            { label: tDashboardPage('chart.traces.bestBid'), data: prices.map(p => bidMap.get(p) ?? 0), backgroundColor: 'rgba(34,197,94,0.6)' },
            { label: tDashboardPage('chart.traces.bestAsk'), data: prices.map(p => askMap.get(p) ?? 0), backgroundColor: 'rgba(239,68,68,0.6)' },
        ],
    };
});

const obVisibleLabels = computed(() => {
    const bidPrices = [...new Set(obBids.value.map(e => e.Price))].sort((a, b) => b - a).slice(0, 2);
    const askPrices = [...new Set(obAsks.value.map(e => e.Price))].sort((a, b) => a - b).slice(0, 2);
    return [...bidPrices, ...askPrices].map(p => p.toFixed(2));
});

const obHistogramOptions = computed(() => getObHistogramOptions(midPrice.value, obVisibleLabels.value));

// Price chart
const MAX_POINTS = 1000;
const plotDiv = ref<HTMLDivElement | null>(null);
let plotInitialized = false;
const rawHistory = ref<OrderBookSnapshot[]>([]);
const loadingChart = ref(true);
const { pageReady } = usePageReady(loadingChart);

type ChartZoom = 'MINUTE' | 'HOUR' | 'ALL';
const chartZoomSelect = ref<ChartZoom>('HOUR');
const chartZoomSelectOpts = computed(() => [
    { name: tDashboardPage('chart.zoom.minute'), value: 'MINUTE' },
    { name: tDashboardPage('chart.zoom.hour'), value: 'HOUR' },
    { name: tDashboardPage('chart.zoom.all'), value: 'ALL' },
]);


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
    loadingChart.value = true;
    rawHistory.value = [];
    plotInitialized = false;
    orderBookStore.clear();
    const authData = getAuthData();
    await Promise.all([
        authData?.accessToken ? accountStore.fetchOrders(authData.accessToken, product) : Promise.resolve(),
        orderBookStore.fetchSnapshot(product),
    ]);
    await fetchChartHistory(product);
});

const initPlot = (labels: string[], bids: (number | null)[], asks: (number | null)[], mids: (number | null)[] = []) => {
    if (!plotDiv.value) return;
    const traces: Plotly.Data[] = [
        {
            name: tDashboardPage('chart.traces.bestBid'),
            x: labels,
            y: bids,
            type: 'scattergl',
            mode: 'lines',
            line: { color: '#22c55e', width: 2, shape: 'spline', smoothing: 0.3 },
            connectgaps: true,
        },
        {
            name: tDashboardPage('chart.traces.bestAsk'),
            x: labels,
            y: asks,
            type: 'scattergl',
            mode: 'lines',
            line: { color: '#ef4444', width: 2, shape: 'spline', smoothing: 0.3 },
            connectgaps: true,
        },
        {
            name: tDashboardPage('chart.traces.midPrice'),
            x: labels,
            y: mids,
            type: 'scattergl',
            mode: 'lines',
            line: { color: '#facc15', width: 1.5, dash: 'dot', shape: 'spline', smoothing: 0.3 },
            connectgaps: true,
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

        orderBookStore.applySnapshot(orderBook);
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
    loadingChart.value = true;
    try {
        const res = await fetch(`/api/market/report?product=${product}&history_len=${historyLength}`);
        if (!res.ok) return;
        const { history } = (await res.json()) as MarketReportResponse;

        rawHistory.value = history.map(s => JSON.parse(s) as OrderBookSnapshot);
    } catch {
        // server not ready yet
    } finally {
        loadingChart.value = false;
        await nextTick();
        plotFromHistory(rawHistory.value);
    }
};

// Trading Panel
const orderSide = ref<'buy' | 'sell'>('buy');
const orderPrice = ref<number | null>(null);
const orderQuantity = ref<number | null>(null);
const submitting = ref(false);

const orderSideOpts = computed(() => [
    { name: tDashboardPage('tradingPanel.buy'), value: 'buy' },
    { name: tDashboardPage('tradingPanel.sell'), value: 'sell' },
]);

watch(midPrice, (val) => {
    if (val !== null && orderPrice.value === null) orderPrice.value = val;
}, { immediate: true });

const cancellingId = ref<string | null>(null);

const cancelOrder = async (orderId: string) => {
    cancellingId.value = orderId;
    try {
        const authData = getAuthData();
        if (!authData?.accessToken) { clearAuthAndRedirect(); return; }
        const res = await fetch(`/api/orders/${orderId}?product=${selectedProduct.value}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${authData.accessToken}` },
        });
        if (res.ok) {
            await Promise.all([
                accountStore.fetchOrders(authData.accessToken, selectedProduct.value),
                accountStore.fetchBalance(authData.accessToken),
            ]);
        } else {
            const data = await res.json().catch(() => ({}));
            showError({ label: tDashboardPage('tradingPanel.toast.cancelFailed'), detail: data.error ?? res.statusText });
        }
    } catch {
        showError({ label: tDashboardPage('tradingPanel.toast.cancelFailed'), detail: '—' });
    } finally {
        cancellingId.value = null;
    }
};

const placeOrder = async () => {
    if (!orderPrice.value || !orderQuantity.value) return;
    submitting.value = true;
    try {
        const authData = getAuthData();
        if (!authData?.accessToken) { clearAuthAndRedirect(); return; }
        const res = await fetch('/api/orders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authData.accessToken}` },
            body: JSON.stringify({
                product: selectedProduct.value,
                side: orderSide.value,
                quantity: orderQuantity.value,
                price: orderPrice.value,
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            showError({ label: tDashboardPage('tradingPanel.toast.orderFailed'), detail: data.error ?? res.statusText });
        } else {
            showSuccess({ label: tDashboardPage('tradingPanel.toast.orderPlaced'), detail: `#${data.orderId} — ${data.status}` });
            orderQuantity.value = null;
            await Promise.all([
                accountStore.fetchOrders(authData.accessToken, selectedProduct.value),
                accountStore.fetchBalance(authData.accessToken),
            ]);
        }
    } catch {
        showError({ label: tDashboardPage('tradingPanel.toast.orderFailed'), detail: '—' });
    } finally {
        submitting.value = false;
    }
};

onMounted(async () => {
    loadingChart.value = true;
    const authData = getAuthData();
    if (!authData?.accessToken) {
        clearAuthAndRedirect();
        return;
    }

    const ok = await accountStore.fetchUser(authData.accessToken);
    if (!ok) {
        const refreshed = await refreshAccessToken();
        if (!refreshed) {
            clearAuthAndRedirect();
            return;
        }
    }

    await marketStore.fetchProducts();
    await Promise.all([
        accountStore.fetchOrders(authData.accessToken, selectedProduct.value),
        orderBookStore.fetchSnapshot(selectedProduct.value),
        accountStore.fetchBalance(authData.accessToken),
    ]);
    wsOpen();
    await fetchChartHistory(selectedProduct.value);
});

</script>

<template>
    <div class="h-screen flex flex-col overflow-hidden gap-3 pb-3">
        <TopBar class="mx-3 mt-3" />
        <!-- Main View -->
        <div class="flex-1 flex flex-row overflow-hidden gap-3 mx-3">
            <div class="w-3/12 flex flex-col overflow-y-auto">
                <!-- Active Orders -->
                <Fieldset :legend="tDashboardPage('panels.activeOrders')" class="active-orders-fieldset h-9/12 grow">
                    <Skeleton v-if="!pageReady" style="height: 100%;" />
                    <Chart v-else type="bar" :data="orderHistogramData" :options="orderHistogramOptions" class="h-full w-full" />
                </Fieldset>
                <!-- Trading Details -->
                <Fieldset :legend="tDashboardPage('panels.tradingDetails')" class="h-3/12 grow">
                    <div class="flex flex-col gap-1 text-sm">
                        <div class="flex justify-between items-center">
                            <span class="text-gray-400">{{ tDashboardPage('metrics.midPrice') }}</span>
                            <Skeleton v-if="!pageReady" width="5rem" height="2rem" />
                            <Message v-else size="small" severity="warn">{{ midPrice?.toFixed(2) ?? '—' }}</Message>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-gray-400">{{ tDashboardPage('metrics.imbalance') }}</span>
                            <Skeleton v-if="!pageReady" width="5rem" height="2rem" />
                            <Message v-else size="small" :severity="imbalanceIndex !== null && imbalanceIndex > 0 ? 'success' : 'error'">
                                {{ imbalanceIndex?.toFixed(3) ?? '—' }}
                            </Message>
                        </div>
                    </div>
                </Fieldset>
            </div>

            <div class="w-6/12 flex flex-col overflow-y-auto">
                <!-- Price Chart -->
                <Fieldset :legend="tDashboardPage('panels.priceChart')">
                    <Skeleton v-if="!pageReady" width="100%" height="18.5rem" />
                    <div v-show="pageReady" ref="plotDiv" class="h-74 w-full" />
                    <div class="flex flex-row justify-between mt-2">
                        <SelectButton :disabled="!pageReady" v-model="chartZoomSelect" :options="chartZoomSelectOpts" option-label="name" option-value="value" :allow-empty="false" />
                        <Skeleton v-if="!pageReady" width="10rem" height="2rem" />
                        <Select v-else v-model="selectedProduct" :options="products" :placeholder="tDashboardPage('chart.selectProduct')" class="w-full md:w-42" />
                    </div>
                </Fieldset>
                <!-- Order Book -->
                <!-- <Fieldset :legend="tDashboardPage('panels.orderBook')" class="overflow-hidden h-3/12">
                    <Skeleton v-if="!pageReady" height="9rem" width="100%" />
                    <Chart v-else type="bar" :data="obHistogramData" :options="obHistogramOptions" :plugins="[obMidPricePlugin]" class="h-full w-full" />
                </Fieldset> -->
                <!-- Order History -->
                <Fieldset :legend="tDashboardPage('panels.orderHistory')" class="grow overflow-hidden">
                    <Skeleton v-if="!pageReady" style="height: 100%;" />
                    <div v-else class="flex flex-col h-full text-xs overflow-hidden">
                        <div class="flex justify-between text-gray-400 px-2 pb-1 font-medium">
                            <span class="w-1/4">{{ tDashboardPage('orderHistory.side') }}</span>
                            <span class="w-1/4 text-right">{{ tDashboardPage('orderHistory.price') }}</span>
                            <span class="w-1/4 text-right">{{ tDashboardPage('orderHistory.quantity') }}</span>
                            <span class="w-1/4 text-right">{{ tDashboardPage('orderHistory.time') }}</span>
                        </div>
                        <div class="overflow-y-auto flex-1">
                            <div v-if="userOrders.length === 0" class="text-gray-400 text-center py-4">{{ tDashboardPage('orderHistory.empty') }}</div>
                            <div v-for="order in userOrders" :key="order.id" class="flex justify-between px-2 py-0.5 hover:bg-surface-100 dark:hover:bg-surface-700">
                                <span class="w-1/4" :class="order.side === 'buy' ? 'text-green-400' : 'text-red-400'">{{ order.side }}</span>
                                <span class="w-1/4 text-right">{{ order.price.toFixed(2) }}</span>
                                <span class="w-1/4 text-right">{{ order.quantity }}</span>
                                <span class="w-1/4 text-right text-gray-400">{{ new Date(order.timestamp / 1_000_000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}</span>
                            </div>
                        </div>
                    </div>
                </Fieldset>
            </div>

            <div class="w-3/12 flex flex-col overflow-hidden gap-3">
                <!-- Trading Details -->
                <Fieldset :legend="tDashboardPage('panels.tradingDetails')" class="shrink-0">
                    <div class="flex flex-col gap-1 text-sm">
                        <template v-if="!pageReady">
                            <div v-for="i in products.length || 1" :key="i" class="flex justify-between items-center">
                                <Skeleton width="4rem" height="1rem" />
                                <Skeleton width="3rem" height="2rem" />
                            </div>
                        </template>
                        <template v-else>
                            <div
                                v-for="product in products.filter(p => (balance?.products?.[p]?.postSellVolume ?? 0) > 0)"
                                :key="product"
                                class="flex justify-between items-center"
                            >
                                <span class="text-gray-400">{{ product }}</span>
                                <Message size="small" severity="secondary">
                                    {{ balance?.products?.[product]?.postSellVolume }} {{ tDashboardPage('metrics.shares') }}
                                </Message>
                            </div>
                            <div v-if="!products.some(p => (balance?.products?.[p]?.postSellVolume ?? 0) > 0)" class="text-gray-400 text-xs text-center py-1">
                                {{ tDashboardPage('metrics.noShares') }}
                            </div>
                        </template>
                    </div>
                </Fieldset>
                <!-- Trading Panel -->
                <Fieldset :legend="tDashboardPage('panels.tradingPanel')" class="shrink-0">
                    <div class="flex flex-col gap-3">
                        <div class="flex flex-col gap-1">
                            <label class="text-xs text-gray-400">{{ tDashboardPage('tradingPanel.product') }}</label>
                            <Skeleton v-if="!pageReady" height="2.25rem" width="100%" />
                            <Select v-else v-model="selectedProduct" :options="products" :placeholder="tDashboardPage('chart.selectProduct')" fluid />
                        </div>
                        <SelectButton
                            v-model="orderSide"
                            :options="orderSideOpts"
                            option-label="name"
                            option-value="value"
                            :allow-empty="false"
                            :disabled="!pageReady || submitting"
                            class="w-full"
                        />
                        <div class="flex flex-col gap-1">
                            <label class="text-xs text-gray-400">{{ tDashboardPage('tradingPanel.price') }}</label>
                            <InputNumber
                                v-model="orderPrice"
                                :min="0.01"
                                :max-fraction-digits="2"
                                :min-fraction-digits="2"
                                :disabled="!pageReady || submitting"
                                fluid
                            />
                        </div>
                        <div class="flex flex-col gap-1">
                            <label class="text-xs text-gray-400">{{ tDashboardPage('tradingPanel.quantity') }}</label>
                            <InputNumber
                                v-model="orderQuantity"
                                :min="1"
                                :max-fraction-digits="0"
                                :disabled="!pageReady || submitting"
                                fluid
                            />
                        </div>
                        <Button
                            :label="tDashboardPage('tradingPanel.submit')"
                            :severity="orderSide === 'buy' ? 'success' : 'danger'"
                            :loading="submitting"
                            :disabled="!pageReady || !orderPrice || !orderQuantity"
                            @click="placeOrder"
                            fluid
                        />
                    </div>
                </Fieldset>
                <!-- Active Orders -->
                <Fieldset :legend="tDashboardPage('panels.activeOrders')" class="grow overflow-hidden active-orders-right-fieldset">
                    <Skeleton v-if="!pageReady" style="height: 100%;" />
                    <div v-else class="flex flex-col h-full text-xs overflow-hidden">
                        <div class="flex justify-between text-gray-400 px-2 pb-1 font-medium">
                            <span class="w-1/4">{{ tDashboardPage('orderHistory.side') }}</span>
                            <span class="w-1/4 text-right">{{ tDashboardPage('orderHistory.price') }}</span>
                            <span class="w-1/4 text-right">{{ tDashboardPage('orderHistory.quantity') }}</span>
                            <span class="w-1/12"></span>
                        </div>
                        <div class="overflow-y-auto flex-1">
                            <div v-if="userOrders.length === 0" class="text-gray-400 text-center py-4">{{ tDashboardPage('activeOrders.noOrders') }}</div>
                            <div
                                v-for="order in userOrders"
                                :key="order.id"
                                class="flex items-center justify-between px-2 py-0.5 hover:bg-surface-100 dark:hover:bg-surface-700"
                            >
                                <span class="w-1/4" :class="order.side === 'buy' ? 'text-green-400' : 'text-red-400'">{{ order.side }}</span>
                                <span class="w-1/4 text-right">{{ order.price.toFixed(2) }}</span>
                                <span class="w-1/4 text-right">{{ order.quantity }}</span>
                                <Button
                                    icon="pi pi-times"
                                    severity="danger"
                                    text
                                    rounded
                                    size="small"
                                    :loading="cancellingId === order.id"
                                    :disabled="cancellingId !== null"
                                    class="w-1/12 p-0!"
                                    @click="cancelOrder(order.id)"
                                />
                            </div>
                        </div>
                    </div>
                </Fieldset>
            </div>
            <Toast />
        </div>
    </div>
</template>

<style>
.active-orders-fieldset .p-fieldset-content-container,
.active-orders-fieldset .p-fieldset-content-wrapper,
.active-orders-fieldset .p-fieldset-content {
    height: 100%;
}

.active-orders-right-fieldset .p-fieldset-content-container,
.active-orders-right-fieldset .p-fieldset-content-wrapper,
.active-orders-right-fieldset .p-fieldset-content {
    height: 100%;
}

.js-plotly-plot .nottext text {
    font-family: var(--p-font-family) !important;
    font-size: var(--p-form-field-sm-font-size) !important;
    fill: var(--p-text-muted-color) !important;
}
</style>
