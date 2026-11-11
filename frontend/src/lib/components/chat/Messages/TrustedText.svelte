<script lang="ts">
    import { api } from '$lib/firewall/api';
    export let chatId: string;
    export let messageId: string;
    export let masked: string;
    let revealed: string | null = null;
    let error = '';
    let busy = false;
    // Leaf-only display state: never bound/exported to history or composer.
    async function reveal() {
        busy = true; error = '';
        try { revealed = (await api('view', { chat_id: chatId, message_id: messageId })).text; }
        catch { error = 'Нет доступа или сервис проверки недоступен.'; }
        finally { busy = false; }
    }
</script>
<div class="whitespace-pre-wrap break-words" data-testid="message-text">{revealed ?? masked}</div>
{#if masked.includes('[PII_')}
    <button class="mt-2 text-xs text-gray-400 underline" disabled={busy} on:click={() => revealed === null ? reveal() : (revealed = null)}>
        {revealed === null ? 'Показать оригинал' : 'Скрыть оригинал'}
    </button>
{/if}
{#if error}<p role="alert">{error}</p>{/if}
