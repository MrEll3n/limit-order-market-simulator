<script lang="ts" setup>
import { useRouter } from 'vue-router';
import LoginPage from './LoginPage.vue';
import { onMounted } from 'vue';

const router = useRouter();

onMounted(() => {
    router.replace({ name: 'login' });
});
</script>

<template></template>
