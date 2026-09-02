package com.roamsync.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.roamsync.app.data.remote.BudgetResponse
import com.roamsync.app.data.remote.TripResponse
import com.roamsync.app.ui.AppScreen
import com.roamsync.app.ui.BackendState
import com.roamsync.app.ui.RoamSyncTheme
import com.roamsync.app.ui.RoamSyncUiState
import com.roamsync.app.ui.RoamSyncViewModel
import com.roamsync.app.ui.formatFen
import dagger.hilt.android.AndroidEntryPoint
import java.time.LocalDate

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    private val viewModel: RoamSyncViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            RoamSyncTheme {
                val state by viewModel.state.collectAsStateWithLifecycle()
                RoamSyncApp(state, viewModel)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RoamSyncApp(state: RoamSyncUiState, viewModel: RoamSyncViewModel) {
    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(state.message) {
        state.message?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.dismissMessage()
        }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("RoamSync") }) },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        when (state.screen) {
            AppScreen.STATUS -> StatusScreen(state, viewModel::refreshBackend, padding)
            AppScreen.CREATE_TRIP -> CreateTripScreen(state.isWorking, viewModel::createTrip, padding)
            AppScreen.BUDGET -> BudgetScreen(
                state = state,
                onAddExpense = viewModel::addExpense,
                onRefresh = viewModel::refreshBudget,
                padding = padding,
            )
        }
    }
}

@Composable
private fun StatusScreen(
    state: RoamSyncUiState,
    onRetry: () -> Unit,
    padding: PaddingValues,
) {
    Column(
        modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        when (state.backendState) {
            BackendState.CHECKING -> {
                CircularProgressIndicator()
                Spacer(Modifier.height(16.dp))
                Text("正在连接 RoamSync 服务…")
            }
            BackendState.READY -> Text("服务已就绪")
            BackendState.UNAVAILABLE -> {
                Text("暂时无法连接服务", style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(8.dp))
                Text("请启动 Docker 后端，并执行 adb reverse tcp:8000 tcp:8000")
                Spacer(Modifier.height(20.dp))
                Button(onClick = onRetry) { Text("重新连接") }
            }
        }
    }
}

@Composable
private fun CreateTripScreen(
    isWorking: Boolean,
    onCreate: (String, String, String, String, String) -> Unit,
    padding: PaddingValues,
) {
    val today = remember { LocalDate.now() }
    var title by rememberSaveable { mutableStateOf("") }
    var startDate by rememberSaveable { mutableStateOf(today.toString()) }
    var endDate by rememberSaveable { mutableStateOf(today.plusDays(1).toString()) }
    var totalBudget by rememberSaveable { mutableStateOf("") }
    var dailyBudget by rememberSaveable { mutableStateOf("") }

    Column(
        modifier = Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("创建第一段旅行", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("预算以人民币填写，服务端会用“分”精确保存。")
        OutlinedTextField(title, { title = it }, label = { Text("旅行名称") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(startDate, { startDate = it }, label = { Text("开始日期 YYYY-MM-DD") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(endDate, { endDate = it }, label = { Text("结束日期 YYYY-MM-DD") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(
            totalBudget,
            { totalBudget = it },
            label = { Text("总预算（元）") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            dailyBudget,
            { dailyBudget = it },
            label = { Text("每日预算（元）") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = { onCreate(title, startDate, endDate, totalBudget, dailyBudget) },
            enabled = !isWorking,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (isWorking) CircularProgressIndicator(modifier = Modifier.height(20.dp)) else Text("创建旅行")
        }
    }
}

@Composable
private fun BudgetScreen(
    state: RoamSyncUiState,
    onAddExpense: (String, String, String) -> Unit,
    onRefresh: () -> Unit,
    padding: PaddingValues,
) {
    val trip = state.trip ?: return
    val budget = state.budget ?: return
    var amount by rememberSaveable { mutableStateOf("") }
    var description by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf("food") }

    Column(
        modifier = Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        TripHeader(trip)
        BudgetCards(budget)
        OutlinedButton(onClick = onRefresh, modifier = Modifier.fillMaxWidth()) { Text("刷新预算") }
        HorizontalDivider()
        Text("手动记一笔", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        OutlinedTextField(
            amount,
            { amount = it },
            label = { Text("金额（元）") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier.fillMaxWidth(),
        )
        CategorySelector(category) { category = it }
        OutlinedTextField(
            description,
            { description = it },
            label = { Text("消费说明") },
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = { onAddExpense(amount, category, description) },
            enabled = !state.isWorking,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isWorking) CircularProgressIndicator(modifier = Modifier.height(20.dp)) else Text("确认记账")
        }
    }
}

@Composable
private fun TripHeader(trip: TripResponse) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(trip.title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("${trip.startDate} 至 ${trip.endDate}")
    }
}

@Composable
private fun BudgetCards(budget: BudgetResponse) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        BudgetCard("今日剩余", budget.todayRemainingFen, budget.currency, Modifier.weight(1f))
        BudgetCard("总剩余", budget.totalRemainingFen, budget.currency, Modifier.weight(1f))
    }
    Text("今日已花 ${formatFen(budget.todaySpentFen, budget.currency)} · ${budget.localDate}")
}

@Composable
private fun BudgetCard(label: String, value: Long, currency: String, modifier: Modifier = Modifier) {
    Card(modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(label, style = MaterialTheme.typography.labelLarge)
            Text(formatFen(value, currency), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CategorySelector(selected: String, onSelected: (String) -> Unit) {
    val categories = listOf(
        "food" to "餐饮",
        "transport" to "交通",
        "ticket" to "门票",
        "lodging" to "住宿",
        "shopping" to "购物",
        "other" to "其他",
    )
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        categories.forEach { (value, label) ->
            FilterChip(
                selected = selected == value,
                onClick = { onSelected(value) },
                label = { Text(label) },
            )
        }
    }
}
