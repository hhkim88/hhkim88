package com.hhkim88.typofix.data

import com.hhkim88.typofix.core.Correction
import com.hhkim88.typofix.core.CorrectionStore
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

/**
 * [CorrectionStore] backed by Room. Typing happens on the IME's main thread and must respond
 * synchronously to every keystroke, so this keeps an in-memory cache for reads and writes to
 * Room asynchronously in the background, updating the cache immediately so reads are never stale.
 */
class RoomCorrectionStore(
    private val dao: TypoCorrectionDao,
    private val scope: CoroutineScope
) : CorrectionStore {

    private val cache = ConcurrentHashMap<String, Correction>()

    init {
        // Small personal dataset (a user's own typos) - a one-time blocking load at IME
        // startup is simpler and fast enough to be safe here.
        runBlocking {
            dao.getAll().forEach { cache[it.typo] = it.toCorrection() }
        }
    }

    override fun lookup(word: String): Correction? = cache[word]

    override fun recordAttempt(typo: String, correction: String) {
        val existing = cache[typo]
        val updated = if (existing != null && existing.correction == correction) {
            existing.copy(count = existing.count + 1)
        } else {
            Correction(typo = typo, correction = correction, count = 1, enabled = true)
        }
        cache[typo] = updated
        val now = System.currentTimeMillis()
        scope.launch(Dispatchers.IO) {
            dao.upsert(
                TypoCorrectionEntity(
                    typo = updated.typo,
                    correction = updated.correction,
                    count = updated.count,
                    enabled = updated.enabled,
                    lastUsedAt = now
                )
            )
        }
    }

    override fun allCorrections(): List<Correction> = cache.values.toList()

    override fun remove(typo: String) {
        cache.remove(typo)
        scope.launch(Dispatchers.IO) { dao.deleteByTypo(typo) }
    }

    override fun setEnabled(typo: String, enabled: Boolean) {
        cache[typo]?.let { cache[typo] = it.copy(enabled = enabled) }
        scope.launch(Dispatchers.IO) { dao.setEnabled(typo, enabled) }
    }

    private fun TypoCorrectionEntity.toCorrection() =
        Correction(typo = typo, correction = correction, count = count, enabled = enabled)
}
