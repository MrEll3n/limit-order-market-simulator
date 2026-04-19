import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { User, Balance, Order, OrderHistoryEntry } from '@/types';

export const useAccountStore = defineStore('account', () => {
    const user = ref<User | null>(null);
    const balance = ref<Balance | null>(null);
    const orders = ref<Record<string, Order>>({});
    const orderHistory = ref<OrderHistoryEntry[]>([]);
    const loadingUser = ref(true);
    const loadingBalance = ref(true);
    const loadingOrders = ref(true);
    const error = ref<string | null>(null);

    async function fetchUser(accessToken: string): Promise<boolean> {
        loadingUser.value = true;
        error.value = null;
        try {
            const res = await fetch('/api/auth/me', {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            user.value = await res.json() as User;
            return true;
        } catch (e) {
            error.value = e instanceof Error ? e.message : 'Failed to fetch user';
            return false;
        } finally {
            loadingUser.value = false;
        }
    }

    async function fetchBalance(accessToken: string, { silent = false } = {}) {
        if (!silent) loadingBalance.value = true;
        error.value = null;
        try {
            const res = await fetch('/api/account/balance', {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            balance.value = await res.json() as Balance;
        } catch (e) {
            error.value = e instanceof Error ? e.message : 'Failed to fetch balance';
        } finally {
            if (!silent) loadingBalance.value = false;
        }
    }

    async function fetchOrders(accessToken: string, product: string, { silent = false } = {}) {
        if (!silent) loadingOrders.value = true;
        error.value = null;
        try {
            const res = await fetch(`/api/account/orders?product=${product}`, {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json() as { orders: Record<string, Order> };
            orders.value = data.orders;
        } catch (e) {
            error.value = e instanceof Error ? e.message : 'Failed to fetch orders';
        } finally {
            if (!silent) loadingOrders.value = false;
        }
    }

    async function fetchOrderHistory(accessToken: string, product: string) {
        try {
            const res = await fetch(`/api/account/history?product=${product}`, {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json() as { history: OrderHistoryEntry[] };
            orderHistory.value = data.history;
        } catch {
            // ignore — history is best-effort
        }
    }

    function clear() {
        user.value = null;
        balance.value = null;
        orders.value = {};
        orderHistory.value = [];
        error.value = null;
    }

    return { user, balance, orders, orderHistory, loadingUser, loadingBalance, loadingOrders, error, fetchUser, fetchBalance, fetchOrders, fetchOrderHistory, clear };
});
