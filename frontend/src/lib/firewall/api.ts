export type Message = { id: string; role: 'user' | 'assistant'; content: string };
export type ChatSummary = { id: string; title: string };
export async function api(operation: string, body?: object) {
    const response = await fetch(`/api/firewall/${operation}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        credentials: 'same-origin', cache: 'no-store',
        ...(body === undefined ? {} : { body: JSON.stringify(body) })
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Проверка недоступна. Сообщение не сохранено.');
    }
    return response.json();
}
