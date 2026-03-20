<script setup lang="ts">
import { onMounted } from 'vue';
import router from '@/router';
import type { LoginResponseOK } from '@/types';

const clearAuthAndRedirect = () => {
    localStorage.removeItem('auth-data');
    router.replace({ name: 'login' });
};

onMounted(async () => {
    const authDataRaw = localStorage.getItem('auth-data');
    if (!authDataRaw) {
        router.replace({ name: 'login' });
        return;
    }

    let authData: LoginResponseOK | undefined;
    try {
        authData = JSON.parse(authDataRaw);
    } catch {
        clearAuthAndRedirect();
        return;
    }

    if (!authData?.accessToken) {
        clearAuthAndRedirect();
        return;
    }

    try {
        const res = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${authData.accessToken}` },
        });

        if (!res.ok) {
            clearAuthAndRedirect();
        }
    } catch {
        clearAuthAndRedirect();
    }
});
</script>

<template>

</template>