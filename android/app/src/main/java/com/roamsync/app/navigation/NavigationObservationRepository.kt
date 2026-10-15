package com.roamsync.app.navigation

import com.roamsync.app.data.remote.NavigationObservationRequest
import com.roamsync.app.data.remote.NavigationObservationResponse
import com.roamsync.app.data.remote.RoamSyncApi
import javax.inject.Inject
import javax.inject.Singleton

@Singleton class NavigationObservationRepository @Inject constructor(private val api: RoamSyncApi) {
    suspend fun upload(observation: NavigationObservationRequest): NavigationObservationResponse = api.observeNavigation(observation)
}
