package com.roamsync.app.ui

import java.math.BigDecimal
import java.math.RoundingMode
import java.text.NumberFormat
import java.util.Currency
import java.util.Locale

fun yuanTextToFen(value: String): Long? = runCatching {
    val amount = BigDecimal(value.trim()).setScale(2, RoundingMode.UNNECESSARY)
    if (amount <= BigDecimal.ZERO) return null
    amount.movePointRight(2).longValueExact()
}.getOrNull()

fun formatFen(value: Long, currencyCode: String = "CNY"): String {
    val formatter = NumberFormat.getCurrencyInstance(Locale.CHINA)
    formatter.currency = Currency.getInstance(currencyCode)
    return formatter.format(BigDecimal.valueOf(value, 2))
}
