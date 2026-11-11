<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { api, type Message, type ChatSummary } from '$lib/firewall/api';
    import Sidebar from '$lib/components/layout/Sidebar.svelte';
    import Navbar from './Navbar.svelte';
    import Messages from './Messages.svelte';
    import MessageInput from './MessageInput.svelte';
    import Spinner from '$lib/components/common/Spinner.svelte';
    let user = '';
    let credential = '';
    let messages: Message[] = [];
    let chats: ChatSummary[] = [];
    let chatId = '';
    let busy = false;
    let ready = false;
    let error = '';
    async function refreshList() { chats = (await api('chats', {})).chats; }
    async function load(id: string) {
        messages = []; error = ''; chatId = '';
        try { const data = await api('history', { chat_id: id }); messages = data.messages; chatId = id; }
        catch { error = 'Чат недоступен или принадлежит другому пользователю.'; }
    }
    async function select(id: string) { await load(id); if (chatId) await goto(`/c/${id}`); }
    async function initialize() {
        try { await refreshList(); }
        catch { error = 'Privacy Gateway недоступен. Сообщения не сохранены.'; }
        const id = $page.params.id;
        if (id) await load(id);
    }
    onMount(async () => {
        try { user = (await api('session')).user; await initialize(); } catch { user = ''; }
        finally { ready = true; }
    });
    async function login() {
        error = ''; busy = true;
        const key = credential; credential = '';
        try { user = (await api('login', { key })).user; await initialize(); }
        catch { error = 'Авторизация не выполнена.'; user = ''; }
        finally { busy = false; }
    }
    async function logout() {
        await api('logout', {}); user = ''; messages = []; chats = []; chatId = ''; error = '';
        await goto('/');
    }
    async function newChat() { messages = []; chatId = ''; error = ''; await goto('/'); }
    async function submit(value: string) {
        busy = true; error = '';
        try {
            const data = await api('chat', { text: value, ...(chatId ? { chat_id: chatId } : {}) });
            await load(data.chat_id); await refreshList(); await goto(`/c/${data.chat_id}`);
        } catch (failure) { error = failure instanceof Error ? failure.message : 'Сообщение не сохранено.'; }
        finally { busy = false; }
    }
</script>
{#if !ready}<Spinner />
{:else if !user}
    <main class="h-dvh flex items-center justify-center bg-gray-900 text-white">
        <form class="w-96 space-y-5 p-8" on:submit|preventDefault={login} autocomplete="off">
            <img src="/static/favicon.png" alt="Open WebUI" class="w-12 h-12" /><h1 class="text-2xl font-bold">Open WebUI</h1>
            <p>AI Firewall — только синтетические данные</p>
            <label class="block">Ключ доступа<input aria-label="Ключ доступа" type="password" bind:value={credential} autocomplete="off" class="block mt-2 w-full rounded-lg p-3 bg-gray-800" /></label>
            <button disabled={busy} class="bg-white text-black rounded-lg p-3 w-full">Войти</button>
            {#if error}<p role="alert">{error}</p>{/if}
        </form>
    </main>
{:else}
    <div class="flex h-dvh w-full bg-gray-900 text-gray-100" data-testid="open-webui-chat">
        <Sidebar {chats} {busy} onNew={newChat} onSelect={select} />
        <main id="main-content" class="flex min-w-0 flex-1 flex-col">
            <Navbar {user} onLogout={logout} />
            {#if !messages.length}<h1 class="text-center text-2xl mt-12">Чем я могу помочь?</h1>{/if}
            {#key chatId}<Messages {messages} {chatId} />{/key}
            {#if error}<p role="alert" class="p-3 text-red-300 text-center">{error}</p>{/if}
            {#if busy}<div role="status"><Spinner /><p class="text-center">Обязательная проверка…</p></div>{/if}
            <MessageInput {busy} onSubmit={submit} />
        </main>
    </div>
{/if}
