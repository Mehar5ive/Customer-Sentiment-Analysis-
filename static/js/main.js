document.addEventListener('DOMContentLoaded', () => {
    // Sections
    const inputSection = document.getElementById('input-section');
    const summarySection = document.getElementById('summary-section');
    const chartsSection = document.getElementById('charts-section');
    const historySection = document.getElementById('history-section');
    const trendsSection = document.getElementById('trends-section');

    // Main Controls
    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('file-input');
    const loader = document.getElementById('loader');
    const errorMessage = document.getElementById('error-message');
    const viewChartsBtn = document.getElementById('view-charts-btn');
    const viewPastResultsBtn = document.getElementById('view-past-results-btn');
    const viewTrendsBtn = document.getElementById('view-trends-btn');
    
    // Filter Controls
    const sentimentFilter = document.getElementById('sentiment-filter');
    const emotionFilter = document.getElementById('emotion-filter');
    const categoryFilter = document.getElementById('category-filter');
    const urgencyFilter = document.getElementById('urgency-filter');
    const resetFiltersBtn = document.getElementById('reset-filters-btn');
    const clearAllBtn = document.getElementById('clear-all-btn');
    const exportCsvBtn = document.getElementById('export-csv-btn');

    // Display
    const summaryContent = document.getElementById('summary-content');
    const downloadCsvBtn = document.getElementById('download-csv-btn');
    const downloadPdfBtn = document.getElementById('download-pdf-btn');
    const historyTableBody = document.getElementById('history-table-body');
    const resultsTitle = document.getElementById('results-title');
    
    const chartInstances = {};
    let lastAnalysisData = null;

    // --- Navigation ---
    function showSection(sectionToShow) {
        inputSection.classList.add('hidden');
        summarySection.classList.add('hidden');
        chartsSection.classList.add('hidden');
        historySection.classList.add('hidden');
        trendsSection.classList.add('hidden');
        if (sectionToShow) sectionToShow.classList.remove('hidden');
    }

    if(viewPastResultsBtn) viewPastResultsBtn.addEventListener('click', () => {
        loadHistoryTable();
        showSection(historySection);
    });

    if(viewChartsBtn) viewChartsBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/history/summary');
            if (!response.ok) throw new Error('Could not fetch history summary.');
            const summaryData = await response.json();
            displayCharts(summaryData, "All Past Results");
            showSection(chartsSection);
        } catch (error) {
            alert(error.message);
        }
    });
    
    if(viewTrendsBtn) viewTrendsBtn.addEventListener('click', () => {
        loadTrendChart();
        showSection(trendsSection);
    });

    document.querySelectorAll('.back-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            showSection(inputSection);
            if(lastAnalysisData) summarySection.classList.remove('hidden');
        });
    });

    // --- Analysis ---
    if(uploadForm) uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        loader.style.display = 'block';
        errorMessage.textContent = '';
        summarySection.classList.add('hidden');
        const formData = new FormData(uploadForm);
        const isFileAnalysis = fileInput.files.length > 0;
        try {
            const response = await fetch('/analyze', { method: 'POST', body: formData });
            const responseData = await response.json();
            if (!response.ok) throw new Error(responseData.error || 'Analysis failed');
            
            lastAnalysisData = responseData;
            
            if (isFileAnalysis) {
                loadHistoryTable();
                showSection(historySection);
            } else {
                displaySummary(lastAnalysisData);
                showSection(inputSection);
                summarySection.classList.remove('hidden');
            }
        } catch (error) {
            errorMessage.textContent = `Error: ${error.message}`;
        } finally {
            loader.style.display = 'none';
            fileInput.value = ''; 
        }
    });

    // --- Display & Charting ---
    function displaySummary(data) {
        const { summary, run_id } = data;
        const score = summary.overall_score;
        const overallSentiment = score > 10 ? 'Positive' : score < -10 ? 'Negative' : 'Neutral';
        const emotions = Object.keys(summary.emotion).join(', ') || 'None Detected';
        const categories = Object.keys(summary.category).join(', ') || 'None Detected';
        summaryContent.innerHTML = `<p><strong>Overall Sentiment:</strong> ${overallSentiment} (${score.toFixed(1)}%)</p><p><strong>Detected Emotions:</strong> ${emotions}</p><p><strong>Detected Categories:</strong> ${categories}</p>`;
        downloadCsvBtn.href = `/download/csv/${run_id}`;
        downloadPdfBtn.href = `/download/pdf/${run_id}`;
    }

    function displayCharts(summary, title = "Analysis Charts") {
        if(resultsTitle) resultsTitle.textContent = title;
        const chartColors = { sentiment: ['#a8c8a4', '#f5b7b1', '#d5d8dc'], emotion: ['#aee1cd', '#f1c40f', '#e74c3c', '#a569bd', '#5dade2'], category: ['#b7d80', '#f5b041', '#85c1e9', '#f7dc6f'], urgency: ['#e74c3c', '#f39c12', '#d5d8dc'] };
        createOrUpdateChart('sentimentChart', 'Sentiment', summary.sentiment, chartColors.sentiment, 'sentiment');
        createOrUpdateChart('emotionChart', 'Emotions', summary.emotion, chartColors.emotion, 'emotion');
        createOrUpdateChart('categoryChart', 'Categories', summary.category, chartColors.category, 'category');
        createOrUpdateChart('urgencyChart', 'Urgency', summary.urgency, chartColors.urgency, 'urgency');
    }

    function createOrUpdateChart(canvasId, label, data, colors, filterType) {
        const canvasEl = document.getElementById(canvasId);
        if (!canvasEl) return;
        const ctx = canvasEl.getContext('2d');
        if (chartInstances[canvasId]) chartInstances[canvasId].destroy();
        chartInstances[canvasId] = new Chart(ctx, {
            type: 'doughnut', data: { labels: Object.keys(data), datasets: [{ data: Object.values(data), backgroundColor: colors }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: '55%', plugins: { legend: { position: 'right' } },
                onClick: (e, elements) => {
                    if (elements.length > 0) {
                        const clickedLabel = chartInstances[canvasId].data.labels[elements[0].index];
                        handleChartClick(filterType, clickedLabel);
                    }
                }
            }
        });
    }
    
    function handleChartClick(filterType, value) {
        if(resetFiltersBtn) resetFiltersBtn.click();
        if (filterType === 'sentiment' && sentimentFilter) sentimentFilter.value = value;
        if (filterType === 'emotion' && emotionFilter) emotionFilter.value = value;
        if (filterType === 'category' && categoryFilter) categoryFilter.value = value;
        if (filterType === 'urgency' && urgencyFilter) urgencyFilter.value = value;
        loadHistoryTable();
        showSection(historySection);
    }
    
    async function loadTrendChart() {
        try {
            const response = await fetch('/trends/sentiment');
            if (!response.ok) throw new Error('Could not fetch trend data.');
            const trendData = await response.json();
            createTrendChart(trendData);
        } catch (error) {
            alert(error.message);
        }
    }

    function createTrendChart(data) {
        const canvasId = 'trendsChart';
        const canvasEl = document.getElementById(canvasId);
        if(!canvasEl) return;
        const ctx = canvasEl.getContext('2d');
        if (chartInstances[canvasId]) chartInstances[canvasId].destroy();
        chartInstances[canvasId] = new Chart(ctx, {
            type: 'line', data: data,
            options: { responsive: true, maintainAspectRatio: false,
                scales: { y: { beginAtZero: true, title: { display: true, text: 'Number of Feedback Entries' } },
                          x: { title: { display: true, text: 'Date' } } }
            }
        });
    }

    // --- History Table & Filtering ---
    async function loadHistoryTable() {
        const params = new URLSearchParams();
        if(sentimentFilter && sentimentFilter.value) params.append('sentiment', sentimentFilter.value);
        if(emotionFilter && emotionFilter.value) params.append('emotion', emotionFilter.value);
        if(categoryFilter && categoryFilter.value) params.append('category', categoryFilter.value);
        if(urgencyFilter && urgencyFilter.value) params.append('urgency', urgencyFilter.value);
        try {
            const response = await fetch(`/history_table?${params.toString()}`);
            const entries = await response.json();
            if(historyTableBody) {
                historyTableBody.innerHTML = '';
                if (entries.length === 0) {
                    historyTableBody.innerHTML = '<tr><td colspan="8" style="text-align:center;">No results match your filters.</td></tr>';
                    return;
                }
                entries.forEach(e => {
                    const confidencePct = (Math.abs(e.confidence) * 100).toFixed(0);
                    const row = document.createElement('tr');
                    row.dataset.id = e.id;
                    row.innerHTML = `<td title="${e.text}">${e.text}</td><td>${e.sentiment}</td><td>${confidencePct}%</td><td>${e.emotion}</td><td>${e.category}</td><td>${e.urgency}</td><td>${e.timestamp}</td><td><button class="btn-danger btn-delete">Delete</button></td>`;
                    historyTableBody.appendChild(row);
                });
            }
        } catch (error) { if(historyTableBody) historyTableBody.innerHTML = '<tr><td colspan="8" style="color:red;">Failed to load history.</td></tr>'; }
    }

    [sentimentFilter, emotionFilter, categoryFilter, urgencyFilter].forEach(filter => {
        if(filter) filter.addEventListener('change', loadHistoryTable);
    });

    if(resetFiltersBtn) resetFiltersBtn.addEventListener('click', () => {
        if(sentimentFilter) sentimentFilter.value = '';
        if(emotionFilter) emotionFilter.value = '';
        if(categoryFilter) categoryFilter.value = '';
        if(urgencyFilter) urgencyFilter.value = '';
        loadHistoryTable();
    });

    if(exportCsvBtn) exportCsvBtn.addEventListener('click', () => {
        const params = new URLSearchParams();
        if(sentimentFilter && sentimentFilter.value) params.append('sentiment', sentimentFilter.value);
        if(emotionFilter && emotionFilter.value) params.append('emotion', emotionFilter.value);
        if(categoryFilter && categoryFilter.value) params.append('category', categoryFilter.value);
        if(urgencyFilter && urgencyFilter.value) params.append('urgency', urgencyFilter.value);
        window.location.href = `/export/csv?${params.toString()}`;
    });

    if(historyTableBody) historyTableBody.addEventListener('click', async (e) => {
        if (e.target.classList.contains('btn-delete')) {
            const row = e.target.closest('tr');
            const id = row.dataset.id;
            if (confirm(`Delete entry #${id}?`)) {
                const response = await fetch(`/history_entry/${id}`, { method: 'DELETE' });
                if (response.ok) row.remove();
                else alert('Failed to delete entry.');
            }
        }
    });

    if(clearAllBtn) clearAllBtn.addEventListener('click', async () => {
        if(confirm('Are you sure you want to delete ALL data permanently?')) {
            const response = await fetch('/history/clear_all', {method: 'DELETE'});
            if(response.ok) loadHistoryTable();
            else alert('Failed to clear data.');
        }
    });
});

