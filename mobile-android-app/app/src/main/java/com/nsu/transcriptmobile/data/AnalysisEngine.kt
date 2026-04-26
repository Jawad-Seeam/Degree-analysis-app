package com.nsu.transcriptmobile.data

import java.time.Instant

object AnalysisEngine {
    private val gradePoints = mapOf(
        "A" to 4.0,
        "A-" to 3.7,
        "B+" to 3.3,
        "B" to 3.0,
        "B-" to 2.7,
        "C+" to 2.3,
        "C" to 2.0,
        "C-" to 1.7,
        "D+" to 1.3,
        "D" to 1.0,
        "F" to 0.0
    )

    private val validGrades = setOf("A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F", "W")

    private val disclaimerTerms = listOf(
        "controller of examinations",
        "official institutional",
        "cannot be released",
        "without the written consent",
        "not apply toward cgpa"
    )

    private data class ProgramRule(
        val code: String,
        val requiredCredits: Int,
        val requirements: Map<String, List<String>>
    )

    private val cseRule = ProgramRule(
        code = "CSE",
        requiredCredits = 130,
        requirements = mapOf(
            "Mandatory GED" to listOf("ENG102", "ENG103", "HIS103", "PHI101"),
            "Core Math" to listOf("MAT116", "MAT120", "MAT250", "MAT350", "MAT361"),
            "Major Core" to listOf("CSE115", "CSE173", "CSE215", "CSE225", "CSE231", "CSE311", "CSE323", "CSE327", "CSE331", "CSE332", "CSE425")
        )
    )

    private val bbaRule = ProgramRule(
        code = "BBA",
        requiredCredits = 124,
        requirements = mapOf(
            "Mandatory GED" to listOf("ENG102", "ENG103", "HIS103", "PHI101", "ENV203"),
            "Core Business" to listOf("ACT201", "ACT202", "FIN254", "MGT210", "MGT314", "MGT368", "MKT202"),
            "Major Core" to listOf("BUS101", "BUS112", "BUS134", "MIS205", "QM212")
        )
    )

    fun analyzeManual(
        userId: Int,
        program: String,
        manualText: String,
        waivedInput: List<String> = emptyList(),
        nextRunId: Int,
    ): RunRecord {
        val rows = parseManual(manualText)
        val rule = when (program.uppercase()) {
            "BBA" -> bbaRule
            else -> cseRule
        }
        val waived = waivedInput.map { it.trim().uppercase() }.filter { it.isNotBlank() }
        val latest = latestRows(rows)
        val retakes = retakeMap(rows)

        val cgpa = calculateCgpa(latest, waived)
        val earned = earnedCredits(latest, waived)
        val remaining = (rule.requiredCredits - earned).coerceAtLeast(0)
        val audit = runAudit(latest, rule, waived)
        val cgpaDetails = buildCgpaDetails(latest, waived)
        val retakeSummary = retakes
            .filter { it.value.size > 1 }
            .map { (course, attempts) ->
                RetakeSummary(
                    course = course,
                    attempts = attempts.sortedBy { semesterNumber(it.semester) }.map { "${it.grade} (${it.semester})" }
                )
            }
            .sortedBy { it.course }
        val issues = audit.filter { it.status != "COMPLETED" && it.status != "WAIVED" }.map { "${it.status}: ${it.course} (${it.category})" }.toMutableList()

        if (remaining > 0) {
            issues.add("CREDIT DEFICIENCY: Need $remaining more credits")
        }
        if (cgpa < 2.0) {
            issues.add("PROBATION: CGPA ${"%.2f".format(cgpa)} is below 2.00")
        }

        val result = AnalyzeResult(
            inputMethod = "manual",
            program = rule.code,
            cgpa = (cgpa * 100.0).toInt() / 100.0,
            earnedCredits = earned,
            requiredCredits = rule.requiredCredits,
            remainingCredits = remaining,
            eligible = issues.isEmpty(),
            waived = waived,
            issues = issues,
            latestRows = latest.values.sortedBy { it.courseCode },
            courseAudit = audit,
            cgpaDetails = cgpaDetails,
            retakeSummary = retakeSummary,
        )

        val summary = HistoryItem(
            id = nextRunId,
            userId = userId,
            inputMethod = "manual",
            program = result.program,
            cgpa = result.cgpa,
            earnedCredits = result.earnedCredits,
            requiredCredits = result.requiredCredits,
            eligible = result.eligible,
            createdAt = Instant.now().toString()
        )

        return RunRecord(summary = summary, result = result)
    }

    fun csvToManualText(csvText: String): String {
        val lines = csvText.lines().map { it.trim() }.filter { it.isNotBlank() }
        if (lines.isEmpty()) return ""

        val startIndex = if (lines.first().contains("Course_Code", ignoreCase = true)) 1 else 0
        val out = mutableListOf<String>()
        for (i in startIndex until lines.size) {
            val p = lines[i].split(",").map { it.trim() }
            if (p.size < 4) continue
            val code = p[0].uppercase()
            val credits = p[1]
            val grade = p[2].uppercase()
            val semester = p[3].replace("  ", " ").trim()
            out.add("$code, $credits, $grade, $semester")
        }
        return out.joinToString("\n")
    }

    fun ocrToManualText(ocrText: String): String {
        val re = Regex(
            pattern = "([A-Za-z]{2,4}\\d{3}[A-Za-z]?)\\s*[, ]\\s*(\\d+(?:\\.\\d+)?)\\s*[, ]\\s*(A-|A|B\\+|B|B-|C\\+|C|C-|D\\+|D|F|W)\\s*[, ]\\s*(Spring|Summer|Fall)\\s*[-/ ]?\\s*(\\d{4})",
            option = RegexOption.IGNORE_CASE,
        )

        val rows = mutableListOf<String>()
        re.findAll(ocrText).forEach { m ->
            val code = m.groupValues[1].uppercase().replace(" ", "")
            val credits = m.groupValues[2]
            val grade = m.groupValues[3].uppercase()
            val season = m.groupValues[4].lowercase().replaceFirstChar { it.uppercase() }
            val year = m.groupValues[5]
            rows.add("$code, $credits, $grade, $season $year")
        }
        return rows.distinct().joinToString("\n")
    }

    fun ocrToManualWithGuardrails(ocrText: String, sourceLabel: String = "Image"): OcrImportResult {
        val raw = normalizeOcrText(ocrText)
        val parsedRows = parseRowsFromLooseText(raw)
        val manual = parsedRows.joinToString("\n") { "${it.courseCode}, ${it.credits}, ${it.grade}, ${it.semester}" }

        val signal = analyzeTextSignal(raw)
        val confidence = when {
            signal.score >= 26 -> "HIGH"
            signal.score >= 10 -> "MEDIUM"
            else -> "LOW"
        }

        val blocked = parsedRows.size < 2 || (confidence == "LOW" && parsedRows.size < 3)
        val warning = when {
            confidence == "HIGH" -> null
            confidence == "MEDIUM" -> "$sourceLabel OCR quality is moderate. Detected rows: ${parsedRows.size}. Please review before analysis."
            else -> "Low OCR confidence for $sourceLabel. Detected rows: ${parsedRows.size}. Result may be inaccurate."
        }

        val previewHeader = "[OCR confidence: $confidence | score: ${signal.score} | pages: [1]/1]"
        val previewBody = raw.lines().take(220).joinToString("\n")
        val preview = "$previewHeader\n\n$previewBody"

        return OcrImportResult(
            manualText = manual,
            confidence = confidence,
            score = signal.score,
            detectedRows = parsedRows.size,
            blocked = blocked,
            warning = warning,
            preview = preview
        )
    }

    private data class TextSignal(
        val score: Int,
        val courseCodes: Int,
        val semesters: Int,
        val rowLike: Int,
        val disclaimerHits: Int,
    )

    private fun analyzeTextSignal(text: String): TextSignal {
        val source = text
        val lowered = source.lowercase()
        val courseCodes = Regex("\\b[A-Z]{2,4}\\d{3}[A-Z]?\\b", RegexOption.IGNORE_CASE).findAll(source).count()
        val semesters = Regex("\\b(Spring|Summer|Fall)\\s+\\d{4}\\b", RegexOption.IGNORE_CASE).findAll(source).count()
        val rowLike = Regex(
            "([A-Za-z]{2,4}\\d{3}[A-Za-z]?).{0,42}(A-|A|B\\+|B|B-|C\\+|C|C-|D\\+|D|F|W).{0,22}(Spring|Summer|Fall)\\s+\\d{4}",
            RegexOption.IGNORE_CASE
        ).findAll(source).count()
        val disclaimerHits = disclaimerTerms.count { lowered.contains(it) }

        val score = (rowLike * 8) + (courseCodes.coerceAtMost(30) * 2) + (semesters * 3) - (disclaimerHits * 3)
        return TextSignal(
            score = score,
            courseCodes = courseCodes,
            semesters = semesters,
            rowLike = rowLike,
            disclaimerHits = disclaimerHits
        )
    }

    private fun normalizeOcrText(raw: String): String {
        var text = raw
        val replacements = mapOf(
            "EEEI" to "EEE1",
            "MATII" to "MAT11",
            " BT " to " B+ ",
            " B5 " to " B ",
            " A> " to " A- ",
            " B00" to " B 0.0"
        )
        replacements.forEach { (old, new) ->
            text = text.replace(old, new)
        }
        return text
    }

    private fun parseRowsFromLooseText(rawText: String): List<CourseRow> {
        val csvRe = Regex(
            "([A-Za-z]{2,4}\\d{3}[A-Za-z]?)\\s*[,\\t]\\s*(\\d+(?:\\.\\d+)?)\\s*[,\\t]\\s*(A-|A|B\\+|B|B-|C\\+|C|C-|D\\+|D|F|W)\\s*[,\\t]\\s*(Spring|Summer|Fall)\\s*[-/ ]?\\s*(\\d{4})",
            RegexOption.IGNORE_CASE
        )
        val wsRe = Regex(
            "([A-Za-z]{2,4}\\d{3}[A-Za-z]?)\\s+(\\d+(?:\\.\\d+)?)\\s+(A-|A|B\\+|B|B-|C\\+|C|C-|D\\+|D|F|W)\\s+(Spring|Summer|Fall)\\s*[-/ ]?\\s*(\\d{4})",
            RegexOption.IGNORE_CASE
        )

        val rows = mutableListOf<CourseRow>()
        val seen = linkedSetOf<String>()

        fun add(codeRaw: String, creditsRaw: String, gradeRaw: String, seasonRaw: String, yearRaw: String) {
            val code = codeRaw.uppercase().replace(" ", "")
            if (!Regex("^[A-Z]{2,4}\\d{3}[A-Z]?$").matches(code)) return
            val credits = creditsRaw.toDoubleOrNull()?.toInt() ?: return
            val grade = normalizeGrade(gradeRaw)
            if (grade !in validGrades) return
            if (credits < 0 || credits > 6) return
            val season = seasonRaw.lowercase().replaceFirstChar { it.uppercase() }
            val semester = "$season $yearRaw"
            if (!Regex("^(Spring|Summer|Fall)\\s+\\d{4}$").matches(semester)) return
            val key = "$code|$credits|$grade|$semester"
            if (seen.add(key)) {
                rows.add(CourseRow(code, credits, grade, semester))
            }
        }

        csvRe.findAll(rawText).forEach {
            add(
                it.groupValues[1],
                it.groupValues[2],
                it.groupValues[3],
                it.groupValues[4],
                it.groupValues[5]
            )
        }
        if (rows.isNotEmpty()) return rows

        wsRe.findAll(rawText).forEach {
            add(
                it.groupValues[1],
                it.groupValues[2],
                it.groupValues[3],
                it.groupValues[4],
                it.groupValues[5]
            )
        }
        return rows
    }

    private fun normalizeGrade(raw: String): String {
        val grade = raw.uppercase().trim()
        return when (grade) {
            "BT", "8+" -> "B+"
            "A>" -> "A-"
            "B00", "BOO" -> "B"
            "AC", "AS", "AB" -> "A"
            else -> grade
        }
    }

    private fun parseManual(text: String): List<CourseRow> {
        val lines = text.lines().map { it.trim() }.filter { it.isNotBlank() }
        if (lines.isEmpty()) {
            throw IllegalArgumentException("Manual input is empty")
        }
        return lines.mapIndexed { idx, line ->
            val p = line.split(",").map { it.trim() }
            if (p.size != 4) {
                throw IllegalArgumentException("Line ${idx + 1} must be: Course_Code, Credits, Grade, Semester")
            }
            val code = p[0].uppercase()
            val credits = p[1].toIntOrNull() ?: throw IllegalArgumentException("Invalid credits at line ${idx + 1}")
            val grade = p[2].uppercase()
            val semester = p[3]
            if (!Regex("^[A-Z]{2,4}\\d{3}[A-Z]?$").matches(code)) {
                throw IllegalArgumentException("Invalid course code at line ${idx + 1}: $code")
            }
            if (credits < 0 || credits > 6) {
                throw IllegalArgumentException("Credits must be 0..6 at line ${idx + 1}")
            }
            if (grade !in validGrades) {
                throw IllegalArgumentException("Invalid grade at line ${idx + 1}: $grade")
            }
            if (!Regex("^(Spring|Summer|Fall)\\s+\\d{4}$", RegexOption.IGNORE_CASE).matches(semester)) {
                throw IllegalArgumentException("Semester must be like 'Spring 2024' at line ${idx + 1}")
            }
            CourseRow(code, credits, grade, normalizeSemester(semester))
        }
    }

    private fun normalizeSemester(raw: String): String {
        val p = raw.trim().split(" ")
        val season = p[0].lowercase().replaceFirstChar { it.uppercase() }
        return "$season ${p[1]}"
    }

    private fun semesterNumber(semester: String): Int {
        val order = mapOf("SPRING" to 0, "SUMMER" to 1, "FALL" to 2)
        val p = semester.split(" ")
        val year = p.getOrNull(1)?.toIntOrNull() ?: 0
        return (year * 10) + (order[p.firstOrNull()?.uppercase()] ?: 9)
    }

    private fun latestRows(rows: List<CourseRow>): Map<String, CourseRow> {
        val sorted = rows.sortedBy { semesterNumber(it.semester) }
        val out = linkedMapOf<String, CourseRow>()
        sorted.forEach { out[it.courseCode] = it }
        return out
    }

    private fun retakeMap(rows: List<CourseRow>): Map<String, List<CourseRow>> {
        val out = mutableMapOf<String, MutableList<CourseRow>>()
        rows.forEach { row ->
            out.getOrPut(row.courseCode) { mutableListOf() }.add(row)
        }
        return out
    }

    private fun earnedCredits(latest: Map<String, CourseRow>, waived: List<String>): Int {
        var total = 0
        latest.values.forEach { row ->
            total += when {
                row.courseCode in waived -> row.credits
                row.grade in listOf("F", "W") -> 0
                else -> row.credits
            }
        }
        return total
    }

    private fun calculateCgpa(latest: Map<String, CourseRow>, waived: List<String>): Double {
        var qp = 0.0
        var ch = 0
        latest.values.forEach { row ->
            if (row.courseCode in waived) return@forEach
            if (row.grade == "W") return@forEach
            if (row.credits == 0) return@forEach
            val gp = gradePoints[row.grade] ?: 0.0
            qp += gp * row.credits
            ch += row.credits
        }
        return if (ch == 0) 0.0 else qp / ch
    }

    private fun runAudit(latest: Map<String, CourseRow>, rule: ProgramRule, waived: List<String>): List<AuditRow> {
        val out = mutableListOf<AuditRow>()
        rule.requirements.forEach { (category, courses) ->
            courses.forEach { c ->
                when {
                    c in waived -> out.add(AuditRow(category, c, "WAIVED", "Requirement waived"))
                    c !in latest -> out.add(AuditRow(category, c, "MISSING", "Not found in transcript"))
                    latest[c]?.grade == "W" -> out.add(AuditRow(category, c, "INCOMPLETE", "Withdrawn in ${latest[c]?.semester}"))
                    latest[c]?.grade == "F" -> out.add(AuditRow(category, c, "FAILED", "Failed in ${latest[c]?.semester}"))
                    else -> out.add(AuditRow(category, c, "COMPLETED", "${latest[c]?.grade} (${latest[c]?.semester})"))
                }
            }
        }
        return out
    }

    private fun buildCgpaDetails(latest: Map<String, CourseRow>, waived: List<String>): List<CgpaDetailRow> {
        return latest.values.sortedBy { it.courseCode }.map { row ->
            when {
                row.courseCode in waived -> CgpaDetailRow(row.courseCode, row.credits, row.grade, false, "Waived")
                row.grade == "W" -> CgpaDetailRow(row.courseCode, row.credits, row.grade, false, "Withdrawal")
                row.credits == 0 -> CgpaDetailRow(row.courseCode, row.credits, row.grade, false, "0-credit")
                else -> CgpaDetailRow(row.courseCode, row.credits, row.grade, true, "")
            }
        }
    }
}
