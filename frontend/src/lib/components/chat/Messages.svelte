<script lang="ts">
    import type { Message } from '$lib/firewall/api';
    import TrustedText from './Messages/TrustedText.svelte';
    export let messages: Message[] = [];
    export let chatId = '';
</script>
<div id="messages-container" class="flex-1 overflow-auto p-6" aria-label="История сообщений">
    <div class="max-w-3xl mx-auto space-y-8">
        {#each messages as message (message.id)}
            <article data-testid="message" data-role={message.role} class="rounded-xl p-4 bg-gray-850">
                <div class="font-semibold mb-2">{message.role === 'user' ? 'Вы' : 'Mock LLM'}</div>
                <TrustedText {chatId} messageId={message.id} masked={message.content} />
            </article>
        {/each}
    </div>
</div>
