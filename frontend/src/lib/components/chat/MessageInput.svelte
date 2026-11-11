<script lang="ts">
    import Textarea from '$lib/components/common/Textarea.svelte';
    import ArrowUp from '$lib/components/icons/ArrowUpCircle.svelte';
    export let busy = false;
    export let onSubmit: (value: string) => Promise<void>;
    let draft = '';
    async function submit() {
        if (busy || !draft.trim()) return;
        const value = draft; draft = '';
        await onSubmit(value);
    }
</script>
<form class="mx-auto w-full max-w-3xl px-5 pb-6" on:submit|preventDefault={submit} autocomplete="off">
    <div class="rounded-3xl bg-gray-850 p-3 flex items-end gap-3">
        <Textarea id="chat-input" ariaLabel="Сообщение" bind:value={draft} disabled={busy}
            placeholder="Сообщение Mock LLM (только синтетические данные)" autocomplete="off" spellcheck={false}
            onKeydown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); } }} />
        <button type="submit" aria-label="Отправить" disabled={busy || !draft.trim()} class="rounded-full bg-white text-black p-2 disabled:opacity-40"><ArrowUp /></button>
    </div>
    <p class="text-xs text-gray-400 text-center mt-2">Файлы, RAG, инструменты и streaming отключены. Только синтетические ПДн.</p>
</form>
