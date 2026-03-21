import router from '@/router';
import type { LoginResponseOK } from '@/types';

const clearAuthAndRedirect = () => {
    localStorage.removeItem('auth-data');
    router.replace({ name: 'login' });
};

const getAuthData = (): LoginResponseOK | null => {
    const raw = localStorage.getItem('auth-data');
    if (!raw) return null;
    try {
        return JSON.parse(raw) as LoginResponseOK;
    } catch {
        return null;
    }
};

const refreshAccessToken = async (): Promise<boolean> => {
    try {
        const res = await fetch('/api/auth/refresh', { method: 'POST' });
        if (!res.ok) return false;

        const data = await res.json();
        const authData = getAuthData();
        if (!authData) return false;

        localStorage.setItem('auth-data', JSON.stringify({ ...authData, accessToken: data.accessToken }));
        return true;
    } catch {
        return false;
    }
};

const logout = async () => {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } finally {
        clearAuthAndRedirect();
    }
};

const useAuth = () => ({
    clearAuthAndRedirect,
    getAuthData,
    refreshAccessToken,
    logout,
});

export default useAuth;
