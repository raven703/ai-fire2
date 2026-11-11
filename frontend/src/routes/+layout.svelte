<script lang="ts">
// Protected build: no upstream socket, telemetry, draft, DB, or service worker bootstraps.
import '../tailwind.css';
import '../app.css';
import { onMount } from 'svelte';
onMount(() => {
    document.documentElement.classList.add('dark');
    document.getElementById('splash-screen')?.remove();
});
</script>
<svelte:head><title>Open WebUI</title><meta name="description" content="Open WebUI — synthetic-only protected build" /></svelte:head>
<slot />
