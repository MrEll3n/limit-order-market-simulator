<script setup lang="ts">
// Vue
import { ref, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';

// Custom theme switcher
import ThemeSwitcher from '@/components/ThemeSwitcher.vue';
import LangSwitcher from '@/components/LangSwitcher.vue';

// Forms
import { yupResolver } from '@primevue/forms/resolvers/yup';
import type { FormSubmitEvent } from '@primevue/forms/form';
import * as yup from 'yup';

// PrimeVue components
import Form from '@primevue/forms/form';
import InputText from 'primevue/inputtext';
import Password from 'primevue/password';
import Button from 'primevue/button';
import Message from 'primevue/message';
import Card from 'primevue/card';
import Toast from 'primevue/toast';

// i18n
const { t } = useI18n();
const tLoginPage = (key: string) => t(`loginPage.${key}`);

// Custom toast handler
import useToastHandler from '@/composables/useToastHandler';
const toast = useToastHandler();

// Cooldown state
const COOLDOWN_MS = 3000;
const isCoolingDown = ref(false);
let cooldownTimer: ReturnType<typeof setTimeout> | null = null;

const startCooldown = () => {
    isCoolingDown.value = true;

    if (cooldownTimer) {
        clearTimeout(cooldownTimer);
    }

    cooldownTimer = setTimeout(() => {
        isCoolingDown.value = false;
        cooldownTimer = null;
    }, COOLDOWN_MS);
};

onBeforeUnmount(() => {
    if (cooldownTimer) clearTimeout(cooldownTimer);
});

// Footer data
const currentYear = new Date().getFullYear();
const gitUser = 'MrEll3n';
const gitRepo = 'limit-order-market-simulator';

const schema = yup.object({
    email: yup.string().required(tLoginPage('inputMsgs.email.required')).email(tLoginPage('inputMsgs.email.notValid')),
    password: yup
        .string()
        .required(tLoginPage('inputMsgs.password.required'))
        .min(8, tLoginPage('inputMsgs.password.min')),
});

const resolver = yupResolver(schema);

type LoginFormValues = {
    email: string;
    password: string;
};

const loginWarn = () => {
    toast.showWarn({
        label: tLoginPage('toast.cooldown.label'),
        detail: tLoginPage('toast.cooldown.detail'),
    });
};

const onFormSubmit = (event: FormSubmitEvent) => {
    if (isCoolingDown.value) {
        loginWarn();
        return;
    }

    if (!event.valid) return;

    const { email, password } = event.values as LoginFormValues;

    startCooldown();

    const args: RequestInit = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    };

    fetch('/api/auth/login', args)
        .then(async (res) => {
            const body: { error?: string } = await res.json().catch(() => ({}));

            if (res.ok) {
                toast.showSuccess({
                    label: tLoginPage('toast.success.label'),
                    detail: tLoginPage('toast.success.detail'),
                });
                return;
            }

            switch (res.status) {
                case 400:
                    toast.showError({
                        label: tLoginPage('toast.invalidInput.label'),
                        detail: body.error ?? tLoginPage('toast.invalidInput.detail'),
                    });
                    break;
                case 401:
                    toast.showError({
                        label: tLoginPage('toast.authenticationFailed.label'),
                        detail: body.error ?? tLoginPage('toast.authenticationFailed.detail'),
                    });
                    break;
                case 403:
                    toast.showError({
                        label: tLoginPage('toast.forbidden.label'),
                        detail: body.error ?? tLoginPage('toast.forbidden.detail'),
                    });
                    break;
                case 500:
                    toast.showError({
                        label: tLoginPage('toast.serverError.label'),
                        detail: body.error ?? tLoginPage('toast.serverError.detail'),
                    });
                    break;
                default:
                    toast.showError({
                        label: tLoginPage('toast.requestFailed.label'),
                        detail: body.error ?? `Unexpected status: ${res.status}`,
                    });
            }
        })
        .catch(() => {
            toast.showError({
                label: tLoginPage('toast.networkError.label'),
                detail: tLoginPage('toast.networkError.detail'),
            });
        });
};
</script>

<template>
    <Toast />
    <div class="min-h-screen flex flex-col">
        <main class="flex-1 flex items-center justify-center p-4">
            <Card class="w-full max-w-sm">
                <template #title>
                    {{ tLoginPage('title') }}
                </template>
                <template #content>
                    <Form v-slot="$form" :resolver="resolver" @submit="onFormSubmit" class="flex flex-col gap-4">
                        <div class="flex flex-col gap-1">
                            <label for="email">{{ tLoginPage('fields.email.label') }}</label>
                            <InputText
                                id="email"
                                name="email"
                                type="email"
                                :placeholder="tLoginPage('fields.email.placeholder')"
                                fluid
                            />
                            <Message v-if="$form.email?.invalid" severity="error" size="small" variant="simple">
                                {{ $form.email.error?.message }}
                            </Message>
                        </div>
                        <div class="flex flex-col gap-1">
                            <label for="password">{{ tLoginPage('fields.password.label') }}</label>
                            <Password
                                id="password"
                                name="password"
                                :placeholder="tLoginPage('fields.password.placeholder')"
                                :feedback="false"
                                toggleMask
                                fluid
                            />
                            <Message v-if="$form.password?.invalid" severity="error" size="small" variant="simple">
                                {{ $form.password.error?.message }}
                            </Message>
                        </div>
                        <div class="flex justify-end">
                            <RouterLink replace to="/register" class="text-sm underline mr-2">
                                {{ tLoginPage('actions.register') }}
                            </RouterLink>
                        </div>
                        <Button type="submit" :label="tLoginPage('actions.login')" :disabled="isCoolingDown" />
                    </Form>
                </template>
            </Card>
        </main>

        <footer class="flex w-full justify-center items-center pb-4">
            <div>
                <a
                    :href="`https://github.com/${gitUser}/${gitRepo}`"
                    target="_blank"
                    rel="noopener noreferrer"
                    :aria-label="tLoginPage('footer.repositoryAriaLabel')"
                    class="inline-flex items-center justify-center rounded-md p-2 hover:bg-black/5"
                >
                    <i class="pi pi-github text-2xl"></i>
                </a>
            </div>
            <span>© {{ currentYear }} {{ tLoginPage('footer.copyright') }}</span>
        </footer>
    </div>
    <!-- Theme Selector -->
    <div class="absolute right-3 top-3 flex gap-2">
        <LangSwitcher />
        <ThemeSwitcher />
    </div>
</template>
