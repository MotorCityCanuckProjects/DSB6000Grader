// =============================================
// Grading App - Main JavaScript
// =============================================

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

    // Show loading, hide results
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
        alert('Error grading paper: ' + error.message);
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
        loader.classList.remove('hidden');
    } else {
        loader.classList.add('hidden');
    }
}

function disableButtons(disabled) {
    document.getElementById('grade-btn').disabled = disabled;
    document.getElementById('clear-btn').disabled = disabled;
}
