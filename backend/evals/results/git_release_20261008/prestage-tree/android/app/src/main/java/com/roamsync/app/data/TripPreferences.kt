package com.roamsync.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.first

private val Context.dataStore by preferencesDataStore(name = "roamsync_preferences")

@Singleton
class TripPreferences @Inject constructor(@param:ApplicationContext private val context: Context) {
    private val lastTripIdKey = stringPreferencesKey("last_trip_id")

    suspend fun getLastTripId(): String? = context.dataStore.data.first()[lastTripIdKey]

    suspend fun setLastTripId(tripId: String) {
        context.dataStore.edit { it[lastTripIdKey] = tripId }
    }
}
