/**
 * Minimalist ChatGPT-Style Client App
 */

const state = {
  semester: 1,
  assessmentType: 'theory',
  curriculum: null,
  chatHistory: [],
  score: { correct: 0, total: 0 }
};

document.addEventListener('DOMContentLoaded', () => {
  loadCurriculum(state.semester);
  resetChat();
});

function switchSemester(sem) {
  state.semester = sem;
  document.querySelectorAll('.pill-item').forEach((p, idx) => {
    p.classList.toggle('active', idx + 1 === sem);
  });
  loadCurriculum(sem);
  resetChat();
}

function resetChat() {
  state.chatHistory = [];
  const container = document.getElementById('messagesContainer');
  if (container) container.innerHTML = '';
  const topNav = document.getElementById('topNavBar');
  if (topNav) topNav.style.display = 'none';
}

async function loadCurriculum(sem) {
  try {
    const res = await fetch(`/api/curriculum?semester=${sem}`);
    if (!res.ok) return;
    state.curriculum = await res.json();
    populateModalDropdown();
  } catch (e) {
    console.error(e);
  }
}

function populateModalDropdown() {
  const dropdown = document.getElementById('modalLessonDropdown');
  dropdown.innerHTML = '';

  if (state.assessmentType === 'labeling') {
    const totalLabel = (state.curriculum && state.curriculum.total_labeling_diagrams != null)
      ? state.curriculum.total_labeling_diagrams
      : 0;
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = `All Approved Diagrams in Semester ${state.semester} (${totalLabel})`;
    dropdown.appendChild(allOpt);

    if (!state.curriculum) return;

    let hasAnyLabeling = false;
    state.curriculum.units.forEach(unit => {
      // Make unit name line directly clickable
      const unitOpt = document.createElement('option');
      unitOpt.value = `unit:${unit.unit_name}`;
      unitOpt.textContent = unit.unit_name;
      unitOpt.style.fontWeight = 'bold';
      dropdown.appendChild(unitOpt);

      unit.lessons.forEach(l => {
        // Only include genuine instructional lessons (Dars), ignore intros and summaries
        if (!l.lesson_name.startsWith('الدرس')) return;
        if (l.labeling_count && l.labeling_count > 0) {
          const opt = document.createElement('option');
          opt.value = l.lesson_name;
          opt.textContent = `\u00A0\u00A0\u00A0\u00A0${l.lesson_name} (🏷️ ${l.labeling_count})`;
          dropdown.appendChild(opt);
          hasAnyLabeling = true;
        }
      });
    });

    if (!hasAnyLabeling && totalLabel === 0) {
      const noOpt = document.createElement('option');
      noOpt.value = '';
      noOpt.disabled = true;
      noOpt.textContent = `No labeling diagrams available for Semester ${state.semester}`;
      dropdown.appendChild(noOpt);
    }
  } else if (state.assessmentType === 'diagram') {
    const totalDiag = (state.curriculum && state.curriculum.total_diagrams != null)
      ? state.curriculum.total_diagrams
      : 0;
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = `All Diagrams in Semester ${state.semester} (${totalDiag})`;
    dropdown.appendChild(allOpt);

    if (!state.curriculum) return;

    state.curriculum.units.forEach(unit => {
      // Make unit name line directly clickable
      const unitOpt = document.createElement('option');
      unitOpt.value = `unit:${unit.unit_name}`;
      unitOpt.textContent = unit.unit_name;
      unitOpt.style.fontWeight = 'bold';
      dropdown.appendChild(unitOpt);

      unit.lessons.forEach(l => {
        // Only include genuine instructional lessons (Dars)
        if (!l.lesson_name.startsWith('الدرس')) return;
        if (l.has_diagrams && l.diagram_count > 0) {
          const opt = document.createElement('option');
          opt.value = l.lesson_name;
          opt.textContent = `\u00A0\u00A0\u00A0\u00A0${l.lesson_name} (🖼️ ${l.diagram_count})`;
          dropdown.appendChild(opt);
        }
      });
    });
  } else {
    // Theory mode: list all genuine instructional lessons (Dars)
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = `All Units & Lessons in Semester ${state.semester}`;
    dropdown.appendChild(allOpt);

    if (!state.curriculum) return;

    state.curriculum.units.forEach(unit => {
      // Make unit name line directly clickable
      const unitOpt = document.createElement('option');
      unitOpt.value = `unit:${unit.unit_name}`;
      unitOpt.textContent = unit.unit_name;
      unitOpt.style.fontWeight = 'bold';
      dropdown.appendChild(unitOpt);

      unit.lessons.forEach(l => {
        // Only include genuine instructional lessons (Dars)
        if (!l.lesson_name.startsWith('الدرس')) return;
        const opt = document.createElement('option');
        opt.value = l.lesson_name;
        opt.textContent = `\u00A0\u00A0\u00A0\u00A0${l.lesson_name}`;
        dropdown.appendChild(opt);
      });
    });
  }
}

// Modal controls
function openAssessmentModal() {
  setModalTab(state.assessmentType || 'theory');
  document.getElementById('assessmentModal').style.display = 'flex';
}

function closeAssessmentModal() {
  document.getElementById('assessmentModal').style.display = 'none';
}

function setModalTab(type) {
  state.assessmentType = type;
  document.getElementById('tabTheory').classList.toggle('active', type === 'theory');
  document.getElementById('tabDiagram').classList.toggle('active', type === 'diagram');
  const tabLab = document.getElementById('tabLabeling');
  if (tabLab) tabLab.classList.toggle('active', type === 'labeling');

  const optionsRow = document.getElementById('assessmentOptionsRow');
  const typeWrapper = document.getElementById('typeSelectWrapper');
  const countWrapper = document.getElementById('countSelectWrapper');

  if (type === 'labeling') {
    if (optionsRow) optionsRow.style.display = 'none';
  } else if (type === 'diagram') {
    if (optionsRow) {
      optionsRow.style.display = 'grid';
      optionsRow.style.gridTemplateColumns = '1fr';
    }
    if (typeWrapper) typeWrapper.style.display = 'none';
    if (countWrapper) countWrapper.style.display = 'block';
  } else {
    // Theory mode
    if (optionsRow) {
      optionsRow.style.display = 'grid';
      optionsRow.style.gridTemplateColumns = '1fr 1fr';
    }
    if (typeWrapper) typeWrapper.style.display = 'block';
    if (countWrapper) countWrapper.style.display = 'block';
  }

  populateModalDropdown();
}

async function confirmStartAssessment() {
  const selectedVal = document.getElementById('modalLessonDropdown') ? document.getElementById('modalLessonDropdown').value : '';
  const qType = document.getElementById('modalQuestionType') ? document.getElementById('modalQuestionType').value : 'both';
  const qCount = document.getElementById('modalQuestionCount') ? parseInt(document.getElementById('modalQuestionCount').value, 10) : 5;

  let unit = null;
  let lesson = null;
  let targetTopic = '';

  if (selectedVal && selectedVal.startsWith('unit:')) {
    unit = selectedVal.replace('unit:', '');
    targetTopic = unit;
  } else if (selectedVal === 'all') {
    lesson = 'all';
    targetTopic = `All Semester ${state.semester}`;
  } else {
    lesson = selectedVal;
    targetTopic = lesson || 'General Science';
  }

  closeAssessmentModal();

  state.score = { correct: 0, total: 0 };

  // Show Top Navigation Bar with Back Arrow whenever an assessment starts
  const topNav = document.getElementById('topNavBar');
  const topNavTitle = document.getElementById('topNavTitle');
  if (topNav) {
    topNav.style.display = 'flex';
    if (topNavTitle) {
      if (state.assessmentType === 'theory') topNavTitle.textContent = `Theory Quiz (${qCount} Questions)`;
      else if (state.assessmentType === 'diagram') topNavTitle.textContent = `Diagram Assessment (${qCount} Questions/Diagram)`;
      else if (state.assessmentType === 'labeling') topNavTitle.textContent = `Interactive Labeling Mode`;
    }
  }

  if (state.assessmentType === 'theory') {
    const qTypes = [];
    if (qType === 'mcq') {
      for (let i = 0; i < qCount; i++) qTypes.push('mcq');
    } else if (qType === 'short') {
      for (let i = 0; i < qCount; i++) qTypes.push('short');
    } else {
      // 'both' strictly sums to qCount (2 -> 1+1, 3 -> 2+1, 5 -> 3+2)
      if (qCount === 2) {
        qTypes.push('mcq', 'short');
      } else if (qCount === 3) {
        qTypes.push('mcq', 'mcq', 'short');
      } else { // 5
        qTypes.push('mcq', 'mcq', 'mcq', 'short', 'short');
      }
    }

    appendUserMessage(`Generate Theory Assessment for: "${targetTopic}" (${qCount} questions • ${qType.toUpperCase()})`);

    // Mount progressive widget immediately on screen
    const widgetObj = createProgressiveTheoryWidget(targetTopic, qTypes.length);
    const prevQuestions = [];

    for (let i = 0; i < qTypes.length; i++) {
      const currentType = qTypes[i];
      const typeLabel = currentType === 'mcq' ? 'MCQ' : 'Short Question';
      widgetObj.updateStatus(`Generating Question ${i + 1} of ${qTypes.length} (${typeLabel})...`);

      try {
        const res = await fetch('/api/assessment/theory/generate-single', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            semester: state.semester,
            unit: unit,
            lesson: lesson,
            topic: targetTopic,
            q_type: currentType,
            question_num: i + 1,
            total_questions: qTypes.length,
            previous_questions: prevQuestions
          })
        });

        if (res.ok) {
          const qData = await res.json();
          widgetObj.appendQuestion(qData, i);
          if (qData.question) {
            prevQuestions.push(qData.question);
          }
        } else {
          console.error(`Failed to generate question ${i + 1}`);
        }
      } catch (err) {
        console.error(`Error generating question ${i + 1}:`, err);
      }
    }

    widgetObj.finish();
  } else if (state.assessmentType === 'diagram') {
    appendUserMessage(`Show Diagram Assessment for: "${targetTopic || 'All'}" (${qCount} questions per diagram)`);
    const thinkingEl = appendThinkingIndicator();

    try {
      // 1. Fast metadata fetch (<30ms) to get the diagrams list
      const listRes = await fetch('/api/assessment/diagram/list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          semester: state.semester,
          unit: unit,
          lesson: lesson || 'all',
          topic: targetTopic,
          limit: 5
        })
      });

      if (!listRes.ok) throw new Error('Failed to find diagrams for this lesson');
      const listData = await listRes.json();
      const diagrams = listData.diagrams || [];

      if (diagrams.length === 0) {
        thinkingEl.remove();
        appendBotMessage(`No approved diagrams found for this lesson in Semester ${state.semester}.`);
        return;
      }

      // 2. Remove thinking indicator and mount progressive widget on screen immediately!
      thinkingEl.remove();
      const widgetObj = createProgressiveDiagramWidget(diagrams.length, qCount);

      // 3. Sequentially generate questions for each diagram; each card appears on screen immediately upon arrival!
      for (let i = 0; i < diagrams.length; i++) {
        const diag = diagrams[i];
        widgetObj.updateStatus(`Generating ${qCount} questions for Diagram ${i + 1} of ${diagrams.length}...`);

        try {
          const singleRes = await fetch('/api/assessment/diagram/generate-single', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              diagram_id: diag.id,
              num_questions: qCount
            })
          });

          if (singleRes.ok) {
            const cardData = await singleRes.json();
            widgetObj.appendCard(cardData, i);
          } else {
            console.error(`Failed to generate questions for diagram ${diag.id}`);
          }
        } catch (diagErr) {
          console.error(`Error on diagram ${diag.id}:`, diagErr);
        }
      }

      widgetObj.finish();
    } catch (e) {
      thinkingEl.remove();
      appendBotMessage(`Error loading diagrams: ${e.message}`);
    }
  } else if (state.assessmentType === 'labeling') {
    appendUserMessage(`Start Interactive Labeling Quiz for: "${targetTopic || 'All'}"`);
    const thinkingEl = appendThinkingIndicator();
    try {
      const res = await fetch('/api/assessment/labeling', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          semester: state.semester,
          unit: unit,
          lesson: lesson || 'all',
          topic: targetTopic,
          limit: 999
        })
      });
      thinkingEl.remove();
      if (!res.ok) throw new Error('Failed to load labeling quiz');
      const data = await res.json();
      renderLabelingWidget(data);
    } catch (e) {
      thinkingEl.remove();
      appendBotMessage(`Error loading labeling quiz: ${e.message}`);
    }
  }
}

// Progressive Theory Assessment Widget (displays questions one by one as they are generated)
function createProgressiveTheoryWidget(title, totalQuestions) {
  const container = document.getElementById('messagesContainer');
  const row = document.createElement('div');
  row.className = 'message-row bot';

  const widget = document.createElement('div');
  widget.className = 'assessment-widget';

  widget.innerHTML = `
    <div class="widget-header" style="display: flex; align-items: center; justify-content: space-between;">
      <div style="display: flex; align-items: center; gap: 8px;">
        <button onclick="resetChat()" title="Back to Home" style="background: transparent; border: none; cursor: pointer; color: var(--text-muted); display: inline-flex; align-items: center; padding: 2px;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
        </button>
        <span class="widget-title">📝 ${escapeHtml(title)}</span>
      </div>
      <span class="widget-score" id="widgetScoreTracker">Score: 0 / 0</span>
    </div>
    <div class="widget-body">
      <div id="progressiveTheoryQuestions" style="display: flex; flex-direction: column; gap: 16px;"></div>
      <div id="theoryStatusIndicator" style="display: flex; align-items: center; gap: 10px; margin-top: 14px; padding: 10px 14px; background: var(--bg-hover, #f1f5f9); border-radius: var(--radius-sm, 6px); font-size: 0.85rem; color: var(--text-muted, #64748b);">
        <div style="width: 14px; height: 14px; border: 2px solid #3b82f6; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
        <span id="theoryStatusText">Starting assessment generation...</span>
      </div>
    </div>
  `;

  row.innerHTML = `<div class="message-avatar">✦</div>`;
  row.appendChild(widget);
  container.appendChild(row);
  scrollToBottom();

  const questionsList = widget.querySelector('#progressiveTheoryQuestions');
  const statusContainer = widget.querySelector('#theoryStatusIndicator');
  const statusText = widget.querySelector('#theoryStatusText');

  return {
    updateStatus(msg) {
      if (statusText) statusText.textContent = msg;
    },
    appendQuestion(q, idx) {
      const qDiv = document.createElement('div');
      qDiv.className = 'question-item';

      if (q.type === 'mcq') {
        qDiv.innerHTML = `
          <div class="question-text"><strong>Q${idx + 1} (MCQ):</strong> ${escapeHtml(q.question)}</div>
          <div class="options-list"></div>
        `;
        const optList = qDiv.querySelector('.options-list');
        if (q.options) {
          Object.entries(q.options).forEach(([letter, text]) => {
            const btn = document.createElement('button');
            btn.className = 'option-btn';
            btn.innerHTML = `<strong style="width: 18px;">${letter}</strong> <span>${escapeHtml(text)}</span>`;
            btn.onclick = () => handleOptionClick(btn, optList, letter, q.correct, q.explanation);
            optList.appendChild(btn);
          });
        }
      } else {
        qDiv.innerHTML = `
          <div class="question-text"><strong>Q${idx + 1} (Short Question):</strong> ${escapeHtml(q.question)}</div>
          <div class="student-answer-wrap">
            <textarea class="student-answer-input" placeholder="✍️ Write your answer here..." rows="3"></textarea>
          </div>
          <button class="toggle-inline-btn" onclick="toggleAnswer(this)" style="margin-top: 4px;">Show Actual Answer</button>
          <div class="inline-answer-box" style="display: none; margin-top: 8px;">
            <strong>Model Answer:</strong><br>${escapeHtml(q.model_answer || '')}
          </div>
        `;
      }

      questionsList.appendChild(qDiv);
      scrollToBottom();
    },
    finish() {
      if (statusContainer) {
        statusContainer.style.display = 'none';
      }
      scrollToBottom();
    }
  };
}

function handleOptionClick(btn, optList, selectedLetter, correctLetter, explanation) {
  const allBtns = optList.querySelectorAll('.option-btn');
  allBtns.forEach(b => b.disabled = true);

  state.score.total += 1;
  const isCorrect = selectedLetter === correctLetter;

  if (isCorrect) {
    btn.classList.add('correct');
    state.score.correct += 1;
  } else {
    btn.classList.add('wrong');
    allBtns.forEach(b => {
      if (b.innerText.trim().startsWith(correctLetter)) {
        b.classList.add('correct');
      }
    });
  }

  const tracker = document.getElementById('widgetScoreTracker');
  if (tracker) tracker.textContent = `Score: ${state.score.correct} / ${state.score.total}`;

  const exp = document.createElement('div');
  exp.className = 'explanation-inline';
  exp.innerHTML = `<strong>${isCorrect ? '✓' : '✗'}</strong> ${escapeHtml(explanation)}`;
  optList.parentElement.appendChild(exp);
}

function toggleAnswer(btn) {
  const box = btn.nextElementSibling;
  const hidden = box.style.display === 'none';
  box.style.display = hidden ? 'block' : 'none';
  btn.textContent = hidden ? 'Hide Actual Answer' : 'Show Actual Answer';
}

// Progressive Diagram Assessment Widget (renders diagram cards one by one as they arrive!)
function createProgressiveDiagramWidget(totalDiagrams, qCount) {
  const container = document.getElementById('messagesContainer');
  const row = document.createElement('div');
  row.className = 'message-row bot';

  const widget = document.createElement('div');
  widget.className = 'assessment-widget';

  widget.innerHTML = `
    <div class="widget-header" style="display: flex; align-items: center; justify-content: space-between;">
      <div style="display: flex; align-items: center; gap: 8px;">
        <button onclick="resetChat()" title="Back to Home" style="background: transparent; border: none; cursor: pointer; color: var(--text-muted); display: inline-flex; align-items: center; padding: 2px;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
        </button>
        <span class="widget-title">🖼️ Diagram Assessment (${totalDiagrams} Diagrams • ${qCount} Questions each)</span>
      </div>
    </div>
    <div class="widget-body" id="diagramCardsList"></div>
    <div class="diagram-progress-status" style="padding: 12px 14px; font-size: 0.85rem; color: var(--text-muted); display: flex; align-items: center; gap: 8px;">
      <span class="thinking-dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>
      <span class="status-text">Preparing diagrams...</span>
    </div>
  `;

  row.innerHTML = `<div class="message-avatar">✦</div>`;
  row.appendChild(widget);
  container.appendChild(row);
  scrollToBottom();

  const cardsList = widget.querySelector('#diagramCardsList');
  const statusContainer = widget.querySelector('.diagram-progress-status');
  const statusText = widget.querySelector('.status-text');

  return {
    updateStatus(msg) {
      if (statusText) statusText.textContent = msg;
      scrollToBottom();
    },
    appendCard(card, idx) {
      const cardEl = document.createElement('div');
      cardEl.className = 'diagram-inline-view';
      cardEl.style.marginBottom = '22px';
      cardEl.style.border = '1px solid var(--border-light, #e2e8f0)';
      cardEl.style.borderRadius = '10px';
      cardEl.style.padding = '14px';
      cardEl.style.background = '#ffffff';

      let questionsHtml = '';
      const questions = card.questions || [];

      questions.forEach((q, qIdx) => {
        if (q.type === 'mcq') {
          questionsHtml += `
            <div class="question-item" style="margin-top: 14px;">
              <div class="question-text"><strong>Q${qIdx + 1} (MCQ):</strong> ${escapeHtml(q.question)}</div>
              <div class="options-list" data-cardidx="${idx}" data-qidx="${qIdx}"></div>
            </div>
          `;
        } else {
          const qLabel = q.type === 'reasoning' ? 'Scientific Reasoning' : 'Short Question';
          questionsHtml += `
            <div class="question-item" style="margin-top: 14px;">
              <div class="question-text"><strong>Q${qIdx + 1} (${qLabel}):</strong> ${escapeHtml(q.question)}</div>
              <div class="student-answer-wrap">
                <textarea class="student-answer-input" placeholder="✍️ Write your answer here..." rows="3"></textarea>
              </div>
              <button class="toggle-inline-btn" onclick="toggleAnswer(this)" style="margin-top: 4px;">Show Actual Answer</button>
              <div class="inline-answer-box" style="display: none; margin-top: 8px;"><strong>Answer:</strong><br>${escapeHtml(q.answer || '')}</div>
            </div>
          `;
        }
      });

      cardEl.innerHTML = `
        <div style="font-size: 0.95rem; font-weight: 600; color: var(--text-main); margin-bottom: 8px;">
          #${idx + 1} — ${escapeHtml(card.lesson)}
        </div>
        <img class="diagram-inline-img" src="${card.image_url}" alt="Diagram" onclick="window.open('${card.image_url}', '_blank')" style="cursor: zoom-in; max-height: 400px; object-fit: contain; width: 100%; border-radius: 6px; background: #fafafa; border: 1px solid var(--border-light);">
        <div class="card-questions-wrap" style="margin-top: 12px;">
          ${questionsHtml}
        </div>
      `;

      // Attach MCQ click events
      questions.forEach((q, qIdx) => {
        if (q.type === 'mcq' && q.options) {
          const optList = cardEl.querySelector(`.options-list[data-cardidx="${idx}"][data-qidx="${qIdx}"]`);
          if (optList) {
            Object.entries(q.options).forEach(([letter, text]) => {
              const btn = document.createElement('button');
              btn.className = 'option-btn';
              btn.innerHTML = `<strong style="width: 18px;">${letter}</strong> <span>${escapeHtml(text)}</span>`;
              btn.onclick = () => handleOptionClick(btn, optList, letter, q.correct, q.explanation);
              optList.appendChild(btn);
            });
          }
        }
      });

      cardsList.appendChild(cardEl);
      scrollToBottom();
    },
    finish() {
      if (statusContainer) {
        statusContainer.style.display = 'none';
      }
      scrollToBottom();
    }
  };
}

// Render Interactive Labeling Assessment
function renderLabelingWidget(data) {
  const container = document.getElementById('messagesContainer');
  const row = document.createElement('div');
  row.className = 'message-row bot';

  const widget = document.createElement('div');
  widget.className = 'assessment-widget';

  widget.innerHTML = `
    <div class="widget-header" style="display: flex; align-items: center; justify-content: space-between;">
      <div style="display: flex; align-items: center; gap: 8px;">
        <button onclick="resetChat()" title="Back to Home" style="background: transparent; border: none; cursor: pointer; color: var(--text-muted); display: inline-flex; align-items: center; padding: 2px;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
        </button>
        <span class="widget-title">🏷️ Interactive Labeling Quiz</span>
      </div>
      <span class="score-badge" id="labelingScoreTracker">Score: 0 / 0</span>
    </div>
    <div class="widget-body" id="labelingList"></div>
  `;

  const target = widget.querySelector('#labelingList');

  data.diagrams.forEach((d, idx) => {
    const cardEl = document.createElement('div');
    cardEl.className = 'diagram-inline-view';
    cardEl.style.marginBottom = '24px';
    cardEl.style.padding = '16px';
    cardEl.style.background = 'var(--bg-card, #ffffff)';
    cardEl.style.borderRadius = '12px';
    cardEl.style.border = '1px solid var(--border-light, #e2e8f0)';

    let pinsHtml = '';
    const pinKeys = Object.keys(d.masked_labels).sort((a, b) => parseInt(a) - parseInt(b));

    pinKeys.forEach(pinNum => {
      let optHtml = `<option value="">-- Choose label for Pin ${pinNum} --</option>`;
      d.options.forEach(opt => {
        optHtml += `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`;
      });

      pinsHtml += `
        <div class="labeling-pin-row" style="display: flex; align-items: center; gap: 12px; margin-bottom: 10px;">
          <span style="display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 50%; background: #0f172a; color: #fff; font-weight: 700; font-size: 0.95rem;">${pinNum}</span>
          <select class="select-clean labeling-select" data-pin="${pinNum}" data-correct="${escapeHtml(d.masked_labels[pinNum])}" style="flex: 1; padding: 8px 12px; border-radius: 8px;">
            ${optHtml}
          </select>
          <span class="pin-feedback" style="font-weight: 600; min-width: 24px;"></span>
        </div>
      `;
    });

    cardEl.innerHTML = `
      <div style="font-size: 0.95rem; font-weight: 600; color: var(--text-main); margin-bottom: 12px;">
        #${idx + 1} — ${escapeHtml(d.lesson)}
      </div>
      <div style="text-align: center; margin-bottom: 16px;">
        <img class="diagram-inline-img" src="${d.image_url}" alt="Labeling Diagram" style="max-height: 420px; border-radius: 8px; border: 1px solid #cbd5e1; cursor: pointer;" onclick="window.open('${d.image_url}', '_blank')">
      </div>
      <div style="background: var(--bg-subtle, #f8fafc); padding: 14px; border-radius: 8px; margin-bottom: 12px;">
        <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-main); margin-bottom: 8px;">
          Identify the parts indicated by pins (حدد الأجزاء المشار إليها بالأرقام):
        </div>
        ${pinsHtml}
      </div>
      <button class="btn-check-labeling" style="padding: 8px 18px; border-radius: 6px; background: #2563eb; color: #fff; border: none; font-weight: 600; cursor: pointer;">
        Check Answers (تحقق من الإجابات)
      </button>
      <div class="labeling-result-msg" style="margin-top: 10px; font-size: 0.9rem; font-weight: 600; display: none;"></div>
    `;

    const btnCheck = cardEl.querySelector('.btn-check-labeling');
    btnCheck.onclick = () => {
      const selects = cardEl.querySelectorAll('.labeling-select');
      let cardCorrect = 0;
      let cardTotal = selects.length;

      selects.forEach(sel => {
        const chosen = sel.value.trim();
        const correct = sel.getAttribute('data-correct').trim();
        const fb = sel.nextElementSibling;
        sel.disabled = true;

        if (chosen === correct) {
          cardCorrect++;
          sel.style.borderColor = '#16a34a';
          sel.style.background = '#f0fdf4';
          fb.innerHTML = '<span style="color: #16a34a;">✓</span>';
        } else {
          sel.style.borderColor = '#dc2626';
          sel.style.background = '#fef2f2';
          fb.innerHTML = `<span style="color: #dc2626;">✗</span> <small style="color: #16a34a; font-weight: 600; margin-left: 6px;">(${correct})</small>`;
        }
      });

      state.score.correct += cardCorrect;
      state.score.total += cardTotal;

      const tracker = document.getElementById('labelingScoreTracker');
      if (tracker) tracker.textContent = `Score: ${state.score.correct} / ${state.score.total}`;

      const resMsg = cardEl.querySelector('.labeling-result-msg');
      resMsg.style.display = 'block';
      if (cardCorrect === cardTotal) {
        resMsg.innerHTML = `<span style="color: #16a34a;">🎉 Perfect! All ${cardTotal} labels identified correctly! (إجابة نموذجية كاملة)</span>`;
      } else {
        resMsg.innerHTML = `<span style="color: #d97706;">Score for this diagram: ${cardCorrect}/${cardTotal} correct. Review the corrections above!</span>`;
      }
      btnCheck.disabled = true;
      btnCheck.style.opacity = '0.6';
    };

    target.appendChild(cardEl);
  });

  row.innerHTML = `<div class="message-avatar">✦</div>`;
  row.appendChild(widget);
  container.appendChild(row);
  scrollToBottom();
}

// Chat Handlers
async function sendChatMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;

  appendUserMessage(text);
  input.value = '';

  const lower = text.toLowerCase();
  const mcqMatch = text.match(/(\d+)\s*(?:mcq|mcqs|question|questions|sawal)/i);

  // Direct conversational trigger for dynamic assessment
  if (mcqMatch) {
    setModalTab('theory');
    openAssessmentModal();
    return;
  }

  if (lower.includes('labeling') || lower.includes('interactive labeling') || lower.includes('label')) {
    setModalTab('labeling');
    openAssessmentModal();
    return;
  }

  if (lower.includes('create an assessment') || lower === 'assessment' || lower === 'quiz' || lower === 'اختبار') {
    openAssessmentModal();
    return;
  }

  const thinkingEl = appendThinkingIndicator();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: state.chatHistory,
        semester: state.semester
      })
    });

    thinkingEl.remove();
    if (!res.ok) throw new Error('Chat failed');
    const data = await res.json();

    state.chatHistory.push({ role: 'user', content: text });
    state.chatHistory.push({ role: 'assistant', content: data.reply });

    appendBotMessage(data.reply, data.suggestions);
  } catch (e) {
    thinkingEl.remove();
    appendBotMessage(`Error: ${e.message}`);
  }
}

function handleQuickChip(text) {
  if (text.toLowerCase().includes('create an assessment')) {
    openAssessmentModal();
  } else if (text.toLowerCase().includes('labeling')) {
    setModalTab('labeling');
    openAssessmentModal();
  } else if (text.toLowerCase().includes('diagram')) {
    setModalTab('diagram');
    openAssessmentModal();
  } else {
    document.getElementById('chatInput').value = text;
    sendChatMessage();
  }
}

function appendUserMessage(text) {
  const container = document.getElementById('messagesContainer');
  const row = document.createElement('div');
  row.className = 'message-row user';
  row.innerHTML = `
    <div class="message-avatar">👤</div>
    <div class="message-body"><p>${escapeHtml(text)}</p></div>
  `;
  container.appendChild(row);
  scrollToBottom();
}

function appendBotMessage(markdown, suggestions = []) {
  const container = document.getElementById('messagesContainer');
  const row = document.createElement('div');
  row.className = 'message-row bot';

  let chips = '';
  if (suggestions && suggestions.length > 0) {
    chips = '<div class="suggestion-wrap">' +
      suggestions.map(s => `<button class="suggestion-chip" onclick="handleQuickChip('${escapeHtml(s)}')">${escapeHtml(s)}</button>`).join('') +
      '</div>';
  }

  row.innerHTML = `
    <div class="message-avatar">✦</div>
    <div class="message-body">
      ${formatSimpleMarkdown(markdown)}
      ${chips}
    </div>
  `;
  container.appendChild(row);
  scrollToBottom();
}

function appendThinkingIndicator() {
  const container = document.getElementById('messagesContainer');
  const row = document.createElement('div');
  row.className = 'message-row bot';
  row.innerHTML = `
    <div class="message-avatar">✦</div>
    <div class="message-body" style="color: var(--text-light);">
      <span class="thinking-dot">●</span> thinking...
    </div>
  `;
  container.appendChild(row);
  scrollToBottom();
  return row;
}

function scrollToBottom() {
  const scrollArea = document.getElementById('chatScrollArea');
  scrollArea.scrollTop = scrollArea.scrollHeight;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatSimpleMarkdown(text) {
  if (!text) return '';
  let f = escapeHtml(text);
  f = f.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  f = f.replace(/\*(.*?)\*/g, '<em>$1</em>');
  f = f.replace(/^\s*[-*]\s+(.*)$/gm, '<li>$1</li>');
  f = f.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  f = f.split('\n\n').map(p => p.trim() ? `<p>${p}</p>` : '').join('');
  return f;
}
