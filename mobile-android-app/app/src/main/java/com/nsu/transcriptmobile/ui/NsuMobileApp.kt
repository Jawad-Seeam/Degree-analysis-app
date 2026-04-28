package com.nsu.transcriptmobile.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.TableChart
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.nsu.transcriptmobile.BuildConfig
import com.nsu.transcriptmobile.data.AppMode
import com.nsu.transcriptmobile.data.ChatMessage

private enum class ScreenTab { HOME, ANALYZE, CHAT, HISTORY, PROFILE }
private enum class AnalyzeInputMethod { MANUAL, CSV, PDF, IMAGE }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NsuMobileApp(vm: MainViewModel = viewModel()) {
    var tab by remember { mutableStateOf(ScreenTab.HOME) }
    var analyzeInput by remember { mutableStateOf(AnalyzeInputMethod.MANUAL) }
    var ui by remember { mutableStateOf(vm.state) }
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current

    val googleSignInLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val data = result.data
        if (data != null) {
            try {
                val task = GoogleSignIn.getSignedInAccountFromIntent(data)
                val account = task.result
                val idToken = account.idToken
                if (!idToken.isNullOrBlank()) {
                    vm.completeGoogleAuth(idToken) { ui = it }
                } else {
                    vm.clearMessage()
                    ui = vm.state.copy(error = "Google sign-in did not return ID token")
                }
            } catch (e: Exception) {
                vm.clearMessage()
                val message = if (e is com.google.android.gms.common.api.ApiException && e.statusCode == 10) {
                    "Google sign-in config mismatch (ApiException 10). Check Android OAuth client package/SHA-1 and GOOGLE_WEB_CLIENT_ID."
                } else {
                    e.message ?: "Google sign-in failed"
                }
                ui = vm.state.copy(error = message)
            }
        }
    }

    fun startGoogleSignIn() {
        if (BuildConfig.GOOGLE_WEB_CLIENT_ID.isBlank()) {
            vm.clearMessage()
            ui = vm.state.copy(error = "GOOGLE_WEB_CLIENT_ID is missing in Android build config")
            return
        }
        val options = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestEmail()
            .requestIdToken(BuildConfig.GOOGLE_WEB_CLIENT_ID)
            .build()
        val client = GoogleSignIn.getClient(context, options)
        client.signOut().addOnCompleteListener {
            googleSignInLauncher.launch(client.signInIntent)
        }
    }

    LaunchedEffect(Unit) {
        vm.checkHealth { ui = it }
    }

    LaunchedEffect(ui.error, ui.info) {
        ui.error?.let {
            snackbar.showSnackbar("Error: $it")
            vm.clearMessage()
            ui = vm.state
        }
        ui.info?.let {
            snackbar.showSnackbar(it)
            vm.clearMessage()
            ui = vm.state
        }
    }

    val bg = Brush.verticalGradient(colors = listOf(Color(0xFF060B1E), Color(0xFF0A1030), Color(0xFF081833)))

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar(
                modifier = Modifier
                    .navigationBarsPadding()
                    .padding(horizontal = 16.dp, vertical = 10.dp)
                    .clip(RoundedCornerShape(26.dp)),
                containerColor = Color(0xFF101B3E)
            ) {
                NavigationBarItem(
                    selected = tab == ScreenTab.HOME,
                    onClick = { tab = ScreenTab.HOME },
                    icon = { Icon(Icons.Default.Home, contentDescription = null) },
                    label = { Text("Home") }
                )
                NavigationBarItem(
                    selected = tab == ScreenTab.ANALYZE,
                    onClick = { tab = ScreenTab.ANALYZE },
                    icon = { Icon(Icons.Default.UploadFile, contentDescription = null) },
                    label = { Text("Analyze") }
                )
                NavigationBarItem(
                    selected = tab == ScreenTab.CHAT,
                    onClick = { tab = ScreenTab.CHAT },
                    icon = { Icon(Icons.Default.Chat, contentDescription = null) },
                    label = { Text("Chat") }
                )
                NavigationBarItem(
                    selected = tab == ScreenTab.HISTORY,
                    onClick = {
                        tab = ScreenTab.HISTORY
                        vm.loadHistory { ui = it }
                    },
                    icon = { Icon(Icons.Default.History, contentDescription = null) },
                    label = { Text("History") }
                )
                NavigationBarItem(
                    selected = tab == ScreenTab.PROFILE,
                    onClick = { tab = ScreenTab.PROFILE },
                    icon = { Icon(Icons.Default.Person, contentDescription = null) },
                    label = { Text("Profile") }
                )
            }
        },
        containerColor = Color.Transparent,
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(bg)
                .padding(padding)
        ) {
            when (tab) {
                ScreenTab.HOME -> HomeTab(
                    ui = ui,
                    onModeChange = { mode -> vm.setMode(mode) { ui = it } },
                    onGoogleSignIn = { startGoogleSignIn() },
                    onEmailSignIn = { email, name -> vm.completeEmailAuth(email, name) { ui = it } },
                    onGoogleSignOut = { vm.signOutOnline { ui = it } }
                )

                ScreenTab.ANALYZE -> AnalyzeTab(
                    ui = ui,
                    selectedInput = analyzeInput,
                    onSelectInput = {
                        analyzeInput = it
                        val method = when (it) {
                            AnalyzeInputMethod.MANUAL -> "manual"
                            AnalyzeInputMethod.CSV -> "csv"
                            AnalyzeInputMethod.PDF -> "manual"
                            AnalyzeInputMethod.IMAGE -> "manual"
                        }
                        vm.updateSelectedInputMethod(method)
                        ui = vm.state
                    },
                    onProgram = { vm.updateProgram(it); ui = vm.state },
                    onText = { vm.updateManualText(it); ui = vm.state },
                    onWaived = { vm.updateWaivedText(it); ui = vm.state },
                    onAnalyze = { vm.analyze { ui = it } },
                    onImportCsv = { uri -> vm.importCsv(uri) { ui = it } },
                    onImportPdf = { uri -> vm.importPdfOcr(uri) { ui = it } },
                    onImportImage = { uri -> vm.importImageOcr(uri) { ui = it } },
                )

                ScreenTab.CHAT -> ChatTab(
                    ui = ui,
                    onSend = { msg -> vm.sendChat(msg) { ui = it } }
                )

                ScreenTab.HISTORY -> HistoryTab(
                    ui = ui,
                    onRunClick = { runId -> vm.selectRun(runId) { ui = it } },
                    onCloseDetails = { vm.clearRunSelection { ui = it } }
                )
                ScreenTab.PROFILE -> ProfileTab(ui)
            }

            if (ui.loading) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color(0x99000000)),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator(color = Color(0xFF19D2C0))
                        Spacer(Modifier.height(10.dp))
                        Text("Working...", color = Color.White)
                    }
                }
            }
        }
    }
}

@Composable
private fun HomeTab(
    ui: MainUiState,
    onModeChange: (AppMode) -> Unit,
    onGoogleSignIn: () -> Unit,
    onEmailSignIn: (String, String) -> Unit,
    onGoogleSignOut: () -> Unit,
) {
    var emailInput by remember { mutableStateOf("") }
    var nameInput by remember { mutableStateOf("") }
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text(
                text = "North South University",
                style = MaterialTheme.typography.headlineMedium,
                color = Color.White,
                fontWeight = FontWeight.ExtraBold
            )
            Text(text = "Degree Audit Mobile", style = MaterialTheme.typography.titleMedium, color = Color(0xFF7BD7FF))
        }

        item {
            CardBlock {
                Text("Mode", color = Color(0xFFB9C9FF), fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { onModeChange(AppMode.OFFLINE) }) { Text("Offline") }
                    Button(onClick = { onModeChange(AppMode.ONLINE) }) { Text("Online") }
                }
                Spacer(Modifier.height(8.dp))
                AssistChip(
                    onClick = {},
                    label = { Text("Current: ${ui.mode.name}") },
                    colors = AssistChipDefaults.assistChipColors(containerColor = Color(0xFF123B36), labelColor = Color(0xFF7FFFD4))
                )
            }
        }

        item {
            CardBlock {
                Text("Google Auth (Online)", color = Color(0xFFB9C9FF), fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                if (ui.onlineSignedIn) {
                    Text("Signed in", color = Color(0xFF8EF2D9), fontWeight = FontWeight.SemiBold)
                    if (ui.onlineUserLabel.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(ui.onlineUserLabel, color = Color(0xFFC4D3FF))
                    }
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = onGoogleSignOut) { Text("Sign out") }
                } else {
                    Text("Not signed in", color = Color(0xFFFFB2B2))
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = onGoogleSignIn) { Text("Sign in with Google") }
                    Spacer(Modifier.height(10.dp))
                    OutlinedTextField(
                        value = emailInput,
                        onValueChange = { emailInput = it },
                        label = { Text("Fallback Email (@northsouth.edu)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = nameInput,
                        onValueChange = { nameInput = it },
                        label = { Text("Name (optional)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(8.dp))
                    Button(
                        onClick = { onEmailSignIn(emailInput.trim(), nameInput.trim()) },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Fallback Sign In")
                    }
                }
            }
        }

        item {
            CardBlock {
                Text("Status", color = Color(0xFFB9C9FF), fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                AssistChip(
                    onClick = {},
                    label = { Text(if (ui.healthOk) "Ready" else "Unavailable") },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = if (ui.healthOk) Color(0xFF123B36) else Color(0xFF3A1920),
                        labelColor = if (ui.healthOk) Color(0xFF7FFFD4) else Color(0xFFFF9FB0)
                    )
                )
                Spacer(Modifier.height(6.dp))
                Text(ui.healthMessage, color = Color(0xFFC4D3FF))
            }
        }

        item {
            val res = ui.latestResult
            CardBlock {
                Text("Latest Analysis", color = Color.White, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                if (res == null) {
                    Text("No analysis yet. Go to Analyze tab.", color = Color(0xFFB9C9FF))
                } else {
                    Text(
                        "CGPA ${"%.2f".format(res.cgpa)}",
                        style = MaterialTheme.typography.headlineLarge,
                        color = Color(0xFF23E2CC)
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                        StatChip("Earned", res.earnedCredits.toString())
                        StatChip("Required", res.requiredCredits.toString())
                        StatChip("Remaining", res.remainingCredits.toString())
                    }
                }
            }
        }
    }
}

@Composable
private fun AnalyzeTab(
    ui: MainUiState,
    selectedInput: AnalyzeInputMethod,
    onSelectInput: (AnalyzeInputMethod) -> Unit,
    onProgram: (String) -> Unit,
    onText: (String) -> Unit,
    onWaived: (String) -> Unit,
    onAnalyze: () -> Unit,
    onImportCsv: (Uri) -> Unit,
    onImportPdf: (Uri) -> Unit,
    onImportImage: (Uri) -> Unit,
) {
    val csvPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri -> uri?.let(onImportCsv) }
    val pdfPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri -> uri?.let(onImportPdf) }
    val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri -> uri?.let(onImportImage) }
    var codeDraft by remember { mutableStateOf("") }
    var creditDraft by remember { mutableStateOf("3") }
    var gradeDraft by remember { mutableStateOf("A") }
    var seasonDraft by remember { mutableStateOf("Spring") }
    var yearDraft by remember { mutableStateOf("2024") }
    var draftError by remember { mutableStateOf<String?>(null) }

    val manualLines = ui.manualText
        .lines()
        .map { it.trim() }
        .filter { it.isNotBlank() }

    fun appendManualRow() {
        val code = codeDraft.trim().uppercase()
        val credits = creditDraft.trim().toIntOrNull()
        val grade = gradeDraft.trim().uppercase()
        val season = seasonDraft.trim().replaceFirstChar { it.uppercase() }
        val year = yearDraft.trim()

        if (!Regex("^[A-Z]{2,4}\\d{3}[A-Z]?$").matches(code)) {
            draftError = "Course code format invalid (example: CSE115)"
            return
        }
        if (credits == null || credits < 0 || credits > 6) {
            draftError = "Credits must be between 0 and 6"
            return
        }
        if (!setOf("A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F", "W").contains(grade)) {
            draftError = "Grade must be valid (A, A-, B+, ... W)"
            return
        }
        if (!setOf("Spring", "Summer", "Fall").contains(season) || !Regex("^\\d{4}$").matches(year)) {
            draftError = "Semester must be Spring/Summer/Fall and year like 2024"
            return
        }

        val built = "$code, $credits, $grade, $season $year"
        val merged = (manualLines + built).joinToString("\n")
        onText(merged)
        codeDraft = ""
        creditDraft = "3"
        gradeDraft = "A"
        seasonDraft = "Spring"
        yearDraft = "2024"
        draftError = null
    }

    fun removeManualRow(index: Int) {
        val next = manualLines.filterIndexed { i, _ -> i != index }
        onText(next.joinToString("\n"))
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text("Analyze Transcript", color = Color.White, style = MaterialTheme.typography.headlineMedium)
            val subtitle = if (ui.mode == AppMode.OFFLINE) {
                "Offline local engine with CSV/OCR import"
            } else {
                "Online mode mirrors web backend flow"
            }
            Text(subtitle, color = Color(0xFF9CB3FF))
        }

        item {
            CardBlock {
                Text("Program", color = Color(0xFFB9C9FF), fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = ui.program, onValueChange = onProgram, label = { Text("Program (CSE or BBA)") }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = ui.waivedText,
                    onValueChange = onWaived,
                    label = { Text("Waived courses (comma separated)") },
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }

        item {
            CardBlock {
                Text("Input Method", color = Color(0xFFB9C9FF), fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    AssistChip(
                        onClick = { onSelectInput(AnalyzeInputMethod.MANUAL) },
                        label = { Text("Manual") },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = if (selectedInput == AnalyzeInputMethod.MANUAL) Color(0xFF1A4A44) else Color(0xFF1A2856),
                            labelColor = Color.White
                        )
                    )
                    AssistChip(
                        onClick = { onSelectInput(AnalyzeInputMethod.CSV) },
                        label = { Text("CSV") },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = if (selectedInput == AnalyzeInputMethod.CSV) Color(0xFF1A4A44) else Color(0xFF1A2856),
                            labelColor = Color.White
                        )
                    )
                    AssistChip(
                        onClick = { onSelectInput(AnalyzeInputMethod.PDF) },
                        label = { Text("PDF") },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = if (selectedInput == AnalyzeInputMethod.PDF) Color(0xFF1A4A44) else Color(0xFF1A2856),
                            labelColor = Color.White
                        )
                    )
                    AssistChip(
                        onClick = { onSelectInput(AnalyzeInputMethod.IMAGE) },
                        label = { Text("Image") },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = if (selectedInput == AnalyzeInputMethod.IMAGE) Color(0xFF1A4A44) else Color(0xFF1A2856),
                            labelColor = Color.White
                        )
                    )
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    when (selectedInput) {
                        AnalyzeInputMethod.MANUAL -> "Manual mode will submit manual_text like web Manual input."
                        AnalyzeInputMethod.CSV -> "CSV mode will submit csv_text like web CSV upload."
                        AnalyzeInputMethod.PDF -> "PDF mode extracts OCR rows, then analyzes using manual rows."
                        AnalyzeInputMethod.IMAGE -> "Image mode extracts OCR rows, then analyzes using manual rows."
                    },
                    color = Color(0xFF9CB3FF)
                )
            }
        }

        if (selectedInput == AnalyzeInputMethod.CSV) {
            item {
                CardBlock {
                    Text("CSV Upload", color = Color.White, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { csvPicker.launch("text/*") }, modifier = Modifier.fillMaxWidth()) { Text("Import CSV") }
                }
            }
        }

        if (selectedInput == AnalyzeInputMethod.PDF) {
            item {
                CardBlock {
                    Text("PDF Upload", color = Color.White, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { pdfPicker.launch("application/pdf") }, modifier = Modifier.fillMaxWidth()) { Text("Import PDF") }
                    Spacer(Modifier.height(8.dp))
                    Text("Best result: upload transcript pages only; clear scan recommended.", color = Color(0xFF9CB3FF))
                }
            }
        }

        if (selectedInput == AnalyzeInputMethod.IMAGE) {
            item {
                CardBlock {
                    Text("Image Upload", color = Color.White, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { imagePicker.launch("image/*") }, modifier = Modifier.fillMaxWidth()) { Text("Import Image OCR") }
                    Spacer(Modifier.height(8.dp))
                    Text("Use straight, high-contrast transcript image with full table visible.", color = Color(0xFF9CB3FF))
                }
            }
        }

        if (selectedInput == AnalyzeInputMethod.MANUAL) {
            item {
                CardBlock {
                    Text("Manual Input Builder", color = Color.White, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(value = codeDraft, onValueChange = { codeDraft = it }, label = { Text("Course Code") }, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        OutlinedTextField(
                            value = creditDraft,
                            onValueChange = { creditDraft = it },
                            label = { Text("Credits") },
                            modifier = Modifier.weight(1f)
                        )
                        OutlinedTextField(
                            value = gradeDraft,
                            onValueChange = { gradeDraft = it },
                            label = { Text("Grade") },
                            modifier = Modifier.weight(1f)
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        OutlinedTextField(
                            value = seasonDraft,
                            onValueChange = { seasonDraft = it },
                            label = { Text("Season") },
                            modifier = Modifier.weight(1f)
                        )
                        OutlinedTextField(
                            value = yearDraft,
                            onValueChange = { yearDraft = it },
                            label = { Text("Year") },
                            modifier = Modifier.weight(1f)
                        )
                    }
                    draftError?.let {
                        Spacer(Modifier.height(8.dp))
                        Text(it, color = Color(0xFFFFA3B1))
                    }
                    Spacer(Modifier.height(10.dp))
                    Button(onClick = { appendManualRow() }, modifier = Modifier.fillMaxWidth()) { Text("Add Course") }

                    if (manualLines.isNotEmpty()) {
                        Spacer(Modifier.height(10.dp))
                        Text("Current Rows", color = Color(0xFFB9C9FF), fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(6.dp))
                        manualLines.take(20).forEachIndexed { idx, line ->
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(line, color = Color(0xFFC9D7FF), modifier = Modifier.weight(1f))
                                Button(onClick = { removeManualRow(idx) }) { Text("Remove") }
                            }
                            Spacer(Modifier.height(6.dp))
                        }
                    }
                }
            }
        }

        if (ui.ocrConfidence.isNotBlank() || ui.ocrWarning != null) {
            item {
                CardBlock {
                    Text("OCR Preview", color = Color.White, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "Confidence: ${if (ui.ocrConfidence.isBlank()) "-" else ui.ocrConfidence} | Score: ${ui.ocrScore} | Rows: ${ui.ocrDetectedRows}",
                        color = Color(0xFFB9C9FF)
                    )
                    ui.ocrWarning?.let {
                        Spacer(Modifier.height(6.dp))
                        Text(it, color = Color(0xFFFFC987))
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = ui.ocrPreview,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Raw OCR Snapshot") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(170.dp)
                    )

                    val parsedRows = ui.manualText
                        .lines()
                        .map { it.trim() }
                        .filter { it.isNotBlank() && it.contains(",") }
                        .take(12)
                    if (parsedRows.isNotEmpty()) {
                        Spacer(Modifier.height(10.dp))
                        Text("Likely Course Rows", color = Color.White, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(6.dp))
                        parsedRows.forEach { line ->
                            Card(
                                colors = CardDefaults.cardColors(containerColor = Color(0xFF15224A)),
                                shape = RoundedCornerShape(10.dp),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 2.dp)
                            ) {
                                Text(
                                    text = line,
                                    color = Color(0xFFC9D7FF),
                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp)
                                )
                            }
                        }
                    }
                }
            }
        }

        item {
            CardBlock {
                OutlinedTextField(
                    value = ui.manualText,
                    onValueChange = onText,
                    label = { Text("Transcript Rows (editable)") },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(170.dp)
                )
                Spacer(Modifier.height(12.dp))
                Button(onClick = onAnalyze, modifier = Modifier.fillMaxWidth()) { Text("Run Analysis") }
                if (ui.ocrBlocked) {
                    Spacer(Modifier.height(6.dp))
                    Text("OCR guardrail warning: review rows before running analysis.", color = Color(0xFFFFA3B1))
                }
            }
        }
    }
}

@Composable
private fun ChatTab(ui: MainUiState, onSend: (String) -> Unit) {
    var input by remember { mutableStateOf("") }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp, vertical = 12.dp)
    ) {
        Text("MCP Chat", color = Color.White, style = MaterialTheme.typography.headlineMedium)
        Text(
            if (ui.mode == AppMode.ONLINE) "Online mode uses backend /api/ai/chat" else "Offline mode gives local fallback",
            color = Color(0xFF9CB3FF)
        )
        Spacer(Modifier.height(10.dp))
        LazyColumn(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(ui.chat) { msg -> ChatBubble(msg) }
        }
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = input, onValueChange = { input = it }, label = { Text("Type message") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        Button(onClick = {
            val text = input.trim()
            if (text.isNotEmpty()) {
                onSend(text)
                input = ""
            }
        }, modifier = Modifier.fillMaxWidth()) {
            Text("Send")
        }
    }
}

@Composable
private fun HistoryTab(
    ui: MainUiState,
    onRunClick: (Int) -> Unit,
    onCloseDetails: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Text("Run History", color = Color.White, style = MaterialTheme.typography.headlineMedium)
            Text("User ${ui.userId} - ${ui.history.size} runs", color = Color(0xFF9CB3FF))
        }
        if (ui.history.isEmpty()) {
            item { CardBlock { Text("No runs loaded yet.", color = Color(0xFFB9C9FF)) } }
        } else {
            items(ui.history) { run ->
                CardBlock {
                    Text("Run #${run.id} - ${run.program}", color = Color.White, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(4.dp))
                    Text("CGPA ${"%.2f".format(run.cgpa)} | ${run.inputMethod.uppercase()}", color = Color(0xFFB9C9FF))
                    Text("${run.earnedCredits}/${run.requiredCredits} credits", color = Color(0xFF90E6D9))
                    Text(run.createdAt, color = Color(0xFF7C8DBF))
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { onRunClick(run.id) }) {
                        Text("View Details")
                    }
                }
            }
        }

        ui.runDetails?.let { details ->
            item {
                CardBlock {
                    Text("Run Details #${details.run.id}", color = Color.White, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(6.dp))
                    Text("Program: ${details.run.program}", color = Color(0xFF9CB3FF))
                    Text("Input: ${details.run.inputMethod.uppercase()}", color = Color(0xFF9CB3FF))
                    Text("CGPA: ${"%.2f".format(details.run.cgpa)}", color = Color(0xFF23E2CC), fontWeight = FontWeight.Bold)

                    Spacer(Modifier.height(10.dp))
                    Text("Latest Rows", color = Color.White, fontWeight = FontWeight.SemiBold)
                    details.latestRows.take(20).forEach { row ->
                        Card(
                            colors = CardDefaults.cardColors(containerColor = Color(0xFF15224A)),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 3.dp)
                        ) {
                            Column(modifier = Modifier.padding(10.dp)) {
                                Text("${row.courseCode}", color = Color.White, fontWeight = FontWeight.SemiBold)
                                Spacer(Modifier.height(4.dp))
                                Text("Credits: ${row.credits} | Grade: ${row.grade} | Semester: ${row.semester}", color = Color(0xFFC9D7FF))
                            }
                        }
                    }

                    Spacer(Modifier.height(10.dp))
                    Text("Issues", color = Color.White, fontWeight = FontWeight.SemiBold)
                    if (details.issues.isEmpty()) {
                        Text("No issues", color = Color(0xFF9BE7C4))
                    } else {
                        details.issues.forEach { Text("- $it", color = Color(0xFFFFB2B2)) }
                    }

                    if (details.courseAudit.isNotEmpty()) {
                        Spacer(Modifier.height(10.dp))
                        Text("Audit", color = Color.White, fontWeight = FontWeight.SemiBold)
                        details.courseAudit.take(25).forEach {
                            val statusColor = when (it.status.uppercase()) {
                                "COMPLETED", "WAIVED" -> Color(0xFF8EF2D9)
                                "MISSING", "FAILED", "INCOMPLETE" -> Color(0xFFFFB2B2)
                                else -> Color(0xFFC9D7FF)
                            }
                            Text("- ${it.category} | ${it.course} | ${it.status} | ${it.details}", color = statusColor)
                        }
                    }

                    if (details.cgpaDetails.isNotEmpty()) {
                        Spacer(Modifier.height(10.dp))
                        Text("CGPA Detail", color = Color.White, fontWeight = FontWeight.SemiBold)
                        details.cgpaDetails.take(25).forEach {
                            val flag = if (it.inCgpa) "In" else "Out"
                            Text("- ${it.course}: ${it.grade} | $flag | ${it.reason}", color = Color(0xFFC9D7FF))
                        }
                    }

                    if (details.retakeSummary.isNotEmpty()) {
                        Spacer(Modifier.height(10.dp))
                        Text("Retake Summary", color = Color.White, fontWeight = FontWeight.SemiBold)
                        details.retakeSummary.forEach {
                            Text("- ${it.course}: ${it.attempts.joinToString(" -> ")}", color = Color(0xFFBFE7FF))
                        }
                    }

                    Spacer(Modifier.height(10.dp))
                    Button(onClick = onCloseDetails) {
                        Text("Close Details")
                    }
                }
            }
        }
    }
}

@Composable
private fun ProfileTab(ui: MainUiState) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { Text("Profile", color = Color.White, style = MaterialTheme.typography.headlineMedium) }
        item {
            CardBlock {
                Text("Hybrid Mobile Client", color = Color.White, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                Text("Mode: ${ui.mode.name}", color = Color(0xFF9CB3FF))
                Text("Current User ID: ${ui.userId}", color = Color(0xFF9CB3FF))
                Text("Program: ${ui.program}", color = Color(0xFF9CB3FF))
                Spacer(Modifier.height(8.dp))
                Text(
                    "Offline mode: local engine + local history. Online mode: backend APIs + MCP chat.",
                    color = Color(0xFFC9D7FF)
                )
            }
        }
        item {
            CardBlock {
                Text("Account", color = Color.White, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                if (ui.onlineSignedIn) {
                    Text("Online session active", color = Color(0xFF8EF2D9))
                    if (ui.onlineUserLabel.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(ui.onlineUserLabel, color = Color(0xFFC9D7FF))
                    }
                } else {
                    Text("Online session not signed in", color = Color(0xFFFFB2B2))
                }
            }
        }
        item {
            CardBlock {
                Text("Current Analyze Context", color = Color.White, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                Text("Input method: ${ui.selectedInputMethod.uppercase()}", color = Color(0xFF9CB3FF))
                Text("OCR confidence: ${if (ui.ocrConfidence.isBlank()) "-" else ui.ocrConfidence}", color = Color(0xFF9CB3FF))
                Text("OCR rows detected: ${ui.ocrDetectedRows}", color = Color(0xFF9CB3FF))
                if (ui.ocrWarning != null) {
                    Spacer(Modifier.height(6.dp))
                    Text(ui.ocrWarning, color = Color(0xFFFFC987))
                }
            }
        }
    }
}

@Composable
private fun CardBlock(content: @Composable ColumnScope.() -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF111A38)),
        shape = RoundedCornerShape(20.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp), content = content)
    }
}

@Composable
private fun StatChip(label: String, value: String) {
    Column(
        modifier = Modifier
            .clip(RoundedCornerShape(16.dp))
            .background(Color(0xFF18264D))
            .padding(horizontal = 14.dp, vertical = 10.dp)
    ) {
        Text(value, color = Color(0xFF2DE6CF), fontWeight = FontWeight.Bold)
        Text(label, color = Color(0xFFAFC4FF), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun ChatBubble(msg: ChatMessage) {
    val isUser = msg.role == "user"
    Card(
        colors = CardDefaults.cardColors(containerColor = if (isUser) Color(0xFF1E315E) else Color(0xFF111A38)),
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(if (isUser) "You" else "Assistant", color = Color(0xFF9CB3FF), fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(4.dp))
            Text(msg.text, color = Color.White)
            if (msg.trace.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                msg.trace.forEach { t ->
                    val low = t.lowercase()
                    val ok = low.contains("| ok |")
                    val chipColor = if (ok) Color(0xFF1E4C44) else Color(0xFF4A222C)
                    val textColor = if (ok) Color(0xFF94F5E7) else Color(0xFFFFB7C2)
                    Box(
                        modifier = Modifier
                            .padding(vertical = 2.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(chipColor)
                            .padding(horizontal = 10.dp, vertical = 6.dp)
                    ) {
                        Text(t, color = textColor)
                    }
                }
            }
        }
    }
}
