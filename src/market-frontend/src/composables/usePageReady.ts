import { computed, type Ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useAccountStore, useMarketStore, useOrderBookStore } from '@/stores';

export function usePageReady(loadingChart?: Ref<boolean>) {
    const { loading: loadingProducts } = storeToRefs(useMarketStore());
    const { loadingUser, loadingBalance, loadingOrders } = storeToRefs(useAccountStore());
    const { loading: loadingOrderBook } = storeToRefs(useOrderBookStore());

    const pageReady = computed(() =>
        !loadingProducts.value &&
        !loadingUser.value &&
        !loadingBalance.value &&
        !loadingOrders.value &&
        !loadingOrderBook.value &&
        !(loadingChart?.value ?? false)
    );

    return { pageReady };
}
