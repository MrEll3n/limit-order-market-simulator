/// <reference types="vite/client" />
/// <reference types="unplugin-vue-router/client" />
/// <reference types="vite-plugin-vue-layouts-next/client" />

declare module 'plotly.js-dist' {
    export * from 'plotly.js';
    export { default } from 'plotly.js';
}

