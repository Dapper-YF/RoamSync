package com.roamsync.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import com.roamsync.app.ui.*
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    private val model: RoamSyncViewModel by viewModels()
    private val tourism: TourismViewModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val state by model.state.collectAsStateWithLifecycle()
            val discovery by tourism.state.collectAsStateWithLifecycle()
            RoamSyncTheme { TourismApp(discovery, tourism, state, model) }
        }
    }
    override fun onResume() { super.onResume(); model.refresh() }
}
