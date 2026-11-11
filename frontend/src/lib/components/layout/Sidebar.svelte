<script lang="ts">
    import ChatPlus from '$lib/components/icons/ChatPlus.svelte';
    import type { ChatSummary } from '$lib/firewall/api';
    export let chats: ChatSummary[] = [];
    export let busy = false;
    export let onNew: () => void;
    export let onSelect: (id: string) => Promise<void>;
</script>
<aside class="w-64 shrink-0 bg-gray-950 p-4 border-r border-gray-800 overflow-auto">
    <div class="flex items-center gap-2 mb-6"><img src="/static/favicon.png" alt="" class="w-7 h-7" /><span class="font-semibold">Open WebUI</span></div>
    <button disabled={busy} on:click={onNew} class="flex items-center gap-2 rounded-lg bg-gray-800 p-3 w-full"><ChatPlus />Новый чат</button>
    <h2 class="text-xs text-gray-400 mt-6 mb-2">История</h2>
    {#each chats as chat}
        <button data-testid="history-chat" disabled={busy} on:click={() => onSelect(chat.id)} class="block p-3 rounded-lg w-full text-left hover:bg-gray-800">{chat.title}</button>
    {/each}
</aside>
