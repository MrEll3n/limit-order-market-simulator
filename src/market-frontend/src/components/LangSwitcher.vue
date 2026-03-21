<script setup lang="ts">
import { computed } from 'vue';
import { useLocaleStore } from '@/stores';

const { toggleLocale, getFlag } = useLocaleStore();

const flagClass = computed(() => {
    return getFlag();
});
</script>

<template>
    <Button rounded text @click="toggleLocale" aria-label="Toggle language">
        <span :class="flagClass"></span>
    </Button>
</template>
