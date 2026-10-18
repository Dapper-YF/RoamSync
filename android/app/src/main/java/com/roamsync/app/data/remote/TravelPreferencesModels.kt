package com.roamsync.app.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class TravelPreferences(
    val version: String = "travel-preferences-v1",
    @SerialName("preferred_categories") val preferredCategories: List<String> = emptyList(),
    val interests: List<String> = emptyList(),
)
