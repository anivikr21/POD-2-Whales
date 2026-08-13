const MAX_FILE_BYTES = 4 * 1024 * 1024;
const PREDICT_ENDPOINT = '/api/predict';
const HEALTH_ENDPOINT = '/api/health';

const input = document.querySelector('#file-input');
const dropZone = document.querySelector('#drop-zone');
const selected = document.querySelector('#file-selected');
const fileName = document.querySelector('#file-name');
const analyze = document.querySelector('#analyze-button');
const resultPanel = document.querySelector('#result-panel');
const resultTitle = document.querySelector('#result-title');
const resultDescription = document.querySelector('#result-description');
const serviceStatus = document.querySelector('#service-status');

let currentFile = null;
let modelReady = false;

function setServiceStatus(message, ready) {
  modelReady = ready;
  serviceStatus.classList.toggle('service-ready', ready);
  serviceStatus.classList.toggle('service-error', !ready);
  serviceStatus.lastChild.textContent = ` ${message}`;
  analyze.disabled = !ready || !currentFile;
}

async function checkBackend() {
  try {
    const response = await fetch(HEALTH_ENDPOINT, { cache: 'no-store' });
    if (!response.ok) throw new Error('API unavailable');

    const health = await response.json();
    if (health.status === 'ready') {
      setServiceStatus('XGBoost model ready', true);
      return;
    }

    const missing = health.missing_model_files?.join(', ') || 'model files';
    setServiceStatus(`Setup required: ${missing}`, false);
  } catch {
    setServiceStatus('Model API unavailable', false);
  }
}

function setFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.csv')) {
    alert('Please choose a CSV file.');
    return;
  }
  if (file.size > MAX_FILE_BYTES) {
    alert('Please choose a CSV smaller than 4 MB.');
    return;
  }

  currentFile = file;
  fileName.textContent = file.name;
  selected.hidden = false;
  selected.style.display = 'flex';
  analyze.disabled = !modelReady;
  resultPanel.hidden = true;
}

function clearScreening() {
  currentFile = null;
  input.value = '';
  selected.hidden = true;
  selected.style.display = '';
  analyze.disabled = true;
  resultPanel.hidden = true;
}

function showResult(title, description, isError = false) {
  resultPanel.classList.toggle('result-error', isError);
  if (isError) {
    delete resultPanel.dataset.classification;
  }
  resultTitle.textContent = title;
  resultDescription.textContent = description;
  resultPanel.hidden = false;
  resultPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function renderResults(data) {
  const firstResult = data.first_result;
  const confidence = Math.round(firstResult.confidence * 100);
  const classCounts = Object.entries(data.summary)
    .filter(([, count]) => count > 0)
    .sort(([, firstCount], [, secondCount]) => secondCount - firstCount);
  const breakdown = classCounts
    .map(([classification, count]) => `${classification}: ${count}`)
    .join(' · ');
  const [dominantClass, dominantCount] = classCounts[0];

  const title = data.rows_analyzed === 1
    ? `${firstResult.classification} — ${confidence}% model confidence`
    : `${dominantClass} — most frequent classification`;

  resultPanel.dataset.classification = dominantClass;

  const description = data.rows_analyzed === 1
    ? `Class probabilities were calculated for one variant. This model output is not a clinical diagnosis.`
    : `${dominantCount.toLocaleString()} of ${data.rows_analyzed.toLocaleString()} variants were classified as ${dominantClass}. ${breakdown}. This model output is not a clinical diagnosis.`;

  showResult(title, description);
}

input.addEventListener('change', () => setFile(input.files[0]));

['dragenter', 'dragover'].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.add('dragging');
  });
});

['dragleave', 'drop'].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.remove('dragging');
  });
});

dropZone.addEventListener('drop', (event) => setFile(event.dataTransfer.files[0]));
document.querySelector('#remove-file').addEventListener('click', clearScreening);

analyze.addEventListener('click', async () => {
  if (!currentFile || !modelReady) return;

  const originalContent = analyze.innerHTML;
  analyze.disabled = true;
  analyze.textContent = 'Analyzing…';

  const formData = new FormData();
  formData.append('file', currentFile);

  try {
    const response = await fetch(PREDICT_ENDPOINT, { method: 'POST', body: formData });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.detail || 'The model could not analyze this file.');
    }

    renderResults(data);
  } catch (error) {
    showResult('Analysis unavailable', error.message, true);
  } finally {
    analyze.disabled = !modelReady;
    analyze.innerHTML = originalContent;
  }
});

document.querySelector('#new-screening').addEventListener('click', () => {
  clearScreening();
  dropZone.scrollIntoView({ behavior: 'smooth', block: 'center' });
});

checkBackend();
