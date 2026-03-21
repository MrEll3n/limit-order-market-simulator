import { useToast } from 'primevue/usetoast';

type ToastHandlerArgs = {
    label: string;
    detail: string;
    time?: number;
};

type ToastSeverity = 'success' | 'info' | 'warn' | 'error' | 'secondary' | 'contrast';

const useToastHandler = () => {
    const toast = useToast();

    const show = (severity: ToastSeverity, { label, detail, time = 3000 }: ToastHandlerArgs) => {
        toast.add({
            severity,
            summary: label,
            detail,
            life: time,
        });
    };

    const showSuccess = (args: ToastHandlerArgs) => show('success', args);
    const showInfo = (args: ToastHandlerArgs) => show('info', args);
    const showWarn = (args: ToastHandlerArgs) => show('warn', args);
    const showError = (args: ToastHandlerArgs) => show('error', args);
    const showSecondary = (args: ToastHandlerArgs) => show('secondary', args);
    const showContrast = (args: ToastHandlerArgs) => show('contrast', args);

    return {
        show,
        showSuccess,
        showInfo,
        showWarn,
        showError,
        showSecondary,
        showContrast,
    };
};

export default useToastHandler;
