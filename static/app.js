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
});

function switchSemester(sem) {
  state.semester = sem;
  document.querySelectorAll('.pill-item').forEach((p, idx) => {
    p.classList.toggle('active', idx + 1 === sem);
  });
  loadCurriculum(sem);
  resetChat(); // Clear screen completely on semester switch
}

function resetChat() {
  state.chatHistory = [];
  const container = document.getElementById('messagesContainer');
  container.innerHTML = ''; // completely blank canvas
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

  if (state.assessmentType === 'diagram') {
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = `All Diagrams in Semester ${state.semester} (${state.curriculum?.total_diagrams || 0})`;
    dropdown.appendChild(allOpt);
  }

  if (!state.curriculum) return;

  state.curriculum.units.forEach(unit => {
    const group = document.createElement('optgroup');
    group.label = unit.unit_name;
    unit.lessons.forEach(l => {
      if (l.lesson_name.includes('تمهيد') || l.lesson_name.includes('فهرس')) return;
      const opt = document.createElement('option');
      opt.value = l.lesson_name;
      opt.textContent = l.lesson_name + (l.has_diagrams ? ` (🖼️ ${l.diagram_count})` : '');
      group.appendChild(opt);
    });
    if (group.children.length > 0) dropdown.appendChild(group);
  });
}

// Modal controls
function openAssessmentModal() {
  populateModalDropdown();
  document.getElementById('assessmentModal').style.display = 'flex';
}

function closeAssessmentModal() {
  document.getElementById('assessmentModal').style.display = 'none';
}

function setModalTab(type) {
  state.assessmentType = type;
  document.getElementById('tabTheory').classList.toggle('active', type === 'theory');
  document.getElementById('tabDiagram').classList.toggle('active', type === 'diagram');
  populateModalDropdown();
}

async function confirmStartAssessment() {
  const lesson = document.getElementById('modalLessonDropdown').value;
  closeAssessmentModal();

  state.score = { correct: 0, total: 0 };

  if (state.assessmentType === 'theory') {
    appendUserMessage(`Generate Theory Assessment for: ${lesson}`);
    const thinkingEl = appendThinkingIndicator();
    try {
      const res = await fetch('/api/assessment/theory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ semester: state.semester, lesson: lesson, num_mcq: 5, num_short: 3 })
      });
      thinkingEl.remove();
      if (!res.ok) throw new Error('Failed to generate assessment');
      const data = await res.json();
      renderTheoryWidget(data);
    } catch (e) {
      thinkingEl.remove();
      appendBotMessage(`Error generating assessment: ${e.message}`);
    }
  } else {
    appendUserMessage(`Show Diagram Assessment for: ${lesson || 'All'}`);
    const thinkingEl = appendThinkingIndicator();
    try {
      const res = await fetch('/api/assessment/diagram', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ semester: state.semester, lesson: lesson })
      });
      thinkingEl.remove();
      if (!res.ok) throw new Error('Failed to load diagrams');
      const data = await res.json();
      renderDiagramWidget(data);
    } catch (e) {
      thinkingEl.remove();
      appendBotMessage(`Error loading diagrams: ${e.message}`);
    }
  }
}

// Render Theory Assessment inside chat as clean widget
function renderTheoryWidget(data) {
  const container = document.getElementById('messagesContainer');
  const row = document.createElement('div');
  row.className = 'message-row bot';

  const widget = document.createElement('div');
  widget.className = 'assessment-widget';

  widget.innerHTML = `
    <div class="widget-header">
      <span class="widget-title">📝 ${escapeHtml(data.title || data.lesson)}</span>
      <span class="widget-score" id="widgetScoreTracker">Score: 0 / 0</span>
    </div>
    <div class="widget-body">
      ${data.diagram_url ? `
        <div style="border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px; background: #fafafa; text-align: center; margin-bottom: 12px;">
          <div style="font-size: 0.75rem; font-weight: 600; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.5px; margin-bottom: 8px;">🖼️ Reference Diagram from Textbook</div>
          <img src="${data.diagram_url}" style="max-width: 100%; max-height: 360px; object-fit: contain; background: white; border-radius: 4px; cursor: zoom-in;" title="Click to view full size" onclick="window.open('${data.diagram_url}', '_blank')">
        </div>
      ` : ''}

      <!-- MCQs -->
      <div style="font-size: 0.85rem; font-weight: 600; text-transform: uppercase; color: var(--text-light); letter-spacing: 0.5px;">Multiple Choice Questions</div>
      <div id="mcqContainer" style="display: flex; flex-direction: column; gap: 18px;"></div>

      <!-- Short Questions -->
      <div style="font-size: 0.85rem; font-weight: 600; text-transform: uppercase; color: var(--text-light); letter-spacing: 0.5px; margin-top: 10px;">Short Answer Questions</div>
      <div id="shortContainer" style="display: flex; flex-direction: column; gap: 14px;"></div>
    </div>
  `;

  // Render MCQs
  const mcqTarget = widget.querySelector('#mcqContainer');
  data.mcqs.forEach((mcq, idx) => {
    const qDiv = document.createElement('div');
    qDiv.className = 'question-item';
    qDiv.innerHTML = `<div class="question-text">${idx + 1}. ${escapeHtml(mcq.question)}</div><div class="options-list"></div>`;

    const optList = qDiv.querySelector('.options-list');
    Object.entries(mcq.options).forEach(([letter, text]) => {
      const btn = document.createElement('button');
      btn.className = 'option-btn';
      btn.innerHTML = `<strong style="width: 18px;">${letter}</strong> <span>${escapeHtml(text)}</span>`;
      btn.onclick = () => handleOptionClick(btn, optList, letter, mcq.correct, mcq.explanation);
      optList.appendChild(btn);
    });
    mcqTarget.appendChild(qDiv);
  });

  // Render Short Questions
  const shortTarget = widget.querySelector('#shortContainer');
  data.short_questions.forEach((sq, idx) => {
    const qDiv = document.createElement('div');
    qDiv.className = 'question-item';
    qDiv.innerHTML = `
      <div class="question-text">${idx + 1}. ${escapeHtml(sq.question)}</div>
      <button class="toggle-inline-btn" onclick="toggleAnswer(this)">Show Answer</button>
      <div class="inline-answer-box" style="display: none;">
        ${escapeHtml(sq.model_answer)}
      </div>
    `;
    shortTarget.appendChild(qDiv);
  });

  row.innerHTML = `<div class="message-avatar">✦</div>`;
  row.appendChild(widget);
  container.appendChild(row);
  scrollToBottom();
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
  btn.textContent = hidden ? 'Hide Answer' : 'Show Answer';
}

// Render Diagram Assessment
function renderDiagramWidget(data) {
  const container = document.getElementById('messagesContainer');
  const row = document.createElement('div');
  row.className = 'message-row bot';

  const widget = document.createElement('div');
  widget.className = 'assessment-widget';

  widget.innerHTML = `
    <div class="widget-header">
      <span class="widget-title">🖼️ Diagram Cards (${data.cards.length} Diagrams)</span>
    </div>
    <div class="widget-body" id="diagramCardsList"></div>
  `;

  const target = widget.querySelector('#diagramCardsList');

  data.cards.forEach((c, idx) => {
    const cardEl = document.createElement('div');
    cardEl.className = 'diagram-inline-view';

    cardEl.innerHTML = `
      <div style="font-size: 0.9rem; font-weight: 600; color: var(--text-main);">#${idx + 1} — ${escapeHtml(c.lesson)}</div>
      <img class="diagram-inline-img" src="${c.image_url}" alt="Diagram" onclick="window.open('${c.image_url}', '_blank')">

      <!-- Q1 Short -->
      <div class="question-item">
        <div class="question-text"><strong>Q1:</strong> ${escapeHtml(c.short_question.question)}</div>
        <button class="toggle-inline-btn" onclick="toggleAnswer(this)">Show Answer</button>
        <div class="inline-answer-box" style="display: none;">${escapeHtml(c.short_question.answer)}</div>
      </div>

      <!-- Q2 MCQ -->
      <div class="question-item">
        <div class="question-text"><strong>Q2:</strong> ${escapeHtml(c.mcq.question)}</div>
        <div class="options-list"></div>
      </div>

      <!-- Q3 Reasoning -->
      <div class="question-item">
        <div class="question-text"><strong>Q3:</strong> ${escapeHtml(c.reasoning_question.question)}</div>
        <button class="toggle-inline-btn" onclick="toggleAnswer(this)">Show Answer</button>
        <div class="inline-answer-box" style="display: none;">${escapeHtml(c.reasoning_question.answer)}</div>
      </div>
    `;

    // MCQ choices
    const optList = cardEl.querySelector('.options-list');
    Object.entries(c.mcq.options).forEach(([letter, text]) => {
      const btn = document.createElement('button');
      btn.className = 'option-btn';
      btn.innerHTML = `<strong style="width: 18px;">${letter}</strong> <span>${escapeHtml(text)}</span>`;
      btn.onclick = () => handleOptionClick(btn, optList, letter, c.mcq.correct, c.mcq.explanation);
      optList.appendChild(btn);
    });

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

  if (text.toLowerCase().includes('assessment') || text.toLowerCase().includes('quiz')) {
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
