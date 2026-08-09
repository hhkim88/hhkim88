package com.hhkim88.typofix.core

data class Correction(
    val typo: String,
    val correction: String,
    val count: Int,
    val enabled: Boolean = true
)

/**
 * Persistence abstraction for learned typo -> correction pairs. The Android
 * app backs this with Room; tests and previews can use [InMemoryCorrectionStore].
 */
interface CorrectionStore {
    fun lookup(word: String): Correction?
    fun recordAttempt(typo: String, correction: String)
    fun allCorrections(): List<Correction>
    fun remove(typo: String)
    fun setEnabled(typo: String, enabled: Boolean)
}

class InMemoryCorrectionStore : CorrectionStore {
    private val data = LinkedHashMap<String, Correction>()

    override fun lookup(word: String): Correction? = data[word]

    override fun recordAttempt(typo: String, correction: String) {
        val existing = data[typo]
        data[typo] = if (existing != null && existing.correction == correction) {
            existing.copy(count = existing.count + 1)
        } else {
            Correction(typo = typo, correction = correction, count = 1, enabled = true)
        }
    }

    override fun allCorrections(): List<Correction> = data.values.toList()

    override fun remove(typo: String) {
        data.remove(typo)
    }

    override fun setEnabled(typo: String, enabled: Boolean) {
        data[typo]?.let { data[typo] = it.copy(enabled = enabled) }
    }
}
