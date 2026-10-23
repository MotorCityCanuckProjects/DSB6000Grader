// =============================================
// Grading App - Main JavaScript
// =============================================

let elapsedTimerId = null;
let gradingStartedAt = null;

async function gradePaper() {
    const studentName = document.getElementById('student-name').value.trim();
    const paperText = document.getElementById('paper-text').value.trim();

    // Basic validation
    if (!studentName) {
        alert('Please enter the student name.');
        return;
    }
    if (!paperText) {
        alert('Please paste the student paper text.');
        return;
    }

    // Show loading, hide results, and prevent duplicate submissions.
    clearGradingError();
    showLoading(true);
    hideResults();
    disableButtons(true);

    try {
        const response = await fetch('/api/grade', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student_name: studentName,
                paper_text: paperText
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Server error. Please try again.');
        }

        const data = await response.json();
        displayResults(data);

    } catch (error) {
        showGradingError('Unable to grade this paper. Please try again. ' + error.message);
    } finally {
        showLoading(false);
        disableButtons(false);
    }
}

function displayResults(data) {
        // Populate summary cards
    document.getElementById('result-student-name').textContent = data.student_name || '--';
    document.getElementById('grade-value').textContent = data.grade || '--';
    document.getElementById('word-count').textContent = data.word_count
        ? data.word_count.toLocaleString() + ' words'
        : '--';

    // Overall feedback
    document.getElementById('evaluation-text').textContent = data.feedback || 'No feedback provided.';

    // Criterion breakdown
    const container = document.getElementById('criterion-feedback');
    container.innerHTML = '';

    if (data.criterion_feedback && data.criterion_feedback.length > 0) {
        data.criterion_feedback.forEach(criterion => {
            const card = document.createElement('div');
            card.className = 'criterion-card';
            card.innerHTML = `
                <div class="criterion-card-header">
                    <h4>${criterion.name}</h4>
                    <span class="criterion-score">${criterion.score} / ${criterion.points} pts</span>
                </div>
                <p>${criterion.feedback}</p>
            `;
            container.appendChild(card);
        });
    }

    // Show results and scroll to them
    const resultsEl = document.getElementById('results');
    resultsEl.classList.remove('hidden');
    resultsEl.scrollIntoView({ behavior: 'smooth' });
}

function clearForm() {
    document.getElementById('student-name').value = '';
    document.getElementById('paper-text').value = '';
    clearGradingError();
    hideResults();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    document.getElementById('student-name').focus();
}

function hideResults() {
    document.getElementById('results').classList.add('hidden');
}

function showLoading(show) {
    const loader = document.getElementById('loading');
    if (show) {
        stopElapsedTimer();
        gradingStartedAt = Date.now();
        updateElapsedTime();
        elapsedTimerId = window.setInterval(updateElapsedTime, 1000);
        loader.classList.remove('hidden');
    } else {
        stopElapsedTimer();
        loader.classList.add('hidden');
    }
}

function updateElapsedTime() {
    const elapsedSeconds = Math.floor((Date.now() - gradingStartedAt) / 1000);
    document.getElementById('elapsed-seconds').textContent = elapsedSeconds;
}

function stopElapsedTimer() {
    if (elapsedTimerId !== null) {
        window.clearInterval(elapsedTimerId);
        elapsedTimerId = null;
    }
    gradingStartedAt = null;
}

function showGradingError(message) {
    const errorEl = document.getElementById('grading-error');
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
}

function clearGradingError() {
    const errorEl = document.getElementById('grading-error');
    errorEl.textContent = '';
    errorEl.classList.add('hidden');
}

function disableButtons(disabled) {
    document.getElementById('grade-btn').disabled = disabled;
    document.getElementById('clear-btn').disabled = disabled;
}

async function downloadPDF() {
    const btn = document.getElementById('download-pdf-btn');
    btn.disabled = true;
    btn.textContent = 'Generating PDF...';

    try {
        const response = await fetch('/api/download-pdf');

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to generate PDF.');
        }

        // Get filename from Content-Disposition header
        const disposition = response.headers.get('Content-Disposition');
        let filename = 'grading-report.pdf';
        if (disposition && disposition.includes('filename=')) {
            filename = disposition.split('filename=')[1].replace(/"/g, '').trim();
        }

        // Trigger download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);

    } catch (error) {
        alert('Error downloading PDF: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '&#8595; Download PDF';
    }
}
