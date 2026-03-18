<script setup lang="ts">
import { yupResolver } from '@primevue/forms/resolvers/yup';
import type { FormSubmitEvent } from '@primevue/forms/form';
import * as yup from 'yup';

import Form from '@primevue/forms/form';
import InputText from 'primevue/inputtext';
import Password from 'primevue/password';
import Button from 'primevue/button';
import Message from 'primevue/message';
import Card from 'primevue/card'
import { StepPanelClasses } from 'primevue';


const currentYear = new Date().getFullYear();
const gitUser = 'MrEll3n'
const gitRepo = 'limit-order-market-simulator'

const schema = yup.object({
    email: yup.string().required('Email is required').email('Email is not valid'),
    password: yup.string().required('Password is required').min(8, 'Password must be at least 8 characters'),
});

const resolver = yupResolver(schema);

const onFormSubmit = (event: FormSubmitEvent) => {
    if (!event.valid) return;

    const { email, password } = event.values;

    // TODO: call /api/auth/login

    console.log({ email, password })
}
</script>

<template>
    <div class="min-h-screen flex flex-col">
        <main class="flex-1 flex items-center justify-center p-4">
            <Card class="w-full max-w-sm">
                <template #title>   
                    Login
                </template>
                <template #content>
                    <Form v-slot="$form" :resolver="resolver" @submit="onFormSubmit" class="flex flex-col gap-4">
                        <div class="flex flex-col gap-1">
                            <label for="email">Email</label>
                            <InputText id="email" name="email" type="email" placeholder="Email" fluid />
                            <Message v-if="$form.email?.invalid" severity="error" size="small" variant="simple">
                                {{ $form.email.error?.message }}
                            </Message>
                        </div>
                        <div class="flex flex-col gap-1">
                            <label for="password">Password</label>
                            <Password id="password" name="password" placeholder="Password" :feedback="false" toggleMask fluid />
                            <Message v-if="$form.password?.invalid" severity="error" size="small" variant="simple">
                                {{ $form.password.error?.message }}
                            </Message>
                        </div>
                        <div class="flex justify-end">
                            <RouterLink to="/register" class="text-sm underline mr-2">
                                Register
                            </RouterLink>
                        </div>
                        <Button type="submit" severity="secondary" label="Login" />
                    </Form>
                </template>
            </Card>
        </main>

        <footer class="flex w-full justify-center items-center pb-4">
            <div>
                <a
                    :href="`https://github.com/${ gitUser }/${ gitRepo }`"
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="Open GitHub repository"
                    class="inline-flex items-center justify-center rounded-md p-2 hover:bg-black/5"
                >
                    <i class="pi pi-github text-2xl"></i>
                </a>
            </div>
            <span>© {{ currentYear }} Limit Order Market Simulator</span>
        </footer>
    </div>
    <Button
        class="absolute right-3 top-3"
        rounded
        text
        icon="pi pi-sun"
        aria-label="themeLabel"
    />
</template>
