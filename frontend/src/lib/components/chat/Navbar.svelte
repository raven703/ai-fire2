<script lang="ts">
    export let user: string;
    export let onLogout: () => Promise<void>;
</script>
<nav class="h-16 shrink-0 px-6 flex items-center justify-between border-b border-gray-800">
    <div><span class="font-semibold">Mock LLM</span><span class="text-xs text-gray-400 ml-3">Защищённый текстовый чат</span></div>
    <button aria-label="Выйти" on:click={onLogout} class="text-sm">{user} · Выйти</button>
</nav>
