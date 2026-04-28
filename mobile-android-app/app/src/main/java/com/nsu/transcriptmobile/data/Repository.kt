package com.nsu.transcriptmobile.data

import android.content.Context
import android.net.Uri
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.time.Instant

class Repository(context: Context) {
    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("nsu_transcript_mobile", Context.MODE_PRIVATE)
    private val gson = Gson()
    private val api = ApiClient.service
    private val keyToken = "access_token"
    private val keyUserId = "online_user_id"
    private val keyUserEmail = "online_user_email"
    private val keyUserName = "online_user_name"

    private fun readRuns(): MutableList<RunRecord> {
        val raw = prefs.getString("runs_json", "[]") ?: "[]"
        val type = object : TypeToken<MutableList<RunRecord>>() {}.type
        return gson.fromJson(raw, type) ?: mutableListOf()
    }

    private fun writeRuns(runs: List<RunRecord>) {
        prefs.edit().putString("runs_json", gson.toJson(runs)).apply()
    }

    fun healthMessage(): String = "Offline engine ready"

    fun getSavedAccessToken(): String = prefs.getString(keyToken, "") ?: ""

    fun getSavedOnlineUserId(): Int? {
        val raw = prefs.getInt(keyUserId, -1)
        return if (raw > 0) raw else null
    }

    fun getSavedOnlineUserLabel(): String {
        val name = prefs.getString(keyUserName, "") ?: ""
        val email = prefs.getString(keyUserEmail, "") ?: ""
        return when {
            name.isNotBlank() && email.isNotBlank() -> "$name ($email)"
            name.isNotBlank() -> name
            email.isNotBlank() -> email
            else -> ""
        }
    }

    suspend fun mobileGoogleAuth(idToken: String): MobileAuthUser {
        val res = api.mobileGoogleAuth(MobileGoogleAuthRequest(id_token = idToken))
        if (!res.ok || res.access_token.isNullOrBlank() || res.user == null) {
            throw IllegalStateException(res.error ?: "Google auth failed")
        }
        prefs.edit()
            .putString(keyToken, res.access_token)
            .putInt(keyUserId, res.user.id)
            .putString(keyUserEmail, res.user.email)
            .putString(keyUserName, res.user.name)
            .apply()
        return res.user
    }

    suspend fun mobileEmailAuth(email: String, name: String? = null): MobileAuthUser {
        val res = api.mobileEmailAuth(MobileEmailAuthRequest(email = email.trim(), name = name))
        if (!res.ok || res.access_token.isNullOrBlank() || res.user == null) {
            throw IllegalStateException(res.error ?: "Email auth failed")
        }
        prefs.edit()
            .putString(keyToken, res.access_token)
            .putInt(keyUserId, res.user.id)
            .putString(keyUserEmail, res.user.email)
            .putString(keyUserName, res.user.name)
            .apply()
        return res.user
    }

    suspend fun mobileAuthMe(): MobileAuthUser {
        val token = getSavedAccessToken()
        if (token.isBlank()) throw IllegalStateException("Sign in required")
        val me = api.mobileAuthMe("Bearer $token")
        if (!me.ok || me.user == null) throw IllegalStateException(me.error ?: "Session invalid")
        prefs.edit()
            .putInt(keyUserId, me.user.id)
            .putString(keyUserEmail, me.user.email)
            .putString(keyUserName, me.user.name)
            .apply()
        return me.user
    }

    fun clearOnlineSession() {
        prefs.edit()
            .remove(keyToken)
            .remove(keyUserId)
            .remove(keyUserEmail)
            .remove(keyUserName)
            .apply()
    }

    private fun authHeader(): String {
        val token = getSavedAccessToken()
        if (token.isBlank()) throw IllegalStateException("Sign in required for online mode")
        return "Bearer $token"
    }

    suspend fun onlineHealth(): String {
        val h = api.health()
        if (!h.ok) return "Backend not ready"
        return try {
            val me = mobileAuthMe()
            "Backend reachable - signed in as ${me.email}"
        } catch (_: Exception) {
            "Backend reachable - sign in required"
        }
    }

    fun analyzeManual(userId: Int, program: String, manualText: String, waived: List<String> = emptyList()): RunRecord {
        val runs = readRuns()
        val nextId = (runs.maxOfOrNull { it.summary.id } ?: 0) + 1
        val record = AnalysisEngine.analyzeManual(
            userId = userId,
            program = program,
            manualText = manualText,
            waivedInput = waived,
            nextRunId = nextId
        )
        runs.add(record)
        writeRuns(runs)
        return record
    }

    fun history(userId: Int): List<HistoryItem> {
        return readRuns()
            .map { it.summary }
            .filter { userId <= 0 || it.userId == userId }
            .sortedByDescending { it.id }
    }

    fun runById(runId: Int): RunRecord? = readRuns().firstOrNull { it.summary.id == runId }

    fun runDetailsOffline(runId: Int): RunDetails? {
        val run = runById(runId) ?: return null
        return RunDetails(
            run = run.summary,
            latestRows = run.result.latestRows,
            issues = run.result.issues,
            waived = run.result.waived,
            courseAudit = run.result.courseAudit,
            cgpaDetails = run.result.cgpaDetails,
            retakeSummary = run.result.retakeSummary,
        )
    }

    suspend fun analyzeOnline(userId: Int, program: String, manualText: String, waived: List<String>): RunRecord {
        val res = api.analyzeMobile(
            authorization = authHeader(),
            MobileAnalyzeRequest(
                input_method = "manual",
                program = program,
                user_id = userId,
                waived = waived,
                manual_text = manualText,
            )
        )
        if (!res.ok || res.result == null) {
            throw IllegalStateException(res.error ?: "Online analyze failed")
        }

        val payload = res.result
        val latest = payload.latest_rows.mapNotNull { m ->
            val code = (m["Course_Code"] ?: m["course_code"])?.toString() ?: return@mapNotNull null
            val credits = (m["Credits"] ?: m["credits"])?.toString()?.toDoubleOrNull()?.toInt() ?: 0
            val grade = (m["Grade"] ?: m["grade"])?.toString() ?: "-"
            val semester = (m["Semester"] ?: m["semester"])?.toString() ?: "-"
            CourseRow(code, credits, grade, semester)
        }

        val result = AnalyzeResult(
            inputMethod = payload.input_method,
            program = payload.program,
            cgpa = payload.cgpa,
            earnedCredits = payload.earned_credits,
            requiredCredits = payload.required_credits,
            remainingCredits = payload.remaining_credits,
            eligible = payload.eligible,
            waived = payload.waived,
            issues = payload.issues,
            latestRows = latest,
            courseAudit = emptyList(),
        )

        val summary = HistoryItem(
            id = res.run_id ?: ((readRuns().maxOfOrNull { it.summary.id } ?: 0) + 1),
            userId = userId,
            inputMethod = payload.input_method,
            program = payload.program,
            cgpa = payload.cgpa,
            earnedCredits = payload.earned_credits,
            requiredCredits = payload.required_credits,
            eligible = payload.eligible,
            createdAt = Instant.now().toString(),
        )
        return RunRecord(summary, result)
    }

    suspend fun historyOnline(userId: Int): List<HistoryItem> {
        val res = api.historyMobile(authHeader())
        if (!res.ok) {
            throw IllegalStateException(res.error ?: "Online history failed")
        }
        return res.runs.map {
            HistoryItem(
                id = it.id,
                userId = userId,
                inputMethod = it.input_method,
                program = it.program,
                cgpa = it.cgpa,
                earnedCredits = it.earned_credits,
                requiredCredits = it.required_credits,
                eligible = it.eligible,
                createdAt = it.created_at,
            )
        }
    }

    suspend fun runDetailsOnline(userId: Int, runId: Int): RunDetails {
        val res = ApiClient.service.historyMobileDetails(authorization = authHeader(), runId = runId)
        if (!res.ok || res.run == null) throw IllegalStateException("Run not found")
        val hit = res.run
        val latestRows = res.latest_rows.mapNotNull { m ->
            val code = (m["Course_Code"] ?: m["course_code"])?.toString() ?: return@mapNotNull null
            val credits = (m["Credits"] ?: m["credits"])?.toString()?.toDoubleOrNull()?.toInt() ?: 0
            val grade = (m["Grade"] ?: m["grade"])?.toString() ?: "-"
            val semester = (m["Semester"] ?: m["semester"])?.toString() ?: "-"
            CourseRow(code, credits, grade, semester)
        }
        val cgpaDetails = res.cgpa_details.mapNotNull { m ->
            val course = (m["course"] ?: m["Course"])?.toString() ?: return@mapNotNull null
            val credits = (m["credits"] ?: m["Credits"])?.toString()?.toDoubleOrNull()?.toInt() ?: 0
            val grade = (m["grade"] ?: m["Grade"])?.toString() ?: "-"
            val inCgpa = ((m["in_cgpa"] ?: m["In CGPA"])?.toString() ?: "").equals("Yes", true)
            val reason = (m["reason"] ?: m["Reason"])?.toString() ?: ""
            CgpaDetailRow(course, credits, grade, inCgpa, reason)
        }
        return RunDetails(
            run = HistoryItem(
                id = hit.id,
                userId = userId,
                inputMethod = hit.input_method,
                program = hit.program,
                cgpa = hit.cgpa,
                earnedCredits = hit.earned_credits,
                requiredCredits = hit.required_credits,
                eligible = hit.eligible,
                createdAt = hit.created_at,
            ),
            latestRows = latestRows,
            issues = res.issues,
            waived = res.waived,
            courseAudit = emptyList(),
            cgpaDetails = cgpaDetails,
            retakeSummary = emptyList(),
        )
    }

    suspend fun chatOnline(userId: Int, message: String): ChatMessage {
        val res = api.chat(
            authorization = authHeader(),
            ChatRequest(
                message = message,
                user_id = userId.toString(),
                context = mapOf("source" to "android"),
            )
        )
        val chips = res.tool_trace.map { "${it.tool} | ${it.status} | ${it.latency_ms}ms" }.toMutableList()
        if (res.fallback_used) {
            chips.add("fallback | used | 0ms")
        }
        if (res.request_id.isNotBlank()) {
            chips.add("request_id | ${res.request_id} | 0ms")
        }
        return ChatMessage(
            role = "assistant",
            text = res.reply,
            trace = chips,
        )
    }

    suspend fun ocrExtractOnline(uri: Uri, inputMethod: String, sourceLabel: String = "Transcript"): OcrImportResult {
        val auth = authHeader()
        val method = inputMethod.lowercase().trim()
        if (method != "pdf" && method != "image") {
            throw IllegalArgumentException("inputMethod must be pdf or image")
        }

        val resolver = appContext.contentResolver
        val fileName = resolver.query(uri, null, null, null, null)?.use { cursor ->
            val nameIdx = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
            if (cursor.moveToFirst() && nameIdx >= 0) cursor.getString(nameIdx) else null
        } ?: if (method == "pdf") "upload.pdf" else "upload.jpg"

        val mime = resolver.getType(uri) ?: if (method == "pdf") "application/pdf" else "image/*"
        val suffix = if (method == "pdf") ".pdf" else ".img"
        val tmp = File.createTempFile("ocr_upload_", suffix, appContext.cacheDir)
        resolver.openInputStream(uri)?.use { input ->
            tmp.outputStream().use { output ->
                input.copyTo(output)
            }
        } ?: throw IllegalStateException("Could not read selected file")

        try {
            val fileBody = tmp.asRequestBody(mime.toMediaType())
            val partName = if (method == "pdf") "pdf_file" else "image_file"
            val filePart = MultipartBody.Part.createFormData(partName, fileName, fileBody)
            val methodPart = method.toRequestBody("text/plain".toMediaType())
            val sourcePart = sourceLabel.toRequestBody("text/plain".toMediaType())

            val res = api.ocrExtract(
                authorization = auth,
                inputMethod = methodPart,
                sourceLabel = sourcePart,
                filePart = filePart,
            )

            if (!res.ok) {
                throw IllegalStateException(res.error ?: "OCR extraction failed")
            }

            return OcrImportResult(
                manualText = res.manual_text ?: "",
                confidence = res.confidence ?: "LOW",
                score = res.score ?: 0,
                detectedRows = res.detected_rows ?: 0,
                blocked = res.blocked ?: true,
                warning = res.warning,
                preview = res.preview ?: "",
            )
        } finally {
            tmp.delete()
        }
    }
}
