export function createApi(fetchRequest) {
  async function request(path, options) {
    const response = await fetchRequest(path, options);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Não foi possível concluir a requisição.');
    }
    return data;
  }

  return {
    prefixes: () => request('/prefixes'),
    convert: (log, prefix) => request('/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ log, prefix }),
    }),
  };
}
