package com.roamsync.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.roamsync.app.data.TripPreferences
import com.roamsync.app.data.TripRepository
import com.roamsync.app.data.remote.BudgetResponse
import com.roamsync.app.data.remote.ExpenseCreateRequest
import com.roamsync.app.data.remote.TripCreateRequest
import com.roamsync.app.data.remote.TripResponse
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException

enum class AppScreen { STATUS, CREATE_TRIP, BUDGET }
enum class BackendState { CHECKING, READY, UNAVAILABLE }

data class RoamSyncUiState(
    val screen: AppScreen = AppScreen.STATUS,
    val backendState: BackendState = BackendState.CHECKING,
    val isWorking: Boolean = false,
    val trip: TripResponse? = null,
    val budget: BudgetResponse? = null,
    val message: String? = null,
)

private data class PendingExpense(
    val amountFen: Long,
    val category: String,
    val description: String,
    val key: String,
)

@HiltViewModel
class RoamSyncViewModel @Inject constructor(
    private val repository: TripRepository,
    private val preferences: TripPreferences,
) : ViewModel() {
    private val _state = MutableStateFlow(RoamSyncUiState())
    val state: StateFlow<RoamSyncUiState> = _state.asStateFlow()
    private var pendingExpense: PendingExpense? = null

    init {
        refreshBackend()
    }

    fun refreshBackend() = viewModelScope.launch {
        _state.update { it.copy(backendState = BackendState.CHECKING, message = null) }
        runCatching { repository.isBackendReady() }
            .onSuccess { ready ->
                if (ready) {
                    _state.update { it.copy(backendState = BackendState.READY) }
                    restoreLastTrip()
                } else {
                    _state.update { it.copy(backendState = BackendState.UNAVAILABLE) }
                }
            }
            .onFailure { error ->
                _state.update {
                    it.copy(
                        backendState = BackendState.UNAVAILABLE,
                        screen = AppScreen.STATUS,
                        message = error.toUserMessage(),
                    )
                }
            }
    }

    private suspend fun restoreLastTrip() {
        val tripId = preferences.getLastTripId()
        if (tripId == null) {
            _state.update { it.copy(screen = AppScreen.CREATE_TRIP) }
            return
        }
        runCatching {
            repository.getTrip(tripId) to repository.getBudget(tripId)
        }.onSuccess { (trip, budget) ->
            _state.update {
                it.copy(screen = AppScreen.BUDGET, trip = trip, budget = budget, message = null)
            }
        }.onFailure {
            _state.update {
                it.copy(screen = AppScreen.CREATE_TRIP, trip = null, budget = null)
            }
        }
    }

    fun createTrip(
        title: String,
        startDate: String,
        endDate: String,
        totalBudgetYuan: String,
        dailyBudgetYuan: String,
    ) {
        val totalFen = yuanTextToFen(totalBudgetYuan)
        val dailyFen = yuanTextToFen(dailyBudgetYuan)
        val validationError = validateTrip(title, startDate, endDate, totalFen, dailyFen)
        if (validationError != null) {
            _state.update { it.copy(message = validationError) }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(isWorking = true, message = null) }
            runCatching {
                val trip = repository.createTrip(
                    TripCreateRequest(
                        title = title.trim(),
                        startDate = startDate,
                        endDate = endDate,
                        totalBudgetFen = requireNotNull(totalFen),
                        dailyBudgetFen = requireNotNull(dailyFen),
                    ),
                )
                preferences.setLastTripId(trip.id)
                val budget = repository.getBudget(trip.id)
                trip to budget
            }.onSuccess { (trip, budget) ->
                _state.update {
                    it.copy(
                        screen = AppScreen.BUDGET,
                        isWorking = false,
                        trip = trip,
                        budget = budget,
                        message = "旅行已创建",
                    )
                }
            }.onFailure { error ->
                _state.update { it.copy(isWorking = false, message = error.toUserMessage()) }
            }
        }
    }

    fun addExpense(amountYuan: String, category: String, description: String) {
        val amountFen = yuanTextToFen(amountYuan)
        if (amountFen == null || description.isBlank()) {
            _state.update { it.copy(message = "请输入有效金额和消费说明") }
            return
        }
        val tripId = _state.value.trip?.id ?: return
        val normalizedDescription = description.trim()
        val existing = pendingExpense
        val pending = if (
            existing != null && existing.amountFen == amountFen &&
            existing.category == category && existing.description == normalizedDescription
        ) existing else PendingExpense(amountFen, category, normalizedDescription, UUID.randomUUID().toString())
        pendingExpense = pending

        viewModelScope.launch {
            _state.update { it.copy(isWorking = true, message = null) }
            runCatching {
                repository.createExpense(
                    tripId,
                    ExpenseCreateRequest(
                        idempotencyKey = pending.key,
                        amountFen = pending.amountFen,
                        category = pending.category,
                        description = pending.description,
                    ),
                )
                repository.getBudget(tripId)
            }.onSuccess { budget ->
                pendingExpense = null
                _state.update {
                    it.copy(isWorking = false, budget = budget, message = "记账成功")
                }
            }.onFailure { error ->
                _state.update { it.copy(isWorking = false, message = error.toUserMessage()) }
            }
        }
    }

    fun refreshBudget() {
        val tripId = _state.value.trip?.id ?: return
        viewModelScope.launch {
            runCatching { repository.getBudget(tripId) }
                .onSuccess { budget -> _state.update { it.copy(budget = budget, message = null) } }
                .onFailure { error -> _state.update { it.copy(message = error.toUserMessage()) } }
        }
    }

    fun dismissMessage() = _state.update { it.copy(message = null) }

    private fun validateTrip(
        title: String,
        startDate: String,
        endDate: String,
        totalFen: Long?,
        dailyFen: Long?,
    ): String? {
        if (title.isBlank()) return "请输入旅行名称"
        val start = runCatching { LocalDate.parse(startDate) }.getOrNull()
        val end = runCatching { LocalDate.parse(endDate) }.getOrNull()
        if (start == null || end == null) return "日期格式应为 YYYY-MM-DD"
        if (end < start) return "结束日期不能早于开始日期"
        if (totalFen == null || dailyFen == null) return "预算必须是大于 0 且最多两位小数的金额"
        if (dailyFen > totalFen) return "每日预算不能超过总预算"
        return null
    }
}

private fun Throwable.toUserMessage(): String = when (this) {
    is HttpException -> "服务器请求失败（HTTP ${code()}）"
    else -> message?.takeIf { it.isNotBlank() } ?: "连接失败，请确认后端和 USB 端口映射已启动"
}
