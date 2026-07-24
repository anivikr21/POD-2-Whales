const input = document.querySelector('#file-input');
const dropZone = document.querySelector('#drop-zone');
const selected = document.querySelector('#file-selected');
const fileName = document.querySelector('#file-name');
const analyze = document.querySelector('#analyze-button');
const resultPanel = document.querySelector('#result-panel');

function setFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.csv')) return alert('Please choose a CSV file.');
  if (file.size > 10 * 1024 * 1024) return alert('Please choose a file smaller than 10 MB.');
  fileName.textContent = file.name;
  selected.hidden = false;
  selected.style.display = 'flex';
  analyze.disabled = false;
  resultPanel.hidden = true;
}

input.addEventListener('change', () => setFile(input.files[0]));
['dragenter','dragover'].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.add('dragging'); }));
['dragleave','drop'].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.remove('dragging'); }));
dropZone.addEventListener('drop', (event) => setFile(event.dataTransfer.files[0]));
document.querySelector('#remove-file').addEventListener('click', () => { input.value = ''; selected.hidden = true; selected.style.display = ''; analyze.disabled = true; });
analyze.addEventListener('click', () => { resultPanel.hidden = false; resultPanel.scrollIntoView({ behavior:'smooth', block:'center' }); });
document.querySelector('#new-screening').addEventListener('click', () => { input.value = ''; selected.hidden = true; selected.style.display = ''; analyze.disabled = true; resultPanel.hidden = true; dropZone.scrollIntoView({ behavior:'smooth', block:'center' }); });
