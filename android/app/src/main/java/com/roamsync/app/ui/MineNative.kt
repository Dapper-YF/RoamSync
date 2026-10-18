package com.roamsync.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
internal fun MineNative(s: TourismState, vm: TourismViewModel, onJourneys: () -> Unit) {
    LazyColumn(contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { PageHeading("YOUR ROAMSYNC", "我的旅行。", "收藏地点、旅行偏好与服务连接。") }
        item {
            AppCard(color = Mist) {
                Text("旅程工作台", style = androidx.compose.material3.MaterialTheme.typography.titleLarge, color = Ink)
                Text("继续筹划旅行，查看已确认的安排与当前进度。", color = androidx.compose.material3.MaterialTheme.colorScheme.onSurfaceVariant)
                Button(onClick = onJourneys, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("打开我的旅程") }
            }
        }
        item {
            AppCard {
                Text("你的旅行资料", style = androidx.compose.material3.MaterialTheme.typography.titleLarge, color = Ink)
                OutlinedButton(onClick = vm::favorites, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("收藏的地点", fontWeight = FontWeight.SemiBold)
                        Text("收藏已保存，下次打开可以继续查看", fontSize = 11.sp, color = androidx.compose.material3.MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                OutlinedButton(onClick = vm::openPreferences, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("旅行偏好", fontWeight = FontWeight.SemiBold)
                        Text("类别 ${s.preferences.preferredCategories.size} 个 · 兴趣 ${s.preferences.interests.size} 项", fontSize = 11.sp, color = androidx.compose.material3.MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                OutlinedButton(onClick = { vm.go("settings") }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("连接与隐私", fontWeight = FontWeight.SemiBold)
                        Text(if (s.connection.isBlank()) "尚未设置服务地址" else "服务连接已设置 · 临时授权由你管理", fontSize = 11.sp, color = androidx.compose.material3.MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        if (!s.notice.isNullOrBlank()) item { Text(s.notice, color = DeepTeal, modifier = Modifier.padding(horizontal = 4.dp)) }
        item { Text("位置只在你明确选择相关功能时使用；行程执行由你手动确认到达和完成。", fontSize = 11.sp, color = androidx.compose.material3.MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 4.dp)) }
    }
}
