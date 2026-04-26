(function () {
    const radios = document.querySelectorAll('input[name="input_method"]');
    const cards = document.querySelectorAll('.mode-card');
    const copyButtons = document.querySelectorAll('.api-copy');

    const courseCode = document.getElementById('courseCode');
    const courseCredits = document.getElementById('courseCredits');
    const courseGrade = document.getElementById('courseGrade');
    const courseSeason = document.getElementById('courseSeason');
    const courseYear = document.getElementById('courseYear');
    const addCourseBtn = document.getElementById('addCourseBtn');
    const manualText = document.getElementById('manualText');
    const courseList = document.getElementById('courseList');
    const emptyCourse = document.getElementById('emptyCourse');
    const creditMinus = document.getElementById('creditMinus');
    const creditPlus = document.getElementById('creditPlus');
    const clearCoursesBtn = document.getElementById('clearCoursesBtn');
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    const courseFormError = document.getElementById('courseFormError');
    const runApiDemoBtn = document.getElementById('runApiDemoBtn');
    const apiDemoResult = document.getElementById('apiDemoResult');
    const ocrPreviewRaw = document.getElementById('ocrPreviewRaw');
    const ocrRows = document.getElementById('ocrRows');
    const ocrMeta = document.getElementById('ocrMeta');
    const aiChatLog = document.getElementById('aiChatLog');
    const aiChatInput = document.getElementById('aiChatInput');
    const aiChatSendBtn = document.getElementById('aiChatSendBtn');
    const aiChatStatus = document.getElementById('aiChatStatus');

    const manualRows = [];
    let editingIndex = -1;

    function updateMode() {
        let active = 'manual';
        radios.forEach((radio) => {
            if (radio.checked) {
                active = radio.value;
            }
        });

        cards.forEach((card) => {
            const show = card.dataset.mode === active;
            card.style.display = show ? 'block' : 'none';
        });
    }

    radios.forEach((radio) => {
        radio.addEventListener('change', updateMode);
    });

    copyButtons.forEach((btn) => {
        btn.addEventListener('click', async () => {
            const text = btn.dataset.copy || '';
            if (!text) {
                return;
            }
            try {
                await navigator.clipboard.writeText(text);
                const oldLabel = btn.textContent;
                btn.textContent = 'Copied';
                window.setTimeout(() => {
                    btn.textContent = oldLabel;
                }, 1000);
            } catch (err) {
                const oldLabel = btn.textContent;
                btn.textContent = 'Copy failed';
                window.setTimeout(() => {
                    btn.textContent = oldLabel;
                }, 1100);
            }
        });
    });

    async function runApiDemo() {
        if (!runApiDemoBtn || !apiDemoResult) {
            return;
        }

        const old = runApiDemoBtn.textContent;
        runApiDemoBtn.disabled = true;
        runApiDemoBtn.textContent = 'Syncing...';
        apiDemoResult.textContent = 'Fetching /api/history...';

        try {
            const historyRes = await fetch('/api/history');
            const historyJson = await historyRes.json();
            if (!historyRes.ok || !historyJson.ok) {
                throw new Error(historyJson.error || 'History API failed');
            }

            const latest = historyJson.runs?.[0] || null;
            if (!latest) {
                apiDemoResult.textContent = JSON.stringify({
                    steps: ['GET /api/history'],
                    history_count: 0,
                    message: 'No saved runs yet. Run an analysis first from the form above.'
                }, null, 2);
                return;
            }

            apiDemoResult.textContent = `Fetching /api/history/${latest.id}...`;
            const detailsRes = await fetch(`/api/history/${latest.id}`);
            const detailsJson = await detailsRes.json();
            if (!detailsRes.ok || !detailsJson.ok) {
                throw new Error(detailsJson.error || 'History details API failed');
            }

            const output = {
                steps: ['GET /api/history', `GET /api/history/${latest.id}`],
                history_count: historyJson.count,
                latest_run: latest,
                latest_run_details: {
                    cgpa: detailsJson.cgpa,
                    total_courses: detailsJson.latest_rows?.length || 0,
                    issues: detailsJson.issues || [],
                    waived: detailsJson.waived || []
                }
            };

            apiDemoResult.textContent = JSON.stringify(output, null, 2);
        } catch (err) {
            apiDemoResult.textContent = `API Demo Error: ${err.message}`;
        } finally {
            runApiDemoBtn.disabled = false;
            runApiDemoBtn.textContent = old;
        }
    }

    function syncTextarea() {
        if (!manualText) {
            return;
        }
        manualText.value = manualRows.join('\n');
    }

    function setError(message) {
        if (!courseFormError) {
            return;
        }
        courseFormError.textContent = message || '';
        courseFormError.style.display = message ? 'block' : 'none';
    }

    function setEditMode(index) {
        editingIndex = index;
        if (!addCourseBtn || !cancelEditBtn) {
            return;
        }
        if (index >= 0) {
            addCourseBtn.textContent = 'Update Course';
            cancelEditBtn.style.display = 'inline-flex';
        } else {
            addCourseBtn.textContent = 'Add Course';
            cancelEditBtn.style.display = 'none';
        }
    }

    function parseRowText(rowText) {
        const parts = rowText.split(',').map((p) => p.trim());
        if (parts.length !== 4) {
            return null;
        }
        const semParts = parts[3].split(' ');
        if (semParts.length < 2) {
            return null;
        }
        return {
            code: parts[0],
            credits: parts[1],
            grade: parts[2],
            season: semParts[0],
            year: semParts[1],
        };
    }

    function fillFormFromRow(rowText) {
        const parsed = parseRowText(rowText);
        if (!parsed || !courseCode || !courseCredits || !courseGrade || !courseSeason || !courseYear) {
            return;
        }
        courseCode.value = parsed.code;
        courseCredits.value = parsed.credits;
        courseGrade.value = parsed.grade;
        courseSeason.value = parsed.season;
        courseYear.value = parsed.year;
    }

    function resetFormInputs() {
        if (!courseCode || !courseCredits || !courseGrade || !courseSeason || !courseYear) {
            return;
        }
        courseCode.value = '';
        courseCredits.value = '3';
        courseGrade.value = 'A';
        courseSeason.value = 'Spring';
        courseYear.value = String(new Date().getFullYear());
        courseCode.focus();
    }

    function renderRows() {
        if (!courseList || !emptyCourse) {
            return;
        }

        const existing = courseList.querySelectorAll('.course-row');
        existing.forEach((row) => row.remove());

        if (!manualRows.length) {
            emptyCourse.style.display = 'block';
            return;
        }

        emptyCourse.style.display = 'none';
        manualRows.forEach((rowText, idx) => {
            const row = document.createElement('div');
            row.className = 'course-row';

            const code = rowText.split(',')[0]?.trim() || 'COURSE';
            const label = document.createElement('span');
            label.textContent = rowText;

            const codeBadge = document.createElement('span');
            codeBadge.className = 'course-code-pill';
            codeBadge.textContent = code;

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'remove-course-btn';
            removeBtn.textContent = 'Remove';
            removeBtn.addEventListener('click', () => {
                manualRows.splice(idx, 1);
                if (editingIndex === idx) {
                    setEditMode(-1);
                    resetFormInputs();
                } else if (editingIndex > idx) {
                    setEditMode(editingIndex - 1);
                }
                syncTextarea();
                renderRows();
            });

            const editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'edit-course-btn';
            editBtn.textContent = 'Edit';
            editBtn.addEventListener('click', () => {
                fillFormFromRow(rowText);
                setEditMode(idx);
                setError('');
            });

            const actions = document.createElement('div');
            actions.className = 'course-actions';
            actions.appendChild(editBtn);
            actions.appendChild(removeBtn);

            const left = document.createElement('div');
            left.className = 'course-left';
            left.appendChild(codeBadge);
            left.appendChild(label);

            row.appendChild(left);
            row.appendChild(actions);
            courseList.appendChild(row);
        });
    }

    function clampCredits() {
        if (!courseCredits) {
            return;
        }
        const raw = parseInt(courseCredits.value || '0', 10);
        if (Number.isNaN(raw)) {
            courseCredits.value = '0';
            return;
        }
        const safe = Math.max(0, Math.min(6, raw));
        courseCredits.value = String(safe);
    }

    function addCourseFromForm() {
        if (!courseCode || !courseCredits || !courseGrade || !courseSeason || !courseYear) {
            return;
        }

        const code = courseCode.value.trim().toUpperCase();
        const credits = parseInt(courseCredits.value || '0', 10);
        const grade = courseGrade.value;
        const season = courseSeason.value;
        const year = parseInt(courseYear.value || '0', 10);

        if (!code) {
            setError('Course code is required.');
            courseCode.focus();
            return;
        }
        if (!/^[A-Z]{2,4}\d{3}[A-Z]?$/.test(code)) {
            setError('Course code format looks invalid. Example: CSE115');
            courseCode.focus();
            return;
        }
        if (Number.isNaN(credits) || credits < 0 || credits > 6) {
            setError('Credits must be between 0 and 6.');
            courseCredits.focus();
            return;
        }
        if (Number.isNaN(year) || year < 2000 || year > 2100) {
            setError('Year must be between 2000 and 2100.');
            courseYear.focus();
            return;
        }

        const built = `${code}, ${credits}, ${grade}, ${season} ${year}`;
        if (editingIndex >= 0) {
            manualRows[editingIndex] = built;
            setEditMode(-1);
        } else {
            manualRows.push(built);
        }
        setError('');
        syncTextarea();
        renderRows();
        resetFormInputs();
    }

    if (addCourseBtn) {
        addCourseBtn.addEventListener('click', addCourseFromForm);
    }

    if (runApiDemoBtn) {
        runApiDemoBtn.addEventListener('click', runApiDemo);
        runApiDemo();
    }

    if (creditMinus) {
        creditMinus.addEventListener('click', () => {
            if (!courseCredits) {
                return;
            }
            const raw = parseInt(courseCredits.value || '0', 10);
            const next = Math.max(0, (Number.isNaN(raw) ? 0 : raw) - 1);
            courseCredits.value = String(next);
        });
    }

    if (creditPlus) {
        creditPlus.addEventListener('click', () => {
            if (!courseCredits) {
                return;
            }
            const raw = parseInt(courseCredits.value || '0', 10);
            const next = Math.min(6, (Number.isNaN(raw) ? 0 : raw) + 1);
            courseCredits.value = String(next);
        });
    }

    if (courseCredits) {
        courseCredits.addEventListener('change', clampCredits);
    }

    if (cancelEditBtn) {
        cancelEditBtn.addEventListener('click', () => {
            setEditMode(-1);
            setError('');
            resetFormInputs();
        });
    }

    if (clearCoursesBtn) {
        clearCoursesBtn.addEventListener('click', () => {
            manualRows.length = 0;
            setEditMode(-1);
            setError('');
            syncTextarea();
            renderRows();
            resetFormInputs();
        });
    }

    if (manualText && manualText.value.trim()) {
        manualText.value
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean)
            .forEach((line) => manualRows.push(line));
        renderRows();
    }

    if (courseFormError) {
        courseFormError.style.display = 'none';
    }

    function parseOcrHeader(headerLine) {
        const meta = {};
        const conf = headerLine.match(/OCR confidence:\s*([A-Z]+)/i);
        const score = headerLine.match(/score:\s*(-?\d+)/i);
        const pages = headerLine.match(/pages:\s*(\[[^\]]*\])\/(\d+)/i);
        if (conf) {
            meta.confidence = conf[1].toUpperCase();
        }
        if (score) {
            meta.score = score[1];
        }
        if (pages) {
            meta.pages = `${pages[1]}/${pages[2]}`;
        }
        return meta;
    }

    function isLikelyCourseRow(line) {
        const text = (line || '').trim();
        if (!text) {
            return false;
        }
        const hasCode = /\b[A-Z]{2,4}\d{3}[A-Z]?\b/.test(text);
        const hasGrade = /\b(A\-|A|B\+|B|B\-|C\+|C|C\-|D\+|D|F|W)\b/.test(text);
        const hasCredit = /\b\d(?:\.\d{1,2})?\b/.test(text);
        const noisy = /(controller|university|official transcript|department)/i.test(text);
        return hasCode && (hasGrade || hasCredit) && !noisy;
    }

    function extractSemesterHeader(line) {
        const m = line.match(/\b(Spring|Summer|Fall)\s*[-/]?\s*(\d{4})\b/i);
        if (!m) {
            return null;
        }
        return `${m[1][0].toUpperCase()}${m[1].slice(1).toLowerCase()} ${m[2]}`;
    }

    function cleanCourseName(text) {
        let s = (text || '').trim();
        s = s.replace(/[|_]{2,}/g, ' ');
        s = s.replace(/\s{2,}/g, ' ');
        return s.trim();
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function applyLinesToManualEditor(lines) {
        if (!manualText || !Array.isArray(lines)) {
            return;
        }
        const cleaned = lines.map((line) => line.trim()).filter(Boolean);
        manualRows.length = 0;
        cleaned.forEach((line) => manualRows.push(line));
        manualText.value = cleaned.join('\n');
        renderRows();
        setEditMode(-1);
        setError('');

        radios.forEach((radio) => {
            radio.checked = radio.value === 'manual';
        });
        updateMode();
        if (manualText) {
            manualText.focus();
        }
    }

    function validateCorrectedLines(lines) {
        const issues = [];
        const courseRe = /^[A-Z]{2,4}\d{3}[A-Z]?$/;
        const gradeSet = new Set(['A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'F', 'W']);
        const semRe = /^(Spring|Summer|Fall)\s+\d{4}$/;

        lines.forEach((line, idx) => {
            const parts = line.split(',').map((p) => p.trim());
            if (parts.length !== 4) {
                issues.push(`Line ${idx + 1}: must be Course_Code, Credits, Grade, Semester`);
                return;
            }

            const [code, creditRaw, gradeRaw, semesterRaw] = parts;
            const grade = gradeRaw.toUpperCase();
            const credit = Number.parseFloat(creditRaw);

            if (!courseRe.test(code.toUpperCase())) {
                issues.push(`Line ${idx + 1}: invalid course code '${code}'`);
            }
            if (!Number.isFinite(credit) || credit < 0 || credit > 6) {
                issues.push(`Line ${idx + 1}: credits must be between 0 and 6`);
            }
            if (!gradeSet.has(grade)) {
                issues.push(`Line ${idx + 1}: invalid grade '${gradeRaw}'`);
            }
            if (!semRe.test(semesterRaw)) {
                issues.push(`Line ${idx + 1}: semester must look like Spring 2010`);
            }
        });

        return issues;
    }

    function updateCorrectionStatus(textarea, statusEl) {
        if (!textarea || !statusEl) {
            return [];
        }
        const lines = textarea.value.split('\n').map((line) => line.trim()).filter(Boolean);
        const issues = validateCorrectedLines(lines);
        if (!issues.length) {
            textarea.classList.remove('warning');
            statusEl.innerHTML = `<span class="ok">Looks good. ${lines.length} row(s) ready for Manual mode.</span>`;
            return [];
        }

        textarea.classList.add('warning');
        statusEl.innerHTML = `<span class="warn">Found ${issues.length} suspicious issue(s):</span><ul>${issues.slice(0, 12).map((issue) => `<li>${escapeHtml(issue)}</li>`).join('')}</ul>`;
        return issues;
    }

    function parseCourseLine(line) {
        const compact = (line || '').replace(/\s+/g, ' ').trim();
        const codeMatch = compact.match(/\b([A-Z]{2,4}\d{3}[A-Z]?)\b/);
        if (!codeMatch) {
            return null;
        }

        const code = codeMatch[1];
        const afterCode = compact.slice(codeMatch.index + code.length).trim();
        const gradeMatch = afterCode.match(/\b(A\-|A|B\+|B|B\-|C\+|C|C\-|D\+|D|F|W)\b/i);
        const grade = gradeMatch ? gradeMatch[1].toUpperCase() : '';

        const tail = compact.slice(codeMatch.index + code.length).trim();
        const nums = tail.match(/\d+(?:\.\d+)?/g) || [];
        let credit = '';
        let counted = '';
        let passed = '';

        function normalizeCreditToken(token) {
            const raw = (token || '').trim();
            if (!raw) {
                return '';
            }
            const val = parseFloat(raw);
            if (!Number.isNaN(val) && val >= 0 && val <= 6) {
                return String(val % 1 === 0 ? val.toFixed(1) : val);
            }
            if (/^\d0$/.test(raw)) {
                const guess = parseInt(raw[0], 10);
                if (guess >= 0 && guess <= 6) {
                    return `${guess}.0`;
                }
            }
            return raw;
        }

        const beforeGrade = gradeMatch ? tail.slice(0, gradeMatch.index) : tail;
        const afterGrade = gradeMatch ? tail.slice(gradeMatch.index + gradeMatch[0].length) : '';
        const numsBefore = beforeGrade.match(/\d+(?:\.\d+)?/g) || [];
        const numsAfter = afterGrade.match(/\d+(?:\.\d+)?/g) || [];

        credit = normalizeCreditToken(numsBefore[numsBefore.length - 1] || nums[0] || '');
        counted = normalizeCreditToken(numsAfter[0] || nums[nums.length - 2] || '');
        passed = normalizeCreditToken(numsAfter[1] || nums[nums.length - 1] || '');

        let namePart = afterCode;
        if (gradeMatch) {
            namePart = afterCode.slice(0, gradeMatch.index).trim();
        }
        namePart = namePart.replace(/\b\d+(?:\.\d+)?\b\s*$/, '').trim();
        if (!namePart) {
            const rough = compact.replace(code, '').replace(/\b\d+(?:\.\d+)?\b/g, '').replace(/\b(A\-|A|B\+|B|B\-|C\+|C|C\-|D\+|D|F|W)\b/gi, '');
            namePart = rough;
        }

        const name = cleanCourseName(namePart) || 'Unknown';
        return { code, name, credit, grade, counted, passed };
    }

    function renderStructuredPreview(payload) {
        if (!ocrRows || !ocrMeta || !payload) {
            return false;
        }

        const meta = payload.meta || {};
        const chips = [];
        if (meta.confidence) {
            chips.push(`Confidence: ${meta.confidence}`);
        }
        chips.push(`Score: ${meta.score || 0}`);
        chips.push(`Pages: ${JSON.stringify(meta.pages || [])}/${meta.total_pages || 0}`);
        chips.push(`Detected Rows: ${payload.detected_rows || 0}`);
        ocrMeta.innerHTML = chips.map((c) => `<span class="ocr-chip">${c}</span>`).join('');

        const html = [];
        const correctedLines = [];
        (payload.semester_blocks || []).forEach((block) => {
            html.push(`<div class="ocr-semester">${block.semester}</div>`);
            (block.rows || []).forEach((d) => {
                correctedLines.push(`${d.course_code}, ${d.credit}, ${d.grade}, ${block.semester}`);
                html.push(`<div class="ocr-row course-hit"><div class="ocr-line-grid"><div class="ocr-cell"><b>Semester:</b> ${block.semester}</div><div class="ocr-cell"><b>Course:</b> <strong>${d.course_code}</strong></div><div class="ocr-cell"><b>Course Name:</b> ${d.course_name || '-'}</div><div class="ocr-cell"><b>Credit:</b> ${d.credit ?? '-'}</div><div class="ocr-cell"><b>Grade:</b> ${d.grade || '-'}</div><div class="ocr-cell"><b>Credit Counted:</b> ${d.credit_counted || '-'}</div><div class="ocr-cell"><b>Credit Passed:</b> ${d.credit_passed || '-'}</div></div></div>`);
            });
        });

        (payload.summary_rows || []).forEach((s) => {
            html.push(`<div class="ocr-row semester-summary"><div class="ocr-line-grid"><div class="ocr-cell"><b>Semester:</b> ${s.semester || '-'}</div><div class="ocr-cell"><b>Semester Credit:</b> ${s.semester_credit || '-'}</div><div class="ocr-cell"><b>TGPA:</b> ${s.tgpa || '-'}</div><div class="ocr-cell"><b>CGPA:</b> ${s.cgpa || '-'}</div></div></div>`);
        });

        const uniqueLines = Array.from(new Set(correctedLines));
        if (uniqueLines.length) {
            html.unshift(
                `<div class="ocr-corrector"><h4>Edit OCR Rows</h4><p>Fix any wrong row below, then move it to Manual mode for reliable analysis.</p><textarea id="ocrCorrectedTextarea" class="ocr-corrected-text" rows="8">${escapeHtml(uniqueLines.join('\n'))}</textarea><div class="ocr-correction-status" id="ocrCorrectionStatus"></div><div class="ocr-correct-actions"><button type="button" class="btn primary" id="useOcrCorrectionsBtn">Use Corrected Rows in Manual Mode</button></div></div>`
            );
        }

        ocrRows.innerHTML = html.length ? html.join('') : '<div class="ocr-empty">No parsed rows found.</div>';

        const useBtn = document.getElementById('useOcrCorrectionsBtn');
        const correctedArea = document.getElementById('ocrCorrectedTextarea');
        const correctionStatus = document.getElementById('ocrCorrectionStatus');
        if (useBtn && correctedArea) {
            updateCorrectionStatus(correctedArea, correctionStatus);
            correctedArea.addEventListener('input', () => {
                updateCorrectionStatus(correctedArea, correctionStatus);
            });
            useBtn.addEventListener('click', () => {
                const lines = correctedArea.value.split('\n').map((line) => line.trim()).filter(Boolean);
                if (!lines.length) {
                    return;
                }
                const issues = updateCorrectionStatus(correctedArea, correctionStatus);
                if (issues.length) {
                    return;
                }
                applyLinesToManualEditor(lines);
            });
        }

        return true;
    }

    function parseSemesterSummary(line) {
        const text = (line || '').replace(/\s+/g, ' ').trim();
        if (!/semester\s*credit|tgpa|cgpa/i.test(text)) {
            return null;
        }
        const sc = text.match(/semester\s*credit\s*:\s*(\d+(?:\.\d+)?)/i);
        const tg = text.match(/tgpa\s*:\s*(\d+(?:\.\d+)?)/i);
        const cg = text.match(/cgpa\s*:\s*(\d+(?:\.\d+)?)/i);
        return {
            semesterCredit: sc ? sc[1] : '-',
            tgpa: tg ? tg[1] : '-',
            cgpa: cg ? cg[1] : '-',
        };
    }

    function renderOcrPreviewUI() {
        if (!ocrPreviewRaw || !ocrRows || !ocrMeta) {
            return;
        }

        const payloadEl = document.getElementById('ocrPreviewPayload');
        if (payloadEl && payloadEl.textContent.trim()) {
            try {
                const payload = JSON.parse(payloadEl.textContent);
                if (renderStructuredPreview(payload)) {
                    return;
                }
            } catch (err) {
                // fall back to raw parsing
            }
        }

        const fullText = ocrPreviewRaw.textContent || '';
        const lines = fullText.split('\n');
        let startIdx = 0;

        if (lines[0] && lines[0].includes('OCR confidence')) {
            const parsed = parseOcrHeader(lines[0]);
            const chips = [];
            if (parsed.confidence) {
                chips.push(`Confidence: ${parsed.confidence}`);
            }
            if (parsed.score) {
                chips.push(`Score: ${parsed.score}`);
            }
            if (parsed.pages) {
                chips.push(`Pages: ${parsed.pages}`);
            }
            ocrMeta.innerHTML = chips.map((c) => `<span class="ocr-chip">${c}</span>`).join('');
            if (lines[1] && !lines[1].trim()) {
                startIdx = 2;
            } else {
                startIdx = 1;
            }
        } else {
            ocrMeta.innerHTML = '<span class="ocr-chip">Debug OCR Snapshot</span>';
        }

        const bodyLines = lines.slice(startIdx);
        const rendered = [];
        let currentSemester = null;

        bodyLines.forEach((line) => {
            const raw = (line || '').trim();
            if (!raw) {
                return;
            }

            const sem = extractSemesterHeader(raw);
            if (sem) {
                currentSemester = sem;
                rendered.push({ type: 'semester', text: sem });
                return;
            }

            const summary = parseSemesterSummary(raw);
            if (summary) {
                rendered.push({ type: 'summary', data: summary });
                return;
            }

            if (isLikelyCourseRow(raw)) {
                const parsed = parseCourseLine(raw);
                if (parsed) {
                    rendered.push({ type: 'course', semester: currentSemester || 'Unknown Semester', data: parsed });
                }
            }
        });

        if (!rendered.length) {
            ocrRows.innerHTML = '<div class="ocr-empty">No clear course-like rows found in this OCR snapshot. Check Raw Extracted Text and upload a cleaner page if needed.</div>';
            return;
        }

        ocrRows.innerHTML = rendered
            .slice(0, 140)
            .map((item) => {
                if (item.type === 'semester') {
                    return `<div class="ocr-semester">${item.text}</div>`;
                }
                if (item.type === 'summary') {
                    return `<div class="ocr-row semester-summary"><div class="ocr-line-grid"><div class="ocr-cell"><b>Semester Credit:</b> ${item.data.semesterCredit}</div><div class="ocr-cell"><b>TGPA:</b> ${item.data.tgpa}</div><div class="ocr-cell"><b>CGPA:</b> ${item.data.cgpa}</div></div></div>`;
                }
                const d = item.data;
                return `<div class="ocr-row course-hit"><div class="ocr-line-grid"><div class="ocr-cell"><b>Semester:</b> ${item.semester}</div><div class="ocr-cell"><b>Course:</b> <strong>${d.code}</strong></div><div class="ocr-cell"><b>Course Name:</b> ${d.name}</div><div class="ocr-cell"><b>Credit:</b> ${d.credit || '-'}</div><div class="ocr-cell"><b>Grade:</b> ${d.grade || '-'}</div><div class="ocr-cell"><b>Credit Counted:</b> ${d.counted || '-'}</div><div class="ocr-cell"><b>Credit Passed:</b> ${d.passed || '-'}</div></div></div>`;
            })
            .join('');
    }

    renderOcrPreviewUI();

    function appendChatMessage(role, text, trace) {
        if (!aiChatLog) {
            return;
        }
        const bubble = document.createElement('div');
        bubble.className = `ai-msg ${role}`;
        bubble.textContent = text;
        aiChatLog.appendChild(bubble);

        if (Array.isArray(trace) && trace.length) {
            const traceWrap = document.createElement('div');
            traceWrap.className = 'ai-tool-trace';
            traceWrap.innerHTML = trace
                .map((t) => `<span class="ai-trace-chip ${t.status === 'ok' ? 'ok' : 'error'}">${t.tool} · ${t.status} · ${t.latency_ms}ms</span>`)
                .join('');
            aiChatLog.appendChild(traceWrap);
        }

        aiChatLog.scrollTop = aiChatLog.scrollHeight;
    }

    async function sendAiChat() {
        if (!aiChatInput || !aiChatSendBtn) {
            return;
        }
        const message = aiChatInput.value.trim();
        if (!message) {
            return;
        }

        appendChatMessage('user', message);
        aiChatInput.value = '';
        aiChatSendBtn.disabled = true;
        if (aiChatStatus) {
            aiChatStatus.textContent = 'Thinking...';
        }

        try {
            const res = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message,
                    user_id: 'web-user',
                    context: { screen: 'dashboard' }
                })
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data?.error?.message || 'AI chat request failed');
            }

            appendChatMessage('assistant', data.reply || 'No reply', data.tool_trace || []);
            if (aiChatStatus) {
                aiChatStatus.textContent = data.fallback_used
                    ? 'Tool failure fallback used. You may retry.'
                    : `Request ID: ${data.request_id}`;
            }
        } catch (err) {
            appendChatMessage('assistant', 'I could not complete that request. Please retry.');
            if (aiChatStatus) {
                aiChatStatus.textContent = `Error: ${err.message}`;
            }
        } finally {
            aiChatSendBtn.disabled = false;
        }
    }

    if (aiChatSendBtn) {
        aiChatSendBtn.addEventListener('click', sendAiChat);
    }
    if (aiChatInput) {
        aiChatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendAiChat();
            }
        });
    }

    updateMode();
})();
