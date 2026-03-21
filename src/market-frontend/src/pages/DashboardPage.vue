<script setup lang="ts">
import { onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import useAuth from '@/composables/useAuth';

const { t } = useI18n();
const tDashboardPage = (key: string) => t(`dashboardPage.${key}`);

const { clearAuthAndRedirect, getAuthData, refreshAccessToken, logout } = useAuth();

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

        if (res.ok) return;

        const refreshed = await refreshAccessToken();
        if (!refreshed) clearAuthAndRedirect();
    } catch {
        clearAuthAndRedirect();
    }
});
</script>

<template>
    <Button :label="tDashboardPage('actions.logout')" @click="logout" />
</template>