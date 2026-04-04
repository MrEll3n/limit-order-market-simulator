<script setup lang="ts">
// Vue
import { ref, onBeforeUnmount, onMounted, computed } from 'vue';
import { useI18n } from 'vue-i18n';

// PrimeVue
import { yupResolver } from '@primevue/forms/resolvers/yup';
import type { FormSubmitEvent } from '@primevue/forms/form';
import * as yup from 'yup';

import Form from '@primevue/forms/form';
import InputText from 'primevue/inputtext';
import Password from 'primevue/password';
import Button from 'primevue/button';
import Message from 'primevue/message';
import Card from 'primevue/card';
import Toast from 'primevue/toast';

// Custom
import ThemeSwitcher from '@/components/ThemeSwitcher.vue';
import LangSwitcher from '@/components/LangSwitcher.vue';
import useToastHandler from '@/composables/useToastHandler';
import useAuth from '@/composables/useAuth';
import router from '@/router';

const { t } = useI18n();
const tRegisterPage = (key: string) => t(`registerPage.${key}`);
const toast = useToastHandler();
const { getAuthData } = useAuth();

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

onMounted(() => {
    const authData = getAuthData();
    if (authData?.accessToken) router.replace({ name: 'dashboard' });

    fetch('/api/config')
        .then((res) => res.json())
        .then((data) => {
            if (Array.isArray(data.allowedEmailDomains)) {
                allowedDomains.value = data.allowedEmailDomains;
            }
        })
        .catch(() => {});
});

const currentYear = new Date().getFullYear();
const gitUser = 'MrEll3n';
const gitRepo = 'limit-order-market-simulator';

const allowedDomains = ref<string[]>([]);

const resolver = computed(() =>
    yupResolver(yup.object({
        email: yup
            .string()
            .required(tRegisterPage('inputMsgs.email.required'))
            .email(tRegisterPage('inputMsgs.email.notValid'))
            .test('domain', tRegisterPage('inputMsgs.email.domain'), (value) =>
                allowedDomains.value.length === 0 ||
                allowedDomains.value.some((d) => value?.endsWith(`@${d}`))
            ),
        password: yup
            .string()
            .required(tRegisterPage('inputMsgs.password.required'))
            .min(8, tRegisterPage('inputMsgs.password.min')),
        confirmPassword: yup
            .string()
            .required(tRegisterPage('inputMsgs.confirmPassword.required'))
            .oneOf([yup.ref('password')], tRegisterPage('inputMsgs.confirmPassword.match')),
    }))
);

type RegisterFormValues = {
    email: string;
    password: string;
    confirmPassword: string;
};

const registerWarn = () => {
    toast.showWarn({
        label: tRegisterPage('toast.cooldown.label'),
        detail: tRegisterPage('toast.cooldown.detail'),
    });
};

const onFormSubmit = (event: FormSubmitEvent) => {
    if (isCoolingDown.value) {
        registerWarn();
        return;
    }

    if (!event.valid) return;

    const { email, password, confirmPassword } = event.values as RegisterFormValues;

    startCooldown();

    const args: RequestInit = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, confirmPassword }),
    };

    fetch('/api/auth/register', args)
        .then(async (res) => {
            const body: { error?: string } = await res.json().catch(() => ({}));

            if (res.ok) {
                toast.showSuccess({
                    label: tRegisterPage('toast.success.label'),
                    detail: tRegisterPage('toast.success.detail'),
                });
                router.replace({ name: 'login' });
                return;
            }

            switch (res.status) {
                case 400:
                    toast.showError({
                        label: tRegisterPage('toast.invalidInput.label'),
                        detail: body.error ?? tRegisterPage('toast.invalidInput.detail'),
                    });
                    break;
                case 409:
                    toast.showError({
                        label: tRegisterPage('toast.conflict.label'),
                        detail: body.error ?? tRegisterPage('toast.conflict.detail'),
                    });
                    break;
                case 500:
                    toast.showError({
                        label: tRegisterPage('toast.serverError.label'),
                        detail: body.error ?? tRegisterPage('toast.serverError.detail'),
                    });
                    break;
                default:
                    toast.showError({
                        label: tRegisterPage('toast.requestFailed.label'),
                        detail: body.error ?? `Unexpected status: ${res.status}`,
                    });
            }
        })
        .catch(() => {
            toast.showError({
                label: tRegisterPage('toast.networkError.label'),
                detail: tRegisterPage('toast.networkError.detail'),
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
                    {{ tRegisterPage('title') }}
                </template>
                <template #content>
                    <Form v-slot="$form" :resolver="resolver" @submit="onFormSubmit" class="flex flex-col gap-4">
                        <div class="flex flex-col gap-1">
                            <label for="email">{{ tRegisterPage('fields.email.label') }}</label>
                            <InputText
                                id="email"
                                name="email"
                                type="email"
                                :placeholder="tRegisterPage('fields.email.placeholder')"
                                fluid
                            />
                            <Message v-if="$form.email?.invalid" severity="error" size="small" variant="simple">
                                {{ $form.email.error?.message }}
                            </Message>
                        </div>
                        <div class="flex flex-col gap-1">
                            <label for="password">{{ tRegisterPage('fields.password.label') }}</label>
                            <Password
                                id="password"
                                name="password"
                                :placeholder="tRegisterPage('fields.password.placeholder')"
                                :feedback="false"
                                toggleMask
                                fluid
                            />
                            <Message v-if="$form.password?.invalid" severity="error" size="small" variant="simple">
                                {{ $form.password.error?.message }}
                            </Message>
                        </div>
                        <div class="flex flex-col gap-1">
                            <label for="confirmPassword">{{ tRegisterPage('fields.confirmPassword.label') }}</label>
                            <Password
                                id="confirmPassword"
                                name="confirmPassword"
                                :placeholder="tRegisterPage('fields.confirmPassword.placeholder')"
                                :feedback="false"
                                toggleMask
                                fluid
                            />
                            <Message
                                v-if="$form.confirmPassword?.invalid"
                                severity="error"
                                size="small"
                                variant="simple"
                            >
                                {{ $form.confirmPassword.error?.message }}
                            </Message>
                        </div>
                        <div class="flex justify-end">
                            <RouterLink replace to="/login" class="text-sm underline mr-2">
                                {{ tRegisterPage('actions.login') }}
                            </RouterLink>
                        </div>
                        <Button type="submit" :label="tRegisterPage('actions.register')" :disabled="isCoolingDown" />
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
                    :aria-label="tRegisterPage('footer.repositoryAriaLabel')"
                    class="inline-flex items-center justify-center rounded-md p-2 hover:bg-black/5"
                >
                    <i class="pi pi-github text-2xl"></i>
                </a>
            </div>
            <span>© {{ currentYear }} {{ tRegisterPage('footer.copyright') }}</span>
        </footer>
    </div>
    <div class="absolute right-3 top-3 flex flex-row gap-2">
        <LangSwitcher />
        <ThemeSwitcher />
    </div>
</template>
