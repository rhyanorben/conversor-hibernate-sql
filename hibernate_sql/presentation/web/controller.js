export function createController(elements, api, clipboard, createOption, downloadSql) {
  let generation = 0;
  let busy = false;
  let pasting = false;

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
    elements.download.disabled = true;
  }

  function invalidate() {
    pasting = false;
    generation += 1;
    busy = false;
    resetOutput();
    updateButtons();
    message('');
  }

  async function input(event) {
    const pasted = pasting || event.inputType === 'insertFromPaste';
    invalidate();
    if (pasted && elements.logs.value.trim()) {
      await generate(false);
    }
  }

  async function importFiles(files) {
    files = Array.from(files);
    if (!files.length) return;
    invalidate();
    const requestGeneration = generation;
    elements.file.value = '';
    if (files.length !== 1) {
      message('Importe um arquivo por vez.', true);
      return;
    }
    const file = files[0];
    if (!/\.(log|txt)$/i.test(file.name)) {
      message('Selecione um arquivo .log ou .txt.', true);
      return;
    }
    if (file.size > 5_000_000) {
      message('Importe no máximo 5 MB de logs.', true);
      return;
    }
    busy = true;
    updateButtons();
    message('Lendo arquivo…');
    try {
      const log = await file.text();
      if (requestGeneration !== generation) return;
      elements.logs.value = log;
      busy = false;
      await generate(false);
    } catch {
      if (requestGeneration !== generation) return;
      busy = false;
      updateButtons();
      message('Não foi possível ler o arquivo. Tente novamente.', true);
    }
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
      elements.download.disabled = !result.sql;
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
    invalidate();
    elements.logs.value = '';
    elements.file.value = '';
    elements.dropZone.classList.remove('dragging');
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
    elements.download.onclick = () => {
      if (elements.output.value) downloadSql(elements.output.value);
    };
    elements.logs.oninput = input;
    elements.logs.onpaste = () => { pasting = true; };
    elements.file.onchange = () => importFiles(elements.file.files);
    elements.dropZone.ondragover = event => {
      if (!Array.from(event.dataTransfer.types).includes('Files')) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
      elements.dropZone.classList.add('dragging');
    };
    elements.dropZone.ondragleave = event => {
      if (!elements.dropZone.contains(event.relatedTarget)) elements.dropZone.classList.remove('dragging');
    };
    elements.dropZone.ondrop = event => {
      elements.dropZone.classList.remove('dragging');
      if (!event.dataTransfer.files.length) return;
      event.preventDefault();
      return importFiles(event.dataTransfer.files);
    };
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
