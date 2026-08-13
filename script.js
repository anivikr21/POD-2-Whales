const input = document.querySelector('#file-input');
const dropZone = document.querySelector('#drop-zone');
const selected = document.querySelector('#file-selected');
const fileName = document.querySelector('#file-name');
const analyze = document.querySelector('#analyze-button');
const resultPanel = document.querySelector('#result-panel');
const resultTitle = resultPanel.querySelector('strong');
const resultDescription = resultPanel.querySelector('p');

let currentFile = null;

function setFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.csv')) return alert('Please choose a CSV file.');
  if (file.size > 10 * 1024 * 1024) return alert('Please choose a file smaller than 10 MB.');

  currentFile = file;
  fileName.textContent = file.name;
  selected.hidden = false;
  selected.style.display = 'flex';
  analyze.disabled = false;
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

function getBackendUrl() {
  let url = localStorage.getItem('lipidlensBackendUrl');

  if (!url) {
    url = prompt('Paste the Backend URL printed by the final Google Colab cell:');
  }

  if (!url) return null;

  url = url.trim().replace(/\/$/, '');
  if (!/^https:\/\//i.test(url)) {
    alert('The backend address must be an HTTPS URL.');
    return null;
  }

  localStorage.setItem('lipidlensBackendUrl', url);
  return url;
}

function renderResults(data) {
  const counts = data.results.reduce((summary, result) => {
    summary[result.classification] = (summary[result.classification] || 0) + 1;
    return summary;
  }, {});

  const firstResult = data.results[0];
  const confidence = Math.round(firstResult.confidence * 100);
  const breakdown = Object.entries(counts)
    .map(([classification, count]) => `${classification}: ${count}`)
    .join(' · ');

  resultTitle.textContent = data.rows_analyzed === 1
    ? `${firstResult.classification} — ${confidence}% confidence`
    : `${data.rows_analyzed} variants analyzed`;
  resultDescription.textContent = `${breakdown}. This model output is not a clinical diagnosis.`;
  resultPanel.hidden = false;
  resultPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
  if (!currentFile) return;

  const backendUrl = getBackendUrl();
  if (!backendUrl) return;

  const originalContent = analyze.innerHTML;
  analyze.disabled = true;
  analyze.textContent = 'Analyzing…';

  const formData = new FormData();
  formData.append('file', currentFile);

  try {
    const response = await fetch(`${backendUrl}/predict`, {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'The model could not analyze this file.');
    }
    if (!data.results?.length) {
      throw new Error('The model returned no results.');
    }

    renderResults(data);
  } catch (error) {
    alert(`${error.message}\n\nIf Colab restarted, clear the saved backend URL and paste the new one.`);
  } finally {
    analyze.disabled = false;
    analyze.innerHTML = originalContent;
  }
});

document.querySelector('#new-screening').addEventListener('click', () => {
  clearScreening();
  dropZone.scrollIntoView({ behavior: 'smooth', block: 'center' });
});
