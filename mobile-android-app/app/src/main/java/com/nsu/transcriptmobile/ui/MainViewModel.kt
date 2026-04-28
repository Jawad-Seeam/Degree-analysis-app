package com.nsu.transcriptmobile.ui

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.nsu.transcriptmobile.data.AnalyzeResult
import com.nsu.transcriptmobile.data.AnalysisEngine
import com.nsu.transcriptmobile.data.AppMode
import com.nsu.transcriptmobile.data.ChatMessage
import com.nsu.transcriptmobile.data.HistoryItem
import com.nsu.transcriptmobile.data.Repository
import com.nsu.transcriptmobile.data.RunDetails
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import com.nsu.transcriptmobile.data.OcrImportResult
import kotlinx.coroutines.tasks.await

data class MainUiState(
    val loading: Boolean = false,
    val mode: AppMode = AppMode.OFFLINE,
    val onlineSignedIn: Boolean = false,
    val onlineUserLabel: String = "",
    val healthOk: Boolean = true,
    val healthMessage: String = "Offline engine ready",
    val userId: Int = 1,
    val program: String = "CSE",
    val manualText: String = "CSE115, 4, A-, Spring 2024\nMAT116, 3, B+, Fall 2023",
    val waivedText: String = "",
    val ocrPreview: String = "",
    val ocrConfidence: String = "",
    val ocrScore: Int = 0,
    val ocrDetectedRows: Int = 0,
    val ocrWarning: String? = null,
    val ocrBlocked: Boolean = false,
    val latestResult: AnalyzeResult? = null,
    val history: List<HistoryItem> = emptyList(),
    val selectedRunId: Int? = null,
    val runDetails: RunDetails? = null,
    val chat: List<ChatMessage> = listOf(ChatMessage("assistant", "Hi! Ask a question, e.g. lookup CSE115")),
    val error: String? = null,
    val info: String? = null,
)

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val repository = Repository(app.applicationContext)

    var state: MainUiState = MainUiState()
        private set

    init {
        val uid = repository.getSavedOnlineUserId()
        state = state.copy(
            onlineSignedIn = !repository.getSavedAccessToken().isBlank() && uid != null,
            onlineUserLabel = repository.getSavedOnlineUserLabel(),
            userId = uid ?: state.userId,
        )
    }

    fun setMode(mode: AppMode, onUpdate: (MainUiState) -> Unit) {
        state = state.copy(mode = mode)
        onUpdate(state)
        checkHealth(onUpdate)
    }

    fun completeGoogleAuth(idToken: String, onUpdate: (MainUiState) -> Unit) {
        state = state.copy(loading = true, error = null, info = null)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val user = repository.mobileGoogleAuth(idToken)
                state = state.copy(
                    loading = false,
                    onlineSignedIn = true,
                    onlineUserLabel = "${user.name} (${user.email})",
                    userId = user.id,
                    info = "Signed in as ${user.email}"
                )
            } catch (e: Exception) {
                state = state.copy(loading = false, onlineSignedIn = false, error = e.message ?: "Google sign in failed")
            }
            onUpdate(state)
        }
    }

    fun completeEmailAuth(email: String, name: String, onUpdate: (MainUiState) -> Unit) {
        state = state.copy(loading = true, error = null, info = null)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val user = repository.mobileEmailAuth(email = email, name = name)
                state = state.copy(
                    loading = false,
                    onlineSignedIn = true,
                    onlineUserLabel = "${user.name} (${user.email})",
                    userId = user.id,
                    info = "Signed in as ${user.email}",
                )
            } catch (e: Exception) {
                state = state.copy(loading = false, onlineSignedIn = false, error = e.message ?: "Email sign in failed")
            }
            onUpdate(state)
        }
    }

    fun signOutOnline(onUpdate: (MainUiState) -> Unit) {
        repository.clearOnlineSession()
        state = state.copy(onlineSignedIn = false, onlineUserLabel = "", info = "Signed out from online mode")
        onUpdate(state)
    }

    fun updateUserId(value: String) {
        val parsed = value.toIntOrNull() ?: return
        state = state.copy(userId = parsed)
    }

    fun updateProgram(value: String) {
        state = state.copy(program = value.uppercase())
    }

    fun updateManualText(value: String) {
        state = state.copy(manualText = value, ocrBlocked = false)
    }

    fun updateWaivedText(value: String) {
        state = state.copy(waivedText = value)
    }

    fun clearMessage() {
        state = state.copy(error = null, info = null)
    }

    fun checkHealth(onUpdate: (MainUiState) -> Unit) {
        if (state.mode == AppMode.OFFLINE) {
            state = state.copy(healthOk = true, healthMessage = repository.healthMessage())
            onUpdate(state)
            return
        }

        state = state.copy(loading = true)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val msg = repository.onlineHealth()
                state = state.copy(loading = false, healthOk = true, healthMessage = msg)
            } catch (e: Exception) {
                state = state.copy(loading = false, healthOk = false, healthMessage = "Online unreachable", error = e.message)
            }
            onUpdate(state)
        }
    }

    fun analyze(onUpdate: (MainUiState) -> Unit) {
        state = state.copy(loading = true, error = null, info = null)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.Default) {
            try {
                val waived = state.waivedText
                    .split(",")
                    .map { it.trim().uppercase() }
                    .filter { it.isNotBlank() }

                val run = if (state.mode == AppMode.OFFLINE) {
                    repository.analyzeManual(
                        userId = state.userId,
                        program = state.program,
                        manualText = state.manualText,
                        waived = waived,
                    )
                } else {
                    repository.analyzeOnline(
                        userId = state.userId,
                        program = state.program,
                        manualText = state.manualText,
                        waived = waived,
                    )
                }

                state = state.copy(
                    loading = false,
                    latestResult = run.result,
                    ocrBlocked = false,
                    info = "Analysis complete. Run ID: ${run.summary.id}"
                )
            } catch (e: Exception) {
                state = state.copy(loading = false, error = e.message ?: "Analyze failed")
            }
            onUpdate(state)
        }
    }

    fun loadHistory(onUpdate: (MainUiState) -> Unit) {
        state = state.copy(loading = true, error = null)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.Default) {
            try {
                val list = if (state.mode == AppMode.OFFLINE) {
                    repository.history(state.userId)
                } else {
                    repository.historyOnline(state.userId)
                }
                state = state.copy(loading = false, history = list)
            } catch (e: Exception) {
                state = state.copy(loading = false, error = e.message ?: "History failed")
            }
            onUpdate(state)
        }
    }

    fun selectRun(runId: Int, onUpdate: (MainUiState) -> Unit) {
        state = state.copy(loading = true, selectedRunId = runId, runDetails = null, error = null)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val details = if (state.mode == AppMode.OFFLINE) {
                    repository.runDetailsOffline(runId) ?: throw IllegalStateException("Run not found")
                } else {
                    repository.runDetailsOnline(userId = state.userId, runId = runId)
                }
                state = state.copy(loading = false, runDetails = details)
            } catch (e: Exception) {
                state = state.copy(loading = false, error = e.message ?: "Failed to load run details")
            }
            onUpdate(state)
        }
    }

    fun clearRunSelection(onUpdate: (MainUiState) -> Unit) {
        state = state.copy(selectedRunId = null, runDetails = null)
        onUpdate(state)
    }

    fun sendChat(message: String, onUpdate: (MainUiState) -> Unit) {
        if (message.isBlank()) return
        val next = state.chat.toMutableList()
        next.add(ChatMessage("user", message))
        state = state.copy(chat = next, loading = true)
        onUpdate(state)

        viewModelScope.launch(Dispatchers.IO) {
            try {
                val reply = if (state.mode == AppMode.OFFLINE) {
                    ChatMessage(
                        role = "assistant",
                        text = "Offline mode: MCP chat requires online mode. Switch to Online for tool calls.",
                    )
                } else {
                    repository.chatOnline(state.userId, message)
                }
                state = state.copy(loading = false, chat = state.chat + reply)
            } catch (e: Exception) {
                state = state.copy(loading = false, chat = state.chat + ChatMessage("assistant", "Chat failed: ${e.message}"))
            }
            onUpdate(state)
        }
    }

    fun importCsv(uri: Uri, onUpdate: (MainUiState) -> Unit) {
        state = state.copy(loading = true, error = null, info = null)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val resolver = getApplication<Application>().contentResolver
                val csvText = resolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() } ?: ""
                val manual = AnalysisEngine.csvToManualText(csvText)
                if (manual.isBlank()) {
                    state = state.copy(loading = false, error = "Could not detect rows from CSV")
                } else {
                    state = state.copy(loading = false, manualText = manual, ocrBlocked = false, info = "CSV imported into editor")
                }
            } catch (e: Exception) {
                state = state.copy(loading = false, error = e.message ?: "CSV import failed")
            }
            onUpdate(state)
        }
    }

    fun importImageOcr(uri: Uri, onUpdate: (MainUiState) -> Unit) {
        state = state.copy(loading = true, error = null, info = null)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val ocr: OcrImportResult = if (state.mode == AppMode.ONLINE) {
                    repository.ocrExtractOnline(uri = uri, inputMethod = "image", sourceLabel = "Image")
                } else {
                    val app = getApplication<Application>()
                    val image = com.google.mlkit.vision.common.InputImage.fromFilePath(app, uri)
                    val recognizer = com.google.mlkit.vision.text.TextRecognition.getClient(
                        com.google.mlkit.vision.text.latin.TextRecognizerOptions.DEFAULT_OPTIONS
                    )
                    val text = recognizer.process(image).await().text
                    AnalysisEngine.ocrToManualWithGuardrails(text, sourceLabel = "Image")
                }
                if (ocr.manualText.isBlank()) {
                    state = state.copy(loading = false, error = "OCR did not find valid course rows")
                } else {
                    state = state.copy(
                        loading = false,
                        manualText = ocr.manualText,
                        ocrPreview = ocr.preview,
                        ocrConfidence = ocr.confidence,
                        ocrScore = ocr.score,
                        ocrDetectedRows = ocr.detectedRows,
                        ocrWarning = ocr.warning,
                        ocrBlocked = ocr.blocked,
                        info = if (ocr.blocked) {
                            "OCR imported, but analysis blocked. Please review and correct rows."
                        } else {
                            "OCR rows imported into editor"
                        }
                    )
                }
            } catch (e: Exception) {
                state = state.copy(loading = false, error = e.message ?: "OCR import failed")
            }
            onUpdate(state)
        }
    }

    fun importPdfOcr(uri: Uri, onUpdate: (MainUiState) -> Unit) {
        state = state.copy(loading = true, error = null, info = null)
        onUpdate(state)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val ocr: OcrImportResult = if (state.mode == AppMode.ONLINE) {
                    repository.ocrExtractOnline(uri = uri, inputMethod = "pdf", sourceLabel = "PDF")
                } else {
                    val app = getApplication<Application>()
                    val resolver = app.contentResolver
                    val pfd = resolver.openFileDescriptor(uri, "r") ?: throw IllegalStateException("Cannot open PDF")
                    val combined = StringBuilder()
                    pfd.use { descriptor ->
                        android.graphics.pdf.PdfRenderer(descriptor).use { renderer ->
                            val recognizer = com.google.mlkit.vision.text.TextRecognition.getClient(
                                com.google.mlkit.vision.text.latin.TextRecognizerOptions.DEFAULT_OPTIONS
                            )
                            val pageCount = renderer.pageCount
                            val maxPages = if (pageCount > 12) 12 else pageCount
                            for (i in 0 until maxPages) {
                                renderer.openPage(i).use { page ->
                                    val bitmap = android.graphics.Bitmap.createBitmap(
                                        page.width * 2,
                                        page.height * 2,
                                        android.graphics.Bitmap.Config.ARGB_8888
                                    )
                                    page.render(bitmap, null, null, android.graphics.pdf.PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                                    val image = com.google.mlkit.vision.common.InputImage.fromBitmap(bitmap, 0)
                                    val txt = recognizer.process(image).await().text
                                    if (txt.isNotBlank()) {
                                        combined.append(txt).append("\n\n")
                                    }
                                }
                            }
                        }
                    }
                    AnalysisEngine.ocrToManualWithGuardrails(combined.toString(), sourceLabel = "PDF")
                }
                if (ocr.manualText.isBlank()) {
                    state = state.copy(loading = false, error = "PDF OCR did not find valid course rows")
                } else {
                    state = state.copy(
                        loading = false,
                        manualText = ocr.manualText,
                        ocrPreview = ocr.preview,
                        ocrConfidence = ocr.confidence,
                        ocrScore = ocr.score,
                        ocrDetectedRows = ocr.detectedRows,
                        ocrWarning = ocr.warning,
                        ocrBlocked = ocr.blocked,
                        info = if (ocr.blocked) {
                            "PDF OCR imported, but analysis blocked. Please review and correct rows."
                        } else {
                            "PDF OCR rows imported into editor"
                        }
                    )
                }
            } catch (e: Exception) {
                state = state.copy(loading = false, error = e.message ?: "PDF OCR import failed")
            }
            onUpdate(state)
        }
    }
}
