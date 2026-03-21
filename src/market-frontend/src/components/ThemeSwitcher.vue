<script setup lang="ts">
import { computed } from 'vue';
import useTheme from '@/composables/useTheme';

const theme = useTheme();

const themeIcon = computed(() => (theme.isDark.value ? 'pi pi-sun' : 'pi pi-moon'));
</script>

<template>
    <Button rounded text :icon="themeIcon" aria-label="themeLabel" @click="theme.toggleTheme" />
</template>
