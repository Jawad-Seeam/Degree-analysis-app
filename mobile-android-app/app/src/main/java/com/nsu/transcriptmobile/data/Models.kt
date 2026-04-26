package com.nsu.transcriptmobile.data

data class CourseRow(
    val courseCode: String,
    val credits: Int,
    val grade: String,
    val semester: String
)

data class AnalyzeResult(
    val inputMethod: String,
    val program: String,
    val cgpa: Double,
    val earnedCredits: Int,
    val requiredCredits: Int,
    val remainingCredits: Int,
    val eligible: Boolean,
    val waived: List<String>,
    val issues: List<String>,
    val latestRows: List<CourseRow>,
    val courseAudit: List<AuditRow>,
    val cgpaDetails: List<CgpaDetailRow> = emptyList(),
    val retakeSummary: List<RetakeSummary> = emptyList(),
)

data class AuditRow(
    val category: String,
    val course: String,
    val status: String,
    val details: String
)

data class HistoryItem(
    val id: Int,
    val userId: Int,
    val inputMethod: String,
    val program: String,
    val cgpa: Double,
    val earnedCredits: Int,
    val requiredCredits: Int,
    val eligible: Boolean,
    val createdAt: String
)

data class RunRecord(
    val summary: HistoryItem,
    val result: AnalyzeResult
)

data class CgpaDetailRow(
    val course: String,
    val credits: Int,
    val grade: String,
    val inCgpa: Boolean,
    val reason: String,
)

data class RetakeSummary(
    val course: String,
    val attempts: List<String>,
)

data class RunDetails(
    val run: HistoryItem,
    val latestRows: List<CourseRow>,
    val issues: List<String>,
    val waived: List<String>,
    val courseAudit: List<AuditRow>,
    val cgpaDetails: List<CgpaDetailRow>,
    val retakeSummary: List<RetakeSummary>,
)

enum class AppMode { OFFLINE, ONLINE }

data class ChatMessage(
    val role: String,
    val text: String,
    val trace: List<String> = emptyList(),
)

data class OcrImportResult(
    val manualText: String,
    val confidence: String,
    val score: Int,
    val detectedRows: Int,
    val blocked: Boolean,
    val warning: String?,
    val preview: String,
)
