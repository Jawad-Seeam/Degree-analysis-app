package com.nsu.transcriptmobile.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

data class MobileGoogleAuthRequest(
    val id_token: String,
)

data class MobileAuthUser(
    val id: Int,
    val email: String,
    val name: String,
    val avatar_url: String? = null,
)

data class MobileGoogleAuthResponse(
    val ok: Boolean,
    val access_token: String? = null,
    val token_type: String? = null,
    val expires_in: Int? = null,
    val user: MobileAuthUser? = null,
    val error: String? = null,
)

data class MobileEmailAuthRequest(
    val email: String,
    val name: String? = null,
)

data class MobileAuthMeResponse(
    val ok: Boolean,
    val user: MobileAuthUser? = null,
    val error: String? = null,
)

data class MobileAnalyzeRequest(
    val input_method: String,
    val program: String,
    val user_id: Int,
    val waived: List<String> = emptyList(),
    val manual_text: String? = null,
    val csv_text: String? = null,
)

data class MobileAnalyzeResponse(
    val ok: Boolean,
    val run_id: Int?,
    val result: MobileAnalyzePayload?,
    val error: String?,
)

data class MobileAnalyzePayload(
    val input_method: String,
    val program: String,
    val cgpa: Double,
    val earned_credits: Int,
    val required_credits: Int,
    val remaining_credits: Int,
    val eligible: Boolean,
    val waived: List<String>,
    val issues: List<String>,
    val latest_rows: List<Map<String, Any?>>,
)

data class MobileHistoryResponse(
    val ok: Boolean,
    val count: Int,
    val runs: List<MobileHistoryItem>,
    val error: String?,
)

data class MobileHistoryItem(
    val id: Int,
    val input_method: String,
    val program: String,
    val cgpa: Double,
    val earned_credits: Int,
    val required_credits: Int,
    val eligible: Boolean,
    val created_at: String,
)

data class HealthResponse(
    val ok: Boolean,
    val service: String,
    val timestamp: String,
    val authenticated: Boolean,
)

data class ChatRequest(
    val message: String,
    val user_id: String,
    val context: Map<String, Any?>,
)

data class ChatTrace(
    val tool: String,
    val status: String,
    val latency_ms: Int,
)

data class ChatResponse(
    val reply: String,
    val tool_trace: List<ChatTrace> = emptyList(),
    val request_id: String,
    val fallback_used: Boolean,
)

data class MobileHistoryDetailsResponse(
    val ok: Boolean,
    val run: MobileHistoryItem?,
    val waived: List<String> = emptyList(),
    val issues: List<String> = emptyList(),
    val latest_rows: List<Map<String, Any?>> = emptyList(),
    val cgpa_details: List<Map<String, Any?>> = emptyList(),
)

data class OcrParseRequest(
    val raw_text: String,
    val source_label: String,
)

data class OcrParseResponse(
    val ok: Boolean,
    val manual_text: String? = null,
    val confidence: String? = null,
    val score: Int? = null,
    val detected_rows: Int? = null,
    val blocked: Boolean? = null,
    val warning: String? = null,
    val preview: String? = null,
    val error: String? = null,
)

interface ApiService {
    @POST("/api/mobile/auth/google")
    suspend fun mobileGoogleAuth(@Body request: MobileGoogleAuthRequest): MobileGoogleAuthResponse

    @POST("/api/mobile/auth/email")
    suspend fun mobileEmailAuth(@Body request: MobileEmailAuthRequest): MobileGoogleAuthResponse

    @GET("/api/mobile/auth/me")
    suspend fun mobileAuthMe(@Header("Authorization") authorization: String): MobileAuthMeResponse

    @GET("/api/health")
    suspend fun health(): HealthResponse

    @POST("/api/mobile/analyze")
    suspend fun analyzeMobile(
        @Header("Authorization") authorization: String,
        @Body request: MobileAnalyzeRequest,
    ): MobileAnalyzeResponse

    @GET("/api/mobile/history")
    suspend fun historyMobile(@Header("Authorization") authorization: String): MobileHistoryResponse

    @GET("/api/mobile/history/{run_id}")
    suspend fun historyMobileDetails(
        @Header("Authorization") authorization: String,
        @Path("run_id") runId: Int,
    ): MobileHistoryDetailsResponse

    @POST("/api/ai/chat")
    suspend fun chat(
        @Header("Authorization") authorization: String,
        @Body request: ChatRequest,
    ): ChatResponse

    @POST("/api/ocr/parse")
    suspend fun ocrParse(@Body request: OcrParseRequest): OcrParseResponse
}
