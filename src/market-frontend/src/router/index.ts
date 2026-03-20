/**
 * router/index.ts
 *
 * Manual routes for ./src/pages/*.vue
 */

// Composables
import { createRouter, createWebHistory } from 'vue-router';
import Index from '@/pages/index.vue';

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            name: 'index',
            path: '/',
            component: Index,
        },
        {
            name: 'login',
            path: '/login',
            component: () => import('@/pages/LoginPage.vue'),
        },
        {
            name: 'register',
            path: '/register',
            component: () => import('@/pages/RegisterPage.vue'),
        },
        {
            name: 'dashboard',
            path: '/dashboard',
            component: () => import('@/pages/DashboardPage.vue'),
        },
    ],
});

export default router;
