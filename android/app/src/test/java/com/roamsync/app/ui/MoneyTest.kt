package com.roamsync.app.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MoneyTest {
    @Test
    fun convertsYuanToFenWithoutFloatingPointLoss() {
        assertEquals(4_800L, yuanTextToFen("48"))
        assertEquals(1L, yuanTextToFen("0.01"))
        assertEquals(80_000L, yuanTextToFen("800.00"))
    }

    @Test
    fun rejectsInvalidAmounts() {
        assertNull(yuanTextToFen("0"))
        assertNull(yuanTextToFen("12.345"))
        assertNull(yuanTextToFen("abc"))
    }
}
