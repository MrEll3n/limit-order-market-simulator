<script module lang="ts">
    import { ref, defineProps, defineEmits } from 'vue';

    const props = defineProps<{
        
    }>();

    const emits = defineEmits<{
        (): void
    }>();
</script>

<template>
    <Button :variant="selectedChartZoom === 'MINUTE' ? undefined : 'outlined'">Minute</Button>
    <Button :variant="selectedChartZoom === 'HOUR' ? undefined : 'outlined'">Hour</Button>
    <Button :variant="selectedChartZoom === 'ALL' ? undefined : 'outlined'">All</Button>
</template>