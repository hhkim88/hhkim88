package com.hhkim88.typofix.core

interface Dictionary {
    fun contains(word: String): Boolean
}

/** Simple in-memory dictionary. The Android app loads its word list from a bundled asset file. */
class WordListDictionary(words: Collection<String>) : Dictionary {
    val all: List<String> = words.filter { it.isNotBlank() }.distinct()
    private val set = all.toHashSet()

    override fun contains(word: String): Boolean = word in set
}
