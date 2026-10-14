import { createApi } from './api.js';
import { createController } from './controller.js';

const elements = Object.fromEntries(
  ['logs', 'output', 'status', 'prefix', 'normal', 'command', 'clear', 'copy']
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
);

await controller.initialize();
