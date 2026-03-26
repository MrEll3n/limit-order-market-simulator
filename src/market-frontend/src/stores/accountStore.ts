import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { User, Balance, Order } from '@/types';

export const useAccountStore = defineStore('account', () => {
    const user = ref<User | null>(null);
    const balance = ref<Balance | null>(null);
    const orders = ref<Record<string, Order>>({});
    const loading = ref(false);
    const error = ref<string | null>(null);

    async function fetchUser(accessToken: string): Promise<boolean> {
        loading.value = true;
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
            loading.value = false;
        }
    }

    async function fetchBalance(accessToken: string) {
        loading.value = true;
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
            loading.value = false;
        }
    }

    async function fetchOrders(accessToken: string, product: string) {
        loading.value = true;
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
            loading.value = false;
        }
    }

    function clear() {
        user.value = null;
        balance.value = null;
        orders.value = {};
        error.value = null;
    }

    return { user, balance, orders, loading, error, fetchUser, fetchBalance, fetchOrders, clear };
});
