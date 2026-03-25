<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import useAuth from '@/composables/useAuth';

import Popover from 'primevue/popover';

const { t } = useI18n();
const tDashboardPage = (key: string) => t(`dashboardPage.${key}`);

const { clearAuthAndRedirect, getAuthData, refreshAccessToken, logout } = useAuth();
const { email } = getAuthData()!;

const op = ref<InstanceType<typeof Popover> | null>(null);
const togglePopover = (event: MouseEvent) => {
    op.value?.toggle(event);
};
</script>

<template>
    <MenuBar>
        <template #start>
            <span class="select-none text-2xl">Honicoin Crypto</span>
        </template>
        <template #end>
            <div class="flex flex-row gap-4 justify-center items-center">
                <span class="text-xl">Balance: 10,000</span>
                <Avatar icon="pi pi-user" size="large" style="cursor: pointer" @click="togglePopover" />
                <Popover ref="op">
                    <div class="flex flex-col w-56">
                        <!-- User info -->
                        <div class="flex items-center gap-3 p-3">
                            <Avatar icon="pi pi-user" size="large" shape="circle" />
                            <div class="flex flex-col overflow-hidden">
                                <span class="text-sm font-semibold truncate">{{ email }}</span>
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
                            />
                        </div>
                    </div>
                </Popover>
            </div>
        </template>
    </MenuBar>
</template>
