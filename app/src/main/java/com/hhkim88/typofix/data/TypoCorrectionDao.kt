package com.hhkim88.typofix.data

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface TypoCorrectionDao {

    @Query("SELECT * FROM typo_corrections ORDER BY lastUsedAt DESC")
    fun observeAll(): Flow<List<TypoCorrectionEntity>>

    @Query("SELECT * FROM typo_corrections")
    suspend fun getAll(): List<TypoCorrectionEntity>

    @Upsert
    suspend fun upsert(entity: TypoCorrectionEntity)

    @Query("DELETE FROM typo_corrections WHERE typo = :typo")
    suspend fun deleteByTypo(typo: String)

    @Query("UPDATE typo_corrections SET enabled = :enabled WHERE typo = :typo")
    suspend fun setEnabled(typo: String, enabled: Boolean)
}
