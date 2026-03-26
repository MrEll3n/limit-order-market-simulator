import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useMarketStore = defineStore('market', () => {
    const products = ref<string[]>([]);
    const selectedProduct = ref<string>('');
    const loading = ref(false);
    const error = ref<string | null>(null);

    async function fetchProducts() {
        loading.value = true;
        error.value = null;
        try {
            const res = await fetch('/api/market/products');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json() as { products: string[] };
            products.value = data.products;
            if (!selectedProduct.value && data.products.length > 0) {
                selectedProduct.value = data.products[0];
            }
        } catch (e) {
            error.value = e instanceof Error ? e.message : 'Failed to fetch products';
        } finally {
            loading.value = false;
        }
    }

    return { products, selectedProduct, loading, error, fetchProducts };
});
