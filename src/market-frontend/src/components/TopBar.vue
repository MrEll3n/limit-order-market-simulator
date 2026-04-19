<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import useAuth from '@/composables/useAuth';
import { usePageReady } from '@/composables/usePageReady';
import { useAccountStore, useMarketStore, useOrderBookStore } from '@/stores';
import { storeToRefs } from 'pinia';
import Popover from 'primevue/popover';

const { t } = useI18n();
const tDashboardPage = (key: string) => t(`dashboardPage.${key}`);

const { logout } = useAuth();
const { pageReady } = usePageReady();

const accountStore = useAccountStore();
const { user, balance } = storeToRefs(accountStore);

const marketStore = useMarketStore();
const { selectedProduct } = storeToRefs(marketStore);

const orderBookStore = useOrderBookStore();
const { midPrice } = storeToRefs(orderBookStore);

const portfolioValue = computed(() => {
    if (!balance.value) return null;
    let total = 0;
    for (const [product, pb] of Object.entries(balance.value.products)) {
        const price = product === selectedProduct.value ? (midPrice.value ?? pb.price) : pb.price;
        if (price !== null) total += pb.postSellVolume * price;
    }
    return total;
});

const op = ref<InstanceType<typeof Popover> | null>(null);
const togglePopover = (event: MouseEvent) => {
    op.value?.toggle(event);
};


</script>

<template>
    <MenuBar>
        <template #start>
            <span class="select-none text-2xl font-extrabold">Honicoin Crypto</span>
        </template>
        <template #end>
            <div class="flex flex-row gap-4 justify-center items-center">
                <Transition name="fade" mode="out-in">
                    <Skeleton v-if="!pageReady" width="9rem" class="mb-2"></Skeleton>
                    <div v-else class="flex flex-row gap-6">
                        <div class="flex flex-col items-end leading-tight">
                            <span class="text-xs text-gray-400">{{ tDashboardPage('metrics.balance') }}</span>
                            <span class="text-base font-semibold">{{ balance?.balance.toFixed(2) }}</span>
                        </div>
                        <div class="flex flex-col items-end leading-tight">
                            <span class="text-xs text-gray-400">{{ tDashboardPage('metrics.portfolio') }}</span>
                            <span class="text-base font-semibold">{{ portfolioValue?.toFixed(2) }}</span>
                        </div>
                    </div>
                </Transition>
                <Avatar icon="pi pi-user" size="large" style="cursor: pointer" @click="togglePopover" />
                <Popover ref="op">
                    <div class="flex flex-col w-56">
                        <!-- User info -->
                        <div class="flex items-center gap-3 p-3">
                            <Avatar icon="pi pi-user" size="large" shape="circle" />
                            <div class="flex flex-col overflow-hidden">
                                <Transition name="fade" mode="out-in">
                                <Skeleton v-if="!pageReady" width="8rem" class="mb-2"></Skeleton>
                                <span v-else class="text-sm font-semibold truncate">{{ user?.email }}</span>
                            </Transition>
                            </div>
                        </div>

                        <Divider class="my-0" />

                        <!-- Theme & Language -->
                        <div class="flex flex-col px-1 py-1">
                            <div
                                class="flex items-center justify-between px-2 py-1 rounded-md hover:bg-surface-100 dark:hover:bg-surface-700"
                            >
                                <div class="flex items-center gap-2 text-sm">
                                    <i class="pi pi-palette text-surface-400" />
                                    <span>{{ tDashboardPage('userMenu.theme') }}</span>
                                </div>
                                <ThemeSwitcher />
                            </div>
                            <div
                                class="flex items-center justify-between px-2 py-1 rounded-md hover:bg-surface-100 dark:hover:bg-surface-700"
                            >
                                <div class="flex items-center gap-2 text-sm">
                                    <i class="pi pi-globe text-surface-400" />
                                    <span>{{ tDashboardPage('userMenu.language') }}</span>
                                </div>
                                <LangSwitcher />
                            </div>
                        </div>

                        <Divider class="my-0" />

                        <!-- Logout -->
                        <div class="px-1 py-1">
                            <Button
                                :label="tDashboardPage('actions.logout')"
                                icon="pi pi-sign-out"
                                severity="danger"
                                text
                                fluid
                                @click="logout"
                                :disabled="!pageReady"
                            />
                        </div>
                    </div>
                </Popover>
            </div>
        </template>
    </MenuBar>
</template>
