package com.nsu.transcriptmobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.nsu.transcriptmobile.ui.NsuMobileApp
import com.nsu.transcriptmobile.ui.theme.NsuTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            NsuTheme {
                NsuMobileApp()
            }
        }
    }
}
