export function createController(elements, api, clipboard, createOption) {
  let generation = 0;
  let busy = false;

  function message(text, error = false) {
    elements.status.textContent = text;
    elements.status.className = error ? 'error' : '';
  }

  function updateButtons() {
    elements.normal.disabled = busy;
    elements.command.disabled = busy || elements.prefix.options.length === 0;
  }

  function resetOutput() {
    elements.output.value = '';
    elements.copy.disabled = true;
  }

  async function generate(withCommand) {
    if (busy) return;
    const requestGeneration = ++generation;
    busy = true;
    resetOutput();
    updateButtons();
    message('Montando queries…');
    try {
      const result = await api.convert(elements.logs.value, withCommand ? elements.prefix.value : '');
      if (requestGeneration !== generation) return;
      elements.output.value = result.sql;
      elements.copy.disabled = !result.sql;
      message(`${result.count} query(s) montada(s).`);
    } catch (error) {
      if (requestGeneration === generation) message(error.message, true);
    } finally {
      if (requestGeneration === generation) {
        busy = false;
        updateButtons();
      }
    }
  }

  function clear() {
    generation += 1;
    busy = false;
    elements.logs.value = '';
    resetOutput();
    updateButtons();
    message('');
    elements.logs.focus();
  }

  async function copy() {
    try {
      await clipboard.writeText(elements.output.value);
      message('SQL copiada.');
    } catch {
      elements.output.focus();
      elements.output.select();
      message('Selecionei a SQL. Pressione Ctrl+C para copiar.');
    }
  }

  async function initialize() {
    elements.normal.onclick = () => generate(false);
    elements.command.onclick = () => generate(true);
    elements.clear.onclick = clear;
    elements.copy.onclick = copy;
    resetOutput();
    updateButtons();
    try {
      const prefixes = await api.prefixes();
      for (const label of prefixes) elements.prefix.append(createOption(label));
      updateButtons();
    } catch {
      message('Não foi possível carregar os comandos. Recarregue a página.', true);
    }
  }

  return { initialize, generate, clear, copy };
}
