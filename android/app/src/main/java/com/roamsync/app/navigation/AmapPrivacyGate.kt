package com.roamsync.app.navigation

import android.content.Context
import android.content.SharedPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** Consent is explicit and persisted; SDK initialization is forbidden beforehand. */
@Singleton class AmapPrivacyGate @Inject constructor(@ApplicationContext context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("amap_privacy", Context.MODE_PRIVATE)
    val accepted: Boolean get() = prefs.getBoolean("accepted", false)
    fun accept() { prefs.edit().putBoolean("accepted", true).apply() }
}
