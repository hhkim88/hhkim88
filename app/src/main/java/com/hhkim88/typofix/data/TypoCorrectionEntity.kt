package com.hhkim88.typofix.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "typo_corrections")
data class TypoCorrectionEntity(
    @PrimaryKey val typo: String,
    val correction: String,
    val count: Int,
    val enabled: Boolean,
    val lastUsedAt: Long
)
