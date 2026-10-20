import { createApi } from './api.js';
import { createController } from './controller.js';

const elements = Object.fromEntries(
  ['logs', 'output', 'status', 'prefix', 'normal', 'command', 'clear', 'copy', 'file', 'dropZone', 'download']
    .map(id => [id, document.getElementById(id)]),
);

const controller = createController(
  elements,
  createApi(window.fetch.bind(window)),
  navigator.clipboard,
  label => {
    const option = document.createElement('option');
    option.value = label;
    option.textContent = label;
    return option;
  },
  sql => {
    const url = URL.createObjectURL(new Blob([sql], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'queries.sql';
    document.body.append(link);
    try {
      link.click();
    } finally {
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    }
  },
);

await controller.initialize();
